#!/usr/bin/env python3
"""`round_names` — the 273-record competition round and leg name catalog.

Located in the attribute chain between the 99-byte match officials table and the 11,331-record
club table. Declared by a `[>= 8 x 0xFF][count u32 = 273]` frame.

A record is `[id u32]`, three strings each followed by a terminator byte, and `[next u16]`.
FMM22 stores the name and two one-space strings, terminated 0x00 (declared here as the
trailer); FMM27 (288 records) fills in a short name and a plural and terminates all three 0xFF.
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..save import cache_key as _cache_key
from ..core import Field, Record, U16, U32, PString
from ..core import TableDef, table_spans
from .save_header import FMM27, save_format

__all__ = [
    "ROUNDS_CATALOG",
    "ROUNDS_TABLE",
    "ROUNDS_TABLE_FMM27",
    "ROUND_HEAD",
    "ROUND_TRAILER",
    "ROUND_TRAILER_WIDTH",
    "locate_rounds",
    "round_names_map",
    "round_names_table",
    "rounds_end",
    "rounds_table",
    "rounds_table_spans",
    "scrape_rounds",
]

ROUND_TRAILER_WIDTH = 14

ROUND_HEAD = Record("round_head", 4, [
    Field(0, 4, "id", U32, note="round / leg identifier"),
], is_head=True)

ROUND_TRAILER = Record("round_trailer", ROUND_TRAILER_WIDTH, [
    Field(0,  4, "flag1", U32, note="typically 1"),
    Field(4,  2, "flag2", U16, note="typically 32 (0x0020)"),
    Field(6,  4, "flag3", U32, note="typically 1"),
    Field(10, 2, "flag4", U16, note="typically 32 (0x0020)"),
    Field(12, 2, "next", U16, note="the next record's index; 0xffff ends the chain"),
])

_ROUNDS_CACHE: Dict[str, Optional[Tuple[int, int]]] = {}


def locate_rounds(mm: Any) -> Optional[Tuple[int, int]]:
    """(base, declared_count) for the round/leg name catalog, or None.

    Declared by a `[>= 8 x 0xFF][count u32]` frame. Record 0 opens with
    `id=1 (u32), len=6 (u32), 'Replay'`, then the version's terminator byte.
    """
    key = _cache_key(mm)
    if key in _ROUNDS_CACHE:
        return _ROUNDS_CACHE[key]
    res = None
    sig = struct.pack("<I", 1) + struct.pack("<I", 6) + b"Replay"
    pos = mm.find(sig)
    while pos != -1 and res is None:
        if pos >= 12 and mm[pos - 12:pos - 4] == b"\xff" * 8:
            res = (pos, struct.unpack_from("<I", mm, pos - 4)[0])
        pos = mm.find(sig, pos + 1)
    _ROUNDS_CACHE[key] = res
    return res


rounds_table = locate_rounds


ROUNDS_TABLE = TableDef(
    name="round_names",
    segments=(
        ROUND_HEAD,
        PString("name", null_terminated=True),
        ROUND_TRAILER,
    ),
    locator=locate_rounds,
)

ROUNDS_CATALOG = ROUNDS_TABLE

ROUND_NEXT = Record("round_next", 2, [
    Field(0, 2, "next", U16, note="the next record's index; 0xffff ends the chain"),
])

ROUNDS_TABLE_FMM27 = TableDef(
    name="round_names",
    segments=(
        ROUND_HEAD,
        PString("name", null_terminated=True, terminator=0xFF, allow_empty=True),
        PString("short_name", null_terminated=True, terminator=0xFF, allow_empty=True),
        PString("plural_name", null_terminated=True, terminator=0xFF, allow_empty=True),
        ROUND_NEXT,
    ),
    locator=locate_rounds,
)


def round_names_table(mm: Any) -> TableDef:
    """The round name table's declaration for this save's format."""
    return ROUNDS_TABLE_FMM27 if save_format(mm) == FMM27 else ROUNDS_TABLE


def rounds_end(mm: Any) -> Optional[int]:
    """Where the table's last record ends, or None."""
    spans = table_spans(mm, round_names_table(mm), include_count_header=False)
    return spans[0][1] if spans else None


def scrape_rounds(mm: Any) -> List[Dict[str, Any]]:
    """Return all decoded round and leg name records."""
    return round_names_table(mm).scrape(mm)


def round_names_map(mm: Any) -> Dict[int, str]:
    """Map {round_id: round_name}."""
    return {r["id"]: r["name"] for r in round_names_table(mm).scrape(mm)}


def rounds_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """Return [(start, end)] byte spans covering the round table and its header."""
    return round_names_table(mm).spans(mm, include_count_header=True)
