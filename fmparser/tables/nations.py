#!/usr/bin/env python3
"""`nations` — the 251-record Nations catalog.

Declared by a `[>= 8 x 0xFF][count u16 = 251]` frame in the reference block (~12.75 MB),
records in id order from 0, and walked by declaration. Each record:

  [uid u32][id u16]                                       NATION_HEAD
  [len u32][name][\\0]  [len u32][nationality][\\0]  [len u32][code]
  [continent_id u16][capital_city_id u16][national_stadium_id u16]   NATION_TAIL
  [23 B: rival nation, world ranking and points, unnamed flags]      NATION_TEAM
  [u16 n][n x ranking u16]                                ranking_history, oldest first
  [u16 = 0]                                               NATION_GAP
  [u8 n][n x f32]                                         coefficients (UEFA, oldest first)
  [u8 = 0]                                                NATION_GAP2
  [u8 n][n x (language_id u16, proficiency u8)]               languages
  [11 B]                                                  NATION_END

The walk ends exactly at the continent table's own count frame, on every save of both
careers. The invariant is `id == slot index`.
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..core import (CountedList, F32, Field, PAD, PString, RAW, Record, TableDef, U8, U16, U32,
                    UNKNOWN, table_spans)
from ..save import cache_key as _cache_key

__all__ = [
    "LANGUAGE_SKILL",
    "NATION_END",
    "NATION_HEAD",
    "NATION_TAIL",
    "NATION_TEAM",
    "NATIONS_TABLE",
    "locate_nations",
    "nations_table_spans",
    "scrape_nations",
]

NATION_HEAD = Record("nation_head", 6, (
    Field(0, 4, "uid", U32),
    Field(4, 2, "id", U16),
), is_head=True)

NATION_TAIL = Record("nation_tail", 6, (
    Field(0, 2, "continent_id", U16),
    Field(2, 2, "capital_city_id", U16),
    Field(4, 2, "national_stadium_id", U16),
), is_head=True)

NATION_TEAM = Record("nation_team", 23, (
    Field(0, 1, UNKNOWN, U8),              # 0..3
    Field(1, 8, UNKNOWN, RAW),             # ff 7f d4 00 00 00 ff 7f on all but one
    Field(9, 1, UNKNOWN, U8),              # 0 / 1
    Field(10, 1, UNKNOWN, U8),             # 1..5
    Field(11, 2, "rival_nation_id", U16, note="0xffff = none"),
    Field(13, 2, UNKNOWN, U16),
    Field(15, 1, UNKNOWN, U8),
    Field(16, 2, UNKNOWN, U16),
    Field(18, 1, "is_ranked", U8),
    Field(19, 2, "world_ranking", U16),
    Field(21, 2, "ranking_points", U16),
), is_head=True)

_RANKING = Record("nation_ranking", 2, (Field(0, 2, "ranking", U16),), is_head=True)
_COEFFICIENT = Record("nation_coefficient", 4, (Field(0, 4, "coefficient", F32),),
                      is_head=True)
LANGUAGE_SKILL = Record("language_skill", 3, (
    Field(0, 2, "language_id", U16),
    Field(2, 1, "proficiency", U8, note="0..100: how well the nation speaks it"),
), is_head=True)
NATION_GAP = Record("nation_gap", 2, (Field(0, 2, UNKNOWN, U16),), is_head=True)
NATION_GAP2 = Record("nation_gap2", 1, (Field(0, 1, UNKNOWN, U8),), is_head=True)
NATION_END = Record("nation_end", 11, (Field(0, 11, UNKNOWN, RAW),), is_head=True)

_NATIONS_CACHE: Dict[str, Optional[Tuple[int, int]]] = {}


def locate_nations(mm: Any) -> Optional[Tuple[int, int]]:
    """(base, declared_count) for the nations catalog, or None.

    Record 0 (`uid=5, id=0, 'Algeria'`) sits right after a `[>= 8 x 0xFF][count u16]` frame.
    """
    key = _cache_key(mm)
    if key in _NATIONS_CACHE:
        return _NATIONS_CACHE[key]
    res = None
    pos = mm.find(struct.pack("<IHI", 5, 0, 7) + b"Algeria\x00")
    if pos >= 10 and mm[pos - 10:pos - 2] == b"\xff" * 8:
        res = (pos, struct.unpack_from("<H", mm, pos - 2)[0])
    _NATIONS_CACHE[key] = res
    return res


def _nation(row: Dict[str, Any], offset: int) -> Dict[str, Any]:
    rival = row["rival_nation_id"]
    return {
        "id": row["id"],
        "uid": row["uid"],
        "name": row["name"],
        "nationality": row["nationality"],
        "code": row["code"],
        "continent_id": row["continent_id"],
        "capital_city_id": row["capital_city_id"],
        "national_stadium_id": row["national_stadium_id"],
        "offset": offset,
        "rival_nation_id": rival if 0 < rival <= 4096 else None,
        "is_ranked": bool(row["is_ranked"]),
        "world_ranking": row["world_ranking"],
        "ranking_points": row["ranking_points"],
        "ranking_history": row["ranking_history"],
        "coefficients": [round(c, 4) for c in row["coefficients"]],
        "languages": row["languages"],
    }


NATIONS_TABLE = TableDef(
    name="nations",
    segments=(
        NATION_HEAD,
        PString("name", null_terminated=True),
        PString("nationality", null_terminated=True),
        PString("code", null_terminated=False),
        NATION_TAIL,
        NATION_TEAM,
        CountedList("ranking_history", U16, _RANKING, scalar=True, max_count=128),
        NATION_GAP,
        CountedList("coefficients", U8, _COEFFICIENT, scalar=True, max_count=32),
        NATION_GAP2,
        CountedList("languages", U8, LANGUAGE_SKILL, max_count=32),
        NATION_END,
    ),
    locator=locate_nations,
    invariant=lambda row, i: row["id"] == i,
    post_process=_nation,
)


def scrape_nations(mm: Any) -> Dict[int, Dict[str, Any]]:
    """{nation_id: record} for every nation in the save."""
    return {r["id"]: r for r in NATIONS_TABLE.scrape(mm)}


def nations_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """[(start, end)] covering the nations table, count frame included."""
    return table_spans(mm, NATIONS_TABLE)
