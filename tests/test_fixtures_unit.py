#!/usr/bin/env python3
"""Synthetic unit tests for world fixtures (fmparser/fixtures.py).

Tests `FIXTURE` schema parsing, date calculations, and segment tiling
using in-memory byte buffers with zero savefile / archive dependency.
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser.tables import fixtures as FX  # noqa: E402
from fmparser import records as RD   # noqa: E402


def build_fixture_record_bytes(
    home_tid: int = 346,
    away_tid: int = 177,
    home_goals: int = 2,
    away_goals: int = 1,
    stage_key: int = 42,
    seq_id: int = 1,
    day_raw: int = 150,  # DOY
    year: int = 2026,
    season_year: int = 2025,
    round_no: int = 12,
) -> bytes:
    """Pack a 92-byte world fixture record."""
    buf = bytearray(FX.STRIDE)
    buf[1] = FX.OPENER  # 0x14
    buf[2:6] = b"\xff\xff\xff\xff"  # fixture opener sentinel pattern

    # Scores at +6..+13
    buf[6] = home_goals
    buf[7] = 0xFF  # no extra goals
    buf[8] = 0xFF  # no pens
    buf[11] = away_goals
    buf[12] = 0xFF
    buf[13] = 0xFF

    # Stage key +31 (u32), seq_id +35 (u16)
    struct.pack_into("<IH", buf, 31, stage_key, seq_id)

    # Home tid +41, away tid +47
    struct.pack_into("<I", buf, 41, home_tid)
    struct.pack_into("<I", buf, 47, away_tid)

    # Date at +53..+56
    struct.pack_into("<HH", buf, 53, day_raw, year)

    # Season year +66
    struct.pack_into("<H", buf, 66, season_year)

    # Stage attributes +76, +77, +80, +81, +83
    buf[76] = 1
    buf[77] = 2
    buf[78] = round_no
    buf[80] = 5
    buf[81] = 6
    buf[83] = 9

    return bytes(buf)


def test_fixture_schema_unpack():
    print("TESTING FIXTURE schema unpack")
    b = build_fixture_record_bytes(
        home_tid=346,
        away_tid=177,
        home_goals=3,
        away_goals=0,
        stage_key=101,
        seq_id=5,
        day_raw=200,
        year=2026,
        season_year=2025,
        round_no=18,
    )
    rec = RD.read(b, FX.FIXTURE, 0)
    assert rec["opener"] == FX.OPENER
    assert rec["home_tid"] == 346
    assert rec["away_tid"] == 177
    assert rec["home_goals"] == 3
    assert rec["away_goals"] == 0
    assert rec["stage_key"] == 101
    assert rec["seq_id"] == 5
    assert rec["year"] == 2026
    assert rec["season_year"] == 2025
    assert rec["round"] == 18
    assert rec["stage_attr_76"] == 1
    assert rec["stage_attr_77"] == 2
    assert rec["stage_attr_83"] == 9
    assert FX.FIXTURE.span == FX.STRIDE == 92
    print("  PASS FIXTURE schema unpack")


def test_fixture_segments():
    print("TESTING fixture segments")
    # Build a synthetic blob with two segments of 2 fixtures each
    hdr = b"\x03\x01tad."  # 6-byte MEMBER_HEADER
    seg1 = build_fixture_record_bytes(stage_key=1) + build_fixture_record_bytes(stage_key=1)
    # Gap of 4 bytes padding to create a residue shift
    gap = b"\x00" * 4
    seg2 = build_fixture_record_bytes(stage_key=2) + build_fixture_record_bytes(stage_key=2)
    blob = hdr + seg1 + gap + seg2

    segs = FX.segments(blob)
    assert len(segs) == 2
    assert segs[0] == (6, 2)
    assert segs[1] == (6 + len(seg1) + len(gap), 2)
    print("  PASS fixture segments split and count")


def main():
    test_fixture_schema_unpack()
    test_fixture_segments()
    return 0


if __name__ == "__main__":
    sys.exit(main())
