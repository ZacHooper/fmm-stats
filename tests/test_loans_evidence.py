#!/usr/bin/env python3
"""
Evidence for the loan pool (`fmparser/tables/loans.py`, docs/parser/loans.md).

On every save found among the eight below: the pool is found, its capacity is the game's
(6,243 on FMM22, 6,637 on FMM27), every person with a `loan_slot` finds his own tid in it,
and every other slot is the fixed empty pattern. On frem-2026-06-11 it is checked against
the player progress table, which the parser already reads and the store builds loan spells
from: the 11 Frem players progress marks as out on loan are exactly the loans out of Frem
and its reserves, and the four slots whose club is Frem are players loaned in, from other
clubs. Slot 0's bytes and values are pinned on one save of each game.

    uv run python tests/test_loans_evidence.py
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.harness import find_save, skip  # noqa: E402

from fmparser.save import Save  # noqa: E402
from fmparser.tables import (loans, person_index, scrape_player_progress,  # noqa: E402
                             tables_for)
from fmparser.tables.person_info import scrape_person_info  # noqa: E402
from fmparser.tables.save_header import FMM27, save_format  # noqa: E402

SAVES = ["frem-2021-06-27.fms", "frem-2023-07-02.fms", "frem-2026-06-11.fms",
         "frem-2030-06-22.fms", "bucaspor-2023-04-01.fms", "truro-2026-07-22.fms",
         "truro-2026-07-25.fms", "truro-2026-08-08.fms"]
USED = {"frem-2021-06-27.fms": 1962, "frem-2026-06-11.fms": 2312, "truro-2026-08-08.fms": 3010}
SLOT0 = {
    "frem-2026-06-11.fms": ("2f 28 00 00 58 01 b3 00 e9 07 b3 00 ea 07 64 01 00 00 00 00 00 00 00 00 00",
                            {"slot": 0, "tid": 10287, "club_tid": 344, "start": "2025-06-29",
                             "end": "2026-06-29", "pct": 100, "option": 0}),
    "truro-2026-08-08.fms": ("aa 02 00 00 4f 01 c7 00 ea 07 96 00 eb 07 64 01 00 ff ff ff ff ff ff ff ff",
                             {"slot": 0, "tid": 682, "club_tid": 335, "start": "2026-07-19",
                              "end": "2027-05-31", "pct": 100, "option": 0}),
}
FREM, FREM_RESERVES = 346, 7296

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
    v27 = save_format(mm) == FMM27
    print(f"\n{name}")
    loc = loans.locate_loans(mm)
    check(loc is not None, "the pool is found")
    if loc is None:
        return True
    base, cap = loc
    check(cap == (6637 if v27 else 6243), f"capacity {cap:,}")
    rows = loans.scrape_loans(mm)
    links = {t: r["loan_slot"] for t, r in enumerate(person_index.scrape_person_index(mm))
             if r["loan_slot"] != 0xFFFF}
    check(len(rows) == len(links), f"{len(rows):,} loans, one per person with a loan_slot")
    check(all(links.get(r["tid"]) == r["slot"] for r in rows), "every loan's person points at its slot")
    empty = sum(mm[base + s * 25:base + s * 25 + 25] == loans.EMPTY for s in range(cap))
    check(empty == cap - len(rows), f"the other {cap - len(rows):,} slots are the empty pattern")
    if name in USED:
        check(len(rows) == USED[name], f"{USED[name]:,} loans")
    clubs = {c["tid"] for c in tables_for(mm)["clubs"].scrape(mm)}
    check(all(r["club_tid"] in clubs for r in rows), "every loan club is a club")
    persons = scrape_person_info(mm)
    check(all(persons[r["tid"]]["club_tid"] != r["club_tid"] for r in rows),
          "no player is on loan at his own club")
    if name in SLOT0:
        hexstr, want = SLOT0[name]
        check(bytes(mm[base:base + 25]) == bytes.fromhex(hexstr.replace(" ", "")), "slot 0 bytes")
        check(rows[0] == want, f"slot 0 reads {want}")
    if name == "frem-2026-06-11.fms":
        latest = {}
        for r in scrape_player_progress(mm):
            if r["tid"] not in latest or str(r["week"]) > str(latest[r["tid"]]["week"]):
                latest[r["tid"]] = r
        marked = {t for t, r in latest.items() if r["status"] & 32}
        out = {r["tid"] for r in rows if persons[r["tid"]]["club_tid"] in (FREM, FREM_RESERVES)}
        check(len(marked) == 11 and marked == out & set(latest),
              f"progress marks {len(marked)} Frem players on loan: exactly the loans out of Frem")
        loaned_in = [r for r in rows if r["club_tid"] == FREM]
        check(len(loaned_in) == 4 and all(persons[r["tid"]]["club_tid"] not in (FREM, FREM_RESERVES)
                                          for r in loaned_in),
              "four loans into Frem, every one from another club")
    return True


def main():
    ran = [check_save(n) for n in SAVES]
    if not any(ran):
        return skip("none of the loan evidence saves found")
    print(f"\n{'FAIL' if failures else 'PASS'}: {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
