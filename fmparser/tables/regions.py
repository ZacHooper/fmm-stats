#!/usr/bin/env python3
"""`regions` — the regions of each nation (South-East, London, West Midlands for England),
the table a city's `region_id` points into.

The fourth table after the cities, behind the derbies (`derbies.py`); the currencies follow:

    [>= 8 x ff][count u16]                 2,467 on Frem, 2,532 on Truro
    per region:
      [id u16 = slot][uid u32]             REGION_HEAD
      [len u32][name][terminator]          "South-East"
      [nation_id u16][weather_id u16]      REGION_TAIL

fmm-editor's FMM26 `Region`, field for field. The terminator is 0x00 on FMM22 and 0xFF on
FMM27. Every region's nation resolves, and every city's region belongs to the city's nation.
"""
from typing import Any, Dict, List, Optional, Tuple

from ..core import Field, PString, Record, TableDef, U16, U32
from ..save import cache_key as _cache_key
from .clubs import after_frame
from .derbies import derbies_end

__all__ = [
    "REGIONS_TABLE",
    "REGIONS_TABLE_FMM27",
    "REGION_HEAD",
    "REGION_TAIL",
    "locate_regions",
    "regions_end",
    "scrape_regions",
]

REGION_HEAD = Record("region_head", 6, (
    Field(0, 2, "id", U16, note="== the slot index; a city's region_id"),
    Field(2, 4, "uid", U32),
), is_head=True)

REGION_TAIL = Record("region_tail", 4, (
    Field(0, 2, "nation_id", U16),
    Field(2, 2, "weather_id", U16, note="ffff on most; fmm-editor's WeatherId"),
), is_head=True)

_CACHE: Dict[Any, Optional[Tuple[int, int]]] = {}


def locate_regions(mm: Any) -> Optional[Tuple[int, int]]:
    """(record 0, declared count): the frame right after the derbies, whose record 0 is
    region 0."""
    key = _cache_key(mm)
    if key in _CACHE:
        return _CACHE[key]
    res = None
    end = derbies_end(mm)
    loc = after_frame(mm, end, 2) if end is not None else None
    if loc is not None and int.from_bytes(mm[loc[0]:loc[0] + 2], "little") == 0:
        res = loc
    _CACHE[key] = res
    return res


def _table(terminator: int) -> TableDef:
    return TableDef(
        name="regions",
        segments=(REGION_HEAD, PString("name", null_terminated=True, terminator=terminator),
                  REGION_TAIL),
        locator=locate_regions,
        invariant=lambda rec, slot: rec["id"] == slot,
    )


REGIONS_TABLE = _table(0x00)
REGIONS_TABLE_FMM27 = _table(0xFF)


def regions_table(mm: Any) -> TableDef:
    from .save_header import FMM27, save_format
    return REGIONS_TABLE_FMM27 if save_format(mm) == FMM27 else REGIONS_TABLE


def regions_end(mm: Any) -> Optional[int]:
    """The byte after the last region, or None when the table is not located."""
    spans = regions_table(mm).spans(mm)
    return spans[-1][1] if spans else None


def scrape_regions(mm: Any) -> List[Dict[str, Any]]:
    """Every region, in id order. Raises `ValueError` when not located or read short."""
    loc = locate_regions(mm)
    if loc is None:
        raise ValueError("regions: no frame after the derbies")
    rows = regions_table(mm).scrape(mm)
    if len(rows) != loc[1]:
        raise ValueError(f"regions: walk read {len(rows)} of {loc[1]} declared")
    return rows
