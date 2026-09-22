#!/usr/bin/env python3
"""`comp_honours` — the master competition roll of honour / winners table from `comp_man.dat`.

Located inside the save's zstd tail archive member `comp_man.dat`.
Tail table consisting of 55-byte records opening with `b"\\xff\\xff\\xff\\xff\\xff\\x00\\x00\\x00"`.
"""
from typing import Any, Dict, List, Optional, Tuple

from ..core import Field, PAD, Record, TableDef, U16, U32, UNKNOWN
from ..core.primitives import NO_ID32

__all__ = [
    "COMP_HONOURS_TABLE",
    "HONOUR",
    "OPENER",
    "STRIDE",
    "honours",
    "locate_comp_honours",
    "read_honour",
    "scrape",
]

STRIDE = 55
OPENER = b"\xff\xff\xff\xff\xff\x00\x00\x00"

HONOUR = Record("comp_man_honour", STRIDE, [
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


def locate_comp_honours(blob: Any) -> Optional[Tuple[int, int]]:
    """(base, record_count) for TableDef locator protocol within comp_man.dat payload."""
    n = len(blob)
    first_idx = blob.find(OPENER)
    if first_idx == -1:
        return None

    # Count contiguous records matching OPENER with stride 55
    count = 0
    i = first_idx
    while i + STRIDE <= n and blob[i:i + 8] == OPENER:
        count += 1
        i += STRIDE

    if count == 0:
        return None
    return (first_idx, count)


def _process_honour(rec: Dict[str, Any], offset: int) -> Dict[str, Any]:
    for key in ("winner_tid", "runner_up_tid", "third_place_tid", "fourth_place_tid"):
        if rec[key] == NO_ID32:
            rec[key] = None
    return rec


COMP_HONOURS_TABLE = TableDef(
    name="comp_honours",
    segments=(HONOUR,),
    locator=locate_comp_honours,
    include_offset=False,
    post_process=_process_honour,
)


def read_honour(blob: Any, o: int) -> Dict[str, Any]:
    """Decode one honour record, mapping sentinel values to None."""
    r = HONOUR.read(blob, o)
    return _process_honour(r, o)


def scrape(blob: Any) -> List[Dict[str, Any]]:
    """[{comp_cid, season, winner_tid, runner_up_tid, ...}] from the 55-byte Roll of Honour grid."""
    return COMP_HONOURS_TABLE.scrape(blob)


# Backwards compatibility alias for compman.honours
honours = scrape
