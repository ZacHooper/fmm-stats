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


def main():
    test_fixed_table()
    test_string_catalog()
    return 0


if __name__ == "__main__":
    sys.exit(main())
