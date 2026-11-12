#!/usr/bin/env python3
"""`derbies` — every named rivalry: Merseyside (Everton v Liverpool), Lombardo (Atalanta v
AC Milan), Gammel Køge Landevej (Frem v Hvidovre).

The third table after the cities, behind the nation unions (`unions.py`):

    [>= 8 x ff][count u16]                 1,377 on Frem, 1,681 on Truro
    per derby:
      [id u32 = slot][uid u32]             DERBY_HEAD
      [len u32][name][terminator]          "Merseyside"
      23 bytes                             DERBY_BODY: the two clubs, then unread bytes

The terminator is 0x00 on FMM22 and 0xFF on FMM27. A club field is `ffffffff` where the
rival is not in the save's database (about half the derbies have both clubs). The six u16s
at +9 are `ffff` on every Truro derby and filled on many Frem ones, so they are career state:
something the running game records about the derby.
"""
from typing import Any, Dict, List, Optional, Tuple

from ..core import Field, PString, Record, TableDef, U8, U16, U32, UNKNOWN
from ..save import cache_key as _cache_key
from .clubs import after_frame
from .unions import unions_end

__all__ = [
    "DERBIES_TABLE",
    "DERBIES_TABLE_FMM27",
    "DERBY_BODY",
    "DERBY_HEAD",
    "derbies_end",
    "locate_derbies",
    "scrape_derbies",
]

DERBY_HEAD = Record("derby_head", 8, (
    Field(0, 4, "id", U32, note="== the slot index"),
    Field(4, 4, "uid", U32),
), is_head=True)

DERBY_BODY = Record("derby_body", 23, (
    Field(0,  4, "club_a_tid", U32, note="ffffffff when the club is not in the database"),
    Field(4,  4, "club_b_tid", U32),
    Field(8,  1, UNKNOWN, U8, note="0-200; Merseyside 180, Melbourne 150, Lanarkshire 95"),
    Field(9,  2, UNKNOWN, U16, note="ffff on every Truro derby; career state on Frem"),
    Field(11, 2, UNKNOWN, U16, note="ffff on every Truro derby"),
    Field(13, 2, UNKNOWN, U16, note="ffff on every Truro derby"),
    Field(15, 2, UNKNOWN, U16, note="0-4"),
    Field(17, 2, UNKNOWN, U16, note="0-3"),
    Field(19, 2, UNKNOWN, U16, note="0-4"),
    Field(21, 2, UNKNOWN, U16, note="0-4"),
))

_CACHE: Dict[Any, Optional[Tuple[int, int]]] = {}


def locate_derbies(mm: Any) -> Optional[Tuple[int, int]]:
    """(record 0, declared count): the frame right after the unions, whose record 0 is
    derby 0."""
    key = _cache_key(mm)
    if key in _CACHE:
        return _CACHE[key]
    res = None
    end = unions_end(mm)
    loc = after_frame(mm, end, 2) if end is not None else None
    if loc is not None and int.from_bytes(mm[loc[0]:loc[0] + 4], "little") == 0:
        res = loc
    _CACHE[key] = res
    return res


def _table(terminator: int) -> TableDef:
    return TableDef(
        name="derbies",
        segments=(DERBY_HEAD, PString("name", null_terminated=True, terminator=terminator),
                  DERBY_BODY),
        locator=locate_derbies,
        invariant=lambda rec, slot: rec["id"] == slot,
    )


DERBIES_TABLE = _table(0x00)
DERBIES_TABLE_FMM27 = _table(0xFF)


def derbies_table(mm: Any) -> TableDef:
    from .save_header import FMM27, save_format
    return DERBIES_TABLE_FMM27 if save_format(mm) == FMM27 else DERBIES_TABLE


def derbies_end(mm: Any) -> Optional[int]:
    """The byte after the last derby, or None when the table is not located."""
    spans = derbies_table(mm).spans(mm)
    return spans[-1][1] if spans else None


def scrape_derbies(mm: Any) -> List[Dict[str, Any]]:
    """Every derby, in id order. Raises `ValueError` when not located or read short."""
    loc = locate_derbies(mm)
    if loc is None:
        raise ValueError("derbies: no frame after the unions")
    rows = derbies_table(mm).scrape(mm)
    if len(rows) != loc[1]:
        raise ValueError(f"derbies: walk read {len(rows)} of {loc[1]} declared")
    return rows
