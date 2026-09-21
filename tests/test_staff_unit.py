#!/usr/bin/env python3
"""Synthetic unit tests for staff records (fmparser/staff.py).

Tests `STAFF` schema parsing, `style()`, and `reputation_tier()` using in-memory
byte buffers with zero save-file dependency.
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser import records as RD  # noqa: E402
from fmparser.tables import staff as ST    # noqa: E402


def build_staff_record_bytes(
    id2: int = 12345,
    ca: int = 150,
    pa: int = 180,
    home_rep: int = 4500,
    curr_rep: int = 5000,
    world_rep: int = 6000,
    attacking_intent: int = 16,
    formations: tuple = (1, 1, 1),
) -> bytes:
    """Pack a 39-byte STAFF record."""
    buf = bytearray(39)
    struct.pack_into("<I", buf, 0, id2)
    struct.pack_into("<HHH", buf, 4, ca, pa, home_rep)
    struct.pack_into("<HH", buf, 10, curr_rep, world_rep)

    # 17 attribute bytes at +14..+30
    for o in range(14, 31):
        buf[o] = 10  # default attribute
    buf[14] = attacking_intent  # specific test value

    # Formation triple at +31..+33
    buf[31] = formations[0]
    buf[32] = formations[1]
    buf[33] = formations[2]

    # 5 undecoded catalog indices at +34..+38
    for o in range(34, 39):
        buf[o] = 2

    return bytes(buf)


def test_staff_schema_unpack():
    print("TESTING STAFF record unpack")
    b = build_staff_record_bytes(
        id2=999,
        ca=140,
        pa=175,
        world_rep=6200,
        attacking_intent=18,
        formations=(4, 5, 6),
    )
    rec = RD.read(b, ST.STAFF, 0)
    assert rec["id2"] == 999
    assert rec["ca"] == 140
    assert rec["pa"] == 175
    assert rec["world_reputation"] == 6200
    assert rec["attacking_intent"] == 18
    assert rec["formation_preferred"] == 4
    assert rec["formation_attacking"] == 5
    assert rec["formation_defensive"] == 6
    assert ST.STAFF.span == ST.STAFF_STRIDE == 39
    print("  PASS STAFF record unpack (fields, attributes, formation triple)")


def test_style_and_reputation_derivatives():
    print("TESTING style() and reputation_tier()")
    # Style: <=7 Defensive, 8-13 Normal, >=14 Attacking
    assert ST.style(5) == "Defensive"
    assert ST.style(7) == "Defensive"
    assert ST.style(8) == "Normal"
    assert ST.style(13) == "Normal"
    assert ST.style(14) == "Attacking"
    assert ST.style(20) == "Attacking"
    assert ST.style(None) is None

    # Reputation tier: <3000 Regional, <5800 National, >=5800 Continental
    assert ST.reputation_tier(1500) == "Regional"
    assert ST.reputation_tier(2999) == "Regional"
    assert ST.reputation_tier(3000) == "National"
    assert ST.reputation_tier(5799) == "National"
    assert ST.reputation_tier(5800) == "Continental"
    assert ST.reputation_tier(7500) == "Continental"
    assert ST.reputation_tier(None) is None
    print("  PASS style() and reputation_tier() edge cases")


def main():
    test_staff_schema_unpack()
    test_style_and_reputation_derivatives()
    return 0


if __name__ == "__main__":
    sys.exit(main())
