#!/usr/bin/env python3
"""`match_slots` — the 25-byte away-first match-slot table.

A fixed-stride table (3,975 slots on Frem, 3,943 on Bucaspor) located by its
invariant trailer constant `b"\\x87\\x01\\xff\\xff"` at +20 on residue class mod 25.
"""
from typing import Any, Dict, List, Optional, Tuple

from ..core import Field, I16, Record, TableDef, U8, U16, UNKNOWN
from ..core import primitives as P
from ..save import cache_key as _cache_key

__all__ = [
    "MATCH_SLOTS_TABLE",
    "NO_CLUB",
    "SLOT",
    "STRIDE",
    "TRAILER",
    "TRAILER_OFF",
    "locate",
    "locate_match_slots",
    "match_slots_table_spans",
    "read_slot",
    "scrape",
]

STRIDE = 25
TRAILER = b"\x87\x01\xff\xff"      # constant at +20..+23
TRAILER_OFF = 20
NO_CLUB = P.NO_ID16

SLOT = Record("match_slot", STRIDE, [
    Field(0,  2, "away_tid",   U16, note="0xffff when the slot references no match"),
    Field(2,  2, "home_tid",   U16),
    Field(4,  1, "away_goals", U8),
    Field(5,  1, "home_goals", U8),
    Field(6,  2, "day",        U16, note="day-of-year, 0-based -- as in the club record"),
    Field(8,  1, UNKNOWN,      U8),
    Field(9,  2, UNKNOWN,      I16),   # call it A. 0..360 on fixture rows.
    Field(11, 2, UNKNOWN,      I16),   # B. r=+0.994 with A; B ~ 0.58 x A.
    Field(13, 2, UNKNOWN,      I16),   # == A - k
    Field(15, 2, UNKNOWN,      I16),   # == B - k, the SAME k.
    Field(17, 2, UNKNOWN,      I16),
    Field(19, 1, UNKNOWN,      U8),
    Field(20, 2, "trailer_a",  U16, note="constant 391 on 93%"),
    Field(22, 2, "trailer_b",  U16, note="constant 0xffff on 99%"),
    Field(24, 1, UNKNOWN,      U8),    # 3 on 93%
])

_MATCH_SLOTS_CACHE: Dict[str, Optional[Tuple[int, int, int]]] = {}


def locate(mm: Any, bridge_slots: int = 40, min_trailers: int = 50) -> Optional[Tuple[int, int, int]]:
    """(start, end, n_trailers) of the table, or None.

    Found by the trailer's residue class mod STRIDE, then the longest contiguous run on that
    class.
    """
    key = _cache_key(mm)
    if key in _MATCH_SLOTS_CACHE:
        return _MATCH_SLOTS_CACHE[key]

    buf = mm[:] if not isinstance(mm, (bytes, bytearray)) else mm
    offs: List[int] = []
    i = buf.find(TRAILER)
    while i != -1:
        offs.append(i)
        i = buf.find(TRAILER, i + 1)

    if not offs:
        _MATCH_SLOTS_CACHE[key] = None
        return None

    best = None
    for res in range(STRIDE):
        on = [o for o in offs if o % STRIDE == res]
        if len(on) < min_trailers:
            continue
        runs: List[List[int]] = []
        cur = [on[0]]
        for a, b in zip(on, on[1:]):
            if b - a <= bridge_slots * STRIDE:
                cur.append(b)
            else:
                runs.append(cur)
                cur = [b]
        runs.append(cur)
        run = max(runs, key=len)
        if best is None or len(run) > len(best):
            best = run

    if not best:
        _MATCH_SLOTS_CACHE[key] = None
        return None

    res_tuple = (best[0] - TRAILER_OFF, best[-1] - TRAILER_OFF + STRIDE, len(best))
    _MATCH_SLOTS_CACHE[key] = res_tuple
    return res_tuple


def locate_match_slots(mm: Any) -> Optional[Tuple[int, int]]:
    """(base, record_count) for TableDef locator protocol."""
    reg = locate(mm)
    if not reg:
        return None
    start, end, _ = reg
    return (start, (end - start) // STRIDE)


def _process_slot(rec: Dict[str, Any], offset: int) -> Dict[str, Any]:
    res = {"offset": offset}
    res.update(rec)
    return res


MATCH_SLOTS_TABLE = TableDef(
    name="match_slots",
    segments=(SLOT,),
    locator=locate_match_slots,
    include_offset=False,
    post_process=_process_slot,
)


def read_slot(mm: Any, o: int) -> Dict[str, Any]:
    """Decode one slot from layout, preserving offset as the first key."""
    res = {"offset": o}
    res.update(SLOT.read(mm, o))
    return res


def scrape(mm: Any, valid_clubs: Optional[Any] = None) -> List[Dict[str, Any]]:
    """Every slot that references a match -> list of dicts, in file order."""
    rows = MATCH_SLOTS_TABLE.scrape(mm)
    out = []
    for r in rows:
        a = r["away_tid"]
        h = r["home_tid"]
        if a in (0, NO_CLUB) or h in (0, NO_CLUB) or a == h:
            continue
        if valid_clubs is not None and (a not in valid_clubs or h not in valid_clubs):
            continue
        out.append(r)
    return out


def match_slots_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """Return [(start, end)] byte spans covering the match slots table."""
    return MATCH_SLOTS_TABLE.spans(mm, include_count_header=False)
