#!/usr/bin/env python3
"""Record schema for fix_man.dat (the 92-byte world fixture list)."""
from ..schema import Field, PAD, Record, U16, U32, U8, UNKNOWN

STRIDE = 92
OPENER = 0x14
DAY_MASK = 0x1FF
DAY_BASE = 1

FIXTURE = Record("world_fixture", STRIDE, [
    Field(0,  1, UNKNOWN, PAD),
    Field(1,  1, "opener", U8, note="always 0x14; this is what the stride histogram keys on"),
    # +2..+15: the goals and shoot-out block
    Field(2,  4, UNKNOWN, PAD),
    Field(6,  1, "home_goals", U8, note="home score; 0xFF = unplayed"),
    Field(7,  1, "home_extra_goals", U8, note="home extra-time/aggregate score; 0xFF = none"),
    Field(8,  1, "home_pens", U8, note="home penalty shoot-out score; 0xFF = none"),
    Field(9,  2, UNKNOWN, PAD),
    Field(11, 1, "away_goals", U8, note="away score; 0xFF = unplayed"),
    Field(12, 1, "away_extra_goals", U8, note="away extra-time/aggregate score; 0xFF = none"),
    Field(13, 1, "away_pens", U8, note="away penalty shoot-out score; 0xFF = none"),
    Field(14, 2, UNKNOWN, PAD),
    Field(16, 8,  UNKNOWN, PAD, note="constant zero"),
    Field(24, 2,  UNKNOWN, PAD, note="8/7 distinct values, varies per match"),
    Field(26, 5,  UNKNOWN, PAD, note="constant padding: 0, 0, 0, 0, 20"),
    # +31: the stage/competition key. Takes 409 distinct values on frem-2026-06-11,
    # partitioning all 26,954 fixtures with nothing left over.
    Field(31, 4,  "stage_key", U32, note="stage key; index into comp_man.dat 78-byte grid"),
    # +35: per-fixture sequence id (256/58 distinct values)
    Field(35, 2,  "seq_id", U16, note="sequence id within round/stage"),
    Field(37, 4,  UNKNOWN, PAD),
    Field(41, 4,  "home_tid", U32, note="282/285 against ground truth; HOME-FIRST"),
    Field(45, 2,  UNKNOWN, PAD, note="secondary home club or aggregate/penalty marker"),
    Field(47, 4,  "away_tid", U32, note="282/285"),
    Field(51, 2,  UNKNOWN, PAD, note="secondary away club or aggregate/penalty marker"),
    # `& 0x1FF` never exceeds 366 across 26,954 records, twice over.
    # Top 7 bits (day_raw >> 9) discarded; ONE-INDEXED -- see DAY_BASE.
    Field(53, 2,  "day_raw", U16),
    Field(55, 2,  "year", U16, note="only the current and previous calendar year, ever"),
    Field(57, 2,  "day2_raw", U16, note="secondary date day"),
    Field(59, 2,  "year2", U16, note="secondary date year"),
    Field(61, 5,  UNKNOWN, PAD),
    Field(66, 2,  "season_year", U16, note="season year (2024/2025; 0 on unplayed/friendlies)"),
    Field(68, 8,  UNKNOWN, PAD),
    # Stage attributes: constant in all 409 stage groups on frem-2026-06-11
    Field(76, 1,  "stage_attr_76", U8, note="stage index within competition (from comp_<id>.dat 'stgs')"),
    Field(77, 1,  "stage_attr_77", U8, note="round index within competition stage (from comp_<id>.dat 'rnds')"),
    # 0-45, or 255 for "no matchday" (friendlies). See the module docstring.
    Field(78, 1,  "round", U8, note="matchday WITHIN a competition; 255 = none"),
    Field(79, 1,  UNKNOWN, PAD),
    Field(80, 1,  "stage_attr_80", U8, note="stage attribute, constant within stage"),
    Field(81, 1,  "stage_attr_81", U8, note="stage attribute, constant within stage"),
    Field(82, 1,  UNKNOWN, PAD),
    Field(83, 1,  "stage_attr_83", U8, note="stage class / subr from rules file"),
    Field(84, 8,  UNKNOWN, PAD),
])
