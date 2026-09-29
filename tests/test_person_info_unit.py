#!/usr/bin/env python3
"""Synthetic unit tests for person info spine (fmparser/tables/person_info.py).

Tests:
1. `PERSON_INFO` record layout, 68-byte head span, field offsets.
2. Constants integrity: `PERSONALITY` (8 attributes), `PERSON_FIELDS`, `DOB_YEAR_LO/HI`.
3. Sentiment and sentinel constants (`NO_CLUB`, `NO_NICKNAME`, `NAME_ID_MAX`).
4. Header frame locating (`locate_person_info`):
   - 8-byte 0xFF sentinel frame + uint32 count
5. Post-processing and record decoding (`_decode_info`):
   - Second nationality ID normalization (0 or 0xFFFF -> None)
   - Club TID bounds normalization (> 0xFFFF -> NO_CLUB)
6. The table walk (`PERSON_INFO_TABLE`): both counted lists, the spine, the span and the
   `tid == slot index` invariant, on a synthetic framed table.
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser.core import DATE, Field, HEX4, PAD, Record, U16, U32, U8
from fmparser.tables import person_info as PI  # noqa: E402


def build_person_info_head_bytes(
    tid: int = 150,
    uid: int = 1001,
    first_name_id: int = 10,
    last_name_id: int = 20,
    common_name_id: int = 0xFFFFFFFF,
    dob_doy: int = 150,
    dob_year: int = 1998,
    nationality_id: int = 42,
    second_nationality_id: int = 0,
    ethnicity: int = 1,
    club_tid: int = 5,
    joined_doy: int = 1,
    joined_year: int = 2020,
    personality: tuple = (15, 14, 16, 12, 10, 18, 14, 11),
    id2: int = 2002,
) -> bytes:
    """Pack a 68-byte PERSON_INFO head record."""
    buf = bytearray(PI.PERSON_INFO.span)
    struct.pack_into("<I", buf, 0, tid)
    struct.pack_into("<I", buf, 4, uid)
    struct.pack_into("<I", buf, 8, first_name_id)
    struct.pack_into("<I", buf, 12, last_name_id)
    struct.pack_into("<I", buf, 16, common_name_id)
    struct.pack_into("<HH", buf, 20, dob_doy, dob_year)
    struct.pack_into("<HH", buf, 24, nationality_id, second_nationality_id)
    struct.pack_into("<B", buf, 28, ethnicity)
    struct.pack_into("<I", buf, 42, club_tid)
    struct.pack_into("<HH", buf, 46, joined_doy, joined_year)

    # 8 personality attributes at +52..+59
    for i, val in enumerate(personality):
        buf[52 + i] = val

    # hex sid at +60..+63, id2 at +64..+67
    buf[60:64] = b"\x12\x34\x56\x78"
    struct.pack_into("<I", buf, 64, id2)

    return bytes(buf)


def test_person_info_schema_and_constants():
    print("TESTING PERSON_INFO schema layout and constants")
    assert PI.PERSON_INFO.span == 68
    assert PI.INFO_HEAD == 68
    assert PI.INFO_LAYOUT is PI.PERSON_INFO

    assert len(PI.PERSONALITY) == 8
    assert PI.PERSONALITY == (
        "adaptability",
        "ambition",
        "determination",
        "loyalty",
        "pressure",
        "professionalism",
        "sportsmanship",
        "temperament",
    )

    for field in PI.PERSONALITY:
        assert field in PI.PERSON_FIELDS

    assert PI.NO_CLUB == 0xFFFF
    assert PI.NAME_ID_MAX == 65536
    assert PI.NO_NICKNAME == b"\xff\xff\xff\xff"
    assert PI.DOB_YEAR_LO == 1955
    assert PI.DOB_YEAR_HI == 2030

    field_map = {f.name: f for f in PI.PERSON_INFO.fields}
    assert field_map["tid"].offset == 0
    assert field_map["uid"].offset == 4
    assert field_map["first_name_id"].offset == 8
    assert field_map["last_name_id"].offset == 12
    assert field_map["dob"].offset == 20
    assert field_map["nationality_id"].offset == 24
    assert field_map["club_tid"].offset == 42
    assert field_map["joined_date"].offset == 46
    assert field_map["adaptability"].offset == 52
    assert field_map["temperament"].offset == 59
    assert field_map["id2"].offset == 64
    print("  PASS schema layout and constants")


def test_person_info_decoding_rules():
    print("TESTING _decode_info field normalization rules")
    # Normal active record
    rec_bytes = build_person_info_head_bytes(
        tid=200,
        uid=5001,
        second_nationality_id=12,
        club_tid=15,
        personality=(18, 17, 16, 15, 14, 13, 12, 11),
    )
    rec = PI._decode_info(rec_bytes, 0)
    assert rec["tid"] == 200
    assert rec["uid"] == 5001
    assert rec["second_nationality_id"] == 12
    assert rec["club_tid"] == 15
    assert rec["adaptability"] == 18
    assert rec["temperament"] == 11

    # Normalization: second_nationality_id == 0 or 0xFFFF -> None
    sec_nat_zero = build_person_info_head_bytes(tid=202, second_nationality_id=0)
    assert PI._decode_info(sec_nat_zero, 0)["second_nationality_id"] is None
    sec_nat_ff = build_person_info_head_bytes(tid=203, second_nationality_id=0xFFFF)
    assert PI._decode_info(sec_nat_ff, 0)["second_nationality_id"] is None

    # Normalization: club_tid > 0xFFFF -> NO_CLUB
    club_overflow = build_person_info_head_bytes(tid=204, club_tid=0x1FFFF)
    assert PI._decode_info(club_overflow, 0)["club_tid"] == PI.NO_CLUB
    print("  PASS _decode_info normalization (nationality, club_tid)")


def build_record(tid, langs=(), rels=(), **head):
    """One whole person record: head, the 17 unnamed bytes, then both counted lists."""
    buf = bytearray(build_person_info_head_bytes(tid=tid, **head))
    buf += b"\xff" * 16 + b"\x00"
    buf += bytes([len(langs)]) + b"".join(struct.pack("<HB", l, v) for l, v in langs)
    buf += struct.pack("<H", len(rels))
    buf += b"".join(struct.pack("<BBIBB", 1, kind, target, 0, 50) for kind, target in rels)
    return bytes(buf)


def framed_table(records, pad=572_000):
    """`[pad][8 x 0xFF][count u32][01][records]`, as the save lays the person table out."""
    return bytearray(b"\x00" * pad + b"\xff" * 8 + struct.pack("<I", len(records)) + b"\x01"
                     + b"".join(records) + b"\xff" * 8)


def locate(buf):
    """locate_person_info on a throwaway buffer: its cache keys on (id, len), and a freed
    test buffer's id is reused by the next one of the same length."""
    PI._PERSON_INFO_CACHE.clear()
    return PI.locate_person_info(buf)


