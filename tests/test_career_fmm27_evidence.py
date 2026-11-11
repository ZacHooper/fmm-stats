#!/usr/bin/env python3
"""
Evidence for the FMM27 career half on truro-2026-07-25: the contract grid, the player
progress pool, training, the player lists and the archive (world fixtures, competition
rounds). Each walk, the raw bytes at recorded offsets, and what the parser makes of them.

`tests/fixtures/career_fmm27_evidence.json` holds the walks' extents, the bytes behind
each value, and the values. The raw bytes catch a different save; the parsed values a
parser change that reads the right bytes into the wrong field; the walks a table that
stops short or drifts onto the next.

    uv run python tests/test_career_fmm27_evidence.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.harness import find_save, skip  # noqa: E402

from fmparser.core import archive as A  # noqa: E402
from fmparser.save import Save  # noqa: E402
from fmparser.tables import (comp_rules, contracts, fixtures, player_lists,  # noqa: E402
                             player_progress, tables_for, training)
from fmparser.tables.save_header import FMM27, save_format  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "career_fmm27_evidence.json")

failures = []


def check(cond, what):
    print(f"  {'ok  ' if cond else 'FAIL'} {what}")
    if not cond:
        failures.append(what)


def main():
    fx = json.load(open(FIXTURE, encoding="utf-8"))
    path = find_save(fx["save"])
    if not path:
        return skip(f"{fx['save']} not found (fetch it with rclone, or rebuild.py)")
    mm = Save(path).mm
    walks = fx["walks"]

    print("FORMAT")
    check(save_format(mm) == FMM27, f"{fx['save']} declares fmm27")
    reg = tables_for(mm)
    check(reg["player_lists"] is player_lists.PLAYER_LISTS_TABLE_FMM27,
          "player_lists reads with FMM27's")
    check(reg["comp_rules"] is comp_rules.COMP_RULES_TABLE_FMM27, "comp_rules reads with FMM27's")
    check(reg["fixtures"] is fixtures.FIXTURES_TABLE_FMM27, "fixtures read with FMM27's")

    print("\nRAW BYTES at the recorded offsets")
    for off, hexstr, what in fx["raw"]:
        want = bytes.fromhex("".join(hexstr.split()))
        check(bytes(mm[off:off + len(want)]) == want, f"@{off} {what}")

    print("\nCONTRACTS")
    want = walks["contracts"]
    co = contracts.scrape_contracts(mm)
    check(contracts.locate_contracts(mm) == (want["base"], want["capacity"]),
          f"the grid at {want['base']:,}, capacity {want['capacity']:,}")
    check(len(co) == want["used"] and all(r["tid"] == k for k, r in enumerate(co)),
          f"{len(co):,} slots walked, tid == slot")
    check(sum(r["marker"] & 1 for r in co) == want["current"], f"{want['current']:,} current")
    for tid, wage in fx["contracts"].items():
        check(co[int(tid)]["wage_units"] == wage, f"tid {tid}: wage_units {wage:,}, past a u16")

    print("\nPLAYER PROGRESS")
    want = walks["player_progress"]
    pr = player_progress.scrape_player_progress(mm)
    check(player_progress.locate_player_progress(mm) == (want["base"], want["rows"]),
          f"the pool at {want['base']:,}, {want['rows']:,} rows")
    check(len(pr) == want["used"] and {r["week"] for r in pr} == {fx["progress_week"]},
          f"{want['used']} used rows, all the week of {fx['progress_week']}")
    check(sorted(r["tid"] for r in pr if r["status"] & 3) == fx["injured"],
          f"injured: tids {fx['injured']}")

    print("\nTRAINING")
    want = walks["training"]
    tr = {r["tid"]: r for r in training.scrape_training(mm)}
    check(training.locate_training(mm) == (want["base"], want["count"]),
          f"the table at {want['base']:,}, count {want['count']:,} = the person count")
    for tid, vals in fx["training"].items():
        got = {k: tr[int(tid)][k] for k in vals}
        check(got == vals, f"tid {tid}: {vals}")

    print("\nPLAYER LISTS")
    want = walks["player_lists"]
    pl = player_lists.scrape_player_lists(mm)
    check(len(pl) == want["lists"] and pl[0]["offset"] == want["first"],
          f"{want['lists']} lists from {want['first']:,}")
    check({str(l["index"]): len(l["entries"]) for l in pl if l["entries"]} == want["used"],
          f"used entries by list: {want['used']}")
    bogle = pl[63]["entries"][0]
    check({k: bogle[k] for k in fx["scrapbook"]["bogle"]} == fx["scrapbook"]["bogle"],
          "list 63, entry 0: Omar Bogle, Truro, role 24, ST 20")
    kane = next(e for e in pl[62]["entries"] if e["player_tid"] == 6634)
    check({k: kane[k] for k in fx["scrapbook"]["kane"]} == fx["scrapbook"]["kane"],
          "list 62: Harry Kane, caps 121 and 85 goals, U21 14 and 8, right-footed")

    print("\nTHE ARCHIVE")
    want = walks["archive"]
    start, header, _ = A.locate(mm)
    ents = A.directory(mm)[1]
    check((start, header) == (want["members_start"], want["directory_header"]),
          f"members from {start:,}, the directory header at {header:,}")
    check(len(ents) == want["members"], f"{len(ents)} members")
    check(all(len(A.read_member(mm, e)) == e.unpacked for e in ents),
          "every member unpacks to its declared size")
    wf = fixtures.fixtures(mm)
    check(len(wf) == walks["fixtures"], f"{len(wf)} world fixtures")
    truro = [{k: x[k] for k in fx["truro_fixtures"][0]} for x in wf
             if 3125 in (x["home_tid"], x["away_tid"])]
    check(truro == fx["truro_fixtures"], "Truro's three friendlies: 2-0, 3-1, 2-1")
    check(len(comp_rules.competition_rounds(mm)) == walks["competition_rounds"],
          f"{walks['competition_rounds']} competition stage/round rows")

    print()
    if failures:
        print(f"FAILED: {len(failures)}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
