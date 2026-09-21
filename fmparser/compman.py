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

from .schemas.compman import (
    HEADER,
    HEADER_STRIDE,
    HONOUR,
    HONOUR_STRIDE,
    STAGE,
    STAGE_STRIDE,
)

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
