#!/usr/bin/env python3
"""Record schemas for the 273-record Round and Leg Names catalog."""
from ..schema import Field, Record, U16, U32

ROUND_COUNT = 273
ROUND_TRAILER_WIDTH = 14

ROUND_HEAD = Record("round_head", 8, [
    Field(0, 4, "id", U32, note="round / leg identifier"),
    Field(4, 4, "len", U32, note="name string byte length"),
], is_head=True)

ROUND_TRAILER = Record("round_trailer", ROUND_TRAILER_WIDTH, [
    Field(0,  4, "flag1", U32, note="typically 1"),
    Field(4,  2, "flag2", U16, note="typically 32 (0x0020)"),
    Field(6,  4, "flag3", U32, note="typically 1"),
    Field(10, 2, "flag4", U16, note="typically 32 (0x0020)"),
    Field(12, 2, "round_idx", U16, note="slot index within catalog"),
])
