#!/usr/bin/env python3
"""Synthetic unit tests for comp_man.dat parsing logic (fmparser/tables/comp_stages.py and comp_honours.py).

Tests `header`, `stages`, and `honours` schemas and readers on synthetic byte
buffers with zero savefile / zstd dependency.
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser.tables import comp_stages as CS
from fmparser.tables import comp_honours as CH


def build_synthetic_compman_blob(
    n_stages: int = 2,
    year_start: int = 2021,
    year_end: int = 2027,
) -> bytes:
    """Build a minimal valid comp_man.dat member, its 6-byte member header included."""
    buf = bytearray()

    # 42-byte HEADER, from the member header
    hdr = bytearray(CS.HEADER_STRIDE)
    hdr[0:6] = b"\x03\x01tad."
    struct.pack_into("<HHH", hdr, 6, 1, 2, 3)
    struct.pack_into("<HH", hdr, 12, year_start, year_end)
    struct.pack_into("<I", hdr, 16, n_stages)
    struct.pack_into("<H", hdr, 20, 2000)
    struct.pack_into("<II", hdr, 22, 100, 200)
    hdr[38:42] = b"\xff\xff\xff\xff"
    buf += hdr

    # n_stages * 78-byte STAGES
    for k in range(n_stages):
        stg = bytearray(CS.STRIDE)
        stg[0] = 1  # opener
        stg[30:46] = b"\xff" * 16
        struct.pack_into("<HH", stg, 46, 2021, 2027)
        struct.pack_into("<HH", stg, 56, 2000, 1)  # base_year, format_flag (1=league)
        struct.pack_into("<HH", stg, 62, 5, 1500)  # region_code, kickoff_time
        struct.pack_into("<H", stg, 66, 10 + k)     # match_week
        buf += stg

    return bytes(buf)


def test_compman_header_and_stages():
    print("TESTING compman header and stages")
    blob = build_synthetic_compman_blob(n_stages=3)

    hdr = CS.header(blob)
    assert hdr["n_stages"] == 3
    assert hdr["year_start"] == 2021
    assert hdr["year_end"] == 2027
    assert hdr["base_year"] == 2000

    stgs = CS.stages(blob)
    assert len(stgs) == 3
    assert stgs[0]["stage_key"] == 0
    assert stgs[1]["stage_key"] == 1
    assert stgs[2]["stage_key"] == 2
    assert stgs[0]["format_flag"] == 1
    assert stgs[0]["kickoff_time"] == 1500
    assert stgs[0]["match_week"] == 10
    assert stgs[1]["match_week"] == 11

    from fmparser.core import record_instances
    found = [(r.name, off) for r, off in record_instances(blob, CS.COMP_STAGES_TABLE)]
    assert found[0] == ("comp_man_header", 0), found[:2]
    assert found[1:] == [("comp_man_stage", CS.HEADER_STRIDE + k * CS.STRIDE) for k in range(3)]
    assert CS.COMP_STAGES_TABLE.scrape(blob) == stgs, "the registered table reads the member"
    print("  PASS compman header and stages parsing; the audit sees the header and every stage")


def test_compman_honour_schema():
    print("TESTING compman honour schema")
    buf = bytearray(CH.STRIDE)
    buf[0:5] = b"\xff" * 5
    struct.pack_into("<HHH", buf, 8, 2021, 2027, 2)  # start, end, format_flag
    struct.pack_into("<H", buf, 14, 1900)
    struct.pack_into("<II", buf, 16, 2, 2025)  # cid 2, season 2025
    struct.pack_into("<IIII", buf, 24, 346, 177, 157, 100)  # 1st..4th place TIDs
    buf[40:55] = b"\xff" * 15

    rec = CH.HONOUR.read(bytes(buf), 0)
    assert rec["comp_cid"] == 2
    assert rec["season"] == 2025
    assert rec["winner_tid"] == 346
    assert rec["runner_up_tid"] == 177
    assert rec["third_place_tid"] == 157
    assert rec["fourth_place_tid"] == 100
    assert CH.HONOUR.span == CH.STRIDE == 55
    print("  PASS compman honour schema")


def main():
    test_compman_header_and_stages()
    test_compman_honour_schema()
    return 0


if __name__ == "__main__":
    sys.exit(main())
