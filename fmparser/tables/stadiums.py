#!/usr/bin/env python3
"""`stadiums` — the Stadiums table (~15,987 records).

Located in the reference block around ~12.8 MB count-framed by `[8x 0xFF][u16 count = 15987]`.

FMM27 (12,509 on Truro) stores three names -- the name, its sponsor-free form and the name
again, the last terminated 0xFF -- and three more bytes (STADIUMS_TABLE_FMM27). Its frame is
found from the nations table's end: the first `[>= 8 x 0xFF][count u16]` whose records 0
and 1 have ids 0 and 1.
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..core import primitives as P
from ..save import cache_key as _cache_key
from ..core import Field, Record, U8, U16, U32, PString, UNKNOWN
from ..core import TableDef
from .nations import nations_table_spans
from .save_header import FMM27, save_format

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
    if save_format(mm) == FMM27:
        _STADIUMS_CACHE[key] = _locate_fmm27(mm)
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


_SEARCH_FMM27 = 1_000_000      # bytes after the nations table to look for the frame


def _locate_fmm27(mm: Any) -> Optional[Tuple[int, int]]:
    """(record 0, count): the first count frame after the nations table whose first two
    records are ids 0 and 1, walked by the FMM27 declaration."""
    spans = nations_table_spans(mm)
    if not spans:
        return None
    lo = spans[0][1]
    hi = min(len(mm), lo + _SEARCH_FMM27)
    pos = mm.find(b"\xff" * 8, lo, hi)
    while pos != -1:
        end = pos + 8
        while end < hi and mm[end] == 0xFF:
            end += 1
        base = end + 2
        if base + STADIUM_HEAD.span <= hi and P.u32(mm, base) == 0:
            count = P.u16(mm, end)
            nxt = _record_end_fmm27(mm, base, hi)
            if count > 1 and nxt is not None and P.u32(mm, nxt) == 1:
                return base, count
        pos = mm.find(b"\xff" * 8, end, hi)
    return None


STADIUM_TAIL_FMM27 = Record("stadium_tail_fmm27", 3, (
    Field(0, 1, UNKNOWN, U8, note="255 on 12,271, 0 on 238"),
    Field(1, 1, UNKNOWN, U8, note="a bitfield shape: 0, 1-4, 64-67, 128-132"),
    Field(2, 1, UNKNOWN, U8, note="0, 1 or 8"),
), is_head=True)

STADIUMS_TABLE_FMM27 = TableDef(
    name="stadiums",
    segments=(
        STADIUM_HEAD,
        PString("name"),
        PString("alt_name"),          # the sponsor-free name (Vitality -> Bournemouth Stadium)
        PString("name_3", null_terminated=True, terminator=0xFF),
        STADIUM_TAIL_FMM27,
    ),
    locator=locate_stadiums,
    include_offset=True,
    invariant=lambda rec, slot: rec["id"] == slot,
)


def _record_end_fmm27(mm: Any, base: int, limit: int) -> Optional[int]:
    pos = base + STADIUM_HEAD.span
    for seg in STADIUMS_TABLE_FMM27.segments[1:]:
        if isinstance(seg, Record):
            pos += seg.span
            continue
        res = seg.read(mm, pos, limit)
        if res is None:
            return None
        pos = res[1]
    return pos


def stadiums_table(mm: Any) -> TableDef:
    """The stadium table's declaration for this save's format."""
    return STADIUMS_TABLE_FMM27 if save_format(mm) == FMM27 else STADIUMS_TABLE


def scrape_stadiums(mm: Any) -> Dict[int, Dict[str, Any]]:
    """{stadium_id: record} for every stadium in the save."""
    return stadiums_table(mm).id_map(mm, key_field="id")
