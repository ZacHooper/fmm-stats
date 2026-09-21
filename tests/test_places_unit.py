#!/usr/bin/env python3
"""Synthetic unit tests for Stadiums and Cities parsing logic (fmparser/places.py).

Tests `_stadium_at`, `_chain_len`, and city record structure using in-memory byte
buffers without requiring a 64 MB savefile.
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser.tables import cities as PL_CITIES, stadiums as PL_STADIUMS  # noqa: E402
from fmparser import records as RD  # noqa: E402


def build_stadium_bytes(
    sid: int = 157,
    uid: int = 200157,
    city_id: int = 51,
    capacity: int = 13800,
    expansion: int = 15000,
    name: str = "Aalborg Portland Park",
    null_term: bool = True,
) -> bytes:
    """Pack an 18-byte STADIUM_HEAD + 4-byte len + name + optional null terminator."""
    buf = bytearray()
    buf += struct.pack("<I", sid)
    buf += struct.pack("<I", uid)
    buf += struct.pack("<H", city_id)
    buf += struct.pack("<I", capacity)
    buf += struct.pack("<I", expansion)

    name_b = name.encode("utf-8")
    buf += struct.pack("<I", len(name_b))
    buf += name_b
    if null_term:
        buf += b"\x00"
    return bytes(buf)


def build_city_bytes(
    cid: int = 51,
    uid: int = 300051,
    nation_id: int = 2,
    latitude: float = 57.0488,
    longitude: float = 9.9217,
    attraction: int = 10,
    region_id: int = 1,
) -> bytes:
    """Pack a 20-byte CITY record."""
    buf = bytearray()
    buf += struct.pack("<H", cid)
    buf += struct.pack("<I", uid)
    buf += struct.pack("<H", nation_id)
    buf += struct.pack("<ff", latitude, longitude)
    buf += struct.pack("<B", attraction)
    buf += struct.pack("<H", region_id)
    buf += struct.pack("<B", 0)  # pad
    return bytes(buf)


def test_stadium_parsing():
    print("TESTING _stadium_at")
    # 1. Valid stadium
    s1 = build_stadium_bytes(sid=157, name="Aalborg Portland Park", capacity=13800)
    mm1 = memoryview(s1)
    rec1, nxt1 = PL_STADIUMS._stadium_at(mm1, 0, len(s1))
    assert rec1 is not None
    assert rec1["id"] == 157
    assert rec1["name"] == "Aalborg Portland Park"
    assert rec1["capacity"] == 13800
    assert nxt1 == len(s1)

    # 2. Implausible capacity (> 300,000) rejected
    s_huge = build_stadium_bytes(sid=1, capacity=500_000)
    rec_huge, _ = PL_STADIUMS._stadium_at(memoryview(s_huge), 0, len(s_huge))
    assert rec_huge is None

    # 3. Missing null terminator rejected
    s_nonull = build_stadium_bytes(sid=2, null_term=False)
    rec_nonull, _ = PL_STADIUMS._stadium_at(memoryview(s_nonull), 0, len(s_nonull))
    assert rec_nonull is None

    # 4. Chain of 3 stadiums
    s_a = build_stadium_bytes(sid=1, name="Stadium A")
    s_b = build_stadium_bytes(sid=2, name="Stadium B")
    s_c = build_stadium_bytes(sid=3, name="Stadium C")
    chain_buf = memoryview(s_a + s_b + s_c)
    chain_len = PL_STADIUMS._chain_len(chain_buf, 0, len(chain_buf))
    assert chain_len == 3

    print("  PASS _stadium_at (valid, capacity gate, null terminator, chaining)")


def test_city_parsing():
    print("TESTING CITY record schema")
    # 1. Valid coordinates
    c1 = build_city_bytes(cid=51, latitude=57.0488, longitude=9.9217)
    rec1 = RD.read(c1, PL_CITIES.CITY, 0)
    assert rec1["id"] == 51
    assert abs(rec1["latitude"] - 57.0488) < 1e-4
    assert abs(rec1["longitude"] - 9.9217) < 1e-4
    assert rec1["nation_id"] == 2

    # 2. Layout span
    assert PL_CITIES.CITY.span == PL_CITIES.CITY_RECORD == 20

    print("  PASS CITY record schema (unpacks fields and float32 lat/lon)")


def main():
    test_stadium_parsing()
    test_city_parsing()
    return 0


if __name__ == "__main__":
    sys.exit(main())
