#!/usr/bin/env python3
"""`club_titles` — the managed club's titles: each competition won, and the years.

After the club seasons pool (`club_seasons.py`), one `00` byte and a run of 550 `ff` (both on
every save measured), then a pool of 32 slots of 65 bytes:

    [u8 count]
    count x [cid u16][club_tid u16][30 x year u16][u8 n_years]   years beyond n_years are ffff
    32 - count empty slots: 64 x ff, then 00

One entry per competition, its years in order: on frem-2030-06-22 the 3. Division 2021,
2. Division 2022, NordicBet Liga 2023 and 3F Superliga 2028 and 2029. Every title year reads
position index 0 in that league in the club seasons.

**How it is found.** From the club seasons pool's end, skip the `00` and the `ff` run; the
locator accepts the count only if every entry names one club, holds at most 30 years with
`ffff` after them, and the rest of the 32 slots are empty.
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..core import Field, Record, TableDef, U8, U16
from ..save import cache_key as _cache_key

__all__ = ["CLUB_TITLE", "CLUB_TITLES_TABLE", "SLOTS", "club_titles_table_spans",
           "locate_club_titles", "scrape_club_titles"]

SLOTS = 30 + 2
YEARS = 30

CLUB_TITLE = Record("club_title", 65, (
    Field(0, 2, "cid", U16, note="the competition won"),
    Field(2, 2, "club_tid", U16, note="the managed club"),
    *[Field(4 + 2 * i, 2, f"year_{i}", U16, group="years") for i in range(YEARS)],
    Field(64, 1, "n_years", U8, note="years used; the rest read ffff"),
))

EMPTY = b"\xff" * 64 + b"\x00"
_CACHE: Dict[Any, Optional[Tuple[int, int]]] = {}


def _entry_ok(mm: Any, o: int) -> bool:
    n = mm[o + 64]
    return n <= YEARS and all(b == 0xFF for b in mm[o + 4 + 2 * n:o + 64])


def locate_club_titles(mm: Any) -> Optional[Tuple[int, int]]:
    """(entry 0, count), or None unless the entries read and the rest of the 32 slots are
    empty."""
    key = _cache_key(mm)
    if key in _CACHE:
        return _CACHE[key]
    from .club_seasons import club_seasons_table_spans
    res = None
    spans = club_seasons_table_spans(mm)
    if spans:
        at = spans[0][1]
        if mm[at] == 0:
            j = at + 1
            while j < len(mm) and mm[j] == 0xFF:
                j += 1
            count, base = mm[j], j + 1
            clubs = {struct.unpack_from("<H", mm, base + 65 * k + 2)[0] for k in range(count)}
            if (j - at - 1 >= 8 and count <= SLOTS and len(clubs) <= 1
                    and all(_entry_ok(mm, base + 65 * k) for k in range(count))
                    and all(mm[base + 65 * k:base + 65 * (k + 1)] == EMPTY
                            for k in range(count, SLOTS))):
                res = (base, count)
    _CACHE[key] = res
    return res


def club_titles_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """The pool, its count byte and empty slots included."""
    loc = locate_club_titles(mm)
    return [(loc[0] - 1, loc[0] + SLOTS * 65)] if loc else []


def _post(rec: Dict[str, Any], off: int) -> Dict[str, Any]:
    years = [rec[f"year_{i}"] for i in range(rec["n_years"])]
    return {"cid": rec["cid"], "club_tid": rec["club_tid"], "years": years}


CLUB_TITLES_TABLE = TableDef(name="club_titles", segments=(CLUB_TITLE,),
                             locator=locate_club_titles, post_process=_post)


def scrape_club_titles(mm: Any) -> List[Dict[str, Any]]:
    """Every competition won, in stored order. Raises `ValueError` when not located."""
    if locate_club_titles(mm) is None:
        raise ValueError("club_titles: the pool after the club seasons does not read")
    return CLUB_TITLES_TABLE.scrape(mm)
