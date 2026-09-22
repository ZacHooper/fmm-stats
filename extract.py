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
    matches.json                 full season: per-player stats, events, team stats, formation
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

from fmparser.save import Save
from fmparser import matches as M
from fmparser import model as MOD
from fmparser import clubs_comps as R
from fmparser import squad as SQ
from fmparser.tables.contracts import (
    LOAN_STATUS,
    scrape_contract_status,
    scrape_contracts,
)
from fmparser.tables.person_info import (
    NO_CLUB,
    PERSON_FIELDS,
    scrape_person_info,
)
from fmparser.tables.player_attributes import scrape_player_attributes
from fmparser import tagged as T
from fmparser.tables import fixtures as FIX
from fmparser import careers as C
from fmparser import history as H
from fmparser import injuries as INJ
from fmparser import clubrecords as CRE
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


def season_phase(matches):
    """Authoritative (season:int|None, phase:str|None) for the snapshot.

    phase is the REAL in-game date (latest match, ISO 'YYYY-MM-DD') — so multiple
    in-season snapshots coexist and sort chronologically for free, and ages compute off
    the true date instead of a start/mid/end approximation. season is the campaign
    end-year derived from that date. Returns (None, None) for a match-less day-1 save;
    the loader then supplies season via --season and synthesises a season-start phase
    date (YYYY-07-01). The old start/mid/end words are no longer produced (legacy stores
    that still hold them keep working — the sort expressions treat them as epoch)."""
    dates = sorted(m["date"] for m in matches if m["date"])
    if not dates:
        return None, None
    latest = dates[-1]
    year, month = int(latest[:4]), int(latest[5:7])
    end_year = year + 1 if month >= 8 else year
    return end_year, latest


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


