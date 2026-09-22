#!/usr/bin/env python3
"""`fixtures` — the world fixture list from `fix_man.dat`.

Located inside the save's zstd tail archive member `fix_man.dat`.
Contains world match fixtures tiled across contiguous 92-byte segments.
"""
from typing import Any, Dict, List, Optional, Set, Tuple

from .. import archive as A
from .. import records as RD
from ..core import Field, PAD, Record, TableDef, U8, U16, U32, UNKNOWN
from ..core.primitives import u16 as _u16, ymd_from as _ymd_from

__all__ = [
    "DAY_BASE",
    "DAY_MASK",
    "FIXTURE",
    "FIXTURES_TABLE",
    "MEMBER",
    "MEMBER_HEADER",
    "NO_ROUND",
    "OPENER",
    "STRIDE",
    "fixtures",
    "locate_fixtures",
    "read_fixture",
    "scrape",
    "segments",
    "summary",
]

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

MEMBER = "fix_man.dat"
MEMBER_HEADER = 6             # every member's decompressed payload opens [03][01]['tad.']
NO_ROUND = 0xFF           # +78 when the match belongs to no matchday (friendlies)


def segments(blob: Any) -> List[Tuple[int, int]]:
    """[(start, count)] for each grid in the member, from the member's own structure."""
    hits = []
    i = MEMBER_HEADER
    n = len(blob)
    while i + STRIDE <= n:
        if blob[i + 1] == OPENER and blob[i + 2:i + 6] == b"\xff\xff\xff\xff":
            hits.append(i)
            i += STRIDE
        else:
            i += 1
    if not hits:
        return []
    out, start, prev = [], hits[0], hits[0]
    for h in hits[1:]:
        if h - prev != STRIDE:
            out.append((start, (prev - start) // STRIDE + 1))
            start = h
        prev = h
    out.append((start, (prev - start) // STRIDE + 1))
    return out


def locate_fixtures(blob: Any) -> Optional[Tuple[int, int]]:
    """(base, record_count) for TableDef locator protocol (first segment).

    For full segmented iteration across all segments in fix_man.dat,
    scrape() / fixtures() calls segments() and FIXTURES_TABLE.
    """
    segs = segments(blob)
    if not segs:
        return None
    return segs[0]


def _process_fixture(r: Dict[str, Any], offset: int) -> Dict[str, Any]:
    hg = None if r["home_goals"] == 0xFF else r["home_goals"]
    ag = None if r["away_goals"] == 0xFF else r["away_goals"]
    hp = None if r["home_pens"] == 0xFF else r["home_pens"]
    ap = None if r["away_pens"] == 0xFF else r["away_pens"]
    rnd = None if r["round"] == NO_ROUND else r["round"]
    rnd_idx = None if r["stage_attr_77"] == 0xFF else r["stage_attr_77"]
    d_day = (r["day_raw"] & DAY_MASK) - DAY_BASE
    return {
        "home_tid": r["home_tid"],
        "away_tid": r["away_tid"],
        "date": _ymd_from(r["year"], d_day),
        "year": r["year"],
        "round": rnd,
        "home_goals": hg,
        "away_goals": ag,
        "home_pens": hp,
        "away_pens": ap,
        "stage_key": r["stage_key"],
        "seq_id": r["seq_id"],
        "season_year": None if r["season_year"] == 0 else r["season_year"],
        "stage_index": r["stage_attr_76"],
        "round_index": rnd_idx,
        "subr": r["stage_attr_83"],
    }


FIXTURES_TABLE = TableDef(
    name="fixtures",
    segments=(FIXTURE,),
    locator=locate_fixtures,
    include_offset=False,
    post_process=_process_fixture,
)


def read_fixture(blob: Any, o: int) -> Dict[str, Any]:
    """Decode one fixture record with normalized fields."""
    r = FIXTURE.read(blob, o)
    return _process_fixture(r, o)


def scrape(blob: Any, valid_clubs: Optional[Set[int]] = None) -> List[Dict[str, Any]]:
    """[{home_tid, away_tid, date, year, round, ...}] for every match in decompressed fix_man.dat."""
    wanted_fields = (
        "home_tid", "away_tid", "day_raw", "year", "round",
        "home_goals", "away_goals", "home_pens", "away_pens",
        "stage_key", "seq_id", "season_year",
        "stage_attr_76", "stage_attr_77", "stage_attr_83",
    )
    out = []
    for start, count in segments(blob):
        for k in range(count):
            base = start + k * STRIDE
            r = RD.read_fields(blob, FIXTURE, base, wanted_fields)
            if valid_clubs is not None and (r["home_tid"] not in valid_clubs
                                            or r["away_tid"] not in valid_clubs):
                continue
            out.append(_process_fixture(r, base))
    return out


def fixtures(mm: Any, valid_clubs: Optional[Set[int]] = None) -> List[Dict[str, Any]]:
    """Extract fixtures from save mmap via member fix_man.dat."""
    blob = A.extract(mm, MEMBER)
    return scrape(blob, valid_clubs=valid_clubs)


def summary(mm: Any) -> Dict[str, Any]:
    """Counts for a quick sanity read, without building the whole list."""
    blob = A.extract(mm, MEMBER)
    segs = segments(blob)
    years: Dict[int, int] = {}
    for start, count in segs:
        y = _u16(blob, start + FIXTURE.field("year").offset)
        years[y] = years.get(y, 0) + count
    return {"segments": len(segs), "records": sum(c for _, c in segs), "by_year": years}
