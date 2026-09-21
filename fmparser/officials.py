#!/usr/bin/env python3
"""`match_officials` — the 99-byte Match Officials / Referees table.

Located in the attribute chain immediately in front of the 273-record round names table.
Declared by a `[>= 8 x 0xFF][count u32]` frame (622 records on Frem, 1,109 on Bucaspor).
Each record is exactly 99 bytes on a dense index grid (`slot_id == 0..N-1`).

Contains:
  * Person identifiers: UID (+4) and info-spine TID (+8)
  * Ability & reputation: CA (+12), PA (+14), Reputation (+16)
  * Six referee attributes on the 1-20 scale (+18..+23)
  * 16-slot prefix-packed array of eligible competition/regional IDs (+31..+94)
  * Active date markers: day of year (+95), year (+97)
"""
import struct

from . import primitives as P
from . import records as RD
from .save import cache_key as _cache_key
from .schema import Field, PAD, RAW, Record, U16, U32, U8, UNKNOWN

OFFICIAL_STRIDE = 99
_FRAME = 12

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

_OFFICIALS_CACHE = {}


def officials_table(mm):
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


def scrape_officials(mm):
    """[{slot_id, uid, tid, ca, pa, reputation, ...}] for all match officials."""
    info = officials_table(mm)
    if not info:
        return []
    base, count = info
    out = []
    for k in range(count):
        o = base + k * OFFICIAL_STRIDE
        rec = RD.read(mm, OFFICIAL, o)
        # Decode the 16 x u32 competition references
        raw_comps = rec["competitions_raw"]
        comp_ids = []
        for j in range(16):
            cid = struct.unpack_from("<I", raw_comps, j * 4)[0]
            if cid != 0xFFFFFFFF:
                comp_ids.append(cid)
        
        row = dict(rec)
        del row["competitions_raw"]
        row["competitions"] = comp_ids
        out.append(row)
    return out
