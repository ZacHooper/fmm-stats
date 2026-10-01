#!/usr/bin/env python3
"""
Extract the current state of an FMM22 save into a labelled output bundle.

    python3 extract.py path/to/save.fms [--label 2022-end] [--out output]

Architecture: scrape each region of the save independently into keyed tables, then
join. The player INFO section is the identity spine (one row per player, ~31k, with
every foreign key); attributes join on SID, clubs on club_tid, names on TID. See
fmparser/tables/.

Writes output/<label>/:
    players.json / players.csv   whole player DB: identity + attributes where they exist
    matches.json                 this season's matches as stored: events, both sides' player
                                 lines, the stored score, our formation and starting positions
    player_match_stats.csv       flat one-row-per-(match, player), with the team played for
    transfers.json               players whose current club differs from a team they played for
    clubs.json                   club TID -> name
    summary.json                 counts, date range, how the label was derived

The label defaults to <season-end-year>-<period>, from the save's latest match date
(Aug-Sep=start, Jul=end, everything else in-season=mid). Override with --label.
"""
import argparse
import csv
import json
import os
from collections import Counter

from fmparser.core import follow
from fmparser.save import Save
from fmparser import model as MOD
from fmparser import clubs_comps as R
from fmparser.tables.contracts import scrape_contracts
from fmparser.tables.training import LOAN_STATUS, scrape_squad_status
from fmparser.tables.person_info import (
    NO_CLUB,
    PERSON_FIELDS,
    scrape_person_info,
)
from fmparser.tables.player_attributes import scrape_player_attributes
from fmparser.tables import fixtures as FIX
from fmparser.tables import comp_rules as CRU
from fmparser.tables import rounds as ROUNDS
from fmparser.tables import rule_files as RULE_FILES
from fmparser.tables import save_header as HDR
from fmparser import careers as C
from fmparser.tables import history as H
from fmparser.tables import player_lists as PL
from fmparser.tables import player_progress as PP
from fmparser.tables import club_records as CRE
from fmparser.tables import training as TRN
from fmparser.tables import matches as MT
from fmparser.tables import (
    cities,
    currencies,
    languages,
    nations,
    player_attributes as PA,
    staff as ST,
    stadiums,
)


def _period(month):
    # Phase is only a coarse hint (a real in-season date is what actually orders
    # snapshots — see history.player_snapshots.snapshot_date). Keep the guess minimal:
    # only pre-season (Aug/Sep) reads as "start" and only the July wrap reads as "end";
    # everything Oct–Jun is "mid". The old Mar–Jul→"end" band mislabelled winter/spring
    # in-season saves (e.g. a 19-Mar save) as "end", so it was dropped.
    if month in (8, 9):
        return "start"
    if month == 7:
        return "end"
    return "mid"          # Oct–Jun (in-season)


def auto_label(season):
    """<season-end-year>-<period> from the latest match date. This is only the cosmetic
    output-DIR name; the authoritative (season, phase) the DB keys on is written explicitly
    into summary.json by season_phase() below."""
    dates = sorted(m["date"] for m in season if m["date"])
    if not dates:
        return "unknown", None
    latest = dates[-1]
    year, month = int(latest[:4]), int(latest[5:7])
    end_year = year + 1 if month >= 8 else year
    return f"{end_year}-{_period(month)}", latest


def season_phase(save_date, matches, rollover):
    """Authoritative (season:int|None, phase:str|None) for the snapshot.

    phase is the save's own in-game date, from its header title (`save_header`); the latest
    match date stands in only if the title does not read. season is the campaign end-year,
    from the career's rollover day. None for a new career's first save (no matches, dated
    before the rollover), which the loader places with --season."""
    dates = sorted(m["date"] for m in matches if m["date"])
    phase = save_date or (dates[-1] if dates else None)
    if phase is None:
        return None, None
    return HDR.campaign(phase, bool(dates), rollover), phase


_PHASES = ("start", "mid", "end")

