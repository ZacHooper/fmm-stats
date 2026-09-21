#!/usr/bin/env python3
"""`match_officials` — the 99-byte Match Officials / Referees table.

Located in the attribute chain immediately in front of the 273-record round names table.
Declared by a `[>= 8 x 0xFF][count u32]` frame (622 records on Frem, 1,109 on Bucaspor).
Each record is exactly 99 bytes on a dense index grid (`slot_id == 0..N-1`).
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

from .save import cache_key as _cache_key
from .schemas.officials import OFFICIAL, OFFICIAL_STRIDE
from .tables import FixedTableDef, fixed_table_spans, walk_fixed_table

__all__ = [
    "OFFICIAL",
    "OFFICIAL_STRIDE",
    "OFFICIALS_TABLE",
    "officials_table",
    "officials_table_spans",
    "scrape_officials",
]

_OFFICIALS_CACHE: Dict[str, Optional[Tuple[int, int]]] = {}


def officials_table(mm: Any) -> Optional[Tuple[int, int]]:
    """(base, declared_count) for the 99-byte match officials table, or None.

    Found by locating the 273 round table's sentinel, which immediately terminates this table.
    """
    key = _cache_key(mm)
    if key in _OFFICIALS_CACHE:
        return _OFFICIALS_CACHE[key]

    pat = b"\xff" * 8 + struct.pack("<I", 273) + struct.pack("<I", 1) + struct.pack("<I", 6) + b"Replay\x00"
    pos = mm.find(pat)
    if pos == -1:
        _OFFICIALS_CACHE[key] = None
        return None

    # Search backward from `pos` for the [8x 0xFF][count u32] frame
    found = None
    for cnt in (622, 1109, 621, 623, 1108, 1110):
        span = cnt * OFFICIAL_STRIDE
        hdr_candidate = pos - span - 4
        if hdr_candidate >= 8 and all(mm[hdr_candidate - 1 - j] == 0xFF for j in range(8)):
            c = struct.unpack_from("<I", mm, hdr_candidate)[0]
            if c == cnt:
                base = hdr_candidate + 4
                if all(struct.unpack_from("<I", mm, base + k * OFFICIAL_STRIDE)[0] == k for k in range(min(cnt, 20))):
                    found = (base, cnt)
                    break

    _OFFICIALS_CACHE[key] = found
    return found


def _post_process_official(rec: Dict[str, Any]) -> Dict[str, Any]:
    raw_comps = rec["competitions_raw"]
    comp_ids = []
    for j in range(16):
        cid = struct.unpack_from("<I", raw_comps, j * 4)[0]
        if cid != 0xFFFFFFFF:
            comp_ids.append(cid)
    row = dict(rec)
    del row["competitions_raw"]
    row["competitions"] = comp_ids
    return row


OFFICIALS_TABLE = FixedTableDef(
    name="match_officials",
    record_schema=OFFICIAL,
    locator=officials_table,
    post_process=_post_process_official,
)


def scrape_officials(mm: Any) -> List[Dict[str, Any]]:
    """[{slot_id, uid, tid, ca, pa, reputation, ...}] for all match officials."""
    return walk_fixed_table(mm, OFFICIALS_TABLE)


def officials_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """[(start, end)] byte spans covering the officials table and its header."""
    return fixed_table_spans(mm, OFFICIALS_TABLE)
