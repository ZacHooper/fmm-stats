#!/usr/bin/env python3
"""`unions` — the six nation unions: European Union, European Economic Area, the
African, Caribbean and Pacific group, the Overseas Territories Act, the Turkic states and
EFTA.

The second table after the cities, right behind the awards (`awards.py`):

    [>= 8 x ff][count u16 = 6]
    per union: [id u16 = slot + 1][len u32][name][terminator]

Six on both games; only two names changed for FMM27 ("Organisation of African, Caribbean
and Pacific States", "Organization of Turkic States"). The terminator is 0x00 on FMM22 and
0xFF on FMM27. Which nations belong to a union is not stored here.
"""
from typing import Any, Dict, List, Optional, Tuple

from ..core import Field, PString, Record, TableDef, U16
from ..save import cache_key as _cache_key
from .awards import awards_end
from .clubs import after_frame

__all__ = [
    "UNIONS_TABLE",
    "UNIONS_TABLE_FMM27",
    "UNION_HEAD",
    "locate_unions",
    "scrape_unions",
    "unions_end",
]

UNION_HEAD = Record("union_head", 2, (
    Field(0, 2, "id", U16, note="== slot index + 1"),
), is_head=True)

_CACHE: Dict[Any, Optional[Tuple[int, int]]] = {}


def locate_unions(mm: Any) -> Optional[Tuple[int, int]]:
    """(record 0, declared count): the frame right after the awards, whose record 0 is id 1."""
    key = _cache_key(mm)
    if key in _CACHE:
        return _CACHE[key]
    res = None
    end = awards_end(mm)
    loc = after_frame(mm, end, 2) if end is not None else None
    if loc is not None and int.from_bytes(mm[loc[0]:loc[0] + 2], "little") == 1:
        res = loc
    _CACHE[key] = res
    return res


def _table(terminator: int) -> TableDef:
    return TableDef(
        name="unions",
        segments=(UNION_HEAD, PString("name", null_terminated=True, terminator=terminator)),
        locator=locate_unions,
        invariant=lambda rec, slot: rec["id"] == slot + 1,
    )


UNIONS_TABLE = _table(0x00)
UNIONS_TABLE_FMM27 = _table(0xFF)


def unions_table(mm: Any) -> TableDef:
    from .save_header import FMM27, save_format
    return UNIONS_TABLE_FMM27 if save_format(mm) == FMM27 else UNIONS_TABLE


def unions_end(mm: Any) -> Optional[int]:
    """The byte after the last union, or None when the table is not located."""
    spans = unions_table(mm).spans(mm)
    return spans[-1][1] if spans else None


def scrape_unions(mm: Any) -> List[Dict[str, Any]]:
    """Every union, in id order. Raises `ValueError` when not located or read short."""
    loc = locate_unions(mm)
    if loc is None:
        raise ValueError("unions: no frame after the awards")
    rows = unions_table(mm).scrape(mm)
    if len(rows) != loc[1]:
        raise ValueError(f"unions: walk read {len(rows)} of {loc[1]} declared")
    return rows
