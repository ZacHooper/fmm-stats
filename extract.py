#!/usr/bin/env python3
"""
Extract an FMM22 save's tables into an output bundle, one JSON file per table, as stored.

    uv run python extract.py path/to/<career>-<date>.fms [--out output]

A save reads the same whatever career it belongs to, so extract takes no career: joining the
tables, placing the snapshot in its campaign and checking the match table against the
fixture list for our clubs are the loader's (`load_duckdb.py --career`).

`STEPS` is the whole extract: one step per table, in the order the tables sit in the save,
each reading its table and nothing else. A cursor walks with them: every table's first
record must sit at or after the end of the table before it, so a locator that lands on the
wrong bytes fails loudly, naming both tables, instead of reading something plausible. A
table that is not there (the match table on a 0-match save) leaves the cursor where it was.
`--no-cursor` skips the check, for a save whose tables are in another order.

Writes output/<label>/ (the label defaults to the save's file name without `.fms`):
    browse_names.json            the browse strings the name id-tables index
    persons.json                 the person table, every record, in tid order
    attribute_records.json       the player attribute table, keyed by sid
    staff_records.json           the staff attribute table, keyed by id2
    round_names.json             the stage/round/leg name catalog
    clubs.json, competitions.json, nations.json, stadiums.json, cities.json,
    currencies.json, languages.json
                                 reference tables, whole (every slot the save declares)
    competition_team_counts.json each nation's team-count rules
    formations.json              the formation catalog the staff records index
    contracts.json               the contract grid
    name_ids.json                the first-name, surname and nickname id-tables
    history.json                 the career-history pool
    club_records.json, player_records.json, club_league_history.json
                                 Club History, per club
    player_progress.json         the weekly Player Progress table
    training.json                the Training page, every player
    matches.json                 this season's matches as stored
    player_scrapbook.json        every scrapbook entry of the 66 player lists
    world_fixtures.json          the archive's world fixture list
    competition_rounds.json      the archive's competition stage/round structures
    summary.json                 the save, its header date and title, counts

The save's header date is the snapshot's identity; a save whose header does not read is
refused.
"""
import argparse
import json
import os
from collections import Counter
from typing import Any, Callable, Dict, NamedTuple, Optional, Tuple

from fmparser.core import archive as ARCH
from fmparser.save import Save
from fmparser import tables as T
from fmparser.tables import (
    cities,
    club_records as CRE,
    clubs as CL,
    comp_rules as CRU,
    competitions as CO,
    contracts,
    currencies,
    fixtures as FIX,
    history as H,
    languages,
    matches as MT,
    names as NM,
    nations,
    person_info,
    player_attributes as PA,
    player_lists as PL,
    player_progress as PP,
    rounds as ROUNDS,
    rule_files as RULE_FILES,
    save_header as HDR,
    stadiums,
    staff as ST,
    training as TRN,
)

Span = Tuple[int, int]               # (first record, one past the table's last byte)
Files = Dict[str, Tuple[Any, Optional[int]]]   # file name -> (content, json indent)


class Step(NamedTuple):
    name: str                                   # the table, as an error names it
    where: Callable[[Any], Optional[Span]]      # mm -> where the table sits, None if absent
    read: Callable[[Any], Files]                # mm -> the files it writes


def registered(*names: str) -> Callable[[Any], Optional[Span]]:
    """`where` for tables in the registry (fmparser.tables.TABLES), stored one after
    another: the first one's first record to the last byte of any of them."""
    def where(mm):
        first = T.first_record(mm, names[0])
        if first is None:
            return None
        return first, max(e for n in names for _, e in T.table_spans(mm, n))
    return where


def browse_names_span(mm) -> Optional[Span]:
    start, end, _ = NM.walk_browse_bounds(mm)
    return None if start is None else (start, end)


def archive_span(mm) -> Span:
    return ARCH.locate(mm)[0], len(mm)


def by_key(rows: Dict[int, Any]) -> Dict[str, Any]:
    """{id: row} with string keys, in id order -- how the keyed reference tables dump."""
    return {str(k): v for k, v in sorted(rows.items())}