# The tail of the global attribute record (attributes.record_tail). Named once here so the
# rec-present branch, the identity-only fill and the CSV header cannot drift apart.
TAIL_FIELDS = ("current_reputation", "world_reputation", "international_retired",
               "squad_number", "preferred_squad_number", "height_cm", "weight_kg")
# The 9 unnamed 1-20 attribute bytes (attributes.HIDDEN_OFFSETS). Carried, not named --
# every identity-only row has to fill them too, or the CSV header and the rows disagree.
HIDDEN_FIELDS = tuple(PA.HIDDEN_OFFSETS.values())
# The entangled 0-255 source bytes, carried RAW so the estimation model can be
# retrained against the store instead of a 25-minute re-extract. See
# attributes.SRC_OFFSETS: scraping and inference are different jobs.
SRC_FIELDS = tuple(PA.SRC_OFFSETS.values()) + tuple(PA.PLAIN_OFFSETS.values())


def parse_label(label):
    """Inverse of auto_label: label string -> (season:int, phase:str).

    season is the end-year of the campaign (21/22 -> 2022), matching auto_label.
    Handles the current form '2022-end' and the legacy form '21-22-end'
    (where the second two-digit group is the end year). Raises ValueError on
    anything else so callers can fall back to summary.json or --season/--phase.
    """
    parts = label.split("-")
    if len(parts) < 2 or parts[-1] not in _PHASES:
        raise ValueError(f"unrecognised label {label!r}")
    phase = parts[-1]
    head = parts[:-1]
    if len(head) == 1 and head[0].isdigit() and len(head[0]) == 4:
        return int(head[0]), phase          # 2022-end
    if len(head) == 2 and all(p.isdigit() and len(p) == 2 for p in head):
        return 2000 + int(head[1]), phase    # 21-22-end -> 2022
    raise ValueError(f"unrecognised label {label!r}")


def _history_clubs(hist):
    """Every club on a player's history chain that has a season on it (two rows or more)."""
    rows = hist["rows"]
    nxt, club = rows["next"], rows["club"]
    pointed = set(nxt)
    out = set()
    for head in hist["heads"].values():
        if not 0 <= head < hist["count"] or head in pointed:
            continue                           # no history yet, or not a chain's first row
        chain = list(follow(nxt, head, H.END))
        if len(chain) > 1:
            out.update(club[k] for k in chain)
    return out


