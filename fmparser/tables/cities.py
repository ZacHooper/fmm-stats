#!/usr/bin/env python3
"""`cities` — the 20-byte Cities table (10,956 records).

Declared by a `[>= 8 x 0xFF][count u16 = 10956]` frame at ~13.49 MB.
Each record is 20 bytes on a dense index grid (`id == slot_index`).
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..save import cache_key as _cache_key
from ..schema import F32, Field, Record, U8, U16, U32, UNKNOWN
from .engine import FixedTableDef

__all__ = [
    "CITIES_TABLE",
    "CITY",
    "CITY_COUNT",
    "CITY_RECORD",
    "cities_table_spans",
    "locate_cities",
    "scrape_cities",
]

CITY_RECORD = 20
CITY_COUNT = 10956

CITY = Record("city", CITY_RECORD, [
    Field(0,  2, "id",         U16, note="== the slot index; that is what bounds the walk"),
    Field(2,  4, "uid",        U32),
    Field(6,  2, "nation_id",  U16, note="0 on 31 real cities with good coordinates"),
    Field(8,  4, "latitude",   F32),
    Field(12, 4, "longitude",  F32),
    Field(16, 1, "attraction", U8),
    Field(17, 2, "region_id",  U16),
    Field(19, 1, UNKNOWN,      U8),
])

_CITIES_CACHE: Dict[str, Optional[Tuple[int, int]]] = {}


def locate_cities(mm: Any) -> Optional[Tuple[int, int]]:
    """(base, declared_count) for the 20-byte cities table, or None."""
    key = _cache_key(mm)
    if key in _CITIES_CACHE:
        return _CITIES_CACHE[key]

    pat = b"\xff" * 8 + struct.pack("<H", CITY_COUNT)
    pos = 0
    while True:
        idx = mm.find(pat, pos)
        if idx == -1:
            break
        base = idx + len(pat)
        if base + 2 <= len(mm) and struct.unpack("<H", mm[base:base + 2])[0] == 0:
            res = (base, CITY_COUNT)
            _CITIES_CACHE[key] = res
            return res
        pos = idx + 1

    _CITIES_CACHE[key] = None
    return None


def _process_city(rec: Dict[str, Any], offset: int) -> Dict[str, Any]:
    placed = (-60.0 <= rec["latitude"] <= 80.0 and -180.0 <= rec["longitude"] <= 180.0)
    rec["latitude"] = round(rec["latitude"], 6) if placed else None
    rec["longitude"] = round(rec["longitude"], 6) if placed else None
    rec["offset"] = offset
    return rec


CITIES_TABLE = FixedTableDef(
    name="cities",
    record_schema=CITY,
    locator=locate_cities,
    include_offset=True,
    post_process=_process_city,
)


def scrape_cities(mm: Any) -> Dict[int, Dict[str, Any]]:
    """{city_id: record} with real latitude/longitude."""
    return CITIES_TABLE.id_map(mm, key_field="id")


def cities_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """Return [(start, end)] byte spans covering the cities table and its header."""
    return CITIES_TABLE.spans(mm, include_count_header=True)
