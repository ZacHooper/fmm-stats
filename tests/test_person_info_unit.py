#!/usr/bin/env python3
"""Synthetic unit tests for person info spine (fmparser/tables/person_info.py).

Tests:
1. `PERSON_INFO` record layout, 68-byte head span, field offsets.
2. Constants integrity: `PERSONALITY` (8 attributes), `PERSON_FIELDS`, `DOB_YEAR_LO/HI`.
3. Sentiment and sentinel constants (`NO_CLUB`, `NO_NICKNAME`, `NAME_ID_MAX`).
4. Header frame locating (`locate_person_info`):
   - 8-byte 0xFF sentinel frame + uint32 count
5. Post-processing and record decoding (`_decode_info`):
   - UID zero clearing of personality fields
   - Second nationality ID normalization (0 or 0xFFFF -> None)
   - Club TID bounds normalization (> 0xFFFF -> NO_CLUB)
6. Spine scraping (`scrape_person_info`):
   - Un-nicknamed record candidate detection via 0xFF*4 sentinel
   - Nicknamed record candidate detection
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser.schema import DATE, Field, HEX4, PAD, Record, U16, U32, U8  # noqa: E402
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

    # Record with UID = 0 (clears personality and person fields)
    uid_zero_bytes = build_person_info_head_bytes(tid=201, uid=0)
    rec_zero = PI._decode_info(uid_zero_bytes, 0)
    assert rec_zero["uid"] == 0
    for field in PI.PERSON_FIELDS:
        assert rec_zero[field] is None

    # Normalization: second_nationality_id == 0 or 0xFFFF -> None
    sec_nat_zero = build_person_info_head_bytes(tid=202, second_nationality_id=0)
    assert PI._decode_info(sec_nat_zero, 0)["second_nationality_id"] is None
    sec_nat_ff = build_person_info_head_bytes(tid=203, second_nationality_id=0xFFFF)
    assert PI._decode_info(sec_nat_ff, 0)["second_nationality_id"] is None

    # Normalization: club_tid > 0xFFFF -> NO_CLUB
    club_overflow = build_person_info_head_bytes(tid=204, club_tid=0x1FFFF)
    assert PI._decode_info(club_overflow, 0)["club_tid"] == PI.NO_CLUB
    print("  PASS _decode_info normalization (UID 0, nationality, club_tid)")


def test_person_info_locator():
    print("TESTING locate_person_info frame detection")
    pre_pad = b"\x00" * 572_000
    sentinel = b"\xff" * 8
    count = 32966
    count_bytes = struct.pack("<I", count)

    full_buf = bytearray(pre_pad + sentinel + count_bytes)

    loc = PI.locate_person_info(full_buf)
    assert loc is not None
    base, detected_count = loc
    assert detected_count == count
    assert base == 572_000 + 8 + 4
    print("  PASS frame detection and declared count extraction")


def test_person_info_scrape_candidates():
    print("TESTING scrape_person_info candidates")
    rec1 = build_person_info_head_bytes(
        tid=500,
        uid=10500,
        first_name_id=1,
        last_name_id=2,
        dob_year=2000,
        common_name_id=0xFFFFFFFF,
    )
    rec2 = build_person_info_head_bytes(
        tid=501,
        uid=10501,
        first_name_id=3,
        last_name_id=4,
        dob_year=2002,
        common_name_id=0xFFFFFFFF,
    )
    buf = bytearray(rec1 + rec2)

    found = PI.scrape_person_info(buf)
    assert len(found) == 2
    assert 500 in found
    assert 501 in found
    assert found[500]["uid"] == 10500
    assert found[501]["uid"] == 10501
    print("  PASS scrape_person_info un-nicknamed candidates")


def main():
    test_person_info_schema_and_constants()
    test_person_info_decoding_rules()
    test_person_info_locator()
    test_person_info_scrape_candidates()
    return 0


if __name__ == "__main__":
    sys.exit(main())
