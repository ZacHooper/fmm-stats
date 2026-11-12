#!/usr/bin/env python3
"""`awards` — every award the game hands out, each with its latest three placed entries.

The first of four count-framed tables between the cities and the currencies: awards, nation
unions (`unions.py`), derbies (`derbies.py`), regions (`regions.py`). Each starts at the end
of the one before, behind `[>= 8 x 0xFF][count]`.

    [>= 8 x ff][count u32]                 807 on Frem, 1,123 on Truro
    per award:
      [id u32 = slot][uid u32]             AWARD_HEAD
      [len u32][name][terminator]          "Footballer of the Year"
      [len u32][long name][terminator]     "World Footballer of the Year"
      23 bytes                             AWARD_BODY: continent, nation, competition, a date
      3 x 26 bytes                         AWARD_ENTRY: person, club, year, score, name ids
      (FMM27 only) 1 byte                  AWARD_TAIL_FMM27

The terminator is 0x00 on FMM22 and 0xFF on FMM27, as in every FMM27 string table.

The three entries are the award's latest edition, not its history: a 2026 save carries each
award's last result and nothing earlier, so a history comes from keeping snapshots. An
unfilled entry is all `ff` except its year. Each entry stores the winner's three name ids as
they were when he won, because his tid is a slot that a newgen can take over later.
"""
from typing import Any, Dict, List, Optional, Tuple

from ..core import FixedList, Field, PString, Record, TableDef, RAW, U8, U16, U32, UNKNOWN
from ..save import cache_key as _cache_key
from .cities import CITY_RECORD, locate_cities
from .clubs import after_frame

__all__ = [
    "AWARDS_TABLE",
    "AWARDS_TABLE_FMM27",
    "AWARD_BODY",
    "AWARD_ENTRY",
    "AWARD_HEAD",
    "AWARD_TAIL_FMM27",
    "awards_end",
    "locate_awards",
    "scrape_awards",
]

AWARD_HEAD = Record("award_head", 8, (
    Field(0, 4, "id", U32, note="== the slot index"),
    Field(4, 4, "uid", U32),
), is_head=True)

AWARD_BODY = Record("award_body", 23, (
    Field(0,  2, "continent_id", U16, note="ffff on worldwide awards; the nation's continent "
                                           "where nation_id is set"),
    Field(2,  2, "nation_id", U16, note="ffff on continental and worldwide awards"),
    Field(4,  2, "cid", U16, note="the competition the award belongs to; ffff for a "
                                  "nation-wide award (Danish Player of the Year)"),
    Field(6,  1, UNKNOWN, U8, note="37 on most; 4 on Top Goalscorer, 3 on Manager of the Year"),
    Field(7,  1, UNKNOWN, U8, note="1 on player awards, 7 on Team of the Year/Week, 2 on "
                                   "manager awards"),
    Field(8,  1, UNKNOWN, U8, note="0-3"),
    Field(9,  1, UNKNOWN, U8, note="2-6"),
    Field(10, 1, UNKNOWN, U8, note="0, 1, 12, 30 or 128"),
    Field(11, 1, UNKNOWN, U8, note="0, 24, 63 or 64"),
    Field(12, 3, UNKNOWN, RAW, note="0 except 3 at +14 on six FMM27 awards"),
    Field(15, 1, UNKNOWN, U8, note="1-5; 1 on every Team of the Week"),
    Field(16, 2, "last_day", U16, note="day of year the latest edition was decided"),
    Field(18, 2, "last_year", U16, note="1900 (with day 1) when never awarded"),
    Field(20, 1, UNKNOWN, U8, note="0 or 14-18"),
    Field(21, 1, UNKNOWN, U8, note="0 or 20-23"),
    Field(22, 1, UNKNOWN, U8, note="0-3"),
))

AWARD_ENTRY = Record("award_entry", 26, (
    Field(0,  4, "person_tid", U32, note="ffffffff on an unfilled entry"),
    Field(4,  4, "club_tid", U32, note="the winner's club when he won; ffffffff when none"),
    Field(8,  2, "year", U16),
    Field(10, 2, "score", U16, note="votes on a voted award, goals on a Top Goalscorer"),
    Field(12, 2, UNKNOWN, U16, note="FMM22 1-30 on filled entries; 0 on every FMM27 one"),
    Field(14, 4, "first_name_id", U32, note="the winner's first-name id when he won"),
    Field(18, 4, "last_name_id", U32),
    Field(22, 4, "common_name_id", U32, note="ffffffff when he has none"),
))

AWARD_TAIL_FMM27 = Record("award_tail_fmm27", 1, (
    Field(0, 1, UNKNOWN, U8, note="0 or 1"),
), is_head=True)

ENTRIES_PER_AWARD = 3


def _segments(terminator: int) -> Tuple[Any, ...]:
    return (
        AWARD_HEAD,
        PString("name", null_terminated=True, terminator=terminator),
        PString("long_name", null_terminated=True, terminator=terminator),
        AWARD_BODY,
        FixedList("entries", AWARD_ENTRY, ENTRIES_PER_AWARD),
    )


_CACHE: Dict[Any, Optional[Tuple[int, int]]] = {}


def locate_awards(mm: Any) -> Optional[Tuple[int, int]]:
    """(record 0, declared count): the frame right after the cities table, whose record 0
    is award 0."""
    key = _cache_key(mm)
    if key in _CACHE:
        return _CACHE[key]
    res = None
    cities = locate_cities(mm)
    if cities is not None:
        loc = after_frame(mm, cities[0] + cities[1] * CITY_RECORD, 4)
        if loc is not None and int.from_bytes(mm[loc[0]:loc[0] + 4], "little") == 0:
            res = loc
    _CACHE[key] = res
    return res


AWARDS_TABLE = TableDef(
    name="awards",
    segments=_segments(0x00),
    locator=locate_awards,
    invariant=lambda rec, slot: rec["id"] == slot,
)

AWARDS_TABLE_FMM27 = TableDef(
    name="awards",
    segments=_segments(0xFF) + (AWARD_TAIL_FMM27,),
    locator=locate_awards,
    invariant=lambda rec, slot: rec["id"] == slot,
)


def awards_table(mm: Any) -> TableDef:
    from .save_header import FMM27, save_format
    return AWARDS_TABLE_FMM27 if save_format(mm) == FMM27 else AWARDS_TABLE


def awards_end(mm: Any) -> Optional[int]:
    """The byte after the last award, or None when the table is not located."""
    spans = awards_table(mm).spans(mm)
    return spans[-1][1] if spans else None


def scrape_awards(mm: Any) -> List[Dict[str, Any]]:
    """Every award, in id order. Raises `ValueError` when the table is not located or its
    walk stops short of the declared count."""
    loc = locate_awards(mm)
    if loc is None:
        raise ValueError("awards: no frame after the cities table")
    rows = awards_table(mm).scrape(mm)
    if len(rows) != loc[1]:
        raise ValueError(f"awards: walk read {len(rows)} of {loc[1]} declared")
    return rows
