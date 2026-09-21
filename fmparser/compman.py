#!/usr/bin/env python3
"""`comp_man.dat` — the master competition stages calendar & roll of honour archive member.

Located inside the save's zstd tail archive (`sicomps`).
Contains:
  1. A 36-byte header declaring the exact record count `n_stages` at +10 (u32).
  2. A preallocated 78-byte grid of `n_stages` records (2,157 to 2,316 records depending on career).
     Record index `k` in this grid corresponds directly to `stage_key == k` in `fix_man.dat`.
  3. An auxiliary tail (~25 KB - 54 KB) containing:
     - Part 1: ~1,152 tournament scheduling blocks (`[u32 count][u32 id, u16 year] * count`).
     - Part 2: Exactly 398 records of 55 bytes each, which is the complete Competition
       Roll of Honour / Winners table across all 7 seasons in the save.
"""
import struct

from . import archive as A
from . import primitives as P
from . import records as RD
from .schema import Field, PAD, Record, U16, U32, U8, UNKNOWN

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

MEMBER = "comp_man.dat"
MEMBER_HEADER = 6     # Decompressed member payload opens with 6-byte '[03][01]tad.'


def load_blob(mm):
    """Decompressed payload of comp_man.dat (excluding 6-byte MEMBER_HEADER)."""
    raw = A.extract(mm, MEMBER)
    return raw[MEMBER_HEADER:]


def header(blob):
    """Parsed 36-byte file header."""
    return RD.read(blob, HEADER, 0)


def stages(blob):
    """[{stage_key: int, ...}] for every stage record in the 78-byte grid."""
    hdr = header(blob)
    n_stages = hdr["n_stages"]
    out = []
    for k in range(n_stages):
        base = HEADER_STRIDE + k * STAGE_STRIDE
        r = RD.read(blob, STAGE, base)
        r["stage_key"] = k
        out.append(r)
    return out


def honours(blob):
    """[{comp_cid, season, winner_tid, runner_up_tid, ...}] from the 55-byte Roll of Honour grid."""
    opener = b"\xff\xff\xff\xff\xff\x00\x00\x00"
    out = []
    i = HEADER_STRIDE
    n = len(blob)
    # Search for the 55-byte grid opener in the tail
    while i <= n - HONOUR_STRIDE:
        if blob[i:i + 8] == opener:
            r = RD.read(blob, HONOUR, i)
            # Filter sentinel values
            if r["winner_tid"] == 0xFFFFFFFF:
                r["winner_tid"] = None
            if r["runner_up_tid"] == 0xFFFFFFFF:
                r["runner_up_tid"] = None
            if r["third_place_tid"] == 0xFFFFFFFF:
                r["third_place_tid"] = None
            if r["fourth_place_tid"] == 0xFFFFFFFF:
                r["fourth_place_tid"] = None
            out.append(r)
            i += HONOUR_STRIDE
        else:
            i += 1
    return out
