#!/usr/bin/env python3
"""Unit tests for the generic composite-stream table engine (fmparser/tables/engine.py).

Tests `TableDef` and `PString` with synthetic byte buffers without requiring a 64 MB savefile,
ensuring fixed grids, single-string catalogs, and multi-string catalogs are sound under all
conditions (offsets, spans, post-processing, decoding fallbacks, error handling).
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser.core import Field, Record, U16, U32, U8, PString
from fmparser.tables import (                              # noqa: E402
    TableDef,
    table_spans,
    walk_table,
)

# Synthetic fixed schema: 7 bytes = [id u32][val u16][flag u8]
DUMMY_FIXED = Record("dummy_fixed", 7, [
    Field(0, 4, "id", U32),
    Field(4, 2, "val", U16),
    Field(6, 1, "flag", U8),
])

# Synthetic catalog schemas:
# Head: 4 bytes = [id u32]
DUMMY_HEAD = Record("dummy_head", 4, [
    Field(0, 4, "id", U32),
], is_head=True)

# Trailer: 4 bytes = [code u32]
DUMMY_TRAILER = Record("dummy_trailer", 4, [
    Field(0, 4, "code", U32),
])


def test_fixed_table():
    print("TESTING TableDef (Fixed Grid)")
    count = 3
    buf = bytearray()
    buf += struct.pack("<I", count)  # count header
    base = len(buf)
    for i in range(count):
        buf += struct.pack("<I", i * 10)  # id
        buf += struct.pack("<H", 100 + i)  # val
        buf += struct.pack("<B", 1)  # flag

    mm = memoryview(buf)

    table_def = TableDef(
        name="test_fixed",
        segments=(DUMMY_FIXED,),
        locator=lambda m: (base, count),
        post_process=lambda r: {**r, "extra": r["id"] * 2},
    )

    rows = walk_table(mm, table_def)
    assert len(rows) == count, f"expected {count} rows, got {len(rows)}"
    assert rows[0] == {"id": 0, "val": 100, "flag": 1, "extra": 0}
    assert rows[1] == {"id": 10, "val": 101, "flag": 1, "extra": 20}
    assert rows[2] == {"id": 20, "val": 102, "flag": 1, "extra": 40}

    assert table_def.scrape(mm) == rows
    assert table_def.spans(mm, include_count_header=True) == table_spans(mm, table_def, include_count_header=True)
    id_map = table_def.id_map(mm, key_field="id")
    assert len(id_map) == 3
    assert id_map[10]["val"] == 101

    offset_def = TableDef(
        name="test_fixed_offset",
        segments=(DUMMY_FIXED,),
        locator=lambda m: (base, count),
        include_offset=True,
    )
    offset_rows = offset_def.scrape(mm)
    assert offset_rows[0]["offset"] == base
    assert offset_rows[1]["offset"] == base + DUMMY_FIXED.stride

    spans = table_spans(mm, table_def, include_count_header=True)
    assert len(spans) == 1
    assert spans[0] == (base, base + count * DUMMY_FIXED.stride)

    missing_def = TableDef(
        name="missing",
        segments=(DUMMY_FIXED,),
        locator=lambda m: None,
    )
    assert walk_table(mm, missing_def) == []
    assert table_spans(mm, missing_def) == []
    print("  PASS TableDef (fixed grid: walking, post_process, spans, missing-locator)")


def test_single_string_catalog():
    print("TESTING TableDef (Single String Catalog)")
    items = [
        (1, "First Leg", 999),
        (2, "Quarter Final", 888),
    ]
    base = 4
    buf = struct.pack("<I", len(items))
    for cid, name, code in items:
        buf += struct.pack("<I", cid)
        nb = name.encode("utf-8")
        buf += struct.pack("<I", len(nb))
        buf += nb
        buf += b"\x00"  # null terminator
        buf += struct.pack("<I", code)

    mm = memoryview(buf)

    cat_def = TableDef(
        name="test_catalog",
        segments=(
            DUMMY_HEAD,
            PString("name", null_terminated=True),
            DUMMY_TRAILER,
        ),
        locator=lambda m: (base, len(items)),
        include_offset=True,
    )

    rows = cat_def.scrape(mm)
    assert len(rows) == 2
    assert rows[0]["id"] == 1
    assert rows[0]["name"] == "First Leg"
    assert rows[0]["code"] == 999
    assert rows[0]["offset"] == base

    assert rows[1]["id"] == 2
    assert rows[1]["name"] == "Quarter Final"
    assert rows[1]["code"] == 888

    spans = table_spans(mm, cat_def, include_count_header=True)
    assert len(spans) == 1
    assert spans[0] == (base, len(buf))

def test_multi_string_catalog():
    print("TESTING TableDef (Multi-String Catalog)")
    items = [
        (0, 100, "English", "English", 139, 1),
        (1, 101, "Malayalam", "", 200, 5),  # empty other_name
    ]
    buf = bytearray()
    buf += struct.pack("<H", len(items))
    base = len(buf)

    HEAD = Record("mhead", 6, [Field(0, 2, "id", U16), Field(2, 4, "uid", U32)], is_head=True)
    TAIL = Record("mtail", 3, [Field(0, 2, "nat_id", U16), Field(2, 1, "diff", U8)], is_head=True)

    for lid, uid, name1, name2, nat, diff in items:
        buf += struct.pack("<HI", lid, uid)
        n1_b = name1.encode("utf-8")
        buf += struct.pack("<I", len(n1_b)) + n1_b
        n2_b = name2.encode("utf-8")
        buf += struct.pack("<I", len(n2_b)) + n2_b
        buf += struct.pack("<HB", nat, diff)

    mm = memoryview(buf)

    multi_def = TableDef(
        name="multi_strings",
        segments=(
            HEAD,
            PString("name", null_terminated=False),
            PString("other_name", null_terminated=False, allow_empty=True),
            TAIL,
        ),
        locator=lambda m: (base, len(items)),
        include_offset=True,
    )

    rows = multi_def.scrape(mm)
    assert len(rows) == 2
    assert rows[0]["name"] == "English"
    assert rows[0]["other_name"] == "English"
    assert rows[0]["nat_id"] == 139
    assert rows[0]["diff"] == 1

    assert rows[1]["name"] == "Malayalam"
    assert rows[1]["other_name"] == ""
    assert rows[1]["nat_id"] == 200
    assert rows[1]["diff"] == 5

    spans = table_spans(mm, multi_def, include_count_header=False)
    assert len(spans) == 1
    assert spans[0] == (base, len(buf))
    print("  PASS TableDef (multi-string catalog with empty strings)")


def test_pstring_primitive():
    print("TESTING PString primitive")
    pstr = PString("text", null_terminated=True)

    # Valid string
    buf = struct.pack("<I", 5) + b"hello\x00"
    res = pstr.read(buf, 0, len(buf))
    assert res == ({"text": "hello"}, 10)

    # Missing null terminator
    bad_buf = struct.pack("<I", 5) + b"helloX"
    assert pstr.read(bad_buf, 0, len(bad_buf)) is None

    # Disallow empty when allow_empty=False
    pstr_no_empty = PString("text", allow_empty=False)
    empty_buf = struct.pack("<I", 0)
    assert pstr_no_empty.read(empty_buf, 0, len(empty_buf)) is None

    # Allow empty
    pstr_empty = PString("text", allow_empty=True)
    res_empty = pstr_empty.read(empty_buf, 0, len(empty_buf))
    assert res_empty == ({"text": ""}, 4)

    # Fallback encoding on invalid UTF-8
    pstr_latin = PString("text")
    latin_buf = struct.pack("<I", 4) + b"M\xfcn" + b"\x00"
    res_latin = pstr_latin.read(latin_buf, 0, len(latin_buf))
    assert res_latin is not None
    assert "text" in res_latin[0]

    print("  PASS PString primitive")


def main():
    test_fixed_table()
    test_single_string_catalog()
    test_multi_string_catalog()
    test_pstring_primitive()
    return 0


if __name__ == "__main__":
    sys.exit(main())