def test_person_info_locator():
    print("TESTING locate_person_info frame detection")
    recs = [build_record(0), build_record(1)]
    base, detected_count = locate(framed_table(recs))
    assert detected_count == 2
    assert base == 572_000 + 8 + 4 + 1, "record 0 follows the 01 header byte"
    # a frame is taken only where the rows start tid 0, 1 (, 2) -- any count, any offset
    assert locate(framed_table(recs, pad=100)) == (100 + 13, 2)
    assert locate(framed_table([build_record(0), build_record(5)])) is None
    decoy = b"\xff" * 8 + struct.pack("<I", 2) + b"\x01" + build_record(3) + build_record(4)
    assert locate(bytearray(decoy) + framed_table(recs, pad=0)) == \
        (len(decoy) + 13, 2), "a frame whose rows are not tid 0, 1 is skipped"
    # no header byte, no table
    no_hdr = framed_table(recs)
    no_hdr[572_000 + 12] = 0
    assert locate(no_hdr) is None
    print("  PASS frame detection and declared count extraction")


def test_person_info_walk():
    print("TESTING PERSON_INFO_TABLE walk")
    recs = [
        build_record(0, langs=[(7, 10)], rels=[(1, 129), (3, 8136)], uid=9),
        build_record(1, uid=10501, first_name_id=3, last_name_id=4, dob_year=2002),
        build_record(2, langs=[(31, 10), (7, 5)], uid=10502),
    ]
    buf = framed_table(recs)
    PI._PERSON_INFO_CACHE.clear()
    rows = PI.PERSON_INFO_TABLE.scrape(buf)
    assert [r["tid"] for r in rows] == [0, 1, 2]
    assert rows[0]["languages"] == [{"language_id": 7, "level": 10}]
    assert rows[0]["relationships"] == [{"target_kind": 1, "target_id": 129},
                                        {"target_kind": 3, "target_id": 8136}]
    assert rows[1]["languages"] == [] and rows[1]["relationships"] == []
    spine = PI.scrape_person_info(buf)
    assert list(spine) == [0, 1, 2] and spine[1]["uid"] == 10501
    assert "languages" not in spine[0], "the spine is the head fields only"
    # the span runs from the 0xFF frame to the end of the last record
    lo = 572_000
    assert PI.person_info_table_spans(buf) == [(lo, lo + 8 + 4 + 1 + sum(map(len, recs)))]
    # tid == slot index: a record out of order ends the walk there
    bad = framed_table(recs + [build_record(7)])
    PI._PERSON_INFO_CACHE.clear()
    assert [r["tid"] for r in PI.PERSON_INFO_TABLE.scrape(bad)] == [0, 1, 2]
    print("  PASS walk, counted lists, spine, span, invariant")


def main():
    test_person_info_schema_and_constants()
    test_person_info_decoding_rules()
    test_person_info_locator()
    test_person_info_walk()
    return 0


if __name__ == "__main__":
    sys.exit(main())