# --- the reads, one per table ------------------------------------------------------------

def read_persons(mm) -> Files:
    """The person table, every record in tid order: a player links his attribute record by
    `sid`, a staff member (sid ffffffff) his staff record by `id2`."""
    info = person_info.scrape_person_info(mm)
    return {"persons.json": ([info[t] for t in sorted(info)], None)}


def read_attribute_records(mm) -> Files:
    """Every player attribute record as stored, in table order. `positions` is the 15
    position-rating bytes decoded to {position: familiarity} (ratings above 1)."""
    out = []
    for rec in PA.scrape_player_attributes(mm).values():
        row = {k: v for k, v in rec.items() if k not in ("offset", "P", "feet", "attributes")}
        row["foot_left"], row["foot_right"] = rec["feet"]["left"], rec["feet"]["right"]
        out.append(row)
    return {"attribute_records.json": (out, None)}


def read_staff_records(mm) -> Files:
    """Every staff attribute record as stored, in table order (formation indices into
    formations.json)."""
    rows = [{k: v for k, v in rec.items() if k not in ("offset", "reputation_tier", "style")}
            for rec in ST.STAFF_TABLE.id_map(mm, key_field="id2").values()]
    return {"staff_records.json": (rows, None)}


def read_round_names(mm) -> Files:
    """The game's stage/round/leg name catalog; a competition's rules name their rounds
    from it."""
    names = ROUNDS.round_names_map(mm) if ROUNDS.locate_rounds(mm) is not None else {}
    return {"round_names.json": ([{"id": i, "name": n} for i, n in sorted(names.items())],
                                 None)}


def read_clubs(mm) -> Files:
    """The whole club table, every declared slot: names, uid, league, and the record's
    trailer (facilities, colours, the 40-slot squad and 11-slot staff arrays, affiliates)."""
    return {"clubs.json": ({str(t): c for t, c in CL.scrape_clubs(mm).items()}, None)}


def read_team_counts(mm) -> Files:
    """Each nation's team-count rules from the rule files: {competition uid: teams}."""
    return {"competition_team_counts.json": (by_key(RULE_FILES.team_counts(mm)), 1)}


def read_history(mm) -> Files:
    """The career-history pool, every row column-wise; a player's chain starts at his
    attribute record's `history_head`, and reading it is the loader's job. Never fatal: a
    pool that is not located or fails its forest check is left out."""
    try:
        return {"history.json": (H.scrape_history(mm), None)}
    except Exception as e:                       # locator/forest failure -> skip history
        print(f"  WARNING: history table not parsed ({e}); continuing without history")
        return {}


def read_club_records(mm) -> Files:
    """Club History, per club: the Team Records and Player Records tables (every written
    slot) and the league history. A record match is here because it set a record: nothing
    should build a fixture list from it."""
    try:
        recs = CRE.scrape_club_records(mm)
    except Exception as e:
        print(f"  WARNING: club records not read ({e})")
        return {}
    return {"club_records.json": (recs["team_records"], None),
            "player_records.json": (recs["player_records"], None),
            "club_league_history.json": (recs["league_history"], None)}


def read_player_progress(mm) -> Files:
    """The weekly Player Progress table, every used row as stored; injury and loan spells
    are read from its status bits in the mart."""
    try:
        progress = PP.scrape_player_progress(mm)
    except ValueError as e:
        print(f"  WARNING: {e}; no player progress")
        progress = []
    return {"player_progress.json": (progress, None)}


def read_training(mm) -> Files:
    """The Training page, for every player in the world: focus role, focus position,
    attribute focus and intensity, and the row's contract flag and squad status as stored.
    A scrapbook entry's role is this focus role on the entry's date."""
    try:
        return {"training.json": (TRN.scrape_training(mm), None)}
    except ValueError as e:
        print(f"  WARNING: training not read ({e})")
        return {}


