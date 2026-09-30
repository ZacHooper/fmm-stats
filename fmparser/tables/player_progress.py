#!/usr/bin/env python3
"""`player_progress` -- the weekly Player Progress table: one row per tracked player per week.

The in-game Player Progress page (the weekly skill-line graph with Injured / Off-Season /
On-loan bands) is this table. A fixed pool of 62,400 rows of 70 bytes -- the same count on
every save of both careers -- with no count in front of it:

    +0   player_tid u32   0xffffffff = an unused row
    +4   6 x u16          the graph's skill lines, 1-20; one slot reads 0xffff (slot 2 for
                          an outfield player, slots 3-4 for a goalkeeper)
    +16  status u16       bitfield: bits 0-1 (3) injured that week, bit 3 (8), bit 4 (16)
                          the off-season week at the season boundary, bit 5 (32) out on
                          loan, bit 6 (64)
    +18  u16              0 on every row
    +20  day u16          day-of-year, 0-based
    +22  year u16         0x07E4 on an unused row
    +24  23 x u16         1-20 or 0xffff: 17 filled for an outfield player, 6 for a
                          goalkeeper; unread

An unused row is one fixed template (tid, lines, day and the +24 block all 0xff; year
0x07E4). The players tracked are the managed club's squad and reserves (35 on
frem-2027-06-15), back to their first week at the club. A week is usually one row; a few are
two to four, in slots anywhere in the pool (the game recycles rows), and the copies can
disagree on the status bits and the lines. `scrape_player_progress` hands every used row over
as stored; what the bits mean for a player is read in the mart.

Located from a run of unused rows, then walked both ways, row by row, while each row is an
unused row or a dated one (`+18` 0, a day of the year, a year from the 0x07E4 sentinel to the
year after the save's own date); the pool must come out at 62,400 rows.
"""
import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..core import Field, PAD, RAW, Record, TableDef, U16, U32, UNKNOWN
from ..save import cache_key as _cache_key
from .save_header import read_save_header

__all__ = [
    "PLAYER_PROGRESS_TABLE",
    "PROGRESS_ROW",
    "ROWS",
    "locate_player_progress",
    "scrape_player_progress",
]

ROWS = 62_400                    # rows in the pool, on every save
NO_PLAYER = 0xFFFFFFFF
EMPTY_YEAR = 0x07E4
NO_LINE = 0xFFFF
LINES = tuple(f"line_{i}" for i in range(6))

PROGRESS_ROW = Record("player_progress_row", 70, [
    Field(0, 4, "player_tid", U32, note="0xffffffff = unused row"),
    Field(4, 2, "line_0", U16),
    Field(6, 2, "line_1", U16),
    Field(8, 2, "line_2", U16, note="0xffff for an outfield player"),
    Field(10, 2, "line_3", U16, note="0xffff for a goalkeeper"),
    Field(12, 2, "line_4", U16, note="0xffff for a goalkeeper"),
    Field(14, 2, "line_5", U16),
    Field(16, 2, "status", U16, note="bitfield: 3 injured, 16 off-season, 32 on loan"),
    Field(18, 2, UNKNOWN, PAD),
    Field(20, 2, "day", U16, note="day-of-year, 0-based"),
    Field(22, 2, "year", U16, note="0x07E4 on an unused row"),
    Field(24, 46, UNKNOWN, RAW),
])

_STRIDE = PROGRESS_ROW.span
_EMPTY = (b"\xff" * 16 + b"\x00" * 4 + b"\xff\xff" + EMPTY_YEAR.to_bytes(2, "little")
          + b"\xff" * 46)
_CACHE: Dict[Any, Optional[Tuple[int, int]]] = {}


def _is_row(mm: Any, o: int, last_year: int) -> bool:
    if o < 0 or o + _STRIDE > len(mm):
        return False
    row = mm[o:o + _STRIDE]
    if row == _EMPTY:
        return True
    zero, day, year = int.from_bytes(row[18:20], "little"), \
        int.from_bytes(row[20:22], "little"), int.from_bytes(row[22:24], "little")
    return zero == 0 and day <= 365 and EMPTY_YEAR <= year <= last_year


def locate_player_progress(mm: Any) -> Optional[Tuple[int, int]]:
    """(base, 62400), or None."""
    key = _cache_key(mm)
    if key in _CACHE:
        return _CACHE[key]
    res = None
    seed = mm.find(_EMPTY * 2)
    date = read_save_header(mm)["date"]
    if seed >= 0 and date:
        last_year = int(date[:4]) + 1
        lo = seed
        while _is_row(mm, lo - _STRIDE, last_year):
            lo -= _STRIDE
        hi = seed
        while _is_row(mm, hi, last_year):
            hi += _STRIDE
        if (hi - lo) // _STRIDE == ROWS:
            res = (lo, ROWS)
    _CACHE[key] = res
    return res


PLAYER_PROGRESS_TABLE = TableDef(
    name="player_progress",
    segments=(PROGRESS_ROW,),
    locator=locate_player_progress,
)


def scrape_player_progress(mm: Any) -> List[Dict[str, Any]]:
    """Every used row, in pool order: {tid, week, status, line_0..line_5}, `week` an ISO date
    and a line None where it reads 0xffff. Raises `ValueError` if the pool is not located."""
    rows = PLAYER_PROGRESS_TABLE.scrape(mm)
    if not rows:
        raise ValueError(f"player_progress: the {ROWS}-row pool is not located")
    out = []
    for r in rows:
        if r["player_tid"] == NO_PLAYER:
            continue
        week = datetime.date(r["year"], 1, 1) + datetime.timedelta(days=r["day"])
        rec = {"tid": r["player_tid"], "week": week.isoformat(), "status": r["status"]}
        rec.update((k, None if r[k] == NO_LINE else r[k]) for k in LINES)
        out.append(rec)
    return out
