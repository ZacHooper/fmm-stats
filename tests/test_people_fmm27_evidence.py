#!/usr/bin/env python3
"""
Evidence for the FMM27 person table: what the game shows, the bytes behind it, and what the
parser makes of them, on truro-2026-07-25.

`tests/fixtures/people_fmm27_evidence.json` holds values read off in-game screens (the
screenshots are docs/parser/img/person_info-fmm27-*.jpg, mapped in docs/parser/person_info.md).
For each: the raw bytes at the recorded offset are what the doc says, and the parsed field
equals the value on screen. The first catches a different save; the second a parser change
that reads the right bytes into the wrong field.

    uv run python tests/test_people_fmm27_evidence.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.harness import find_save, skip  # noqa: E402

from fmparser.save import Save  # noqa: E402
from fmparser.tables import names, person_info  # noqa: E402
from fmparser.tables.save_header import FMM27, save_format  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "people_fmm27_evidence.json")

failures = []


def check(cond, what):
    print(f"  {'ok  ' if cond else 'FAIL'} {what}")
    if not cond:
        failures.append(what)


def levels(entries):
    return {str(e["language_id"]): e["level"] for e in entries}


def main():
    fx = json.load(open(FIXTURE, encoding="utf-8"))
    path = find_save(fx["save"])
    if not path:
        return skip(f"{fx['save']} not found (fetch it with rclone, or rebuild.py)")
    mm = Save(path).mm

    print("FORMAT")
    check(save_format(mm) == FMM27, f"{fx['save']} declares fmm27")
    table = person_info.person_table(mm)
    check(table is person_info.PERSON_INFO_TABLE_FMM27, "person_table picks the FMM27 declaration")

    print("\nRAW BYTES at the recorded offsets")
    for off, hexstr, what in fx["raw"]:
        want = bytes.fromhex("".join(hexstr.split()))
        check(bytes(mm[off:off + len(want)]) == want, f"@{off} {what}")

    print("\nTHE WALK")
    rows = {r["tid"]: r for r in table.scrape(mm)}
    check(len(rows) == fx["count"], f"{len(rows):,} of {fx['count']:,} records, tid == slot")
    spine = person_info.scrape_person_info(mm)
    check(len(spine) == fx["count"], "persons.json spine has every person")

    print("\nPERSON_INFO (Player Profile, Player Personal)")
    browse = names.walk_browse(mm)
    ids = {k: {r["id"]: r["ordinal"] for r in v} for k, v in names.scrape_name_ids(mm).items()}
    for tid, want in fx["persons"].items():
        row, out = rows[int(tid)], spine[int(tid)]
        first, last = (browse[ids[t][row[k]]] for t, k in
                       (("first_names", "first_name_id"), ("surnames", "last_name_id")))
        check(f"{first} {last}" == want["name"], f"tid {tid} is {want['name']}")
        for k, v in want.items():
            if k == "name":
                continue
            if k in ("default_languages", "other_languages"):
                got = levels(row[k])
            elif k == "relationships":
                got = len(row[k])
            else:
                got = out[k]
            check(got == v, f"{want['name']}: {k} = {v!r}" + ("" if got == v else f" (got {got!r})"))

    print()
    if failures:
        print(f"FAIL: {len(failures)} check(s)")
        return 1
    print("PASS: FMM27 person evidence")
    return 0


if __name__ == "__main__":
    sys.exit(main())
