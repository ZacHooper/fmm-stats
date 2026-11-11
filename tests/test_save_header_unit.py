#!/usr/bin/env python3
"""Unit tests for the save header (fmparser/tables/save_header.py), no save needed.

  TITLE     the 250-byte NUL-padded title reads to date / manager / nickname
  FMM27     the FMM27 header's strings and stamp read, and the declared version picks the format
  CAMPAIGN  the per-career rollover (careers.campaign), and a new career's first save
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import careers as C  # noqa: E402
from fmparser.tables import save_header as H  # noqa: E402


def header(title: str) -> bytes:
    raw = title.encode("utf-8")
    return raw + b"\x00" * (H.SAVE_HEADER.span - len(raw)) + b"\x01\x24"


def test_title():
    print("TESTING save header title")
    h = H.read_save_header(header("9/8/27 - Mr Manager (Frem)"))
    assert h == {"title": "9/8/27 - Mr Manager (Frem)", "date": "2027-08-09",
                 "manager": "Mr Manager", "nickname": "Frem", "format": "fmm22"}, h
    h = H.read_save_header(header("1/4/23 - Herr Manager (Bucaspor 1928)"))
    assert (h["date"], h["manager"], h["nickname"]) == ("2023-04-01", "Herr Manager",
                                                       "Bucaspor 1928")
    # a title that does not read keeps the text and names nothing
    for bad in ("Mr Manager (Frem)", "31/2/23 - Mr Manager (Frem)", ""):
        h = H.read_save_header(header(bad))
        assert h["title"] == bad and h["date"] is None and h["nickname"] is None, (bad, h)
    print("  PASS title")


def pstr(s: str) -> bytes:
    raw = s.encode("utf-8")
    return len(raw).to_bytes(4, "little") + raw


def fmm27_header(day: int, year: int, written_at: int) -> bytes:
    stamp = bytearray(64)
    stamp[28:32] = day.to_bytes(2, "little") + year.to_bytes(2, "little")
    stamp[35:39] = written_at.to_bytes(4, "little")
    return (pstr("Truro City") + pstr("Truro") + pstr("Truro") + bytes(stamp)
            + pstr("27.0.0-d+2495469") + pstr("fmm27-rel-staging") + b"\x00"
            + pstr("27.0.0+2495469") + pstr("fmm27-rel-staging") + bytes(14)
            + pstr("fmm27-rel-staging") + pstr("27.0.0+2495469") + b"\xff" * 16)


def test_fmm27():
    print("TESTING FMM27 header")
    buf = fmm27_header(205, 2026, 1794341015)        # day 205 of 2026 = 25 July
    assert H.save_format(buf) == H.FMM27
    assert H.read_save_header(buf) == {"title": "Truro City", "date": "2026-07-25",
                                       "manager": None, "nickname": None, "format": "fmm27"}
    row = H.FMM27_HEADER.scrape(buf)[0]
    assert row["written_at"] == 1794341015 and row["build_3"] == "27.0.0+2495469", row
    assert H.save_header_end(buf) == len(buf) - 16
    # FMM22 declares no version, and keeps its fixed 250-byte header
    old = header("9/8/27 - Mr Manager (Frem)")
    assert H.save_format(old) == H.FMM22 and H.save_header_end(old) == H.SAVE_HEADER.span
    # a manager named like a channel is not a declaration: it has no length prefix
    assert H.save_format(header("9/8/27 - fmm27-rel (Frem)")) == H.FMM22
    # a declared version with no reader is returned as declared, and dates nothing
    other = buf.replace(b"fmm27-rel-staging", b"fmm26-rel-staging")
    assert H.save_format(other) == "fmm26", H.save_format(other)
    assert H.read_save_header(other)["date"] is None
    print("  PASS fmm27")


def test_campaign():
    print("TESTING campaign (per-career rollover)")
    dk, tr = (6, 30), (6, 20)
    assert C.campaign("2024-06-29", True, dk) == 2024
    assert C.campaign("2024-06-30", True, dk) == 2025
    assert C.campaign("2024-06-30", False, dk) == 2025  # past the rollover, no matches yet
    assert C.campaign("2024-11-22", True, dk) == 2025
    assert C.campaign("2025-01-10", True, dk) == 2025
    assert C.campaign("2021-06-27", False, dk) == 2022  # a new career's first save
    assert C.campaign("2022-06-19", True, tr) == 2022   # Turkey rolls over on 20 June
    assert C.campaign("2022-06-20", False, tr) == 2023
    print("  PASS campaign")


def main():
    test_title()
    test_fmm27()
    test_campaign()
    return 0


if __name__ == "__main__":
    sys.exit(main())
