#!/usr/bin/env python3
"""`round_names` — the 273-record competition round and leg name catalog.

Located in the attribute chain between the 99-byte match officials table and the 11,331-record
club table. Declared by a `[>= 8 x 0xFF][count u32 = 273]` frame.
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

from .save import cache_key as _cache_key
from .schemas.rounds import ROUND_COUNT, ROUND_HEAD, ROUND_TRAILER, ROUND_TRAILER_WIDTH
from .tables import StringCatalogDef, string_catalog_spans, walk_string_catalog

__all__ = [
    "ROUNDS_CATALOG",
    "ROUND_COUNT",
    "ROUND_HEAD",
    "ROUND_TRAILER",
    "ROUND_TRAILER_WIDTH",
    "round_names_map",
    "rounds_table",
    "rounds_table_spans",
    "scrape_rounds",
]

_ROUNDS_CACHE: Dict[str, Optional[Tuple[int, int]]] = {}


def rounds_table(mm: Any) -> Optional[Tuple[int, int]]:
    """(base, declared_count) for the 273 round/leg name table, or None."""
    key = _cache_key(mm)
    if key in _ROUNDS_CACHE:
        return _ROUNDS_CACHE[key]

    pat = b"\xff" * 8 + struct.pack("<I", ROUND_COUNT) + struct.pack("<I", 1) + struct.pack("<I", 6) + b"Replay\x00"
    pos = mm.find(pat)
    if pos == -1:
        _ROUNDS_CACHE[key] = None
        return None

    base = pos + 8 + 4
    res = (base, ROUND_COUNT)
    _ROUNDS_CACHE[key] = res
    return res


ROUNDS_CATALOG = StringCatalogDef(
    name="round_names",
    head_schema=ROUND_HEAD,
    trailer_schema=ROUND_TRAILER,
    locator=rounds_table,
    string_field="name",
    len_field="len",
    null_terminated=True,
)


def scrape_rounds(mm: Any) -> List[Dict[str, Any]]:
    """[{id: int, name: str, round_idx: int, ...}] for all 273 round and leg names."""
    return walk_string_catalog(mm, ROUNDS_CATALOG)


def round_names_map(mm: Any) -> Dict[int, str]:
    """{id: name} mapping for quick resolution."""
    return {r["id"]: r["name"] for r in scrape_rounds(mm)}


def rounds_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """[(start, end)] byte spans covering the round names catalog and its header."""
    return string_catalog_spans(mm, ROUNDS_CATALOG)
