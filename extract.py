#!/usr/bin/env python3
"""
Extract the current state of an FMM22 save into a labelled output bundle.

    uv run python extract.py path/to/<career>-<date>.fms --career <key> [--out output]

Architecture: scrape each region of the save independently into keyed tables, then
join. The player INFO section is the identity spine (one row per player, ~31k, with
every foreign key); attributes join on SID, clubs on club_tid, names on TID. See
fmparser/tables/.

Writes output/<label>/, one JSON file per table (see the `dump(...)` calls in main()):
    players.json, staff.json     the person spine joined to the attribute / staff records
    history.json                 career history chains
    matches.json                 this season's matches as stored: events, both sides' player
                                 lines, the stored score, our formation and starting positions
    world_fixtures.json          the archive's world fixture list, with scores
    clubs.json, competitions.json, nations.json, stadiums.json, ...
                                 reference tables, whole (every slot the save declares)
    summary.json                 season, phase, counts

The label defaults to the save's file name without `.fms` (`frem-2023-07-02`); saves are
named `<career>-<header date>`, so label, save and `phase` are one string. `phase` (the
store's key) is the save's own in-game date, from its header title, and `season` the
campaign it belongs to; a save whose header does not read is refused.
"""
import argparse
import json
import os
from collections import Counter

from fmparser.save import Save
from fmparser import model as MOD
from fmparser import clubs_comps as R
from fmparser.tables.contracts import scrape_contracts
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
    clubs as CL,
    competitions as CO,
    currencies,
    languages,
    nations,
    player_attributes as PA,
    staff as ST,
    stadiums,
)


def season_phase(save_date, matches, rollover):
    """(season, phase) for the snapshot: phase is the save's own in-game date, from its header
    title (`save_header`), and season the campaign it belongs to, from the career's rollover
    day. A save whose header does not read cannot be placed and is refused."""
    if save_date is None:
        raise SystemExit("the save's header title has no readable date, so the snapshot "
                         "cannot be placed; is this an FMM22 save?")
    return HDR.campaign(save_date, any(m["date"] for m in matches), rollover), save_date


# The tail of the global attribute record (attributes.record_tail). Named once here so the
# rec-present branch and the identity-only fill cannot drift apart.
TAIL_FIELDS = ("current_reputation", "world_reputation", "international_retired",
               "squad_number", "preferred_squad_number", "height_cm", "weight_kg")
# The 9 unnamed 1-20 attribute bytes (attributes.HIDDEN_OFFSETS). Carried, not named --
# every identity-only row has to fill them too.
HIDDEN_FIELDS = tuple(PA.HIDDEN_OFFSETS.values())
# The entangled 0-255 source bytes, carried RAW so the estimation model can be
# retrained against the store instead of a 25-minute re-extract. See
# attributes.SRC_OFFSETS: scraping and inference are different jobs.
SRC_FIELDS = tuple(PA.SRC_OFFSETS.values()) + tuple(PA.PLAIN_OFFSETS.values())


def build_database(mm, info, club_names):
    """Whole-DB player rows via staging + join. Returns (players, staff, histories).
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

    def club_label(ct):
        if ct == NO_CLUB:
            return "Free agent"
        return club_names.get(ct) or f"#{ct}"

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
        club_tid = p["club_tid"]
        row = {"tid": tid, "name": full_name(tid, p),
               "club": club_label(club_tid), "club_tid": club_tid,
               "dob": p["dob"], "nationality_id": p["nationality_id"],
               **{k: p[k] for k in PERSON_FIELDS},
               "has_attributes": rec is not None}
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
    return players, staff, histories


def scrapbook_entries(mm):
    """Every used scrapbook entry, list by list: its list, the list's season (0xffff while
    in progress), its slot, and the entry's named fields."""
    return [{"list": lst["index"], "list_season": lst["season"], "slot": e["slot"],
             **{k: v for k, v in e.items() if k not in ("offset", "slot")}}
            for lst in PL.scrape_player_lists(mm) for e in lst["entries"]]


