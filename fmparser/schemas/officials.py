#!/usr/bin/env python3
"""Record schemas for the 99-byte Match Officials table."""
from ..schema import Field, PAD, RAW, Record, U16, U32, U8, UNKNOWN

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
