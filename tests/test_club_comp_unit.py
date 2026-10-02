#!/usr/bin/env python3
"""Synthetic unit tests for the club and competition tables (fmparser/tables/clubs.py,
competitions.py), no save needed. Each table is pointed at an in-memory buffer by swapping
its locator; everything else is the table's own declaration.

  COMP   a named slot, one with a reference list, and a blank slot (empty names, FF name-end)
  CLUB   the trailer's counted lists (affiliates, squad, the 9-byte tail), a national team's
         negative uid, league membership, and the whole record of a row
  WALK   a slot out of order ends the walk there
"""
import dataclasses
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser.tables import clubs as CL, competitions as CO  # noqa: E402


def pstr(s: str, end: bytes = b"") -> bytes:
    b = s.encode("utf-8")
    return struct.pack("<I", len(b)) + b + end


def comp_slot(cid, uid, name="Test Comp", short="TC", code="TC", typ=0, nation=1,
              reputation=150, level=1, parent_cid=0xFFFF, refs=()) -> bytes:
    end = b"\x00" if name else b"\xff"                  # NAME_END: FF after an empty name
    return (struct.pack("<HI", cid, uid) + pstr(name, end) + pstr(short, end) + pstr(code)
            + struct.pack("<BHHHHHBH", typ, 1, nation, 0, 0, reputation, level, parent_cid)
            + struct.pack("<I", len(refs))
            + b"".join(struct.pack("<IHBB", r, s, o, 0) for r, s, o in refs)
            + b"\x00" * 12 + struct.pack("<HHH", 2024, 2025, 2026) + b"\x00" * 3)


def club_slot(tid, uid, name="Test FC", short="TFC", code="TFC", country=42, league_code=2,
              marker=True, affiliates=(), squad=(), staff=(), main=0, tail=0) -> bytes:
    fixed = bytearray(167)
    struct.pack_into("<HH", fixed, 0, country, country)
    struct.pack_into("<H", fixed, 158, league_code)
    struct.pack_into("<H", fixed, 160, 0xFFFF if marker else 7)
    slots = list(squad) + [0xFFFFFFFF] * (40 - len(squad))
    staff_block = bytearray(123)
    for i in range(11):
        struct.pack_into("<I", staff_block, 4 * i, staff[i] if i < len(staff) else 0xFFFFFFFF)
    struct.pack_into("<IB", staff_block, 44, main, 1)
    return (struct.pack("<Ii", tid, uid) + pstr(name, b"\x00") + pstr(short, b"\x00")
            + pstr(code) + bytes(fixed)
            + struct.pack("<I", 8) + b"\xff" * 7 + b"\x00"
            + bytes([3]) + struct.pack("<H", 500) + b"\x00" * 20
            + struct.pack("<H", len(affiliates))
            + b"".join(struct.pack("<IIIHHHHB", 0, a, b, 1, 2020, 1, 2021, 0)
                       for a, b in affiliates)
            + struct.pack("<H", 40) + b"".join(struct.pack("<I", t) for t in slots)
            + bytes(staff_block)
            + struct.pack("<H", tail) + b"\x00" * (9 * tail))


def over(table, buf, n):
    """The table, pointed at `buf` from offset 0 for `n` rows."""
    return dataclasses.replace(table, locator=lambda mm: (0, n))


def test_comp():
    print("TESTING competition rows")
    rows_b = [comp_slot(0, 200_000_000, "3F Superliga", "Superliga", "SL"),
              comp_slot(1, 200_000_001, "Copa", "Copa", "CP",
                        refs=((1913, 2022, 1), (0xFFFFFFFF, 0, 0))),
              comp_slot(2, 2_000_000_001, "", "", "")]
    buf = b"".join(rows_b)
    rows = over(CO.COMP_TABLE, buf, 3).scrape(buf)
    assert [r["cid"] for r in rows] == [0, 1, 2]
    assert CO._comp(rows[0]) == {"cid": 0, "uid": 200_000_000, "name": "3F Superliga",
                                 "short": "Superliga", "code": "SL", "type": "league",
                                 "type_id": 0, "nation_id": 1, "reputation": 150,
                                 "level": 1, "parent_cid": None}
    assert rows[1]["refs"] == [{"ref": 1913, "season": 2022, "ordinal": 1},
                               {"ref": 0xFFFFFFFF, "season": 0, "ordinal": 0}]
    assert rows[2]["name"] == "" and rows[2]["refs"] == []
    assert over(CO.COMP_TABLE, buf, 3).spans(buf) == [(0, len(buf))]
    print("  PASS named, with refs, and blank slots")


def test_club():
    print("TESTING club rows")
    rows_b = [club_slot(0, -961, "Argentina", "Argentina", "ARG", league_code=0),
              club_slot(1, 10001, "Arsenal", "ARS", country=1, league_code=10,
                        affiliates=((1, 7),), squad=(5, 6), staff=(9,), main=0, tail=2),
              club_slot(2, 10002, "Reserves", "RES", marker=False, main=1)]
    buf = b"".join(rows_b)
    rows = over(CL.CLUB_TABLE, buf, 3).scrape(buf)
    assert [r["tid"] for r in rows] == [0, 1, 2]
    assert rows[0]["uid"] == -961 and CL._club(rows[0])["league_cid"] is None
    d = CL._club(rows[1])
    assert {k: d[k] for k in ("tid", "uid", "name", "short", "league_cid", "country")} == {
        "tid": 1, "uid": 10001, "name": "Arsenal", "short": "ARS", "league_cid": 10,
        "country": 1}
    assert CL._club(rows[2])["league_cid"] is None, "no FFFF marker: not a league member"
    assert d["affiliates"] == [{"club1_tid": 1, "club2_tid": 7, "start_day": 1,
                                "start_year": 2020, "end_day": 1, "end_year": 2021}]
    assert d["squad"] == [5, 6] and d["staff"] == [9]
    assert d["league_pos"] == 3 and d["reputation"] == 500
    assert CL._club(rows[2])["main_club_tid"] == 1
    assert len(rows_b[1]) - len(rows_b[0]) == len("Arsenal") - len("Argentina") \
        + len("ARS") - len("Argentina") + 21 + 2 * 9, "affiliates and tail sized by count"
    print("  PASS national team, league membership, counted lists, the whole record")


def test_walk_stops():
    print("TESTING a slot out of order ends the walk")
    buf = comp_slot(0, 1, "A", "A", "A") + comp_slot(99, 2, "B", "B", "B")
    assert [r["cid"] for r in over(CO.COMP_TABLE, buf, 2).scrape(buf)] == [0]
    buf = club_slot(0, 1, "C0", "C0") + club_slot(42, 2, "C1", "C1")
    assert [r["tid"] for r in over(CL.CLUB_TABLE, buf, 2).scrape(buf)] == [0]
    print("  PASS")


def main():
    test_comp()
    test_club()
    test_walk_stops()
    return 0


if __name__ == "__main__":
    sys.exit(main())
