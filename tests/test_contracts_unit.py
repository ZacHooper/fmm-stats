#!/usr/bin/env python3
"""Synthetic unit tests for the contract grid (fmparser/tables/contracts.py).

Tests:
1. `CONTRACT` record schema layout and span.
2. `CONTRACT_TABLE` FixedTableDef registration and operations.
3. Direct O(1) arithmetic lookup and decoding logic via `scrape_contracts()`:
   - tid matching slot index
   - marker decoding (0x01 active vs non-active markers)
   - wage calculation from wage_units * WAGE_GBP_PER_UNIT
   - date decoding (start_date, expiry, expiry_year)
   - out-of-bounds guards (missing/blank slots)
4. Header frame locating (`locate_contracts`):
   - 11-byte 0x12 frame matching and capacity header parsing
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser.core import DATE, Field, PAD, Record, U16, U32, U8
from fmparser.tables import TABLES  # noqa: E402
from fmparser.tables import contracts as CT  # noqa: E402
from fmparser.tables.contracts import WAGE_GBP_PER_UNIT  # noqa: E402


def build_contract_slot_bytes(
    tid: int,
    marker: int = 0x01,
    wage_units: int = 100,
    expiry_doy: int = 180,
    expiry_year: int = 2026,
    start_doy: int = 1,
    start_year: int = 2021,
) -> bytes:
    """Pack an 83-byte CONTRACT record."""
    buf = bytearray(CT.CONTRACT_STRIDE)
    struct.pack_into("<I", buf, 0, tid)
    struct.pack_into("<B", buf, 4, marker)
    struct.pack_into("<H", buf, 5, wage_units)
    # Expiry at +13: [doy u16][year u16]
    struct.pack_into("<HH", buf, 13, expiry_doy, expiry_year)
    # Start date at +36: [doy u16][year u16]
    struct.pack_into("<HH", buf, 36, start_doy, start_year)
    return bytes(buf)



def test_contract_schema_and_table_def():
    print("TESTING CONTRACT schema and FixedTableDef")
    assert CT.CONTRACT.span == 83
    assert CT.CONTRACT_STRIDE == 83
    assert CT.CONTRACT_RECORD == 83

    # Check key field offsets
    field_map = {f.name: f for f in CT.CONTRACT.fields}
    assert field_map["tid"].offset == 0
    assert field_map["marker"].offset == 4
    assert field_map["wage_units"].offset == 5
    assert field_map["expiry"].offset == 13
    assert field_map["expiry_year"].offset == 15
    assert field_map["start_date"].offset == 36

    # Verify registration in central tables registry
    assert "contracts" in TABLES
    assert TABLES["contracts"] is CT.CONTRACT_TABLE
    assert CT.CONTRACT.span == 83
    assert CT.CONTRACT_TABLE.stride == 83


def test_contract_scraping_and_decoding():
    print("TESTING scrape_contracts direct arithmetic and decoding")
    slots = [
        build_contract_slot_bytes(tid=0, marker=0x01, wage_units=50, expiry_year=2025, start_year=2020),
        build_contract_slot_bytes(tid=1, marker=0x01, wage_units=200, expiry_year=2028, start_year=2022),
        build_contract_slot_bytes(tid=2, marker=0x10, wage_units=0),  # Inactive marker
    ]
    raw_buf = bytearray(b"".join(slots))

    # Synthetic buffer of 3 slots (tid 0, 1, 2)
    contracts = CT.scrape_contracts(raw_buf)
    assert len(contracts) == 2, f"expected 2 active contracts, got {len(contracts)}"
    assert 0 in contracts
    assert 1 in contracts
    assert 2 not in contracts  # inactive marker 0x10 ignored

    c0 = contracts[0]
    assert c0["wage_units"] == 50
    assert c0["wage_gbp"] == 50 * WAGE_GBP_PER_UNIT
    assert c0["expiry_year"] == 2025
    assert c0["expiry"] == "2025-06-30"

    c1 = contracts[1]
    assert c1["wage_units"] == 200
    assert c1["wage_gbp"] == 200 * WAGE_GBP_PER_UNIT
    assert c1["expiry_year"] == 2028

    # Test targeted lookup by tids_or_info
    info_map = {0: {}, 5: {}}  # tid 5 is beyond buffer capacity
    partial = CT.scrape_contracts(raw_buf, tids_or_info=info_map)
    assert len(partial) == 1
    assert 0 in partial
    assert 5 not in partial
    print("  PASS direct arithmetic, marker filtering, and wage conversion")



def test_contracts_locator_frame():
    print("TESTING locate_contracts frame matching")
    capacity = 15000
    pre_pad = b"\x00" * 15_000_000
    delimiter = b"\x12" * 11
    # Frame layout before base0:
    # idx..idx+11 = delimiter (11 bytes)
    # idx+11..base0 = 6 bytes (total 17 bytes: idx+11..idx+11+6)
    # base0 - 6 .. base0 - 2 = uint32 capacity (at idx + 11)
    # base0 - 2 .. base0 = 2 bytes pad
    frame = bytearray(6)
    struct.pack_into("<I", frame, 0, capacity)
    slot0 = build_contract_slot_bytes(tid=0)
    slot1 = build_contract_slot_bytes(tid=1)

    full_buf = bytearray(pre_pad + delimiter + bytes(frame) + slot0 + slot1)

    loc = CT.locate_contracts(full_buf)
    assert loc is not None
    base, count = loc
    assert count == capacity
    assert base == 15_000_000 + 17
    print("  PASS delimiter and slot capacity frame detection")


def main():
    test_contract_schema_and_table_def()
    test_contract_scraping_and_decoding()
    test_contracts_locator_frame()
    return 0


if __name__ == "__main__":
    sys.exit(main())