def main():
    ap = argparse.ArgumentParser(description="Extract an FMM22 save's current state.")
    ap.add_argument("save", help="path to the .fms save file")
    ap.add_argument("--label", help="output folder name (default: the save's file name "
                    "without .fms, e.g. frem-2023-07-02)")
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
    header = HDR.read_save_header(mm)
    snap_season, snap_phase = season_phase(header["date"], season, career.rollover)   # the DB grain
    label = args.label or os.path.splitext(os.path.basename(args.save))[0]
    dest = os.path.join(args.out, label)
    os.makedirs(dest, exist_ok=True)

    info = scrape_person_info(mm)            # player-info spine (scraped once, shared)
    # The whole club table, every declared slot: names, uid, league, and the record's
    # trailer (facilities, colours, the 40-slot squad and 11-slot staff arrays, affiliates).
    clubs = {}
    for tid, c in CL.scrape_clubs(mm).items():
        d = CL.club_details(mm, tid)
        clubs[str(tid)] = {"tid": tid, "uid": c["uid"],
                           **{k: v for k, v in d.items() if k != "tid"}}
    club_names = {int(t): c["name"] for t, c in clubs.items()}
    players, staff, histories = build_database(mm, info, club_names)
    # The whole competition table, every named slot.
    competitions = {str(cid): c for cid, c in sorted(CO.scrape_competitions(mm).items())}
    nations_map = nations.scrape_nations(mm)

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
    # Each nation's team-count rules: {competition uid: teams}
    # (fmparser/tables/rule_files.team_counts).
    dump("competition_team_counts.json",
         {str(u): n for u, n in sorted(RULE_FILES.team_counts(mm).items())})
    dump("clubs.json", clubs, indent=None)
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
    # The contract grid, every used slot as stored (fmparser/tables/contracts.py): marker
    # 0x01 is a current contract; wages and the player's contract are read in the store.
    dump("contracts.json", scrape_contracts(mm), indent=None)
    # The Training page, for every player in the world: focus role, focus position, attribute
    # focus and intensity, and the row's contract flag and squad status as stored
    # (fmparser/tables/training.py). A scrapbook entry's role is this
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
        world = FIX.fixtures(mm)
    except ImportError as e:
        print(f"  NOTE: world fixtures skipped ({e}); run `uv sync --extra archive`")
        world = []
    except Exception as e:
        print(f"  NOTE: world fixtures unavailable ({type(e).__name__}: {e})")
        world = []
    dump("world_fixtures.json", world, indent=None)
    # The match table against the fixture list: the same games, since the rollover. This is
    # what tells an empty table after the rollover from a table the locator missed.
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
    # the weekly Player Progress table, every used row as stored; injury and loan spells are
    # read from its status bits in the mart (fmparser/tables/player_progress.py)
    try:
        progress = PP.scrape_player_progress(mm)
    except ValueError as e:
        print(f"  WARNING: {e}; no player progress")
        progress = []
    dump("player_progress.json", progress, indent=None)

    attributed = sum(1 for p in players.values() if p["has_attributes"])
    summary = {
        "label": label,
        "season": snap_season, "phase": snap_phase,
        "career": {"key": career.key, "name": career.name,
                   "managed_tid": career.managed_tid,
                   "reserve_tid": career.reserve_tid, "db": career.db},
        "save": os.path.abspath(args.save),
        "save_date": header["date"], "save_title": header["title"],
        "competitions": {str(c): n for c, n
                         in sorted(Counter(m["comp_id"] for m in season).items())},
        "counts": {"matches": len(season), "players": len(players), "players_with_attributes": attributed,
                   "history_rows": histories["count"] if histories else 0,
                   "staff": len(staff), "competitions": len(competitions),
                   "clubs": len(clubs),
                   "player_progress_rows": len(progress),
                   "world_fixtures": len(world)},
    }
    dump("summary.json", summary)

    print(f"extracted -> {dest}/")
    print(f"  matches {len(season)}  players {len(players)} "
          f"({attributed} with attributes)  staff {len(staff)}  "
          f"competitions {len(competitions)}  clubs {len(clubs)}")
    print(f"  label {label}  season {snap_season}  phase {snap_phase}")
    s.close()


if __name__ == "__main__":
    main()
