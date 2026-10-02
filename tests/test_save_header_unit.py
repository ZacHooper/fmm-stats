#!/usr/bin/env python3
"""Unit tests for the save header (fmparser/tables/save_header.py), no save needed.

  TITLE     the 250-byte NUL-padded title reads to date / manager / nickname
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
                 "manager": "Mr Manager", "nickname": "Frem"}, h
    h = H.read_save_header(header("1/4/23 - Herr Manager (Bucaspor 1928)"))
    assert (h["date"], h["manager"], h["nickname"]) == ("2023-04-01", "Herr Manager",
                                                       "Bucaspor 1928")
    # a title that does not read keeps the text and names nothing
    for bad in ("Mr Manager (Frem)", "31/2/23 - Mr Manager (Frem)", ""):
        h = H.read_save_header(header(bad))
        assert h["title"] == bad and h["date"] is None and h["nickname"] is None, (bad, h)
    print("  PASS title")


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
    test_campaign()
    return 0


if __name__ == "__main__":
    sys.exit(main())
