#!/usr/bin/env python3
"""`stadiums` — the Stadiums table (~15,987 records).

Located in the reference block around ~12.8 MB by structural chaining.
"""
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from .. import primitives as P
from ..schema import Field, Record, U16, U32

__all__ = [
    "STADIUM_HEAD",
    "STADIUM_HEADER",
    "scrape_stadiums",
]

STADIUM_HEADER = 18

STADIUM_HEAD = Record("stadium_head", STADIUM_HEADER, [
    Field(0, 4, "id", U32),
    Field(4, 4, "uid", U32),
    Field(8, 2, "city_id", U16),
    Field(10, 4, "capacity", U32),
    Field(14, 4, "expansion_capacity", U32),
], is_head=True)

_STADIUM_HEADER = STADIUM_HEADER


def _stadium_at(mm: Any, o: int, n: int) -> Tuple[Optional[Dict[str, Any]], Optional[int]]:
    """Parse a stadium record at `o`, returning (rec, next_offset) or (None, None)."""
    if o < 0 or o + _STADIUM_HEADER + 4 > n:
        return None, None
    ln = P.u32(mm, o + _STADIUM_HEADER)
    if not (1 <= ln <= 120) or o + _STADIUM_HEADER + 4 + ln + 1 > n:
        return None, None
    raw = bytes(mm[o + _STADIUM_HEADER + 4:o + _STADIUM_HEADER + 4 + ln])
    if mm[o + _STADIUM_HEADER + 4 + ln] != 0:      # names are NUL-terminated
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
    rec = {"id": P.u32(mm, o), "uid": P.u32(mm, o + 4), "city_id": P.u16(mm, o + 8),
           "capacity": cap, "expansion_capacity": exp, "name": name, "offset": o}
    return rec, o + _STADIUM_HEADER + 4 + ln + 1


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


def scrape_stadiums(mm: Any, min_chain: int = 25) -> Dict[int, Dict[str, Any]]:
    """{stadium_id: record} for every stadium in the save."""
    n = len(mm)
    a = np.frombuffer(mm, dtype=np.uint8)
    end = n - 200
    ln = (a[_STADIUM_HEADER:end].astype(np.uint32)
          | (a[_STADIUM_HEADER + 1:end + 1].astype(np.uint32) << 8)
          | (a[_STADIUM_HEADER + 2:end + 2].astype(np.uint32) << 16)
          | (a[_STADIUM_HEADER + 3:end + 3].astype(np.uint32) << 24))
    seeds = np.flatnonzero((ln >= 3) & (ln <= 60))
    out: Dict[int, Dict[str, Any]] = {}
    seen_start = None
    for o in seeds.tolist():
        if _chain_len(mm, o, n) >= min_chain:
            seen_start = o
            break
    if seen_start is None:
        return out
    o = seen_start
    while True:
        rec, nxt = _stadium_at(mm, o, n)
        if rec is None or nxt is None:
            break
        out.setdefault(rec["id"], rec)
        o = nxt
    return out
