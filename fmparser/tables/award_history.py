#!/usr/bin/env python3
"""`award_history` — past editions of every award: the date, and the 1st to 3rd placed.

The awards table (`awards.py`) holds each award's latest edition; this holds them all, the
"Season / Winner" list on an award's screen: every year of an annual award, and only the
current season of a weekly or monthly one (week by week, month by month). It sits
straight after the training table:

    [count u32]                            807 on day one, 1,364 on frem-2026-06-11
    per edition, 92 bytes:
      [award_id u32][day u16][year u16]    the award (an awards row) and the edition's date
      3 x 28 B                             1st, 2nd, 3rd

An annual award's date is day 0 of its year (1 January); a monthly award's is the 1st of the
month after the one it is for (September's Player of the Month is dated 1 October); a weekly
award's is a Tuesday.
Each placed entry stores the person's three name ids as they were, as the awards table
does, because his tid is a slot. An unfilled place is all `ff`.

On every save measured the latest edition of each award names the same 1st as the awards
table: 265 of 265 awards with a winner on frem-2026-06-11, 340 of 340 on truro-2026-08-08.
"""
from typing import Any, Dict, List, Optional, Tuple

from ..core import DATE, Field, FixedList, Record, TableDef, U32, UNKNOWN
from ..save import cache_key as _cache_key
from .training import locate_training

__all__ = ["AWARD_EDITION", "AWARD_PLACE", "AWARD_HISTORY_TABLE", "locate_award_history",
           "scrape_award_history"]

AWARD_EDITION = Record("award_edition", 8, (
    Field(0, 4, "award_id", U32, note="an awards row's id"),
    Field(4, 4, "date", DATE, note="1 January for an annual award; the 1st of the "
                                   "month after for a monthly one"),
), is_head=True)

AWARD_PLACE = Record("award_place", 28, (
    Field(0,  4, "person_tid", U32, note="ffffffff on an unfilled place"),
    Field(4,  4, "first_name_id", U32, note="his name as it was"),
    Field(8,  4, "last_name_id", U32),
    Field(12, 4, "common_name_id", U32, note="ffffffff when he has none"),
    Field(16, 4, "club_tid", U32),
    Field(20, 4, UNKNOWN, U32, note="0 on every FMM27 place; small numbers on many FMM22 ones"),
    Field(24, 4, "score", U32, note="votes, or goals on a Top Goalscorer"),
))

TRAINING_STRIDE = 61
_CACHE: Dict[Any, Optional[Tuple[int, int]]] = {}


def locate_award_history(mm: Any) -> Optional[Tuple[int, int]]:
    """(edition 0, count): the u32 count straight after the training table."""
    key = _cache_key(mm)
    if key in _CACHE:
        return _CACHE[key]
    res = None
    tr = locate_training(mm)
    if tr is not None:
        at = tr[0] + tr[1] * TRAINING_STRIDE
        res = (at + 4, int.from_bytes(mm[at:at + 4], "little"))
    _CACHE[key] = res
    return res


def _award_count(mm: Any) -> int:
    from .awards import locate_awards
    loc = locate_awards(mm)
    return loc[1] if loc else 0


AWARD_HISTORY_TABLE = TableDef(
    name="award_history",
    segments=(AWARD_EDITION, FixedList("places", AWARD_PLACE, 3)),
    locator=locate_award_history,
)


def award_history_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """The table, its u32 count included."""
    loc = locate_award_history(mm)
    return [(loc[0] - 4, loc[0] + loc[1] * 92)] if loc else []


def scrape_award_history(mm: Any) -> List[Dict[str, Any]]:
    """Every edition, in stored order. Raises `ValueError` when not located, when the walk
    is short, or when an edition names an award the awards table doesn't have."""
    loc = locate_award_history(mm)
    if loc is None:
        raise ValueError("award_history: the training table is not located")
    rows = AWARD_HISTORY_TABLE.scrape(mm)
    if len(rows) != loc[1]:
        raise ValueError(f"award_history: walk read {len(rows)} of {loc[1]} declared")
    awards = _award_count(mm)
    bad = [r["award_id"] for r in rows if r["award_id"] >= awards]
    if bad:
        raise ValueError(f"award_history: {len(bad)} editions name no award (first {bad[0]})")
    return rows