def read_scrapbook(mm) -> Files:
    """Every used scrapbook entry of the 66 player lists, list by list: its list, the
    list's season (0xffff while in progress), its slot, and the entry's named fields. Our
    squad's exact attributes are its entries in the manager's lists; the store picks them."""
    rows = [{"list": lst["index"], "list_season": lst["season"], "slot": e["slot"],
             **{k: v for k, v in e.items() if k not in ("offset", "slot")}}
            for lst in PL.scrape_player_lists(mm) for e in lst["entries"]]
    return {"player_scrapbook.json": (rows, None)}


def read_archive(no_archive: bool) -> Callable[[Any], Files]:
    """The zstd archive at the save's tail: the world fixture list and every competition's
    stage/round structure.

    The fixture list is a two-calendar-year rolling window of matches already played, so it
    enriches this snapshot only; it carries no competition field (a fixture's stage and
    round index into its competition's rules, `competition_rounds`). Reading the archive
    needs zstandard: without it the extract stops unless --no-archive says to go on without
    both. An archive that is there but does not read degrades to empty files with a NOTE."""
    def read(mm):
        try:
            world = FIX.fixtures(mm)
        except ImportError as e:
            if not no_archive:
                raise SystemExit(f"the save's archive needs zstandard ({e}): run extract as "
                                 f"`uv run python extract.py ...`, or pass "
                                 f"--no-archive to extract without the fixtures and rules")
            world = []
        except Exception as e:
            print(f"  NOTE: world fixtures unavailable ({type(e).__name__}: {e})")
            world = []
        try:
            rounds = CRU.competition_rounds(mm)
        except ImportError:
            rounds = []                          # --no-archive; refused above otherwise
        except Exception as e:
            print(f"  NOTE: competition rules unavailable ({type(e).__name__}: {e})")
            rounds = []
        return {"world_fixtures.json": (world, None), "competition_rounds.json": (rounds, None)}
    return read


def one(file: str, scrape: Callable[[Any], Any],
        indent: Optional[int] = None) -> Callable[[Any], Files]:
    """The read for a table that dumps as `scrape` returns it, to one file."""
    return lambda mm: {file: (scrape(mm), indent)}


def steps(no_archive: bool = False):
    """Every table extract reads, in the order the save stores them."""
    return [
        Step("browse names", browse_names_span, one("browse_names.json", NM.walk_browse)),
        Step("person_info", registered("person_info"), read_persons),
        Step("player_attributes", registered("player_attributes"), read_attribute_records),
        Step("staff", registered("staff"), read_staff_records),
        Step("round_names", registered("round_names"), read_round_names),
        Step("clubs", registered("clubs"), read_clubs),
        Step("competitions", registered("competitions"),
             one("competitions.json", lambda mm: by_key(CO.scrape_competitions(mm)), 1)),
        Step("nations", registered("nations"),
             one("nations.json", lambda mm: by_key(nations.scrape_nations(mm)), 1)),
        Step("stadiums", registered("stadiums"),
             one("stadiums.json", lambda mm: by_key(stadiums.scrape_stadiums(mm)))),
        Step("cities", registered("cities"),
             one("cities.json", lambda mm: by_key(cities.scrape_cities(mm)))),
        Step("currencies", registered("currencies"),
             one("currencies.json", lambda mm: by_key(currencies.scrape_currencies(mm)), 1)),
        Step("languages", registered("languages"),
             one("languages.json", lambda mm: by_key(languages.scrape_languages(mm)), 1)),
        Step("rule_files", registered("rule_files"), read_team_counts),
        Step("formation catalog", ST.formation_catalog_span,
             one("formations.json", ST.formation_catalog, 1)),
        Step("contracts", registered("contracts"),
             one("contracts.json", contracts.scrape_contracts)),
        Step("name id-tables", registered("surnames", "first_names", "nicknames"),
             one("name_ids.json", NM.scrape_name_ids)),
        Step("history", registered("history"), read_history),
        Step("club_records", registered("club_records"), read_club_records),
        Step("player_progress", registered("player_progress"), read_player_progress),
        Step("training", registered("training"), read_training),
        Step("matches", registered("matches"), one("matches.json", MT.scrape_matches, 1)),
        Step("player_lists", registered("player_lists", "player_list_trailers"),
             read_scrapbook),
        Step("archive", archive_span, read_archive(no_archive)),
    ]


