#!/usr/bin/env python3
"""Unit tests for the generic table abstraction engine (fmparser/tables.py).

Tests `FixedTableDef` and `StringCatalogDef` with synthetic byte buffers without requiring
a 64 MB savefile, ensuring the walker, spans generator, post-processing, and encoding
fallbacks are sound under all conditions.
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser.schema import Field, Record, U16, U32, U8  # noqa: E402
from fmparser.tables import (                              # noqa: E402
    FixedTableDef,
    StringCatalogDef,
    fixed_table_spans,
    string_catalog_spans,
    walk_fixed_table,
    walk_string_catalog,
)

# Synthetic fixed schema: 7 bytes = [id u32][val u16][flag u8]
DUMMY_FIXED = Record("dummy_fixed", 7, [
    Field(0, 4, "id", U32),
    Field(4, 2, "val", U16),
    Field(6, 1, "flag", U8),
])

# Synthetic catalog schemas:
# Head: 8 bytes = [id u32][len u32]
DUMMY_HEAD = Record("dummy_head", 8, [
    Field(0, 4, "id", U32),
    Field(4, 4, "len", U32),
], is_head=True)

# Trailer: 4 bytes = [code u32]
DUMMY_TRAILER = Record("dummy_trailer", 4, [
    Field(0, 4, "code", U32),
])


def test_fixed_table():
    print("TESTING FixedTableDef")
    # Build a 3-record table with a 4-byte count header
    count = 3
    buf = bytearray()
    buf += struct.pack("<I", count)  # count header
    base = len(buf)
    for i in range(count):
        buf += struct.pack("<I", i * 10)  # id
        buf += struct.pack("<H", 100 + i)  # val
        buf += struct.pack("<B", 1)  # flag

    mm = memoryview(buf)

    table_def = FixedTableDef(
        name="test_fixed",
        record_schema=DUMMY_FIXED,
        locator=lambda m: (base, count),
        post_process=lambda r: {**r, "extra": r["id"] * 2},
    )

    rows = walk_fixed_table(mm, table_def)
    assert len(rows) == count, f"expected {count} rows, got {len(rows)}"
    assert rows[0] == {"id": 0, "val": 100, "flag": 1, "extra": 0}
    assert rows[1] == {"id": 10, "val": 101, "flag": 1, "extra": 20}
    assert rows[2] == {"id": 20, "val": 102, "flag": 1, "extra": 40}

    # Test object methods directly
    assert table_def.scrape(mm) == rows
    assert table_def.spans(mm, include_count_header=True) == fixed_table_spans(mm, table_def, include_count_header=True)
    id_map = table_def.id_map(mm, key_field="id")
    assert len(id_map) == 3
    assert id_map[10]["val"] == 101

    # Test include_offset
    offset_def = FixedTableDef(
        name="test_fixed_offset",
        record_schema=DUMMY_FIXED,
        locator=lambda m: (base, count),
        include_offset=True,
    )
    offset_rows = offset_def.scrape(mm)
    assert offset_rows[0]["offset"] == base
    assert offset_rows[1]["offset"] == base + DUMMY_FIXED.stride

    spans = fixed_table_spans(mm, table_def, include_count_header=True)
    assert len(spans) == count + 1  # count header + 3 rows
    assert spans[0] == (0, 4)  # count header span
    assert spans[1] == (4, 11)
    assert spans[2] == (11, 18)
    assert spans[3] == (18, 25)

    # Empty / not found locator
    missing_def = FixedTableDef(
        name="missing",
        record_schema=DUMMY_FIXED,
        locator=lambda m: None,
    )
    assert walk_fixed_table(mm, missing_def) == []
    assert fixed_table_spans(mm, missing_def) == []
    print("  PASS FixedTableDef (walking, post_process, spans, missing-locator)")


def test_string_catalog():
    print("TESTING StringCatalogDef")
    # Build a 2-record catalog:
    # Row 0: id=1, "First Leg" (9 bytes), null, code=999
    # Row 1: id=2, "Quarter Final" (13 bytes), null, code=888
    items = [
        (1, "First Leg", 999),
        (2, "Quarter Final", 888),
    ]
    buf = bytearray()
    buf += struct.pack("<I", len(items))  # count header at 0
    base = len(buf)

    for rid, name, code in items:
        name_bytes = name.encode("utf-8")
        buf += struct.pack("<I", rid)
        buf += struct.pack("<I", len(name_bytes))
        buf += name_bytes
        buf += b"\x00"
        buf += struct.pack("<I", code)

    mm = memoryview(buf)

    catalog_def = StringCatalogDef(
        name="test_catalog",
        head_schema=DUMMY_HEAD,
        trailer_schema=DUMMY_TRAILER,
        locator=lambda m: (base, len(items)),
        string_field="name",
        len_field="len",
        null_terminated=True,
    )

    rows = walk_string_catalog(mm, catalog_def)
    assert len(rows) == len(items), f"expected {len(items)} rows, got {len(rows)}"
    assert rows[0] == {"id": 1, "name": "First Leg", "code": 999}
    assert rows[1] == {"id": 2, "name": "Quarter Final", "code": 888}

    # Test object methods directly
    assert catalog_def.scrape(mm) == rows
    assert catalog_def.spans(mm, include_count_header=True) == string_catalog_spans(mm, catalog_def, include_count_header=True)
    id_map = catalog_def.id_map(mm, key_field="id")
    assert len(id_map) == 2
    assert id_map[1]["name"] == "First Leg"

    # Test include_offset
    offset_cat = StringCatalogDef(
        name="test_cat_offset",
        head_schema=DUMMY_HEAD,
        trailer_schema=DUMMY_TRAILER,
        locator=lambda m: (base, len(items)),
        string_field="name",
        len_field="len",
        null_terminated=True,
        include_offset=True,
    )
    offset_cat_rows = offset_cat.scrape(mm)
    assert offset_cat_rows[0]["offset"] == base
    assert "offset" in offset_cat_rows[1]

    spans = string_catalog_spans(mm, catalog_def, include_count_header=True)
    assert len(spans) == len(items) + 1
    assert spans[0] == (0, 4)  # count header
    # Check contiguity
    for i in range(1, len(spans) - 1):
        assert spans[i][1] == spans[i + 1][0], f"gap between span {i} and {i+1}"
    assert spans[-1][1] == len(buf)

    print("  PASS StringCatalogDef (walking, spans, null terminator, trailer)")


def test_stadiums_catalog():
    print("TESTING STADIUMS_CATALOG")
    from fmparser.tables.stadiums import STADIUMS_CATALOG
    from tests.test_places_unit import build_stadium_bytes

    # Build 3 stadiums with differing name lengths (variable length records)
    s1 = build_stadium_bytes(sid=1, name="Short", capacity=10000)
    s2 = build_stadium_bytes(sid=2, name="A Bit Longer Stadium Name", capacity=25000)
    s3 = build_stadium_bytes(sid=3, name="Super Long Stadium Arena 2026", capacity=60000)
    # Plus one invalid capacity stadium that should be filtered by post_process
    s_bad = build_stadium_bytes(sid=4, name="Mega Dome", capacity=500_000)

    buf = memoryview(s1 + s2 + s3 + s_bad)
    rows = STADIUMS_CATALOG.scrape(buf)
    # s_bad should be excluded by post_process
    assert len(rows) == 3
    assert rows[0]["id"] == 1 and rows[0]["name"] == "Short"
    assert rows[1]["id"] == 2 and rows[1]["name"] == "A Bit Longer Stadium Name"
    assert rows[2]["id"] == 3 and rows[2]["name"] == "Super Long Stadium Arena 2026"

    # Verify spans cover the variable-length records accurately
    spans = STADIUMS_CATALOG.spans(buf, include_count_header=False)
    assert len(spans) == 3  # capacity check gates s_bad out of the chain
    for i in range(len(spans) - 1):
        assert spans[i][1] == spans[i + 1][0], f"spans must be contiguous: {spans[i]} and {spans[i+1]}"

    # Verify id_map
    id_map = STADIUMS_CATALOG.id_map(buf)
    assert set(id_map.keys()) == {1, 2, 3}

    # Verify corrupt null terminator stops the walk
    s_nonull = build_stadium_bytes(sid=5, name="Corrupt", null_term=False)
    corrupt_buf = memoryview(s1 + s_nonull + s2)
    corrupt_rows = STADIUMS_CATALOG.scrape(corrupt_buf)
    # After s1, s_nonull has no NUL terminator so the walk stops immediately
    assert len(corrupt_rows) == 1
    assert corrupt_rows[0]["id"] == 1
    print("  PASS STADIUMS_CATALOG (variable-length strings, capacity gate, NUL enforcement, spans)")


def test_name_id_tables():
    print("TESTING NAME_ID_TABLES")
    from fmparser.tables.names import (
        SURNAMES_TABLE,
        walk_browse_bounds,
    )

    # 1. Test browse string table parsing (flat [len u32][utf-8])
    browse_buf = bytearray(b"\x00" * 250)  # pad to > 200
    start = len(browse_buf)
    names = ["Smith", "Jones", "Williams", "Brown", "Taylor"] * 250  # > 1000 names
    for name in names:
        nb = name.encode("utf-8")
        browse_buf += struct.pack("<I", len(nb))
        browse_buf += nb
    end = len(browse_buf)

    b_start, b_end, parsed_names = walk_browse_bounds(memoryview(browse_buf))
    assert b_start == start
    assert b_end == end
    assert len(parsed_names) == len(names)
    assert parsed_names[:5] == ["Smith", "Jones", "Williams", "Brown", "Taylor"]

    # 2. Test FixedTableDef on synthetic 16B records
    records_buf = bytearray()
    for i in range(5):
        records_buf += struct.pack("<II", i, 100 + i) + b"\x00" * 8

    mv = memoryview(records_buf)
    sur_rows = SURNAMES_TABLE.scrape(mv)
    assert len(sur_rows) == 5
    assert sur_rows[0]["ordinal"] == 0 and sur_rows[0]["id"] == 100
    assert sur_rows[4]["ordinal"] == 4 and sur_rows[4]["id"] == 104

    # Spans
    spans = SURNAMES_TABLE.spans(mv, include_count_header=False)
    assert len(spans) == 5
    assert spans[0] == (0, 16)
    assert spans[-1] == (64, 80)
    print("  PASS NAME_ID_TABLES (browse string bounds, 16B FixedTableDef scraping/spans)")


def test_player_attributes_table():
    print("TESTING PLAYER_ATTRIBUTES_TABLE")
    from fmparser.tables.player_attributes import PLAYER_ATTRIBUTES_TABLE

    buf = bytearray()
    # 0..4: sid
    buf += bytes.fromhex("12345678")
    # 4..8: history link
    buf += struct.pack("<I", 0)
    # 8..42: 34 bytes (src, hidden, attrs, plain offsets)
    buf += b"\x0a" * 34
    # 42..57: 15 position rating bytes (1..20, with max = 20)
    buf += bytes([1] * 14 + [20])
    # 57: foot_left
    buf += b"\x0f"
    # 58: foot_right
    buf += b"\x14"
    # 59..61: ca
    buf += struct.pack("<H", 120)
    # 61..63: pa
    buf += struct.pack("<H", 150)
    # 63..65: reputation
    buf += struct.pack("<H", 5000)
    # 65..67: current_reputation
    buf += struct.pack("<H", 5100)
    # 67..69: world_reputation
    buf += struct.pack("<H", 4800)
    # 69: international_retired
    buf += b"\x00"
    # 70..72: unknown (2B)
    buf += b"\x00\x00"
    # 72: squad_number
    buf += b"\x09"
    # 73: preferred_squad_number
    buf += b"\x09"
    # 74..76: height_cm
    buf += struct.pack("<H", 185)
    # 76..78: weight_kg
    buf += struct.pack("<H", 78)

    assert len(buf) == 78, f"expected 78 bytes, got {len(buf)}"

    mv = memoryview(buf)
    rows = PLAYER_ATTRIBUTES_TABLE.scrape(mv)
    assert len(rows) == 1
    r = rows[0]
    assert r["sid"] == "12345678"
    assert r["P"] == 42
    assert r["ca"] == 120
    assert r["pa"] == 150
    assert r["feet"] == {"left": 15, "right": 20}
    assert r["height_cm"] == 185
    assert r["weight_kg"] == 78
    assert isinstance(r["attributes"], dict)
    assert r["attributes"]["Pace"] == 10
    assert isinstance(r["positions"], dict)

    spans = PLAYER_ATTRIBUTES_TABLE.spans(mv, include_count_header=False)
    assert spans == [(0, 78)]
    print("  PASS PLAYER_ATTRIBUTES_TABLE (78B stride, field unpacking, positions dict, attributes)")


def main():
    test_fixed_table()
    test_string_catalog()
    test_stadiums_catalog()
    test_name_id_tables()
    test_player_attributes_table()
    return 0


if __name__ == "__main__":
    sys.exit(main())
