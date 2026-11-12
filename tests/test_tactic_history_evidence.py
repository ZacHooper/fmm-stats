#!/usr/bin/env python3
"""
Evidence for `tactic_history` (`fmparser/tables/tactic_history.py`, docs/parser/tactic_history.md).

On every save found among the eight below the records are found from the person stamps' end
and every one reads (an ff after each role, a printable NUL-padded name, a flag of 0 or 1).
On truro-2026-07-22 and -25 the last record is, slot for slot, the Tactics - Formation
screen (SCREEN below), which pins FMM27's role codes. They grow as a career is played (1, 5, 15 on Truro's three saves) and stop at 30 (both late
Frem saves). On truro-2026-08-08 the last record is named after the formation every match
report of ours carries, 4-1-2-1-2, and its back four reads Full-Back, Full-Back, Central
Defender, Central Defender (3, 3, 5, 5) for the DR, DL, DC, DC the reports list first. On
frem-2026-06-11 the FMM22 codes, read through seeds/roles.csv, give its "4-1-4-1" as
Full-Back x2, Central Defender x2, Defensive Midfielder, Wide Midfielder, Winger, Roaming
Playmaker, Box to Box Midfielder, Target Forward.

    uv run python tests/test_tactic_history_evidence.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.harness import find_save, skip  # noqa: E402

from fmparser.save import Save  # noqa: E402
from fmparser.tables import matches as MT, scrape_tactic_history  # noqa: E402

SAVES = ["frem-2021-06-27.fms", "frem-2023-07-02.fms", "frem-2026-06-11.fms",
         "frem-2030-06-22.fms", "bucaspor-2023-04-01.fms", "truro-2026-07-22.fms",
         "truro-2026-07-25.fms", "truro-2026-08-08.fms"]
COUNTS = {"frem-2021-06-27.fms": 1, "frem-2026-06-11.fms": 30, "frem-2030-06-22.fms": 30,
          "bucaspor-2023-04-01.fms": 12, "truro-2026-07-22.fms": 1, "truro-2026-07-25.fms": 5,
          "truro-2026-08-08.fms": 15}

# The Tactics - Formation screen on each save, its Squad list after the GK
# (docs/parser/img/tactic_history-fmm27-5.jpg and -1.jpg): CD CD CD WB WB BWM AP AP P TF,
# and WB WB CD CD BWM CM CM AP PF AF.
SCREEN = {"truro-2026-07-22.fms": ("5-2-1-2", [5, 5, 5, 4, 4, 16, 18, 18, 19, 20]),
          "truro-2026-07-25.fms": ("4-1-2-1-2", [4, 4, 5, 5, 16, 14, 14, 18, 24, 22])}

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
    rows = scrape_tactic_history(mm)
    check(len(rows) == COUNTS.get(name, len(rows)), f"{len(rows)} tactic history")
    check(all(r["gk_role"] == 0 and len(r["roles"]) == 10 for r in rows),
          "every tactic: goalkeeper role 0, ten outfield roles")
    if name == "truro-2026-08-08.fms":
        formations = {m["formation"] for m in MT.scrape_matches(mm)}
        check(formations == {"4-1-2-1-2"} and rows[-1]["name"] == "4-1-2-1-2",
              "the last record is 4-1-2-1-2, our match formation")
        check(rows[-1]["roles"][:4] == [3, 3, 5, 5], "its back four: Full-Back x2, Central Defender x2")
    if name in SCREEN:
        check(rows[-1]["name"] == SCREEN[name][0] and rows[-1]["roles"] == SCREEN[name][1],
              f"last record = the Formation screen: {SCREEN[name][0]} {SCREEN[name][1]}")
    if name == "frem-2026-06-11.fms":
        t = [r for r in rows if r["name"] == "4-1-4-1"]
        check(t and t[0]["roles"] == [3, 3, 5, 5, 30, 8, 9, 32, 16, 19],
              "4-1-4-1: FB, FB, CD, CD, DM, Wide Midfielder, Winger, Roaming Playmaker, BBM, Target Forward")
    return True


def main():
    ran = [check_save(n) for n in SAVES]
    if not any(ran):
        return skip("none of the tactic history evidence saves found")
    print(f"\n{'FAIL' if failures else 'PASS'}: {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
