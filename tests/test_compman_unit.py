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


def _honour(cid, season, tids, start, end):
    """One 55-byte roll-of-honour record."""
    buf = bytearray(CH.STRIDE)
    struct.pack_into("<II", buf, 0, cid, season)
    struct.pack_into("<IIII", buf, 8, *tids)
    buf[24:44] = b"\xff" * 20
    struct.pack_into("<HHHH", buf, 47, start, end, 1, 1900)
    return bytes(buf)


def test_compman_honour_schema():
    print("TESTING compman honour schema")
    rec = CH.read_honour(_honour(2, 2029, (346, 337, 2465, 0xFFFFFFFF), 2028, 2029), 0)
    assert rec["comp_cid"] == 2
    assert rec["season"] == 2029
    assert rec["winner_tid"] == 346
    assert rec["runner_up_tid"] == 337
    assert rec["third_place_tid"] == 2465
    assert rec["fourth_place_tid"] is None
    assert (rec["start_year"], rec["end_year"], rec["base_year"]) == (2028, 2029, 1900)
    assert CH.HONOUR.span == CH.STRIDE == 55
    print("  PASS compman honour schema")


def test_compman_honours_framing():
    print("TESTING compman honours framed by their count")
    head = build_synthetic_compman_blob(n_stages=2) + b"\x00" * 37   # stages, then the calendar
    recs = [_honour(2, 2028, (1, 2, 3, 0xFFFFFFFF), 2027, 2028),
            _honour(263, 2028, (4, 5, 0xFFFFFFFF, 0xFFFFFFFF), 2027, 2028),
            _honour(2, 2029, (6, 7, 8, 0xFFFFFFFF), 2028, 2029)]
    blob = head + struct.pack("<I", len(recs)) + b"".join(recs)
    assert CH.locate_comp_honours(blob) == (len(head) + 4, 3)
    rows = CH.scrape(blob)
    assert [(r["comp_cid"], r["season"], r["winner_tid"]) for r in rows] == [(2, 2028, 1), (263, 2028, 4), (2, 2029, 6)]
    assert rows[1]["third_place_tid"] is None
    assert rows[0]["start_year"] == 2027, "record 0 is read, with its own years"

    empty = head + struct.pack("<I", 0)
    assert CH.locate_comp_honours(empty) == (len(empty), 0) and CH.scrape(empty) == []

    wrong_count = head + struct.pack("<I", 2) + b"".join(recs)
    assert CH.locate_comp_honours(wrong_count) is None, "a count that does not tile is no frame"
    broken = bytearray(blob)
    broken[len(head) + 4 + CH.STRIDE + 30] = 0
    assert CH.locate_comp_honours(bytes(broken)) is None, "a record without the signature is no frame"
    print("  PASS compman honours framing")


def main():
    test_compman_header_and_stages()
    test_compman_honour_schema()
    test_compman_honours_framing()
    return 0


if __name__ == "__main__":
    sys.exit(main())
