#!/usr/bin/env python3
"""`person_stamps` — a dated 4-byte row per person, after our matches.

    [01][01][count u32 = person count - 1]    32,965 on Frem, 44,959 on Truro
    [count x 4 B], row k = person tid k, for every tid but the last

The last tid has no row: on every save measured it is non-playing staff at the managed club
who joined on the career's first day, which is the user's own manager.

Each row is `[u8 level][u16 day][u8 year offset]`, a date counted from 1 January of the
save's database year (2021 on FMM22, 2026 on FMM27): day 203 with offset 0 is 22 July, the
first day of both careers, and most rows hold it. Rows that moved on hold the last rollover
(day 180, offset 4 = 29 June 2025 on frem-2026-06-11). `level` is 0-3, and 3 on every
player of the managed club on every save measured; staff there can be 0 or 1.

The table sits after our matches, and on FMM22 behind five u16 nation ids that are not read.
On a save with no matches it is found the same way: the one `[01][01][person count - 1]`
between the training table and the player lists.
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..core import Field, Record, TableDef, U8, U16, UNKNOWN
from ..save import cache_key as _cache_key
from .training import locate_training

__all__ = [
    "PERSON_STAMP",
    "PERSON_STAMPS_TABLE",
    "locate_person_stamps",
    "scrape_person_stamps",
]

PERSON_STAMP = Record("person_stamp", 4, (
    Field(0, 1, "level", U8, note="0-3; 3 on every player of the managed club"),
    Field(1, 2, "day", U16, note="day of year"),
    Field(3, 1, "year_offset", U8, note="years after the database year (2021 / 2026)"),
))

TRAINING_STRIDE = 61
_CACHE: Dict[Any, Optional[Tuple[int, int]]] = {}


def locate_person_stamps(mm: Any) -> Optional[Tuple[int, int]]:
    """(record 0, count): the only `[01][01][person count - 1]` between the training table
    and the player lists. None when there is not exactly one."""
    key = _cache_key(mm)
    if key in _CACHE:
        return _CACHE[key]
    from . import first_record, tables_for
    res = None
    persons = tables_for(mm)["person_info"].runs(mm)
    training = locate_training(mm)
    lists = first_record(mm, "player_lists")
    if persons and training and lists:
        count = persons[0][1] - 1
        sig = b"\x01\x01" + struct.pack("<I", count)
        lo = training[0] + training[1] * TRAINING_STRIDE
        hit = mm.find(sig, lo, lists)
        if hit != -1 and mm.find(sig, hit + 1, lists) == -1 and hit + 6 + 4 * count <= lists:
            res = (hit + 6, count)
    _CACHE[key] = res
    return res


PERSON_STAMPS_TABLE = TableDef(name="person_stamps", segments=(PERSON_STAMP,),
                               locator=locate_person_stamps)


def scrape_person_stamps(mm: Any) -> List[Dict[str, Any]]:
    """Every row, row k for person tid k. Raises `ValueError` when not located."""
    if locate_person_stamps(mm) is None:
        raise ValueError("person_stamps: no single [01][01][person count - 1] after training")
    return PERSON_STAMPS_TABLE.scrape(mm)
