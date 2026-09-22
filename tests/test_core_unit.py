#!/usr/bin/env python3
"""Comprehensive unit tests for fmparser.core primitives, types, schema, and table engine."""
import os
import struct
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser.core import (
    DATE,
    F32,
    HEX4,
    PAD,
    RAW,
    U8,
    U16,
    U32,
    UNKNOWN,
    Field,
    PString,
    Record,
    Table,
    f32,
    find_framed_count,
    hex2,
    hex4,
    i16,
    i32,
    table_spans,
    tag4,
    tag4_to_disk,
    u8,
    u16,
    u16_or_none,
    u32,
    validate,
    walk_table,
    ymd,
    ymd_from,
)


# ==============================================================================
# 1. Primitives Unit Tests
# ==============================================================================

def test_primitives_integers():
    buf = struct.pack("<BbHhIi", 250, -10, 65000, -32000, 4000000000, -2000000000)
    assert u8(buf, 0) == 250
    assert u16(buf, 2) == 65000
    assert i16(buf, 4) == -32000
    assert u32(buf, 6) == 4000000000
    assert i32(buf, 10) == -2000000000

    # Bounds check
    assert u16_or_none(buf, 0) == struct.unpack_from("<H", buf, 0)[0]
    assert u16_or_none(buf, len(buf)) is None
    assert u16_or_none(buf, len(buf) - 1) is None


def test_primitives_floats():
    buf = struct.pack("<ff", 3.1415927, -42.5)
    assert abs(f32(buf, 0) - 3.1415927) < 1e-6
    assert abs(f32(buf, 4) - (-42.5)) < 1e-6


def test_primitives_hex():
    buf = b"\xde\xad\xbe\xef\x01\x02"
    assert hex4(buf, 0) == "deadbeef"
    assert hex2(buf, 4) == "0102"


def test_primitives_dates():
    # day 58 of 2026 = 2026-02-28
    buf = struct.pack("<HH", 58, 2026)
    assert ymd(buf, 0) == "2026-02-28"
    assert ymd_from(2026, 58) == "2026-02-28"

    # Invalid year returns None (e.g. year 0 or negative overflow)
    assert ymd(struct.pack("<HH", 0, 0), 0) is None


def test_primitives_tag4():
    buf = b"TCEF" # Stored reversed: 'FECT' -> 'CEFT'
    assert tag4(buf, 0) == "FECT"
    assert tag4_to_disk("FECT") == b"TCEF"


# ==============================================================================
# 2. PString Primitive Unit Tests
# ==============================================================================

def test_pstring_standard():
    ps = PString("club_name")
    buf = struct.pack("<I", 7) + b"Arsenal"
    res = ps.read(buf, 0, len(buf))
    assert res is not None
    data, next_off = res
    assert data == {"club_name": "Arsenal"}
    assert next_off == 11


def test_pstring_null_terminated():
    ps = PString("country", null_terminated=True)
    buf = struct.pack("<I", 7) + b"Denmark\x00"
    res = ps.read(buf, 0, len(buf))
    assert res is not None
    data, next_off = res
    assert data == {"country": "Denmark"}
    assert next_off == 12  # 4 + 7 + 1

    # Missing null terminator fails
    buf_bad = struct.pack("<I", 7) + b"DenmarkX"
    assert ps.read(buf_bad, 0, len(buf_bad)) is None


def test_pstring_empty():
    ps_disallow = PString("desc", allow_empty=False)
    ps_allow = PString("desc", allow_empty=True)
    buf = struct.pack("<I", 0)

    assert ps_disallow.read(buf, 0, len(buf)) is None
    res = ps_allow.read(buf, 0, len(buf))
    assert res is not None
    assert res[0] == {"desc": ""}
    assert res[1] == 4


def test_pstring_encoding_fallback():
    ps = PString("text")
    # 0xE9 is é in latin-1, invalid standalone in utf-8
    bad_utf8 = struct.pack("<I", 4) + b"Caf\xe9"
    res = ps.read(bad_utf8, 0, len(bad_utf8))
    assert res is not None
    assert res[0] == {"text": "Café"}


def test_pstring_bounds_and_overflow():
    ps = PString("val")
    buf = struct.pack("<I", 100) + b"short"
    assert ps.read(buf, 0, len(buf)) is None
    assert ps.read(b"\x01\x00", 0, 2) is None


# ==============================================================================
# 3. Schema & Record.read() Unit Tests
# ==============================================================================