def build_database(mm, season, info):
    """Whole-DB player rows via staging + join. Returns (players, club_names).
    `info` is the shared player-info spine ({tid: identity}) scraped once in main().
    Every row is the player's own record as stored. Our squad's exact attributes, feet,
    value and name come from their scrapbook entries (`player_scrapbook.json`), which the
    store joins on (`staging.players`)."""
    attrs = scrape_player_attributes(mm)        # {sid: attribute record}
    # Staff get a SEPARATE attribute record, keyed by the info field's `id2` (+64), holding
    # coaching ability and the preferred/attacking/defensive formation triple. See
    # fmparser/staff.py.
    formations = ST.formation_catalog(mm)
    staff_attrs = ST.scrape_staff_attributes(
        mm, (p["id2"] for p in info.values() if p["sid"] == "ffffffff"))
    status = scrape_squad_status(mm)            # {tid: squad-status code}
    contracts = scrape_contracts(mm, info)      # {tid: {wage_units, wage_gbp, expiry, expiry_year}}

    # whole-DB name resolver: first/last name ids -> strings.
    R.build_name_resolver(mm)

    def full_name(tid, p):
        # The common name first: it is the display name, and without it 2,424 people appear
        # under their full legal names ('Tite' as Adenor Leonardo Bachi). Legal name last.
        return (R.resolve_common_name(mm, p.get("common_name_id"))
                or R.resolve_name(mm, p["first_name_id"], p["last_name_id"]))

    # career history: the whole pool as stored, plus each player's head row (the attribute
    # record's `history_head`). Reading a chain is the loader's job. Never fatal: if the pool
    # can't be located or fails its forest check, extraction proceeds without history.
    try:
        histories = H.scrape_history(mm, info, attrs)
    except Exception as e:                       # locator/forest failure -> skip history
        print(f"  WARNING: history table not parsed ({e}); continuing without history")
        histories = None

    # resolve club names only for clubs that actually have loaded players (they exist,
    # so the lookup is cheap) plus clubs that appeared in matches or on a player's history
    # chain -- every row of a chain with a season on it, so origin clubs get named too
    club_ids = {p["club_tid"] for p in info.values()
                if p["sid"] in attrs and p["club_tid"] != NO_CLUB}
    for m in season:
        club_ids.add(m["home_tid"])
        club_ids.add(m["away_tid"])
    if histories:
        club_ids.update(_history_clubs(histories))
    club_ids.discard(NO_CLUB)
    club_names, club_leagues = {}, {}
    for ct in club_ids:
        rec = R.club_record(mm, ct, "long")
        if rec:
            club_names[ct] = rec["name"]
            if rec["league"]:               # club->league from the club record (day-1 safe)
                club_leagues[ct] = rec["league"]

    def club_label(ct):
        if ct == NO_CLUB:
            return "Free agent"
        return club_names.get(ct, f"#{ct}")

    players, staff = {}, {}
    for tid, p in info.items():
        # SID == ffffffff means no linked player record -> staff (manager/coach/scout).
        # Confirmed: these average age 45 (68% over 40) vs 26 for players. There's also
        # an explicit type flag at info+33 (1=player/0=staff) that agrees ~99%; the ~0.7%
        # disagreement is likely player-coaches (both roles). We classify by SID, which
        # handles them correctly (a player-coach has a real SID -> counted as a player).
        # Not worth special-casing further for now.
        if p["sid"] == "ffffffff":
            row = {"tid": tid, "name": full_name(tid, p),
                   "club": club_label(p["club_tid"]),
                   "club_tid": p["club_tid"], "dob": p["dob"],
                   "nationality_id": p["nationality_id"],
                   **{k: p[k] for k in PERSON_FIELDS}}
            sa = staff_attrs.get(p["id2"])
            if sa:
                row.update({k: sa[k] for k in ST.STAFF_FIELDS})
                # store the catalog index AND the resolved name: the index is the save's
                # own id, the name is what a human reads.
                for slot in ST.FORMATION_SLOTS.values():
                    ix = sa[slot]
                    row[f"{slot}_name"] = (formations[ix]
                                           if ix < len(formations) else None)
            staff[str(tid)] = row
            continue
        rec = attrs.get(p["sid"])
        sc = status.get(tid)
        club_tid = p["club_tid"]
        c = contracts.get(tid)                  # contract detail (wage + expiry); may be None
        row = {"tid": tid, "name": full_name(tid, p),
               "club": club_label(club_tid), "club_tid": club_tid,
               "dob": p["dob"], "nationality_id": p["nationality_id"],
               **{k: p[k] for k in PERSON_FIELDS},
               "has_attributes": rec is not None,
               "squad_status": sc,
               "loaned_out": sc == LOAN_STATUS and p["club_tid"] != NO_CLUB,
               "wage_units": c["wage_units"] if c else None,
               "wage_gbp": c["wage_gbp"] if c else None,
               "contract_expiry": c["expiry"] if c else None,
               "contract_expiry_year": c["expiry_year"] if c else None}
        if rec:
            row["is_gk"] = int(rec["positions"].get("GK", 0) == 20)
            row["ca"], row["pa"] = rec["ca"], rec["pa"]
            row["reputation"] = rec["reputation"]
            row["positions"] = rec["positions"]
            # the rest of the global record (see attributes.record_tail), for every
            # attributed player.
            for k in TAIL_FIELDS + HIDDEN_FIELDS + SRC_FIELDS:
                row[k] = rec[k]
            # Only what the record states plainly. The 15 entangled attributes and Teamwork
            # are DERIVED, and derivation is the database's job -- staging.player_attributes
            # is a view over these exact values plus staging.attribute_model.
            row["attributes"] = {a: (rec["attributes"][a] if a in MOD.EXACT_SINGLE else None)
                                 for a in MOD.ATTR_ORDER}
            row["estimated"] = {a: a not in MOD.EXACT_SINGLE and a != "Teamwork"
                                for a in MOD.ATTR_ORDER}
            row["feet"] = rec["feet"]
        else:                              # identity only (free agents / no record)
            row.update({"is_gk": None, "ca": None, "pa": None, "reputation": None,
                        "positions": {}, "feet": None,
                        "attributes": None, "estimated": None,
                        **{k: None for k in TAIL_FIELDS + HIDDEN_FIELDS + SRC_FIELDS}})
        players[str(tid)] = row
    return players, staff, club_names, club_leagues, histories