def located(step: Step, mm) -> Optional[Span]:
    """Where the step's table sits, or None when it is not there. A locator that fails is
    "not there" here; the read decides whether that is fatal."""
    try:
        return step.where(mm)
    except Exception:
        return None


def summary(label: str, save: str, header: Dict[str, Any], out: Dict[str, Any]):
    """The save, its header date and title, and what each table held."""
    persons, matches = out["persons.json"], out["matches.json"]
    players = [p for p in persons if p["sid"] != "ffffffff"]
    sids = {r["sid"] for r in out["attribute_records.json"]}
    history = out.get("history.json")
    return {
        "label": label,
        "save": os.path.abspath(save),
        "save_date": header["date"], "save_title": header["title"],
        "competitions": {str(c): n for c, n
                         in sorted(Counter(m["comp_id"] for m in matches).items())},
        "counts": {"matches": len(matches), "players": len(players),
                   "players_with_attributes": sum(1 for p in players if p["sid"] in sids),
                   "history_rows": history["count"] if history else 0,
                   "staff": len(persons) - len(players),
                   "competitions": len(out["competitions.json"]),
                   "clubs": len(out["clubs.json"]),
                   "player_progress_rows": len(out["player_progress.json"]),
                   "world_fixtures": len(out["world_fixtures.json"])},
    }


def main():
    ap = argparse.ArgumentParser(description="Extract an FMM22 save's tables.")
    ap.add_argument("save", help="path to the .fms save file")
    ap.add_argument("--label", help="output folder name (default: the save's file name "
                    "without .fms, e.g. frem-2023-07-02)")
    ap.add_argument("--out", default="output", help="output root (default: output/)")
    ap.add_argument("--no-archive", action="store_true",
                    help="extract without the save's archive (the world fixtures and the "
                         "competition rules) when zstandard is not installed")
    ap.add_argument("--no-cursor", action="store_true",
                    help="read every table wherever its locator finds it, without checking "
                         "that the tables sit in the order extract expects")
    args = ap.parse_args()

    s = Save(args.save)
    mm = s.mm
    header = HDR.read_save_header(mm)
    if header["date"] is None:
        raise SystemExit("the save's header title has no readable date, so the snapshot "
                         "cannot be placed; is this an FMM22 save?")
    label = args.label or os.path.splitext(os.path.basename(args.save))[0]
    dest = os.path.join(args.out, label)
    os.makedirs(dest, exist_ok=True)

    def dump(name, obj, indent=1):
        with open(os.path.join(dest, name), "w", newline="") as f:
            json.dump(obj, f, ensure_ascii=False, indent=indent)

    cursor, previous = HDR.SAVE_HEADER.span, "the save header"
    out: Dict[str, Any] = {}
    for step in steps(args.no_archive):
        span = located(step, mm)
        if span is not None and not args.no_cursor:
            if span[0] < cursor:
                raise SystemExit(
                    f"{step.name}: its first record is at {span[0]:,}, before the cursor "
                    f"{cursor:,} where {previous} ends -- the save's tables are not in the "
                    f"order extract reads them (--no-cursor reads each wherever it is found)")
            cursor, previous = span[1], step.name
        for name, (obj, indent) in step.read(mm).items():
            dump(name, obj, indent)
            out[name] = obj

    summ = summary(label, args.save, header, out)
    dump("summary.json", summ)
    c = summ["counts"]
    print(f"extracted -> {dest}/")
    print(f"  matches {c['matches']}  players {c['players']} "
          f"({c['players_with_attributes']} with attributes)  staff {c['staff']}  "
          f"competitions {c['competitions']}  clubs {c['clubs']}")
    print(f"  label {label}  save date {header['date']}")
    s.close()


if __name__ == "__main__":
    main()
