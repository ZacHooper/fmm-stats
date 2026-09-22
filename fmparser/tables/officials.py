#!/usr/bin/env python3
"""`match_officials` — the 99-byte Match Officials / Referees table.

Located in the attribute chain immediately in front of the 273-record round names table.
Declared by a `[>= 8 x 0xFF][count u32]` frame (622 records on Frem, 1,109 on Bucaspor).
Each record is exactly 99 bytes on a dense index grid (`slot_id == 0..N-1`).
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..save import cache_key as _cache_key
from ..core import PAD, RAW, Field, Record, U16, U32, U8, UNKNOWN
from ..core import TableDef

__all__ = [
    "OFFICIAL",
    "OFFICIAL_STRIDE",
    "OFFICIALS_TABLE",
    "locate_officials",
    "officials_table",
    "officials_table_spans",
    "scrape_officials",
]

OFFICIAL_STRIDE = 99

OFFICIAL = Record("official", OFFICIAL_STRIDE, [
    Field(0,  4, "slot_id", U32, note="grid index 0..N-1"),
    Field(4,  4, "uid", U32, note="person UID"),
    Field(8,  4, "tid", U32, note="person TID in info spine"),
    Field(12, 2, "ca", U16, note="current ability"),
    Field(14, 2, "pa", U16, note="potential ability"),
    Field(16, 2, "reputation", U16),
    Field(18, 1, "allowing_flow", U8, note="attribute 0 (1-20 scale)"),
    Field(19, 1, "discipline", U8, note="attribute 1 (1-20 scale)"),
    Field(20, 1, "important_matches", U8, note="attribute 2 (1-20 scale)"),
    Field(21, 1, "pressure", U8, note="attribute 3 (1-20 scale)"),
    Field(22, 1, "refereeing", U8, note="attribute 4 (1-20 scale)"),
    Field(23, 1, "running_match", U8, note="attribute 5 (1-20 scale)"),
    Field(24, 5, UNKNOWN, PAD, note="constant 0x00 padding"),
    Field(29, 2, "null_year", U16, note="typically 1900 null-year marker"),
    Field(31, 64, "competitions_raw", RAW, note="16 x u32 prefix-packed eligible competition/region IDs"),
    Field(95, 2, "day_of_year", U16),
    Field(97, 2, "year", U16),
])

_OFFICIALS_CACHE: Dict[str, Optional[Tuple[int, int]]] = {}


def locate_officials(mm: Any) -> Optional[Tuple[int, int]]:
    """(base, declared_count) for the 99-byte match officials table, or None.

    Located in the attribute chain immediately in front of the round names table.
    Bounded by the dense `slot_id == 0..N-1` invariant and the declared count header.
    """
    key = _cache_key(mm)
    if key in _OFFICIALS_CACHE:
        return _OFFICIALS_CACHE[key]

    sig = struct.pack("<I", 1) + struct.pack("<I", 6) + b"Replay\x00"
    pos = mm.find(sig)
    if pos == -1:
        _OFFICIALS_CACHE[key] = None
        return None

    # Step back past the 0xFF sentinel preceding rounds to the end of officials
    k = pos - 4
    while k > 0 and mm[k - 1] == 0xFF:
        k -= 1

    # The last official record sits at k - OFFICIAL_STRIDE; its slot_id is N - 1
    if k >= OFFICIAL_STRIDE + 12:
        last_slot_id = struct.unpack_from("<I", mm, k - OFFICIAL_STRIDE)[0]
        count = last_slot_id + 1
        hdr = k - count * OFFICIAL_STRIDE - 4
        if hdr >= 8:
            k_hdr = hdr
            ff = 0
            while k_hdr > 0 and mm[k_hdr - 1] == 0xFF:
                ff += 1
                k_hdr -= 1
            if ff >= 8:
                declared = struct.unpack_from("<I", mm, hdr)[0]
                if declared == count:
                    res = (hdr + 4, count)
                    _OFFICIALS_CACHE[key] = res
                    return res

    _OFFICIALS_CACHE[key] = None
    return None


officials_table = locate_officials

OFFICIALS_TABLE = TableDef(
    name="match_officials",
    segments=(OFFICIAL,),
    locator=locate_officials,
)


def scrape_officials(mm: Any) -> List[Dict[str, Any]]:
    """Return all decoded match officials records."""
    return OFFICIALS_TABLE.scrape(mm)


def officials_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """Return [(start, end)] byte spans covering the match officials table and its header."""
    return OFFICIALS_TABLE.spans(mm, include_count_header=True)