def scrapbook_entries(mm):
    """Every used scrapbook entry, list by list: its list, the list's season (0xffff while
    in progress), its slot, and the entry's named fields."""
    return [{"list": lst["index"], "list_season": lst["season"], "slot": e["slot"],
             **{k: v for k, v in e.items() if k not in ("offset", "slot")}}
            for lst in PL.scrape_player_lists(mm) for e in lst["entries"]]


_STAT_FIELDS = ["posOrder", "rating", "goals", "assists", "passA", "passC",
                "keyPass", "tackA", "tackW", "intercept", "shotA", "shotO",
                "condition", "subOn", "subOff", "yellow"]


def flatten_matches(season):
    """One row per (match, player), carrying the team actually played for."""
    rows = []
    for m in season:
        for side, team, opp in (("home_xi", m["home_tid"], m["away_tid"]),
                                ("away_xi", m["away_tid"], m["home_tid"])):
            for p in m[side]:
                row = {"date": m["date"], "comp_id": m["comp_id"],
                       "tid": p["tid"], "team_tid": team, "opponent_tid": opp}
                row.update({k: p[k] for k in _STAT_FIELDS})
                rows.append(row)
    return rows


def build_leagues(mm, club_leagues, nations_map=None):
    """Leagues reference built from club->league facts and reference comp records."""
    leagues = {}
    for code in sorted(set(club_leagues.values())):
        if not code or code == 0xFFFF:
            continue
        d = R.comp_detail(mm, code) or {}
        nid = d.get("nation_id")
        members = sorted(t for t, c in club_leagues.items() if c == code)
        nat_name = nations_map.get(nid, {}).get("name") if nations_map and nid is not None else None
        leagues[code] = {
            "cid": code,
            "name": d.get("name") or R.league_name(mm, code),
            "type": d.get("type", "league"),
            "nation_id": nid,
            "nation": nat_name,
            "reputation": d.get("reputation"),
            "level": d.get("level"),
            "parent_cid": d.get("parent_cid"),
            "members": members,
            "member_count": len(members),
            "fixtures": 0,
        }
    return leagues


def league_label(detail):
    """Human league name: the resolved name, else 'Nation (unnamed)' when only the nation
    is known (foreign comps without a name record), else None."""
    if not detail:
        return None
    if detail.get("name"):
        return detail["name"]
    if detail.get("nation"):
        return f"{detail['nation']} (unnamed)"
    return None


def build_competitions(mm, season):
    """Reference for every competition in the season: name/short/code, type, nation, and
    num_teams (each nation's team-count rules in the data dictionary,
    fmparser/tables/rule_files.team_counts)."""
    counts = RULE_FILES.team_counts(mm)
    comps = {}
    for cid in sorted({m["comp_id"] for m in season if m.get("comp_id")}):
        d = R.comp_detail(mm, cid) or {"cid": cid}
        if "uid" in d:
            d["num_teams"] = counts.get(d["uid"])
        d["matches_in_save"] = sum(1 for m in season if m.get("comp_id") == cid)
        comps[str(cid)] = d
    return comps


