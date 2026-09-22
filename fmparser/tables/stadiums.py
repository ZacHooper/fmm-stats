#!/usr/bin/env python3
"""`stadiums` — the Stadiums table (~15,987 records).

Located in the reference block around ~12.8 MB count-framed by `[8x 0xFF][u16 count = 15987]`.
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

from .. import primitives as P
from ..save import cache_key as _cache_key
from ..schema import Field, Record, U16, U32, PString
from .engine import TableDef

__all__ = [
    "STADIUM_HEAD",
    "STADIUM_HEADER",
    "STADIUMS_CATALOG",
    "STADIUMS_TABLE",
    "locate_stadiums",
    "scrape_stadiums",
]

STADIUM_HEADER = 22

STADIUM_HEAD = Record("stadium_head", 18, [
    Field(0, 4, "id", U32),
    Field(4, 4, "uid", U32),
    Field(8, 2, "city_id", U16),
    Field(10, 4, "capacity", U32),
    Field(14, 4, "expansion_capacity", U32),
], is_head=True)

_STADIUMS_CACHE: Dict[Tuple[int, int], Optional[Tuple[int, int]]] = {}


def _stadium_at(mm: Any, o: int, n: int) -> Tuple[Optional[Dict[str, Any]], Optional[int]]:
    """Parse a stadium record at `o`, returning (rec, next_offset) or (None, None)."""
    if o < 0 or o + STADIUM_HEADER > n:
        return None, None
    ln = P.u32(mm, o + 18)
    if not (1 <= ln <= 120) or o + STADIUM_HEADER + ln + 1 > n:
        return None, None
    raw = bytes(mm[o + STADIUM_HEADER:o + STADIUM_HEADER + ln])
    if mm[o + STADIUM_HEADER + ln] != 0:      # names are NUL-terminated
        return None, None
    try:
        name = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None, None
    if not name or not any(c.isalpha() for c in name):
        return None, None
    cap, exp = P.u32(mm, o + 10), P.u32(mm, o + 14)
    if cap > 300_000 or exp > 300_000:
        return None, None
    rec = {
        "id": P.u32(mm, o),
        "uid": P.u32(mm, o + 4),
        "city_id": P.u16(mm, o + 8),
        "capacity": cap,
        "expansion_capacity": exp,
        "name": name,
        "offset": o,
    }
    return rec, o + STADIUM_HEADER + ln + 1


def _chain_len(mm: Any, o: int, n: int, limit: int = 40) -> int:
    """How many stadium records chain consecutively from `o` (capped)."""
    k = 0
    while k < limit:
        rec, nxt = _stadium_at(mm, o, n)
        if rec is None or nxt is None:
            break
        o = nxt
        k += 1
    return k


def locate_stadiums(mm: Any) -> Optional[Tuple[int, int]]:
    """(base, declared_count) for the 15,987 stadium table, or None."""
    key = _cache_key(mm)
    if key in _STADIUMS_CACHE:
        return _STADIUMS_CACHE[key]

    pat = b"\xff" * 8 + struct.pack("<H", 15987)
    pos = 0
    find_fn = mm.find if hasattr(mm, "find") else bytes(mm).find
    while True:
        idx = find_fn(pat, pos)
        if idx == -1:
            break
        base = idx + 10
        if base + 4 <= len(mm) and int.from_bytes(mm[base:base + 4], "little") == 0:
            res = (base, 15987)
            _STADIUMS_CACHE[key] = res
            return res
        pos = idx + 1

    # Fallback / synthetic test path (e.g. buffers without the full 8x 0xFF header)
    n = len(mm)
    if n >= STADIUM_HEADER:
        k = 0
        cur = 0
        while cur + STADIUM_HEADER <= n:
            rec, nxt = _stadium_at(mm, cur, n)
            if rec is None or nxt is None:
                break
            cur = nxt
            k += 1
        if k > 0:
            res = (0, k)
            _STADIUMS_CACHE[key] = res
            return res

    _STADIUMS_CACHE[key] = None
    return None


STADIUMS_TABLE = TableDef(
    name="stadiums",
    segments=(
        STADIUM_HEAD,
        PString("name", null_terminated=True),
    ),
    locator=locate_stadiums,
    include_offset=True,
)

STADIUMS_CATALOG = STADIUMS_TABLE


def scrape_stadiums(mm: Any) -> Dict[int, Dict[str, Any]]:
    """{stadium_id: record} for every stadium in the save."""
    return STADIUMS_TABLE.id_map(mm, key_field="id")
