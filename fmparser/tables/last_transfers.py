#!/usr/bin/env python3
"""`last_transfers` — each player's latest transfer: the fee and the buying club.

One 30-byte row per player attribute record, straight after the transfer band:

    [count u32 = the player attribute count]     26,505 on Frem, 36,344 on Truro
    [count x 30 B], row k = attribute record k

A row is empty (`EMPTY` in its first 26 bytes) for a player never transferred since the
career began: all of them on a day-one save, 10,323 filled of 26,505 on frem-2026-06-11, 428
of 36,344 on truro-2026-08-08. Every filled row names a person at +10, and on
truro-2026-08-08 every one is a player with an accepted bid in the transfer band, the
buying club the bid's (424 of 428) and the fee its fee (418). Filled rows survive the July
rollover that empties the band (5,016 on frem-2023-07-02, two days after it), so a row is
the player's latest move, not just this window's.

Every row, filled or empty, ends in the same date: the save's own day. That is the table's
invariant, and how it is found: the transfer band in front has no parser table, so the
locator takes the first u32 equal to the player attribute count after the loan pool whose
rows all end in one valid date.
"""
import struct
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from ..core import DATE, Field, Record, TableDef, RAW, U8, U16, U32, UNKNOWN
from ..save import cache_key as _cache_key

__all__ = ["EMPTY", "LAST_TRANSFER", "LAST_TRANSFERS_TABLE", "last_transfers_table_spans",
           "locate_last_transfers", "scrape_last_transfers"]

LAST_TRANSFER = Record("last_transfer", 30, (
    Field(0,  4, "fee", U32, note="pounds; 0 on a free"),
    Field(4,  4, UNKNOWN, RAW, note="0 on every filled row"),
    Field(8,  2, "club_tid", U16, note="the buying club"),
    Field(10, 2, "tid", U16, note="the player"),
    Field(12, 2, UNKNOWN, RAW, note="0 on every filled row"),
    Field(14, 1, UNKNOWN, U8, note="1; 8 on 14 rows of frem-2026-06-11"),
    Field(15, 3, UNKNOWN, RAW, note="0 on every filled row"),
    Field(18, 4, UNKNOWN, U32, note="equal to fee on every filled row measured"),
    Field(22, 4, UNKNOWN, RAW, note="0 on every filled row"),
    Field(26, 4, "as_of", DATE, note="the save's own day, on every row"),
))

EMPTY = bytes.fromhex("ffffffffffffffffffffffffffff00000000ffffffffffffffff")
STRIDE = LAST_TRANSFER.span

_CACHE: Dict[Any, Optional[Tuple[int, int]]] = {}


def _one_date(mm: Any, base: int, n: int) -> bool:
    stamp = mm[base + 26:base + 30]
    day, year = struct.unpack("<HH", stamp)
    try:
        date(year, 1, 1) + timedelta(days=day)
    except (ValueError, OverflowError):
        return False
    if not 1900 < year < 2200 or day > 365:
        return False
    return all(mm[base + k * STRIDE + 26:base + k * STRIDE + 30] == stamp for k in range(n))


def locate_last_transfers(mm: Any) -> Optional[Tuple[int, int]]:
    """(row 0, count): the first u32 equal to the player attribute count after the loan
    pool whose rows all end in the same valid date. None otherwise."""
    key = _cache_key(mm)
    if key in _CACHE:
        return _CACHE[key]
    from . import first_record, tables_for
    from .loans import loans_table_spans
    res = None
    runs = tables_for(mm)["player_attributes"].runs(mm)
    loans = loans_table_spans(mm)
    hi = first_record(mm, "surnames")
    if runs and loans and hi:
        n = runs[0][1]
        sig = struct.pack("<I", n)
        hit = mm.find(sig, loans[0][1], hi)
        while hit != -1:
            base = hit + 4
            if base + n * STRIDE <= hi and _one_date(mm, base, n):
                res = (base, n)
                break
            hit = mm.find(sig, hit + 1, hi)
    _CACHE[key] = res
    return res


def last_transfers_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """The table, its u32 count included."""
    loc = locate_last_transfers(mm)
    return [(loc[0] - 4, loc[0] + loc[1] * STRIDE)] if loc else []


LAST_TRANSFERS_TABLE = TableDef(name="last_transfers", segments=(LAST_TRANSFER,),
                                locator=locate_last_transfers, include_offset=True)


def scrape_last_transfers(mm: Any) -> List[Dict[str, Any]]:
    """Every filled row, in attribute-record order, with its `row` (the attribute record
    index). Raises `ValueError` when the table is not located."""
    loc = locate_last_transfers(mm)
    if loc is None:
        raise ValueError("last_transfers: no player-count frame after the loans whose rows "
                         "all end in one date")
    base = loc[0]
    out = []
    for rec in LAST_TRANSFERS_TABLE.scrape(mm):
        off = rec.pop("offset")
        if mm[off:off + len(EMPTY)] == EMPTY:
            continue
        out.append({"row": (off - base) // STRIDE, **rec})
    return out