def write_players_csv(path, players):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tid", "name", "club", "club_tid", "loan", "league", "league_cid",
                    "GK", "CA", "PA", "rep", "dob", "nat", "positions"]
                   + list(TAIL_FIELDS + HIDDEN_FIELDS + SRC_FIELDS) + MOD.ATTR_ORDER)
        # attributed players first (by CA desc), then identity-only rows
        def sortkey(p):
            return (0 if p["has_attributes"] else 1, -(p["ca"] or 0), p["tid"])
        for p in sorted(players.values(), key=sortkey):
            pos = "/".join(k for k, v in sorted(p["positions"].items(),
                                                key=lambda kv: -kv[1]))
            attr = p["attributes"] or {}
            w.writerow([p["tid"], p["name"] or "", p["club"], p["club_tid"],
                        "Y" if p.get("loaned_out") else "",
                        p.get("league") or "", p.get("league_cid") or "",
                        "Y" if p["is_gk"] else "", p["ca"] or "", p["pa"] or "",
                        p["reputation"] or "", p["dob"] or "", p["nationality_id"], pos]
                       + [("" if p.get(k) is None else p[k])
                          for k in TAIL_FIELDS + HIDDEN_FIELDS]
                       + [attr.get(a, "") for a in MOD.ATTR_ORDER])


def write_match_stats_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        cols = ["date", "comp_id", "tid", "team_tid", "opponent_tid"] + _STAT_FIELDS
        w.writerow(cols)
        for r in rows:
            w.writerow([r[c] for c in cols])


