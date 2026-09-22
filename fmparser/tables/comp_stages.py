#!/usr/bin/env python3
"""`comp_stages` — the master competition stages calendar from `comp_man.dat`.

Located inside the save's zstd tail archive member `comp_man.dat`.
Declared count `n_stages` at header offset +10 (u32), followed by a pure fixed-stride
grid of `n_stages` x 78-byte records.
"""
from typing import Any, Dict, List, Optional, Tuple

from ..core import Field, PAD, Record, TableDef, U8, U16, U32, UNKNOWN
from ..core.primitives import u32 as _u32

__all__ = [
    "COMP_STAGES_TABLE",
    "HEADER",
    "HEADER_STRIDE",
    "STAGE",
    "STRIDE",
    "header",
    "locate_comp_stages",
    "read_stage",
    "scrape",
    "stages",
]

HEADER_STRIDE = 36
STRIDE = 78

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
STAGE = Record("comp_man_stage", STRIDE, [
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


def locate_comp_stages(blob: Any) -> Optional[Tuple[int, int]]:
    """(base, record_count) for TableDef locator protocol within comp_man.dat payload."""
    if len(blob) < HEADER_STRIDE:
        return None
    n_stages = _u32(blob, 10)
    if HEADER_STRIDE + n_stages * STRIDE > len(blob):
        return None
    return (HEADER_STRIDE, n_stages)


def _process_stage(rec: Dict[str, Any], offset: int) -> Dict[str, Any]:
    # stage_key is the 0-based record ordinal in the grid
    stage_key = (offset - HEADER_STRIDE) // STRIDE
    rec["stage_key"] = stage_key
    return rec


COMP_STAGES_TABLE = TableDef(
    name="comp_stages",
    segments=(STAGE,),
    locator=locate_comp_stages,
    include_offset=False,
    post_process=_process_stage,
)


def header(blob: Any) -> Dict[str, Any]:
    """Parsed 36-byte file header."""
    return HEADER.read(blob, 0)


def read_stage(blob: Any, o: int) -> Dict[str, Any]:
    """Decode one stage record."""
    stage_key = (o - HEADER_STRIDE) // STRIDE
    res = STAGE.read(blob, o)
    res["stage_key"] = stage_key
    return res


def scrape(blob: Any) -> List[Dict[str, Any]]:
    """[{stage_key: int, ...}] for every stage record in the 78-byte grid."""
    return COMP_STAGES_TABLE.scrape(blob)


# Backwards compatibility alias for compman.stages
stages = scrape
