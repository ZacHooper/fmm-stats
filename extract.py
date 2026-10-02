#!/usr/bin/env python3
"""
Extract the current state of an FMM22 save into a labelled output bundle.

    uv run python extract.py path/to/<career>-<date>.fms --career <key> [--out output]

Architecture: scrape each table of the save independently and dump it as stored; joining
them is the store's job. The person table is the identity spine (one record per person,
~33k, with every foreign key); a player's attribute record joins on its `sid`, a staff
member's on its `id2`, clubs on club_tid, names on their name ids. See fmparser/tables/.

Writes output/<label>/, one JSON file per table (see the `dump(...)` calls in main()):
    persons.json                 the person table, every record
    attribute_records.json       the player attribute table, keyed by sid
    staff_records.json           the staff attribute table, keyed by id2
    formations.json              the formation catalog the staff records index
    names.json                   the name tables the persons' name ids index
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
from fmparser.tables.contracts import scrape_contracts
from fmparser.tables.person_info import scrape_person_info
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
from fmparser.tables import names as NM
from fmparser.tables import (
    cities,
    clubs as CL,
    competitions as CO,
    currencies,
    languages,
    nations,
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


def attribute_records(mm):
    """Every player attribute record as stored, in table order. `positions` is the 15
    position-rating bytes decoded to {position: familiarity} (ratings above 1)."""
    out = []
    for rec in scrape_player_attributes(mm).values():
        row = {k: v for k, v in rec.items() if k not in ("offset", "P", "feet", "attributes")}
        row["foot_left"], row["foot_right"] = rec["feet"]["left"], rec["feet"]["right"]
        out.append(row)
    return out


def staff_records(mm):
    """Every staff attribute record as stored, in table order (formation indices into
    formations.json)."""
    return [{k: v for k, v in rec.items() if k not in ("offset", "reputation_tier", "style")}
            for rec in ST.STAFF_TABLE.id_map(mm, key_field="id2").values()]


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
    ap.add_argument("--no-archive", action="store_true",
                    help="extract without the save's archive (the world fixtures and the "
                         "competition rules) when zstandard is not installed")
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
    attrs = scrape_player_attributes(mm)     # {sid: attribute record}
    # career history: the whole pool as stored, plus each player's head row (the attribute
    # record's `history_head`). Reading a chain is the loader's job. Never fatal: if the pool
    # can't be located or fails its forest check, extraction proceeds without history.
    try:
        histories = H.scrape_history(mm, info, attrs)
    except Exception as e:                       # locator/forest failure -> skip history
        print(f"  WARNING: history table not parsed ({e}); continuing without history")
        histories = None
    # The whole competition table, every named slot.
    competitions = {str(cid): c for cid, c in sorted(CO.scrape_competitions(mm).items())}
    nations_map = nations.scrape_nations(mm)

    def dump(name, obj, indent=1):
        with open(os.path.join(dest, name), "w", newline="") as f:
            json.dump(obj, f, ensure_ascii=False, indent=indent)

    # The person table, every record in tid order: a player links his attribute record by
    # `sid`, a staff member (sid ffffffff) his staff record by `id2`.
    persons = [info[t] for t in sorted(info)]
    dump("persons.json", persons, indent=None)
    dump("attribute_records.json", attribute_records(mm), indent=None)
    dump("staff_records.json", staff_records(mm), indent=None)
    dump("formations.json", ST.formation_catalog(mm))
    # the name tables the persons' name ids index: browse strings + three id-tables
    dump("names.json", NM.scrape_names(mm), indent=None)
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
    # Reading the archive needs zstandard (a project dependency); without it the extract
    # stops unless --no-archive says to go on without the fixtures and rules. An archive that
    # is there but does not read degrades to an empty file with a NOTE.
    try:
        world = FIX.fixtures(mm)
    except ImportError as e:
        if not args.no_archive:
            raise SystemExit(f"the save's archive needs zstandard ({e}): run extract as "
                             f"`uv run python extract.py ...`, or pass "
                             f"--no-archive to extract without the fixtures and rules")
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
    except ImportError:
        comp_rounds = []                     # --no-archive; refused above otherwise
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

    players = [p for p in persons if p["sid"] != "ffffffff"]
    attributed = sum(1 for p in players if p["sid"] in attrs)
    staff = len(persons) - len(players)
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
                   "staff": staff, "competitions": len(competitions),
                   "clubs": len(clubs),
                   "player_progress_rows": len(progress),
                   "world_fixtures": len(world)},
    }
    dump("summary.json", summary)

    print(f"extracted -> {dest}/")
    print(f"  matches {len(season)}  players {len(players)} "
          f"({attributed} with attributes)  staff {staff}  "
          f"competitions {len(competitions)}  clubs {len(clubs)}")
    print(f"  label {label}  season {snap_season}  phase {snap_phase}")
    s.close()


if __name__ == "__main__":
    main()
