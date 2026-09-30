#!/usr/bin/env python3
"""Synthetic unit tests for the Player Progress table (fmparser/tables/player_progress.py)
and the injury / loan spells over it (fmparser/injuries.py). No save needed.

  LOCATE    the 62,400-row pool is found from a run of unused rows and walked both ways to
            its own edges -- a dated row at the very first slot included -- between filler
            and a zero wall; a pool of any other size is not located
  SERIES    a week's two rows are OR-ed; unused rows are skipped
  SPELLS    injured weeks and on-loan weeks grouped into spells, for any number of weeks
"""
import datetime
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser import injuries as INJ  # noqa: E402
from fmparser.tables import player_progress as PP  # noqa: E402

ROWS = 62_400                       # the pool size measured on every save, not PP.ROWS
HEADER = b"8/8/27 - Mr Manager (Frem)".ljust(250, b"\x00")
FILLER = (b"\xff" * 20 + b"\x00" * 4) * 400


def row(tid, day, year, status=0):
    return (struct.pack("<I6HHHHH", tid, 10, 11, 0xFFFF, 12, 13, 14, status, 0, day, year)
            + b"\x05\x00" * 17 + b"\xff" * 12)


def pool(rows, total=ROWS):
    body = list(rows) + [PP._EMPTY] * (total - len(rows))
    return HEADER + FILLER + b"".join(body) + b"\x00" * 8192


def d(s):
    return datetime.date.fromisoformat(s)


def doy(s):
    return d(s).timetuple().tm_yday - 1


def weeks(start, n, status):
    out, day = [], d(start)
    for _ in range(n):
        out.append((day.isoformat(), status))
        day += datetime.timedelta(days=7)
    return out


def build():
    rows = [row(9001, doy("2027-07-14"), 2027, 1)]            # the very first slot
    for when, status in weeks("2027-08-01", 3, 1) + weeks("2027-09-12", 2, 0):
        rows.append(row(9002, doy(when), int(when[:4]), status))
        rows.append(row(9002, doy(when), int(when[:4]), 0))   # the week's second row
    for when, status in weeks("2027-07-03", 5, PP.ON_LOAN):
        rows.append(row(9003, doy(when), int(when[:4]), status))
    return pool(rows)


def test_locate():
    print("TESTING the player-progress locator")
    PP._CACHE.clear()
    buf = build()
    assert PP.locate_player_progress(buf) == (len(HEADER) + len(FILLER), ROWS)
    PP._CACHE.clear()
    assert PP.locate_player_progress(pool([], ROWS - 1)) is None, "a short pool"
    print("  PASS the pool from a dated first row to the zero wall; a short pool is refused")


def test_series_and_spells():
    print("TESTING the series and the spells")
    PP._CACHE.clear()
    buf = build()
    series = PP.progress_series(buf)
    assert set(series) == {9001, 9002, 9003}
    assert series[9002][d("2027-08-01")] == 1 and series[9002][d("2027-09-12")] == 0
    inj, loan = INJ.extract_availability(buf, [9001, 9002, 9003, 9004], 2028)
    assert inj == {9001: [("2027-07-14", "2027-07-14", 1)],
                   9002: [("2027-08-01", "2027-08-15", 3)]}, inj
    assert loan == {9003: [("2027-07-03", "2027-07-31", 5)]}, loan
    print("  PASS two rows a week OR-ed; a one-week injury and a loan window as spells")


def main():
    test_locate()
    test_series_and_spells()
    return 0


if __name__ == "__main__":
    sys.exit(main())
