#!/usr/bin/env python3
"""Record schemas for comp_man.dat (competition stages & roll of honour)."""
from ..schema import Field, PAD, Record, U16, U32, U8, UNKNOWN

HEADER_STRIDE = 36
STAGE_STRIDE = 78
HONOUR_STRIDE = 55

# 1. THE 36-BYTE FILE HEADER
HEADER = Record("comp_man_header", HEADER_STRIDE, [
    Field(0,  2, "unk0", U16),
    Field(2,  2, "unk2", U16),
    Field(4,  2, "unk4", U16),
    Field(6,  2, "year_start", U16),
    Field(8,  2, "year_end", U16),
    Field(10, 4, "n_stages", U32, note="exact count of 78-byte stage records in the grid"),
    Field(14, 2, "base_year", U16, note="typically 2000"),
    Field(16, 4, "unk16", U32),
    Field(20, 4, "unk20", U32),
    Field(24, 8, UNKNOWN, PAD),
    Field(32, 4, UNKNOWN, PAD, note="0xFFFFFFFF terminator"),
])

# 2. THE 78-BYTE STAGE RECORD (record index `k` == stage_key `k`)
STAGE = Record("comp_man_stage", STAGE_STRIDE, [
    Field(0,  1, "opener", U8),
    Field(1,  5, UNKNOWN, PAD, note="record format / status flags"),
    Field(6,  24, UNKNOWN, PAD),
    Field(30, 16, UNKNOWN, PAD, note="constant 0xFF filler"),
    Field(46, 2, "start_year", U16, note="earliest validity year"),
    Field(48, 2, "end_year", U16, note="latest validity year"),
    Field(50, 6, UNKNOWN, PAD),
    Field(56, 2, "base_year", U16, note="typically 2000"),
    Field(58, 2, "format_flag", U16, note="1=league/group, 2/4=knockout"),
    Field(60, 2, UNKNOWN, PAD),
    Field(62, 2, "region_code", U16, note="federation/region identifier"),
    Field(64, 2, "kickoff_time", U16, note="default kickoff time e.g. 1500 (3pm), 1930 (7:30pm)"),
    Field(66, 2, "match_week", U16, note="calendar scheduling week 0..60 across season"),
    Field(68, 2, UNKNOWN, PAD),
    Field(70, 2, "match_capacity", U16, note="match count / team slot allocation or FourCC"),
    Field(72, 2, UNKNOWN, PAD),
    Field(74, 2, "scheduling_priority", U16, note="tie leg ordinal / scheduling priority or FourCC"),
    Field(76, 2, UNKNOWN, PAD),
])

# 3. THE 55-BYTE ROLL OF HONOUR / WINNERS RECORD
HONOUR = Record("comp_man_honour", HONOUR_STRIDE, [
    Field(0,  8, UNKNOWN, PAD, note="opener: 0xFF x 5 then 0x00 x 3"),
    Field(8,  2, "start_year", U16),
    Field(10, 2, "end_year", U16),
    Field(12, 2, "format_flag", U16),
    Field(14, 2, "base_year", U16, note="1900"),
    Field(16, 4, "comp_cid", U32, note="true competition ID"),
    Field(20, 4, "season", U32, note="season year"),
    Field(24, 4, "winner_tid", U32, note="1st place / Cup Winner club TID"),
    Field(28, 4, "runner_up_tid", U32, note="2nd place / Finalist club TID"),
    Field(32, 4, "third_place_tid", U32, note="3rd place club TID"),
    Field(36, 4, "fourth_place_tid", U32, note="4th place club TID"),
    Field(40, 15, UNKNOWN, PAD, note="0xFF padding"),
])
