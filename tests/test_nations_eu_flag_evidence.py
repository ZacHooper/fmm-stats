#!/usr/bin/env python3
"""
Evidence for the nations' EU flag (`eu_flag`, fmparser/tables/nations.py), one save of each
game: FMM27 `NATION_INFO_FMM27` +1, FMM22 `NATION_TEAM` +9.

  RAW      England (139) stores 0 and Ireland (163) stores 1, at the byte the declaration
           reads, counted from the record's start (the names' lengths are fixed per game)
  SET      the flagged nations are exactly the list below: the EU 27, the EEA (Iceland,
           Liechtenstein, Norway), Switzerland and the Faroes on both games; FMM27 adds
           France's overseas regions, Gibraltar, Northern Ireland and Bosnia & Herzegovina.
           England, Scotland and Wales are unflagged on both.

    uv run python tests/test_nations_eu_flag_evidence.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.harness import find_save, skip  # noqa: E402

from fmparser.save import Save  # noqa: E402
from fmparser.tables import nations  # noqa: E402

EU27_FMM27 = {
    "Austria", "Belgium", "Bulgaria", "Croatia", "Cyprus", "Czechia", "Denmark", "Estonia",
    "Finland", "France", "Germany", "Greece", "Hungary", "Ireland", "Italy", "Latvia",
    "Lithuania", "Luxembourg", "Malta", "Netherlands", "Poland", "Portugal", "Romania",
    "Slovakia", "Slovenia", "Spain", "Sweden"}
EU27_FMM22 = EU27_FMM27 - {"Czechia", "Netherlands"} | {"Czech Republic", "Holland"}
BOTH = {"Iceland", "Liechtenstein", "Norway", "Switzerland", "Faroe Islands"}
FMM27_ONLY = {"French Guiana", "Guadeloupe", "Martinique", "Mayotte", "Réunion", "St Martin",
              "Gibraltar", "N.Ireland", "Bosnia & Herzegovina"}

# save -> (flagged set, {nation id: (bytes from the record's start, stored byte)})
SAVES = {
    "truro-2026-07-25.fms": (EU27_FMM27 | BOTH | FMM27_ONLY, {139: (44, 0), 163: (42, 1)}),
    "frem-2023-07-02.fms": (EU27_FMM22 | BOTH, {139: (52, 0), 163: (50, 1)}),
}

failures = []


def check(cond, what):
    print(f"  {'ok  ' if cond else 'FAIL'} {what}")
    if not cond:
        failures.append(what)


def main():
    ran = 0
    for name, (want, raw) in SAVES.items():
        path = find_save(name)
        if not path:
            print(f"  (skipped: {name} not found)")
            continue
        ran += 1
        mm = Save(path).mm
        rows = nations.scrape_nations(mm)
        print(f"\n{name}")
        for nid, (delta, byte) in raw.items():
            r = rows[nid]
            check(mm[r["offset"] + delta] == byte and r["eu_flag"] == bool(byte),
                  f"{r['name']}: byte {r['offset'] + delta:,} = {byte}, eu_flag {bool(byte)}")
        got = {r["name"] for r in rows.values() if r["eu_flag"]}
        check(got == want, f"{len(want)} flagged nations"
              + ("" if got == want else f": extra {sorted(got - want)}, missing {sorted(want - got)}"))
        check(not got & {"England", "Scotland", "Wales"}, "England, Scotland, Wales unflagged")
    if not ran:
        return skip("neither truro-2026-07-25.fms nor frem-2023-07-02.fms found")
    print(f"\n{'FAIL' if failures else 'PASS'}: {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
