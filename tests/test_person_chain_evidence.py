#!/usr/bin/env python3
"""
Evidence for the per-person chain's second and third links, read from 2026-11-12: the staff
rows and the club rows after the per-person rows, on both games.

`tests/fixtures/person_chain_evidence.json` pins each walk's start and count, how many club
rows carry the extra block, and the raw bytes at the staff rows' end. The rest is checked
against tables we already trust:

  - the staff rows' count is the staff table's and their walk ends on the club count;
  - the club rows' count is the club table's and their walk ends on a u16 equal to the
    player-attribute count;
  - the chain is contiguous: person_index -> staff_rows -> club_rows, no byte between.

    uv run python tests/test_person_chain_evidence.py
"""
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.harness import find_save, skip  # noqa: E402

from fmparser.save import Save  # noqa: E402
from fmparser.tables import (club_rows, person_index, player_status, staff,  # noqa: E402
                             staff_rows, tables_for)
from fmparser.tables.person_info import scrape_person_info  # noqa: E402
from fmparser.tables.player_attributes import scrape_player_attributes  # noqa: E402
from fmparser.tables.player_attributes import locate_player_attributes  # noqa: E402
from fmparser.tables.save_header import FMM27, save_format  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "person_chain_evidence.json")

failures = []


def check(cond, what):
    print(f"  {'ok  ' if cond else 'FAIL'} {what}")
    if not cond:
        failures.append(what)


def check_save(name, fx):
    path = find_save(name)
    if not path:
        print(f"  (skipped: {name} not found)")
        return False
    mm = Save(path).mm
    v27 = save_format(mm) == FMM27
    print(f"\n{name} ({'FMM27' if v27 else 'FMM22'})")

    print(" RAW BYTES")
    for off, hexstr, what in fx["raw"]:
        want = bytes.fromhex("".join(hexstr.split()))
        check(bytes(mm[off:off + len(want)]) == want, f"@{off} {what}")

    print(" WALKS")
    sr, cr = staff_rows.locate_staff_rows(mm), club_rows.locate_club_rows(mm)
    want = fx["staff_rows"]
    check(sr == (want["base"], want["count"]), f"staff rows at {want['base']:,}, {want['count']:,}")
    want = fx["club_rows"]
    check(cr == (want["base"], want["count"]), f"club rows at {want['base']:,}, {want['count']:,}")
    rows = club_rows.scrape_club_rows(mm)
    check(len(rows) == want["count"], f"club rows read {want['count']:,} rows")
    extra = club_rows.club_rows_extra_count(mm)
    check(extra == want["extra"], f"{want['extra']:,} club rows carry the extra block")
    check(len(staff_rows.scrape_staff_rows(mm)) == fx["staff_rows"]["count"],
          "staff rows read their count")

    for tid, want in fx.get("club_values", {}).items():
        for k, v in want.items():
            check(rows[int(tid)][k] == v, f"club {tid} {k} = {v}")

    print(" CHAIN")
    pi = person_index.locate_person_index(mm)
    stride = (person_index.PERSON_INDEX_FMM27 if v27 else person_index.PERSON_INDEX).span
    check(pi[0] + pi[1] * stride + 2 == sr[0], "staff rows start where the per-person rows end")
    check(sr[1] == staff.locate_staff(mm)[1], "staff rows: one per staff record")
    check(staff_rows.staff_rows_end(mm) + 2 == cr[0], "club rows start where the staff rows end")
    check(cr[1] == tables_for(mm)["clubs"].runs(mm)[0][1], "club rows: one per club")
    end = club_rows.club_rows_table_spans(mm)[0][1]
    players = locate_player_attributes(mm)[1]
    check(struct.unpack_from("<H", mm, end)[0] == players,
          f"club rows end on the player-attribute count {players:,}")
    if fx["players"] is not None:
        check(players == fx["players"], f"that count is {fx['players']:,}")
    if not v27:
        check(player_status.locate_player_status(mm) is None,
              "FMM22: player_status is not located (its walk is not proved there)")
    if "player_status" in fx:
        check_player_status(mm, fx["player_status"], end)
    return True


ARROWS = {"green-up": range(18, 21), "green": range(15, 18), "yellow": range(12, 15),
          "orange": range(10, 12), "red": range(1, 10)}


def check_player_status(mm, fx, club_end):
    print(" PLAYER STATUS (FMM27)")
    loc = player_status.locate_player_status(mm)
    check(loc == (club_end + 4, fx["count"]), f"blocks start after the club rows' end and "
                                              f"the u32 count {fx['count']:,}")
    rows = player_status.scrape_player_status(mm)
    check(len(rows) == fx["count"], "every block read")
    # join on tid -> sid -> block index; the fields under test come out
    sids = list(scrape_player_attributes(mm))
    persons = scrape_person_info(mm)
    clubs = {c["tid"]: c["name"] for c in tables_for(mm)["clubs"].scrape(mm)}
    block = {tid: rows[sids.index(persons[int(tid)]["sid"])] for tid in fx["screen"]}
    starts = [loc[0]]
    for _ in range(max(sids.index(persons[int(t)]["sid"]) for t in fx["slots_raw"])):
        starts.append(player_status._block_end(mm, starts[-1]))
    for tid, hexstr in fx["slots_raw"].items():
        at = starts[sids.index(persons[int(tid)]["sid"])] + player_status.STATUS_HEAD.span
        want = bytes.fromhex("".join(hexstr.split()))
        check(bytes(mm[at:at + len(want)]) == want, f"tid {tid}: interested-club slot bytes")
    for tid, names in fx["interested"].items():
        got = [clubs[t] for t in block[tid]["interested_club_tids"]]
        check(got == names, f"tid {tid}: interested clubs {', '.join(names)}")
    for tid, s in fx["screen"].items():
        form = "-".join(str(r) for r in block[tid]["form"] if r is not None) or "-"
        check(form == s["form"], f"{s['name']}: form {s['form']}")
        check(block[tid]["morale"] in ARROWS[s["arrow"]],
              f"{s['name']}: morale {block[tid]['morale']} fits the {s['arrow']} arrow")


def main():
    fx = json.load(open(FIXTURE, encoding="utf-8"))
    ran = [check_save(name, s) for name, s in fx["saves"].items()]
    if not any(ran):
        return skip("none of the pinned saves found")
    print(f"\n{'FAIL' if failures else 'PASS'}: {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
