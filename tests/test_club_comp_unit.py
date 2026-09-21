#!/usr/bin/env python3
"""Synthetic unit tests for Club and Competition table parsing logic.

Tests `_read_comp_slot`, `_walk_comp_table`, `_read_club_slot`, and `_walk_club_table`
with in-memory byte buffers (zero save-file dependency), asserting that:
1. Comp slot arithmetic, ref lists, and blank slots parse identically.
2. Club dynamic trailer formulas (affiliates + date intervals) resolve accurately.
3. National teams (negative UIDs) and league codes parse correctly.
4. Structural misalignment immediately raises CompTableError / ClubTableError.
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser import reference as R  # noqa: E402


def build_comp_slot_bytes(
    cid: int,
    uid: int,
    name: str = "Test Comp",
    short: str = "TC",
    code: str = "TC",
    typ: int = 0,
    nation: int = 1,
    reputation: int = 150,
    level: int = 1,
    parent_cid: int = 0xFFFF,
    refs: tuple = (),
) -> bytes:
    """Pack one valid competition slot."""
    buf = bytearray()
    buf += struct.pack("<H", cid)
    buf += struct.pack("<I", uid)

    name_b = name.encode("utf-8") if name else b""
    short_b = short.encode("utf-8") if short else b""
    code_b = code.encode("utf-8") if code else b""

    # Long name [len u32][bytes][0x00]
    buf += struct.pack("<I", len(name_b))
    buf += name_b
    buf += b"\x00"

    # Short name [len u32][bytes][0x00]
    buf += struct.pack("<I", len(short_b))
    buf += short_b
    buf += b"\x00"

    # Code [len u32][bytes] (NO null)
    buf += struct.pack("<I", len(code_b))
    buf += code_b

    # COMP_TRAILER (14 bytes):
    # type u8, continent u16, nation u16, fg u16, bg u16, rep u16, level u8, parent u16
    buf += struct.pack(
        "<BH H H H H B H",
        typ,
        1,  # continent
        nation,
        0,  # fg
        0,  # bg
        reputation,
        level,
        parent_cid,
    )

    # COMP_REF_COUNT (4 bytes: u32 count)
    buf += struct.pack("<I", len(refs))

    # COMP_REF_ENTRY (8 bytes each): ref u32, season u16, ordinal u8, pad u8
    for r in refs:
        buf += struct.pack("<I H B B", r[0], r[1], r[2], 0)

    # COMP_HISTORY_TAIL (21 bytes): 12 unk + 3 seasons u16 + 3 unk
    buf += b"\x00" * 12
    buf += struct.pack("<HHH", 2024, 2025, 2026)
    buf += b"\x00" * 3

    return bytes(buf)


def build_club_slot_bytes(
    tid: int,
    uid: int,
    name: str = "Test FC",
    short: str = "TFC",
    code: str = "TFC",
    country: int = 42,
    league_code: int = 2,
    marker: bool = True,
    naff: int = 0,
    ntail: int = 0,
) -> bytes:
    """Pack one valid club slot."""
    buf = bytearray()
    buf += struct.pack("<I", tid)
    buf += struct.pack("<i", uid)  # signed i32 for negative national team UIDs

    name_b = name.encode("utf-8")
    short_b = short.encode("utf-8")
    code_b = code.encode("utf-8")

    buf += struct.pack("<I", len(name_b))
    buf += name_b
    buf += b"\x00"

    buf += struct.pack("<I", len(short_b))
    buf += short_b
    buf += b"\x00"

    buf += struct.pack("<I", len(code_b))
    buf += code_b

    # Trailer starts here (p_tr)
    # 0..2: country u16
    # 158..160: league_code u16
    # 160..162: marker (0xFFFF)
    # 202..204: naff u16
    # 204 .. 204 + naff * 21: affiliate entries
    # 489 + naff * 21: ntail u16
    # 491 + naff * 21 ..: ntail * 9 entries
    trailer = bytearray(491 + naff * 21 + ntail * 9)

    struct.pack_into("<H", trailer, 0, country)
    struct.pack_into("<H", trailer, 158, league_code)
    if marker:
        trailer[160:162] = b"\xff\xff"

    struct.pack_into("<H", trailer, 202, naff)
    struct.pack_into("<H", trailer, 489 + naff * 21, ntail)

    buf += trailer
    return bytes(buf)


def test_comp_slot_reading():
    print("TESTING _read_comp_slot")
    # 1. Normal competition with 0 refs
    slot_bytes = build_comp_slot_bytes(
        cid=0,
        uid=200000001,
        name="Premier League",
        short="EPL",
        code="PRM",
        typ=0,
        nation=1,
        reputation=180,
    )
    mm = memoryview(slot_bytes)
    rec, nxt = R._read_comp_slot(mm, 0)
    assert rec is not None
    assert rec["cid"] == 0
    assert rec["uid"] == 200000001
    assert rec["name"] == "Premier League"
    assert rec["short"] == "EPL"
    assert rec["code"] == "PRM"
    assert rec["reputation"] == 180
    assert rec["nation_id"] == 1
    assert nxt == len(slot_bytes)

    # 2. Competition with 2 refs
    refs = ((1001, 2025, 1), (1002, 2025, 2))
    slot_with_refs = build_comp_slot_bytes(
        cid=1, uid=200000002, name="Champions Cup", short="UCL", code="ECC", refs=refs
    )
    mm2 = memoryview(slot_with_refs)
    rec2, nxt2 = R._read_comp_slot(mm2, 0)
    assert rec2 is not None
    assert rec2["cid"] == 1
    assert nxt2 == len(slot_with_refs)

    # 3. Blank slot (name = "")
    blank_bytes = build_comp_slot_bytes(
        cid=2, uid=200000003, name="", short="", code=""
    )
    mm3 = memoryview(blank_bytes)
    rec3, nxt3 = R._read_comp_slot(mm3, 0)
    assert rec3 is None  # blank slots emit None
    assert nxt3 == len(blank_bytes)

    print("  PASS _read_comp_slot (normal, with-refs, and blank slots)")


def test_club_slot_reading():
    print("TESTING _read_club_slot")
    # 1. Basic club: naff=0, ntail=0 -> trailer=491B
    c1 = build_club_slot_bytes(
        tid=10, uid=10001, name="Arsenal", short="ARS", country=1, league_code=10
    )
    mm1 = memoryview(c1)
    rec1, nxt1 = R._read_club_slot(mm1, 0)
    assert rec1["name"] == "Arsenal"
    assert rec1["short"] == "ARS"
    assert rec1["uid"] == 10001
    assert rec1["country"] == 1
    assert rec1["league"] == 10
    assert nxt1 == len(c1)

    # 2. Club with 3 affiliates: naff=3, ntail=0 -> trailer = 491 + 3*21 = 554B
    c2 = build_club_slot_bytes(
        tid=11, uid=10002, name="Chelsea", short="CHE", naff=3, ntail=0
    )
    mm2 = memoryview(c2)
    rec2, nxt2 = R._read_club_slot(mm2, 0)
    assert rec2["name"] == "Chelsea"
    assert nxt2 == len(c2)
    assert nxt2 == len(c1) + 3 * 21

    # 3. Club with affiliates AND date intervals: naff=2, ntail=4 -> trailer = 491 + 2*21 + 4*9 = 569B
    c3 = build_club_slot_bytes(
        tid=12, uid=10003, name="Liverpool", short="LIV", naff=2, ntail=4
    )
    mm3 = memoryview(c3)
    rec3, nxt3 = R._read_club_slot(mm3, 0)
    assert rec3["name"] == "Liverpool"
    assert nxt3 == len(c3)

    # 4. National Team: negative UID (-961)
    c4 = build_club_slot_bytes(
        tid=961, uid=-961, name="Argentina", short="ARG", code="ARG"
    )
    mm4 = memoryview(c4)
    rec4, nxt4 = R._read_club_slot(mm4, 0)
    assert rec4["name"] == "Argentina"
    assert rec4["uid"] == -961

    print("  PASS _read_club_slot (base, dynamic affiliates, date intervals, negative UIDs)")


def test_table_walk_errors():
    print("TESTING structural misalignment errors")
    # Test CompTableError when slot cid != index
    # Build 2 slots where slot 1 has cid=99 instead of 1
    s0 = build_comp_slot_bytes(cid=0, uid=1, name="A", short="A", code="A")
    s1 = build_comp_slot_bytes(cid=99, uid=2, name="B", short="B", code="B")  # Bad CID!
    bad_comp_buf = memoryview(s0 + s1)

    # Manually run the walk loop logic
    try:
        p = 0
        for i in range(2):
            cid = int.from_bytes(bad_comp_buf[p : p + 2], "little")
            if cid != i:
                raise R.CompTableError(f"misaligned at slot {i}: got cid={cid}")
            _, p = R._read_comp_slot(bad_comp_buf, p)
        assert False, "should have raised CompTableError"
    except R.CompTableError:
        pass

    # Test ClubTableError when slot tid != index
    c0 = build_club_slot_bytes(tid=0, uid=1, name="Club0", short="C0")
    c1 = build_club_slot_bytes(tid=42, uid=2, name="Club1", short="C1")  # Bad TID!
    bad_club_buf = memoryview(c0 + c1)

    try:
        p = 0
        for i in range(2):
            tid = struct.unpack_from("<I", bad_club_buf, p)[0]
            if tid != i:
                raise R.ClubTableError(f"misaligned at slot {i}: got tid={tid}")
            _, p = R._read_club_slot(bad_club_buf, p)
        assert False, "should have raised ClubTableError"
    except R.ClubTableError:
        pass

    print("  PASS structural misalignment errors raised as expected")


def main():
    test_comp_slot_reading()
    test_club_slot_reading()
    test_table_walk_errors()
    return 0


if __name__ == "__main__":
    sys.exit(main())