def test_record_validation_and_read():
    rec = Record(
        name="test_record",
        span=14,
        fields=[
            Field(0, 2, "id", U16),
            Field(2, 4, "uid", U32),
            Field(6, 4, "rate", F32),
            Field(10, 4, "when", DATE),
        ],
        register=False,
    )
    assert validate(rec) == []

    # 58th day of 2026 = 2026-02-28
    buf = struct.pack("<HIfHH", 42, 1001, 1.25, 58, 2026)
    decoded = rec.read(buf, 0)
    assert decoded["id"] == 42
    assert decoded["uid"] == 1001
    assert abs(decoded["rate"] - 1.25) < 1e-6
    assert decoded["when"] == "2026-02-28"


def test_record_anchor_and_groups():
    rec = Record(
        name="anchored_record",
        span=8,
        fields=[
            Field(0, 4, "prefix", U32, group="A"),
            Field(4, 4, "target", U32, group="B"),
        ],
        anchor=4,
        register=False,
    )
    buf = struct.pack("<II", 111, 222)
    # Landmark is at anchor offset 4
    at_anchor = rec.read_at_anchor(buf, 4)
    assert at_anchor == {"prefix": 111, "target": 222}

    assert rec.read_group(buf, 0, "A") == {"prefix": 111}
    assert rec.read_group(buf, 0, "B") == {"target": 222}


def test_record_pad_and_unknown():
    rec = Record(
        name="pad_unknown",
        span=6,
        fields=[
            Field(0, 2, "id", U16),
            Field(2, 2, UNKNOWN, PAD),
            Field(4, 2, "val", U16),
        ],
        register=False,
    )
    assert validate(rec) == []
    buf = struct.pack("<HHH", 1, 999, 2)
    out = rec.read(buf, 0)
    # PAD is omitted from output
    assert out == {"id": 1, "val": 2}


# ==============================================================================
# 4. Table Engine & Walking Unit Tests
# ==============================================================================

def test_fixed_stride_table():
    rec = Record("item", 6, [Field(0, 2, "id", U16), Field(2, 4, "val", U32)], register=False)
    data = b""
    for i in range(5):
        data += struct.pack("<HI", i, i * 100)

    table = Table(
        name="items",
        segments=(rec,),
        locator=lambda mm: (0, 5),
    )

    rows = walk_table(data, table)
    assert len(rows) == 5
    assert [r["id"] for r in rows] == [0, 1, 2, 3, 4]
    assert [r["val"] for r in rows] == [0, 100, 200, 300, 400]
    assert table_spans(data, table) == [(0, 30)]


def test_composite_table():
    head = Record("head", 2, [Field(0, 2, "id", U16)], is_head=True, register=False)
    name_seg = PString("name")
    tail = Record("tail", 2, [Field(0, 2, "score", U16)], is_head=True, register=False)

    buf = b""
    for i in range(3):
        buf += struct.pack("<H", i)
        s = f"Entry_{i}".encode("utf-8")
        buf += struct.pack("<I", len(s)) + s
        buf += struct.pack("<H", i * 10)

    table = Table(
        name="composite",
        segments=(head, name_seg, tail),
        locator=lambda mm: (0, 3),
    )

    rows = walk_table(buf, table)
    assert len(rows) == 3
    assert rows[0] == {"id": 0, "name": "Entry_0", "score": 0}
    assert rows[1] == {"id": 1, "name": "Entry_1", "score": 10}
    assert rows[2] == {"id": 2, "name": "Entry_2", "score": 20}
    assert table_spans(buf, table) == [(0, len(buf))]


def test_find_framed_count():
    # Frame: 8 x 0xFF followed by u32 count 1500
    frame = b"\xff" * 8 + struct.pack("<I", 1500) + b"\x00" * 20
    buf = b"\x00" * 64 + frame + b"\x00" * 32

    res = find_framed_count(buf, 0, len(buf), width=4, min_ff=8)
    assert res is not None
    content_offset, count = res
    assert count == 1500
    assert content_offset == 64 + 8 + 4


def main():
    test_primitives_integers()
    test_primitives_floats()
    test_primitives_hex()
    test_primitives_dates()
    test_primitives_tag4()
    test_pstring_standard()
    test_pstring_null_terminated()
    test_pstring_empty()
    test_pstring_encoding_fallback()
    test_pstring_bounds_and_overflow()
    test_record_validation_and_read()
    test_record_anchor_and_groups()
    test_record_pad_and_unknown()
    test_fixed_stride_table()
    test_composite_table()
    test_find_framed_count()
    print("ALL 16 CORE UNIT TESTS PASSED")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

