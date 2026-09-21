#!/usr/bin/env python3
"""`round_names` — the 273-record competition round and leg name catalog.

Located in the attribute chain between the 99-byte match officials table and the 11,331-record
club table. Declared by a `[>= 8 x 0xFF][count u32 = 273]` frame.

Each record is variable-length:
  1. An 8-byte head: `[id u32][name_length u32]`
  2. `name_length` UTF-8 / Latin-1 bytes
  3. A 1-byte `0x00` null terminator
  4. A 14-byte trailer: `[u32 flag1][u16 flag2][u32 flag3][u16 flag4][u16 round_idx]`
     (typically `(1, 32, 1, 32, slot_index)`).
"""
import struct

from . import primitives as P
from . import records as RD
from .save import cache_key as _cache_key
from .schema import Field, Record, U16, U32

ROUND_COUNT = 273
_FRAME = 12             # [8 x 0xFF][count u32]
_TRAILER_WIDTH = 14

ROUND_HEAD = Record("round_head", 8, [
    Field(0, 4, "id", U32, note="round / leg identifier"),
    Field(4, 4, "len", U32, note="name string byte length"),
], is_head=True)

ROUND_TRAILER = Record("round_trailer", _TRAILER_WIDTH, [
    Field(0,  4, "flag1", U32, note="typically 1"),
    Field(4,  2, "flag2", U16, note="typically 32 (0x0020)"),
    Field(6,  4, "flag3", U32, note="typically 1"),
    Field(10, 2, "flag4", U16, note="typically 32 (0x0020)"),
    Field(12, 2, "round_idx", U16, note="slot index within catalog"),
])


_ROUNDS_CACHE = {}


def rounds_table(mm):
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


def scrape_rounds(mm):
    """[{id: int, name: str, round_idx: int, ...}] for all 273 round and leg names."""
    info = rounds_table(mm)
    if not info:
        return []
    base, count = info
    pos = base
    n = len(mm)
    out = []
    for _ in range(count):
        if pos + 8 > n:
            break
        head = RD.read(mm, ROUND_HEAD, pos)
        rid = head["id"]
        slen = head["len"]
        if pos + 8 + slen + 1 + _TRAILER_WIDTH > n:
            break
        raw_name = mm[pos + 8:pos + 8 + slen]
        try:
            name = raw_name.decode("utf-8")
        except UnicodeDecodeError:
            name = raw_name.decode("latin-1")
        
        trailer_pos = pos + 8 + slen + 1
        trailer = RD.read(mm, ROUND_TRAILER, trailer_pos)
        out.append({
            "id": rid,
            "name": name,
            "flag1": trailer["flag1"],
            "flag2": trailer["flag2"],
            "flag3": trailer["flag3"],
            "flag4": trailer["flag4"],
            "round_idx": trailer["round_idx"],
        })
        pos = trailer_pos + _TRAILER_WIDTH
    return out


def round_names_map(mm):
    """{id: name} mapping for quick resolution."""
    return {r["id"]: r["name"] for r in scrape_rounds(mm)}
