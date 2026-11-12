#!/usr/bin/env python3
"""`person_index` — one short row per person, right after the languages table.

    [count u32 = the person count]         32,966 on Frem, 44,960 on Truro; no 0xFF frame
    [count x 14 B] (FMM22) / [count x 15 B] (FMM27), row k = person tid k

The walk ends exactly on the staff count (4,642 / 6,212): the staff block that follows is
counted by the staff table, so the next table is per staff member. That landing is the
table's extent proof; `locate_person_index` refuses a frame that doesn't make it.

Each row holds two u16 row numbers (`ffff` for most people). `loan_slot` is the person's
slot in the loan pool (`loans.py`): set for every player on loan, 2,312 on frem-2026-06-11
and 3,010 on truro-2026-08-08, and the slot holds his tid. `row_b` is set for about 30
people and points into a table not read yet. The rest is unnamed.

FMM27's row is FMM22's with one byte inserted at +2 (always 0) and two `ff` bytes appended.
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..core import Field, Record, TableDef, RAW, U8, U16, UNKNOWN
from ..save import cache_key as _cache_key
from .languages import LANGUAGES_TABLE
from .save_header import FMM27, save_format
from .staff import locate_staff

__all__ = [
    "PERSON_INDEX",
    "PERSON_INDEX_FMM27",
    "PERSON_INDEX_TABLE",
    "PERSON_INDEX_TABLE_FMM27",
    "locate_person_index",
    "scrape_person_index",
]

PERSON_INDEX = Record("person_index", 14, (
    Field(0, 1, UNKNOWN, U8, note="0, 1 or 3"),
    Field(1, 1, UNKNOWN, U8, note="0 or 1"),
    Field(2, 2, "loan_slot", U16, note="his slot in the loan pool; ffff when not on loan"),
    Field(4, 2, "row_b", U16, note="a row in a table not read yet; set for ~30 people"),
    Field(6, 2, UNKNOWN, U16, note="ffff, or 0 where row_b is set"),
    Field(8, 1, UNKNOWN, U8, note="0, 1, 2 or 32"),
    Field(9, 5, UNKNOWN, RAW, note="0 on every row measured"),
))

PERSON_INDEX_FMM27 = Record("person_index_fmm27", 15, (
    Field(0,  1, UNKNOWN, U8, note="0, 1 or 3"),
    Field(1,  1, UNKNOWN, U8, note="0 or 1"),
    Field(2,  1, UNKNOWN, U8, note="0 on every row measured; not in FMM22"),
    Field(3,  2, "loan_slot", U16, note="his slot in the loan pool; ffff when not on loan"),
    Field(5,  2, "row_b", U16, note="a row in a table not read yet; set for ~30 people"),
    Field(7,  2, UNKNOWN, U16, note="ffff, or 0 where row_b is set"),
    Field(9,  1, UNKNOWN, U8, note="0, 1 or 8"),
    Field(10, 3, UNKNOWN, RAW, note="0 on every row measured"),
    Field(13, 2, UNKNOWN, RAW, note="ffff on every row measured; not in FMM22"),
))

_CACHE: Dict[Any, Optional[Tuple[int, int]]] = {}


def locate_person_index(mm: Any) -> Optional[Tuple[int, int]]:
    """(record 0, count) right after the languages table: a u32 equal to the person count,
    whose rows end exactly on a u32 equal to the staff count. None otherwise."""
    key = _cache_key(mm)
    if key in _CACHE:
        return _CACHE[key]
    from . import tables_for
    res = None
    spans = LANGUAGES_TABLE.spans(mm)
    persons = tables_for(mm)["person_info"].runs(mm)
    staff = locate_staff(mm)
    if spans and persons and staff:
        end = spans[-1][1]
        count = struct.unpack_from("<I", mm, end)[0]
        stride = (PERSON_INDEX_FMM27 if save_format(mm) == FMM27 else PERSON_INDEX).span
        after = end + 4 + count * stride
        if (count == persons[0][1] and after + 4 <= len(mm)
                and struct.unpack_from("<I", mm, after)[0] == staff[1]):
            res = (end + 4, count)
    _CACHE[key] = res
    return res


PERSON_INDEX_TABLE = TableDef(name="person_index", segments=(PERSON_INDEX,),
                              locator=locate_person_index)
PERSON_INDEX_TABLE_FMM27 = TableDef(name="person_index", segments=(PERSON_INDEX_FMM27,),
                                    locator=locate_person_index)


def scrape_person_index(mm: Any) -> List[Dict[str, Any]]:
    """Every row, row k for person tid k. Raises `ValueError` when not located."""
    if locate_person_index(mm) is None:
        raise ValueError("person_index: no person-count frame after languages that lands "
                         "on the staff count")
    table = PERSON_INDEX_TABLE_FMM27 if save_format(mm) == FMM27 else PERSON_INDEX_TABLE
    return table.scrape(mm)