def build_database(mm, season, info, markers=(SQ.CLUB_MARKER,)):
    """Whole-DB player rows via staging + join. Returns (players, club_names).
    `info` is the shared player-info spine ({tid: identity}) scraped once in main().
    `markers` are the managed club's squad markers (careers.Career.squad_markers): the
    first team plus, when the career has one, the reserve side. Both lists must be scanned
    — a player in the reserves has a live record only under the RESERVE marker, and the
    copy under the first-team marker is frozen at the day he dropped out of that list.
    A player loaned IN has no record under either — his exact attrs+value sit under a
    third marker shape entirely, [parent_club_tid][managed_tid]; see attributes.loan_marker."""
    if isinstance(markers, (bytes, bytearray)):          # back-compat: a single marker
        markers = (bytes(markers),)
    attrs = scrape_player_attributes(mm)        # {sid: attribute record}
    # Staff get a SEPARATE attribute record, keyed by the info field's `id2` (+64), holding
    # coaching ability and the preferred/attacking/defensive formation triple. See
    # fmparser/staff.py.
    formations = ST.formation_catalog(mm)
    staff_attrs = ST.scrape_staff_attributes(
        mm, (p["id2"] for p in info.values() if p["sid"] == "ffffffff"))
    status = scrape_contract_status(mm, info)   # {tid: squad-status code}
    contracts = scrape_contracts(mm, info)      # {tid: {wage_units, wage_gbp, expiry, expiry_year}}

    # names + exact attributes for the managed squad (snapshot), incl. loaned-IN players
    bounds = SQ.squad_snapshot_bounds(mm, markers)
    club_of_marker = {m: int.from_bytes(m[:2], "little") for m in markers}
    managed_tid = club_of_marker[markers[0]]             # the first team

    def _pick(per_marker, tid, strict=False):
        """(marker, entry) under the club the player is CURRENTLY in.

        Players sit in both squad lists after moving between them; the current club breaks
        the tie and is what makes the reserve copy win for a reserve player.

        `strict` decides what happens when NO marker matches the current club — i.e. the
        player has left both our lists (sold, released, or out on loan) and the only copies
        are frozen at the day he left. For NAMES that copy is still fine, so the loose form
        falls back to the last one found. For ATTRIBUTES it is actively wrong — verified on
        Hervé Buur, whose frozen copy read Pace 10 four days before the true value of 16,
        while the ordinary estimated scrape (the one every non-managed player already uses)
        got 16 exactly. So the strict form returns None and lets the caller fall through to
        estimate_player, trading a false 'exact' for an honest +/-1."""
        if not per_marker:
            return None, None
        cur = (info.get(tid) or {}).get("club_tid")
        for m, v in per_marker.items():
            if club_of_marker[m] == cur:
                return m, v
        if strict:
            return None, None
        m = list(per_marker)[-1]
        return m, per_marker[m]

    per_tid = {}
    for m in markers:
        for tid, v in SQ.own_squad_full(mm, *bounds, marker=m).items():
            per_tid.setdefault(tid, {})[m] = v
    own, own_marker = {}, {}
    for tid, per in per_tid.items():
        own_marker[tid], own[tid] = _pick(per, tid)
    own_names = {t: v["name"] for t, v in own.items()}

    # whole-DB name resolver: first/last name ids -> strings.
    R.build_name_resolver(mm)

    def full_name(tid, p):
        # Order matters. `own_names` is the managed squad's names straight off the squad
        # snapshot -- what the GAME shows us -- so it wins outright. Then the common name,
        # which is also a display name and is the reason 2,424 people used to appear under
        # their full legal names ('Tite' as Adenor Leonardo Bachi). Legal name last.
        return (own_names.get(tid)
                or R.resolve_common_name(mm, p.get("common_name_id"))
                or R.resolve_name(mm, p["first_name_id"], p["last_name_id"]))

    # A loanee's squad-list "loaned_in" flag is trusted for NAME purposes (that copy is
    # fine even stale) but NOT as proof the loan is still live: verified on this exact
    # career, Ernest Nuamah reads loaned_in=True, club_tid=346 across EIGHT CONSECUTIVE
    # snapshots spanning 2023-01-06 to 2024-11-10 — almost two years, far longer than any
    # real loan, and eight other names showed the identical pattern. The squad-list entry
    # simply never got cleared. Attaching the exact-record's real attrs+value to a stale
    # ghost would be worse than the false-owned-marker case attr_record's docstring already
    # guards against: it fabricates a plausible-looking CURRENT transfer value for a player
    # who may not even be at the club any more.
    #
    # Gate on the club's squad array: only attach exact loanee attributes if the player is
    # actually in our senior or reserve squad array.
    our_club_ids = set(club_of_marker.values())
    our_squad_tids = {
        tid
        for ct in our_club_ids
        for tid in (R.club_details(mm, ct) or {}).get("squad", [])
    }

    own_exact = {}
    for tid in own_names:
        li = own.get(tid) or {}
        r = None
        if li.get("loaned_in") and li.get("parent_club_tid") and tid in our_squad_tids:
            # A loanee's exact record is anchored by [parent_club_tid][managed_tid], not
            # [club][0xffff] — see attributes.loan_marker(). Try it first: a loanee never
            # appears under our own club markers, so the fallback below would just spend a
            # full scan finding nothing before we get here anyway.
            r = SQ.attr_record(mm, tid, bounds=bounds,
                               marker=SQ.loan_marker(managed_tid, li["parent_club_tid"]))
        if r is None:
            _, r = _pick(SQ.attr_records(mm, tid, bounds=bounds, markers=markers), tid, strict=True)
        if r:
            own_exact[tid] = {"attrs": SQ.decode_confirmed_attributes(r["attrs"]),
                              "feet": {"left": r["feet"][0], "right": r["feet"][1]},
                              "value": r["value"]}

    # career (season-by-season) history: {tid: {origin_club_tid, seasons, ...}}. The history
    # slab is a forest of linked lists and each player's chain head is stored in his ATTRIBUTE
    # record (u32 @ P-38) — hence `attrs` here; the link is exact, not a positional alignment.
    # Origin club (the chain head's club) is the Athletic-Bilbao eligibility key. Computed
    # before club-name resolution so the (often obscure) origin/history clubs get named too.
    # Never fatal: if the slab can't be located for a save, extraction proceeds without history.
    try:
        histories = H.build(mm, info, attrs)
    except Exception as e:                       # locator/enumeration failure -> skip history
        print(f"  WARNING: history table not parsed ({e}); continuing without history")
        histories = {}

    # resolve club names only for clubs that actually have loaded players (they exist,
    # so the lookup is cheap) plus clubs that appeared in matches or in any player's history
    club_ids = {p["club_tid"] for p in info.values()
                if p["sid"] in attrs and p["club_tid"] != NO_CLUB}
    for m in season:
        club_ids.add(m["home_tid"])
        club_ids.add(m["away_tid"])
    for h in histories.values():               # origin/current + every season's club
        club_ids.add(h["origin_club_tid"])
        club_ids.add(h["last_season_club_tid"])
        club_ids.update(s["club_tid"] for s in h["seasons"])
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
        h = histories.get(tid)
        li = own.get(tid)                       # snapshot membership (owned or loaned-in)
        loaned_in = bool(li and li["loaned_in"])
        # A loaned-IN player plays for us: present them under the managed club (so squad /
        # ratings / percentiles include them), but keep their real owner in parent_club_tid.
        club_tid = (club_of_marker.get(own_marker.get(tid), managed_tid)
                    if loaned_in else p["club_tid"])
        parent_tid = li["parent_club_tid"] if loaned_in else None
        c = contracts.get(tid)                  # contract detail (wage + expiry); may be None
        row = {"tid": tid, "name": full_name(tid, p),
               "club": club_label(club_tid), "club_tid": club_tid,
               "dob": p["dob"], "nationality_id": p["nationality_id"],
               **{k: p[k] for k in PERSON_FIELDS},
               "has_attributes": rec is not None,
               "squad_status": sc,
               "loaned_out": sc == LOAN_STATUS and p["club_tid"] != NO_CLUB,
               "loaned_in": loaned_in,
               "parent_club_tid": parent_tid,
               "parent_club": club_label(parent_tid) if parent_tid else None,
               # career-history summary (full seasons live in history.json). origin_club_tid
               # = youth club (Bilbao eligibility key); None for newgens with no record yet.
               "has_history": h is not None,
               "origin_club_tid": h["origin_club_tid"] if h else None,
               "origin_club": club_label(h["origin_club_tid"]) if h else None,
               "history_confidence": h["confidence"] if h else None,
               "wage_units": c["wage_units"] if c else None,
               "wage_gbp": c["wage_gbp"] if c else None,
               "contract_expiry": c["expiry"] if c else None,
               "contract_expiry_year": c["expiry_year"] if c else None}
        if rec:
            row["is_gk"] = int(rec["positions"].get("GK", 0) == 20)
            row["ca"], row["pa"] = rec["ca"], rec["pa"]
            row["reputation"] = rec["reputation"]
            row["positions"] = rec["positions"]
            # the rest of the global record (see attributes.record_tail). Present for every
            # attributed player, own squad or not — it is read off the global record, not
            # the managed-club snapshot.
            for k in TAIL_FIELDS + HIDDEN_FIELDS + SRC_FIELDS:
                row[k] = rec[k]
            if tid in own_exact:           # own squad: exact snapshot attributes
                row["attributes"] = {a: own_exact[tid]["attrs"][a] for a in MOD.ATTR_ORDER}
                row["estimated"] = {a: False for a in MOD.ATTR_ORDER}
                row["feet"] = own_exact[tid]["feet"]
                row["value"] = own_exact[tid]["value"]
            else:
                # Everyone else: write ONLY what the record states plainly. The 15 entangled
                # attributes and Teamwork are DERIVED, and derivation is the database's job --
                # staging.player_attributes is a view over these exact values plus
                # staging.attribute_model. Estimating here is what used to make retraining the
                # model cost a full re-extract of every save.
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
                row = {"date": m["date"], "competition": m["competition"],
                       "tid": p["tid_int"], "team_tid": team, "opponent_tid": opp}
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
    """Reference for every competition in the season: name/short/code, type,
    nation, and num_teams (from the tagged region). See fmparser/reference &
    fmparser/tagged."""
    counts = T.league_team_counts(mm)
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
        cols = ["date", "competition", "tid", "team_tid", "opponent_tid"] + _STAT_FIELDS
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
    season = M.extract_season(mm, our_tids=(career.managed_tid, career.reserve_tid))
    auto, latest = auto_label(season)
    label = args.label or auto
    dest = os.path.join(args.out, label)
    os.makedirs(dest, exist_ok=True)

    info = scrape_person_info(mm)            # player-info spine (scraped once, shared)
    players, staff, club_names, club_leagues, histories = build_database(
        mm, season, info, career.squad_markers)
    match_rows = flatten_matches(season)
    competitions = build_competitions(mm, season)

    # leagues reference + club->league. The club record gives membership directly: exact,
    # current as of the save date, and available on a day-1 save before any match.
    valid_clubs = {p["club_tid"] for p in info.values() if p["club_tid"] != NO_CLUB}
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
    # full career histories keyed by tid (season list per player). ~10.5k players have one;
    # newgens/youth have no record yet. See fmparser/history.py.
    dump("history.json", {str(t): h for t, h in histories.items()}, indent=None)
    dump("matches.json", season)
    dump("competitions.json", competitions)
    # Full club records: facts, colours, and the fixed 40-slot SQUAD + 11-slot STAFF arrays.
    # See reference.parse_club_trailer. Only clubs we already resolved a name for, so this
    # inherits the same validation rather than trusting the raw index.
    club_details = {}
    for ct in sorted(club_names):
        d = R.club_details(mm, ct)
        if d and "squad" in d:
            club_details[str(ct)] = d
    dump("club_details.json", club_details, indent=None)
    # Club History: the Team Records and Player Records tables, per club. This is the region
    # previously misread as match RESULTS -- it is not
    # one, and fmparser/clubrecords.py's docstring has the identification against in-game
    # screenshots. Stored because it is real, verified data we can name; nothing consumes it
    # yet, and NOTHING should build a fixture list from it.
    recs = CRE.build(mm, valid_clubs, valid_players=set(info))
    dump("club_records.json", recs["team_records"], indent=None)
    dump("player_records.json", recs["player_records"], indent=None)
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
    # (fmparser/fixtures.py -> fmparser/archive.py). ~27k matches over ~1,750 clubs against
    # the ~60 of our own that matches.py parses.
    #
    # Three things this is NOT, all of them load-bearing:
    #   * not history -- it is a TWO-CALENDAR-YEAR ROLLING WINDOW of matches already played,
    #     so a 2026 save knows nothing about 2021. It enriches this snapshot only. Covering
    #     the career means unioning it across snapshots, which nothing does yet.
    #   * not scored -- the goal bytes sit in a variable-shape block and are right only when
    #     that block takes its plain shape. See fixtures.py; they are not emitted.
    #   * not attributed to a competition -- no competition field is identified in the record.
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
    # injury spells for the managed squad, from the weekly Player-Progress table. Captures TRAINING
    # injuries too (match_events only has in-match ones). Our squad only. See fmparser/injuries.py.
    # NB: `season` here is the MATCHES list; injuries key off the end-year int, derived below.
    # A match-less day-1 save has no season int (its Player-Progress holds the prior campaign we
    # already captured) — skip it rather than mislabel those weeks under the new season.
    snap_season, snap_phase = season_phase(season)   # authoritative DB grain (phase = date)
    squad_tids = [t for t, p in players.items()
                  if p["club_tid"] in (career.managed_tid, career.reserve_tid)]
    # the same weekly series also carries an ON-LOAN bit (bit 5), which gives exact loan
    # windows for players we loan OUT — see fmparser/injuries.py for the decode + validation.
    injuries, loans = (INJ.extract_availability(mm, squad_tids, snap_season)
                       if snap_season is not None else ({}, {}))
    dump("injuries.json", {str(t): sp for t, sp in injuries.items()}, indent=None)
    dump("loans.json", {str(t): sp for t, sp in loans.items()}, indent=None)
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
        "latest_match": latest, "date_range": [dates[0], dates[-1]] if dates else None,
        "competitions": dict(Counter(m.get("competition") for m in season)),
        "counts": {"matches": len(season), "player_match_lines": len(match_rows),
                   "players": len(players), "players_with_attributes": attributed,
                   "players_with_history": len(histories),
                   "staff": len(staff), "competitions": len(competitions),
                   "leagues": len(leagues), "clubs_named": len(club_names),
                   "injured_players": len(injuries),
                   "loaned_out_players": len(loans),
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
