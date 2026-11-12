#!/usr/bin/env python3
"""
Evidence for `saved_tactics` (`fmparser/tables/saved_tactics.py`, docs/parser/saved_tactics.md).

On every save found among the eight below the tactics are found from the person stamps' end
and every one reads (an ff after each role, a printable NUL-padded name, a flag of 0 or 1);
a career's first save holds one. On truro-2026-08-08 there is a tactic named after the
formation every match report of ours carries, 4-1-2-1-2, and its back four reads Full-Back,
Full-Back, Central Defender, Central Defender (3, 3, 5, 5) for the DR, DL, DC, DC the
match reports list first. On frem-2026-06-11 the FMM22 codes, read through
seeds/roles.csv, give its 4-1-4-1 as Full-Back x2, Central Defender x2, Defensive
Midfielder, Wide Midfielder, Winger, Roaming Playmaker, Box to Box Midfielder, Target
Forward.

    uv run python tests/test_saved_tactics_evidence.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.harness import find_save, skip  # noqa: E402

from fmparser.save import Save  # noqa: E402
from fmparser.tables import matches as MT, scrape_saved_tactics  # noqa: E402

SAVES = ["frem-2021-06-27.fms", "frem-2023-07-02.fms", "frem-2026-06-11.fms",
         "frem-2030-06-22.fms", "bucaspor-2023-04-01.fms", "truro-2026-07-22.fms",
         "truro-2026-07-25.fms", "truro-2026-08-08.fms"]
COUNTS = {"frem-2021-06-27.fms": 1, "frem-2026-06-11.fms": 30, "bucaspor-2023-04-01.fms": 12,
          "truro-2026-07-22.fms": 1, "truro-2026-08-08.fms": 15}

failures = []


def check(cond, what):
    print(f"  {'ok  ' if cond else 'FAIL'} {what}")
    if not cond:
        failures.append(what)


def check_save(name):
    path = find_save(name)
    if not path:
        return False
    mm = Save(path).mm
    print(f"\n{name}")
    rows = scrape_saved_tactics(mm)
    check(len(rows) == COUNTS.get(name, len(rows)), f"{len(rows)} saved tactics")
    check(all(r["gk_role"] == 0 and len(r["roles"]) == 10 for r in rows),
          "every tactic: goalkeeper role 0, ten outfield roles")
    if name == "truro-2026-08-08.fms":
        formations = {m["formation"] for m in MT.scrape_matches(mm)}
        named = [r for r in rows if r["name"] in formations]
        check(formations == {"4-1-2-1-2"} and len(named) == 1, "a tactic named 4-1-2-1-2, our match formation")
        check(named and named[0]["roles"][:4] == [3, 3, 5, 5], "its back four: Full-Back x2, Central Defender x2")
    if name == "frem-2026-06-11.fms":
        t = [r for r in rows if r["name"] == "4-1-4-1"]
        check(t and t[0]["roles"] == [3, 3, 5, 5, 30, 8, 9, 32, 16, 19],
              "4-1-4-1: FB, FB, CD, CD, DM, Wide Midfielder, Winger, Roaming Playmaker, BBM, Target Forward")
    return True


def main():
    ran = [check_save(n) for n in SAVES]
    if not any(ran):
        return skip("none of the saved tactics evidence saves found")
    print(f"\n{'FAIL' if failures else 'PASS'}: {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
