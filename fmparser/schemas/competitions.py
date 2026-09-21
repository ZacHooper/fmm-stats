#!/usr/bin/env python3
"""Record schemas for competition records and trailers."""
from ..schema import Field, PAD, Record, U8, U16, U32, UNKNOWN

COMP_TRAILER = Record("comp_trailer", 14, (
    Field(0,  1, "type", U8),
    Field(1,  2, "continent", U16, note="declared, not read"),
    Field(3,  2, "nation", U16),
    Field(5,  2, "fg_colour", U16, note="declared, not read"),
    Field(7,  2, "bg_colour", U16, note="declared, not read"),
    Field(9,  2, "reputation", U16),
    Field(11, 1, "level", U8),
    Field(12, 2, "parent_cid", U16),
), is_head=True)

COMP_REF_COUNT = Record("comp_ref_count", 4, (
    Field(0, 1, "n_refs", U8),
    Field(1, 3, UNKNOWN, PAD),
), is_head=True)

COMP_REF_ENTRY = Record("comp_ref_entry", 8, (
    Field(0, 4, "ref", U32),
    Field(4, 2, "season", U16),
    Field(6, 1, "ordinal", U8),
    Field(7, 1, UNKNOWN, PAD),
))

COMP_HISTORY_TAIL = Record("comp_history_tail", 21, (
    Field(0,  4, UNKNOWN, PAD),
    Field(4,  4, UNKNOWN, PAD),
    Field(8,  4, UNKNOWN, PAD),
    Field(12, 2, "season_0", U16),
    Field(14, 2, "season_1", U16),
    Field(16, 2, "season_2", U16),
    Field(18, 2, UNKNOWN, PAD),
    Field(20, 1, UNKNOWN, PAD),
))