def main():
    ap = argparse.ArgumentParser(description="Extract an FMM22 save's current state.")
    ap.add_argument("save", help="path to the .fms save file")
    ap.add_argument("--label", help="output label (default: auto <year>-<period>)")
    ap.add_argument("--out", default="output", help="output root (default: output/)")
    ap.add_argument("--career", help="managed-career key from fmparser/careers.py "
                    f"(default: {C.DEFAULT_CAREER}). Known: {', '.join(sorted(C.CAREERS))}")
    args = ap.parse_args()

    career = C.resolve_career(args.career)
    print(f"career: {career.name} (managed tid {career.managed_tid}, "
          f"reserves {career.reserve_tid})")

    s = Save(args.save)
    mm = s.mm
    season = MT.scrape_matches(mm)
    auto, latest = auto_label(season)
    label = args.label or auto
    dest = os.path.join(args.out, label)
    os.makedirs(dest, exist_ok=True)

    info = scrape_person_info(mm)            # player-info spine (scraped once, shared)
    players, staff, club_names, club_leagues, histories = build_database(mm, season, info)
    match_rows = flatten_matches(season)
    competitions = build_competitions(mm, season)

    # leagues reference + club->league. The club record gives membership directly: exact,
    # current as of the save date, and available on a day-1 save before any match.
    nations_map = nations.scrape_nations(mm)
    leagues = build_leagues(mm, club_leagues, nations_map=nations_map)
    club2league = dict(club_leagues)
    for p in players.values():
        lc = club2league.get(p["club_tid"])
        p["league_cid"] = lc
        p["league"] = league_label(leagues.get(lc))

    def dump(name, obj, indent=1):
        with open(os.path.join(dest, name), "w", newline="") as f:
            json.dump(obj, f, ensure_ascii=False, indent=indent)

    dump("players.json", players, indent=None)     # ~24k players -> compact
    dump("staff.json", staff, indent=None)         # ~7k non-players (identity only)
    # the career-history pool, every row column-wise, and each player's head row
    # (fmparser/tables/history.py); the loader reads the chains
    if histories:
        dump("history.json", histories, indent=None)
    dump("matches.json", season)
    dump("competitions.json", competitions)
    # Full club records: facts, colours, and the fixed 40-slot SQUAD + 11-slot STAFF arrays.
    # See tables.clubs.CLUB_TABLE. Only clubs we already resolved a name for, so this
    # inherits the same validation rather than trusting the raw index.
    club_details = {}
    for ct in sorted(club_names):
        d = R.club_details(mm, ct)
        if d and "squad" in d:
            club_details[str(ct)] = d
    dump("club_details.json", club_details, indent=None)
    # Club History, per club: the Team Records and Player Records tables (every written slot)
    # and the league history (fmparser/tables/club_records.py). A record match is here
    # because it set a record: NOTHING should build a fixture list from it.
    try:
        recs = CRE.scrape_club_records(mm)
    except Exception as e:
        print(f"  WARNING: club records not read ({e})")
        recs = None
    if recs is not None:
        dump("club_records.json", recs["team_records"], indent=None)
        dump("player_records.json", recs["player_records"], indent=None)
        dump("club_league_history.json", recs["league_history"], indent=None)
    # Every scrapbook entry in the 66 player lists, as stored (fmparser/tables/player_lists.py):
    # the World and Manager's Best Eleven pools, season by season and all-time. Our squad's
    # exact attributes are its entries in the manager's lists; the store picks them.
    dump("player_scrapbook.json", scrapbook_entries(mm), indent=None)
    # The Training page, for every player in the world: focus role, focus position, attribute
    # focus and intensity (fmparser/tables/training.py). A scrapbook entry's role is this
    # focus role on the entry's date.
    try:
        dump("training.json", TRN.scrape_training(mm), indent=None)
    except ValueError as e:
        print(f"  WARNING: training not read ({e})")
    # Stadiums + cities: capacity and real lat/long. Reference data, so it repeats per
    # snapshot exactly like clubs.json does — the club record's stadium_id joins
    # club -> stadium -> city -> coordinates. See fmparser/tables/stadiums.py and cities.py.
    dump("stadiums.json", {str(k): v for k, v in sorted(stadiums.scrape_stadiums(mm).items())},
         indent=None)
    dump("cities.json", {str(k): v for k, v in sorted(cities.scrape_cities(mm).items())},
         indent=None)
    # Reference data dumps — languages (resolve person language lists),
    # currencies (exchange rate per GBP) and nations.
    dump("languages.json", {str(k): v for k, v in sorted(languages.scrape_languages(mm).items())})
    dump("currencies.json", {str(k): v for k, v in sorted(currencies.scrape_currencies(mm).items())})
    dump("nations.json", {str(k): v for k, v in sorted(nations_map.items())})
    dump("leagues.json", {str(c): d for c, d in sorted(leagues.items())})
    # club -> league for the whole DB (source='club_league'): from the club records ONLY —
    # a pure snapshot of which competition each club is in on the save date. This is what the
    # dashboard resolves on. Any historical/derived view belongs in the DuckDB ETL, which has
    # the raw fixture list (staging.results, each row carrying its cid) to derive it from.
    dump("club_league.json",
         {str(t): {"league_cid": c, "league_name": (leagues.get(c) or {}).get("name")}
          for t, c in sorted(club2league.items())})
    dump("clubs.json", {str(t): n for t, n in sorted(club_names.items())})
    # The WORLD fixture list, from the zstd archive at the tail of the save
    # (fmparser/tables/fixtures.py -> fmparser/core/archive.py). ~27k matches over ~1,750 clubs against
    # the ~60 of our own in the match table (tables/matches.py).
    #
    # Three things this is NOT, all of them load-bearing:
    #   * not history -- it is a TWO-CALENDAR-YEAR ROLLING WINDOW of matches already played,
    #     so a 2026 save knows nothing about 2021. It enriches this snapshot only. Covering
    #     the career means unioning it across snapshots, which nothing does yet.
    #   * not scored -- the goal bytes sit in a variable-shape block and are right only when
    #     that block takes its plain shape. See fixtures.py; they are not emitted.
    #   * not attributed to a competition -- the record carries no competition field. Its
    #     stage_index/round_index index into the competition's own rules member, which a
    #     match's comp_id reaches through the competition uid (competition_rounds below).
    #
    # Degrades to an empty file rather than failing the extract: the archive needs
    # `uv sync --extra archive`, and a save could in principle carry no archive at all.
    try:
        world = FIX.fixtures(mm, valid_clubs=set(club_names))
    except ImportError as e:
        print(f"  NOTE: world fixtures skipped ({e}); run `uv sync --extra archive`")
        world = []
    except Exception as e:
        print(f"  NOTE: world fixtures unavailable ({type(e).__name__}: {e})")
        world = []
    dump("world_fixtures.json", world, indent=None)
    # The match table against the fixture list: the same games, since the rollover. This is
    # what tells an empty table after the rollover from a table the locator missed.
    header = HDR.read_save_header(mm)
    if world and header["date"]:
        until = header["date"]
        since = f"{until[:4]}-{career.rollover[0]:02d}-{career.rollover[1]:02d}"
        if since > until:
            since = f"{int(until[:4]) - 1}{since[4:]}"
        MT.check_against_fixtures(season, world, (career.managed_tid, career.reserve_tid),
                                  since, until)
    # Every competition's stage/round structure (archive members comp_<uid>.dat) and the
    # round-name catalog it names them from (main save). Together they label a fixture:
    # (uid, stage_index, round_index) -> 'League Path' / 'Third Qualifying Round'.
    try:
        comp_rounds = CRU.competition_rounds(mm)
    except ImportError as e:
        print(f"  NOTE: competition rules skipped ({e}); run `uv sync --extra archive`")
        comp_rounds = []
    except Exception as e:
        print(f"  NOTE: competition rules unavailable ({type(e).__name__}: {e})")
        comp_rounds = []
    dump("competition_rounds.json", comp_rounds, indent=None)
    round_names = (ROUNDS.round_names_map(mm) if ROUNDS.locate_rounds(mm) is not None
                   else {})
    dump("round_names.json",
         [{"id": i, "name": n} for i, n in sorted(round_names.items())], indent=None)
    snap_season, snap_phase = season_phase(header["date"], season, career.rollover)   # the DB grain
    # the weekly Player Progress table, every used row as stored; injury and loan spells are
    # read from its status bits in the mart (fmparser/tables/player_progress.py)
    try:
        progress = PP.scrape_player_progress(mm)
    except ValueError as e:
        print(f"  WARNING: {e}; no player progress")
        progress = []
    dump("player_progress.json", progress, indent=None)
    write_players_csv(os.path.join(dest, "players.csv"), players)
    write_match_stats_csv(os.path.join(dest, "player_match_stats.csv"), match_rows)

    attributed = sum(1 for p in players.values() if p["has_attributes"])
    dates = sorted(m["date"] for m in season if m["date"])
    summary = {
        "label": label, "label_auto": auto,
        "season": snap_season, "phase": snap_phase,
        "label_source": "argument" if args.label else "auto",
        "career": {"key": career.key, "name": career.name,
                   "managed_tid": career.managed_tid,
                   "reserve_tid": career.reserve_tid, "db": career.db},
        "save": os.path.abspath(args.save),
        "save_date": header["date"], "save_title": header["title"],
        "latest_match": latest, "date_range": [dates[0], dates[-1]] if dates else None,
        "competitions": {str(c): n for c, n
                         in sorted(Counter(m["comp_id"] for m in season).items())},
        "counts": {"matches": len(season), "player_match_lines": len(match_rows),
                   "players": len(players), "players_with_attributes": attributed,
                   "history_rows": histories["count"] if histories else 0,
                   "staff": len(staff), "competitions": len(competitions),
                   "leagues": len(leagues), "clubs_named": len(club_names),
                   "player_progress_rows": len(progress),
                   "world_fixtures": len(world)},
    }
    dump("summary.json", summary)

    print(f"extracted -> {dest}/")
    print(f"  matches {len(season)}  players {len(players)} "
          f"({attributed} with attributes)  staff {len(staff)}  "
          f"leagues {len(leagues)}  clubs {len(club_names)}")
    print(f"  label {label} (auto {auto}, latest match {latest})")
    s.close()


if __name__ == "__main__":
    main()
