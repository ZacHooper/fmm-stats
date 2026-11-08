#!/usr/bin/env python3
"""`comp_honours` — the competition roll of honour, the last table in `comp_man.dat`.

`[count u32][count x 55 B]`, ending on the member's last byte: one record per finished
competition season, in the order the seasons finished. The count frames it: the table starts
`4 + count x 55` bytes before the member's end, and that position holds `count`. Every record
carries `ff x 20` then `00 x 3` at +24. docs/parser/comp_honours.md is the reference.
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..core import Field, PAD, RAW, Record, TableDef, U16, U32, UNKNOWN
from ..core.primitives import NO_ID32

__all__ = [
    "COMP_HONOURS_TABLE",
    "COUNT",
    "HONOUR",
    "SIGNATURE",
    "SIGNATURE_AT",
    "STRIDE",
    "honours",
    "locate_comp_honours",
    "read_honour",
    "scrape",
]

STRIDE = 55
SIGNATURE_AT = 24
SIGNATURE = b"\xff" * 20 + b"\x00" * 3

COUNT = Record("comp_man_honours_count", 4, [
    Field(0, 4, "count", U32, note="records that follow; count x 55 ends on the member's last byte"),
])

HONOUR = Record("comp_man_honour", STRIDE, [
    Field(0,  4, "comp_cid", U32, note="competition cid"),
    Field(4,  4, "season", U32, note="end year of the season (2029 = 2028/29)"),
    Field(8,  4, "winner_tid", U32, note="1st place / cup winner, club tid"),
    Field(12, 4, "runner_up_tid", U32, note="2nd place / losing finalist, club tid"),
    Field(16, 4, "third_place_tid", U32, note="3rd place club tid; ffffffff on a cup"),
    Field(20, 4, "fourth_place_tid", U32, note="ffffffff on every record measured"),
    Field(24, 20, UNKNOWN, PAD, note="0xFF x 20"),
    Field(44, 3, UNKNOWN, PAD, note="0x00 x 3"),
    Field(47, 2, "start_year", U16, note="the season's first calendar year"),
    Field(49, 2, "end_year", U16, note="its last; equal for a calendar-year competition"),
    Field(51, 2, UNKNOWN, RAW, note="1 on every record"),
    Field(53, 2, "base_year", U16, note="1900"),
])


def _framed_at(blob: Any, base: int, count: int) -> bool:
    """True if `count` records from `base` all carry the signature."""
    return all(blob[o:o + len(SIGNATURE)] == SIGNATURE
               for o in range(base + SIGNATURE_AT, base + count * STRIDE, STRIDE))


def locate_comp_honours(blob: Any) -> Optional[Tuple[int, int]]:
    """(record 0, declared count) within the comp_man.dat member: the one count `n` whose
    u32 sits `4 + n x 55` bytes before the member's end and whose `n` records all carry the
    signature. None when no count, or more than one, frames the tail."""
    end = len(blob)
    hits = []
    for n in range((end - COUNT.span) // STRIDE + 1):
        base = end - n * STRIDE
        if struct.unpack_from("<I", blob, base - COUNT.span)[0] == n and _framed_at(blob, base, n):
            hits.append((base, n))
    return hits[0] if len(hits) == 1 else None


def _process_honour(rec: Dict[str, Any], offset: int) -> Dict[str, Any]:
    for key in ("winner_tid", "runner_up_tid", "third_place_tid", "fourth_place_tid"):
        if rec[key] == NO_ID32:
            rec[key] = None
    return rec


COMP_HONOURS_TABLE = TableDef(
    name="comp_honours",
    member="comp_man.dat",
    segments=(HONOUR,),
    locator=locate_comp_honours,
    include_offset=False,
    post_process=_process_honour,
    header=COUNT,
)


def read_honour(blob: Any, o: int) -> Dict[str, Any]:
    """Decode one honour record, mapping `ffffffff` clubs to None."""
    return _process_honour(HONOUR.read(blob, o), o)


def scrape(blob: Any) -> List[Dict[str, Any]]:
    """[{comp_cid, season, winner_tid, runner_up_tid, ...}] for every record, in file order."""
    return COMP_HONOURS_TABLE.scrape(blob)


honours = scrape
