#!/usr/bin/env python3
"""`round_names` — the 273-record competition round and leg name catalog.

Located in the attribute chain between the 99-byte match officials table and the 11,331-record
club table. Declared by a `[>= 8 x 0xFF][count u32 = 273]` frame.
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..save import cache_key as _cache_key
from ..schema import Field, Record, U16, U32
from .engine import StringCatalogDef, string_catalog_spans, walk_string_catalog

__all__ = [
    "ROUNDS_CATALOG",
    "ROUND_COUNT",
    "ROUND_HEAD",
    "ROUND_TRAILER",
    "ROUND_TRAILER_WIDTH",
    "locate_rounds",
    "round_names_map",
    "rounds_table",
    "rounds_table_spans",
    "scrape_rounds",
]

ROUND_COUNT = 273
ROUND_TRAILER_WIDTH = 14

ROUND_HEAD = Record("round_head", 8, [
    Field(0, 4, "id", U32, note="round / leg identifier"),
    Field(4, 4, "len", U32, note="name string byte length"),
], is_head=True)

ROUND_TRAILER = Record("round_trailer", ROUND_TRAILER_WIDTH, [
    Field(0,  4, "flag1", U32, note="typically 1"),
    Field(4,  2, "flag2", U16, note="typically 32 (0x0020)"),
    Field(6,  4, "flag3", U32, note="typically 1"),
    Field(10, 2, "flag4", U16, note="typically 32 (0x0020)"),
    Field(12, 2, "round_idx", U16, note="slot index within catalog"),
])

_ROUNDS_CACHE: Dict[str, Optional[Tuple[int, int]]] = {}


def locate_rounds(mm: Any) -> Optional[Tuple[int, int]]:
    """(base, declared_count) for the 273 round/leg name catalog, or None."""
    key = _cache_key(mm)
    if key in _ROUNDS_CACHE:
        return _ROUNDS_CACHE[key]

    pat = b"\xff" * 8 + struct.pack("<I", ROUND_COUNT) + struct.pack("<I", 1) + struct.pack("<I", 6) + b"Replay\x00"
    pos = mm.find(pat)
    if pos == -1:
        _ROUNDS_CACHE[key] = None
        return None

    res = (pos + 12, ROUND_COUNT)
    _ROUNDS_CACHE[key] = res
    return res


rounds_table = locate_rounds


ROUNDS_CATALOG = StringCatalogDef(
    name="round_names",
    head_schema=ROUND_HEAD,
    trailer_schema=ROUND_TRAILER,
    locator=locate_rounds,
    string_field="name",
    len_field="len",
    null_terminated=True,
)


def scrape_rounds(mm: Any) -> List[Dict[str, Any]]:
    """Return all decoded round and leg name records."""
    return ROUNDS_CATALOG.scrape(mm)


def round_names_map(mm: Any) -> Dict[int, str]:
    """Map {round_id: round_name}."""
    return {r["id"]: r["name"] for r in ROUNDS_CATALOG.scrape(mm)}


def rounds_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """Return [(start, end)] byte spans covering the round table and its header."""
    return ROUNDS_CATALOG.spans(mm, include_count_header=True)
