#!/usr/bin/env python3
"""`staff_rows` — one 8-byte row per member of staff, straight after the per-person rows.

    [count u16 = the staff count]          4,642 on Frem, 5,697 on Bucaspor, 6,212 on Truro
    [count x 8 B], row k = staff id2 k     the same 8 bytes on FMM22 and FMM27

No 0xFF frame: the count sits flush against the per-person rows' end (`person_index.py`),
and the walk ends exactly on a u16 equal to the club count, the count in front of
`club_rows`. That landing, on every save of both games, is the table's extent proof.

What the row holds is open. On frem-2026-06-11, 943 rows are not all zero, and they are
managers', employed or not. On 938 of those 943, the u16 at +5 is at most three times the
byte at +7 (+7 tops out at 49), which is the shape of a league record: points and games.
That is a lead, not a reading. On a day-one save (frem-2021-06-27) every row is zero but
+7, and on truro-2026-07-22 almost every row is zero.
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..core import Field, Record, TableDef, U8, U16, UNKNOWN
from ..save import cache_key as _cache_key

__all__ = ["STAFF_ROW", "STAFF_ROWS_TABLE", "locate_staff_rows", "scrape_staff_rows",
           "staff_rows_end", "staff_rows_table_spans"]

STAFF_ROW = Record("staff_row", 8, (
    Field(0, 2, UNKNOWN, U16, note="0 to ~830; on Frem's user row 202 / 424 / 829 in 2023 / "
                                   "2026 / 2030"),
    Field(2, 2, UNKNOWN, U16, note="0 on ~99% of rows"),
    Field(4, 1, UNKNOWN, U8, note="0 on ~97% of rows"),
    Field(5, 2, UNKNOWN, U16, note="at most 3 x +7 on 938 of 943 non-zero rows: points?"),
    Field(7, 1, UNKNOWN, U8, note="0 to 49: games?"),
))

_CACHE: Dict[Any, Optional[Tuple[int, int]]] = {}


def _club_count(mm: Any) -> Optional[int]:
    from . import tables_for
    runs = tables_for(mm)["clubs"].runs(mm)
    return runs[0][1] if runs else None


def locate_staff_rows(mm: Any) -> Optional[Tuple[int, int]]:
    """(row 0, count): a u16 equal to the staff count where the per-person rows end, whose
    rows end exactly on a u16 equal to the club count. None otherwise."""
    key = _cache_key(mm)
    if key in _CACHE:
        return _CACHE[key]
    from .person_index import PERSON_INDEX, PERSON_INDEX_FMM27, locate_person_index
    from .save_header import FMM27, save_format
    from .staff import locate_staff
    res = None
    pi, staff, clubs = locate_person_index(mm), locate_staff(mm), _club_count(mm)
    if pi and staff and clubs:
        stride = (PERSON_INDEX_FMM27 if save_format(mm) == FMM27 else PERSON_INDEX).span
        at = pi[0] + pi[1] * stride
        count = struct.unpack_from("<H", mm, at)[0]
        end = at + 2 + count * STAFF_ROW.span
        if (count == staff[1] and end + 2 <= len(mm)
                and struct.unpack_from("<H", mm, end)[0] == clubs):
            res = (at + 2, count)
    _CACHE[key] = res
    return res


def staff_rows_end(mm: Any) -> Optional[int]:
    """Where the last row ends: the club rows' count."""
    loc = locate_staff_rows(mm)
    return loc[0] + loc[1] * STAFF_ROW.span if loc else None


def staff_rows_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """The rows, their u16 count included."""
    loc = locate_staff_rows(mm)
    return [(loc[0] - 2, staff_rows_end(mm))] if loc else []


STAFF_ROWS_TABLE = TableDef(name="staff_rows", segments=(STAFF_ROW,), locator=locate_staff_rows)


def scrape_staff_rows(mm: Any) -> List[Dict[str, Any]]:
    """Every row, row k for staff id2 k. Raises `ValueError` when not located."""
    if locate_staff_rows(mm) is None:
        raise ValueError("staff_rows: no staff count after the per-person rows that lands on "
                         "the club count")
    return STAFF_ROWS_TABLE.scrape(mm)
