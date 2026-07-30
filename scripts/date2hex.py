#!/usr/bin/env python3
"""
date2hex — turn a calendar date into the hex byte patterns to search for in a save.

In the light-result / fixture grid the date sits as two little-endian u16s:
    [+12 year][+14 day-of-year]  ->  bytes:  <yr_lo> <yr_hi> <day_lo> <day_hi>

The year encoding is offset (see docs/STANDINGS_HANDOFF.md), and day-of-year is
seen both 0- and 1-indexed, so this prints every plausible pattern to try.

Usage:
    python3 scripts/date2hex.py 2021-09-18
    python3 scripts/date2hex.py 2021-09-18 2022-01-22      # several at once
    python3 scripts/date2hex.py 2021                       # just a year -> year bytes
"""
import sys
from datetime import date


def le16(v: int) -> str:
    """u16 little-endian as space-separated hex bytes, e.g. 2021 -> 'e5 07'."""
    return f"{v & 0xFF:02x} {(v >> 8) & 0xFF:02x}"


def report(s: str):
    parts = s.split("-")
    if len(parts) == 1:                      # year only
        yr = int(parts[0])
        print(f"\n{yr}")
        print(f"  year u16 LE : {le16(yr)}   (also try {yr-1}: {le16(yr-1)})")
        return

    d = date.fromisoformat(s)
    doy0 = (d - date(d.year, 1, 1)).days     # 0-indexed (matches the one clean sample)
    doy1 = doy0 + 1                           # 1-indexed
    print(f"\n{d.isoformat()}  (day-of-year: {doy0} 0-idx / {doy1} 1-idx)")
    for yr in (d.year, d.year - 1):           # real year and the -1 offset variant
        lbl = "" if yr == d.year else "  [year-1 offset]"
        print(f"  year {yr}{lbl}")
        print(f"    date pattern (yr+day, 0-idx): {le16(yr)} {le16(doy0)}")
        print(f"    date pattern (yr+day, 1-idx): {le16(yr)} {le16(doy1)}")
        print(f"    day only 0-idx: {le16(doy0)}    day only 1-idx: {le16(doy1)}")


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    for a in args:
        report(a)


if __name__ == "__main__":
    main()
