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

FMM27 (251 on Truro) stores fmm-editor's FMM26 `Nation`: the names terminated 0xFF, no
ranking history, and after the languages a men's and a women's national team, each behind a
presence flag (NATIONS_TABLE_FMM27; `nations_table(mm)` picks the declaration):

  [uid u32][id u16], the three names, NATION_TAIL     as FMM22
  [7 B]                                               NATION_INFO_FMM27
  [u8 n][n x (language_id u16, proficiency u8)]       languages
  [u8 flag][19 B][u8 n][n x f32][11 B] if flag        the men's team, then the women's
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..core import (Conditional, CountedList, F32, Field, PAD, PString, RAW, Record, TableDef,
                    U8, U16, U32, UNKNOWN, table_spans)
from .save_header import FMM27, save_format
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
    Field(1, 8, UNKNOWN, RAW),             # ff 7f d4 00 00 00 ff 7f on all but Denmark
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
    sig = struct.pack("<IHI", 5, 0, 7) + b"Algeria"
    pos = mm.find(sig)
    while pos != -1 and res is None:
        if pos >= 10 and mm[pos - 10:pos - 2] == b"\xff" * 8:
            res = (pos, struct.unpack_from("<H", mm, pos - 2)[0])
        pos = mm.find(sig, pos + 1)
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


# FMM27: fmm-editor's `StateOfDevelopment`, two unnamed values, `Region`, one more byte.
NATION_INFO_FMM27 = Record("nation_info_fmm27", 7, (
    Field(0, 1, "state_of_development", U8, note="fmm-editor's name"),
    Field(1, 1, UNKNOWN, U8),
    Field(2, 2, UNKNOWN, U16),
    Field(4, 2, "region_id", U16, note="fmm-editor's `Region`"),
    Field(6, 1, UNKNOWN, U8),
), is_head=True)


def _team(sex: str, prefix: str) -> Conditional:
    """FMM27's national team for `sex` (fmm-editor's `NationalTeam`): `[u8 present]`, then,
    when present, 19 bytes, the coefficients and 11 bytes. The men's team keeps FMM22's keys
    (its single team is the men's); the women's are prefixed."""
    flag = Record(f"nation_{sex}_flag", 1, (Field(0, 1, f"has_{sex}_team", U8),), is_head=True)
    body = Record(f"nation_{sex}_team", 19, (
        Field(0, 8, UNKNOWN, RAW, note="four colours"),
        Field(8, 1, f"{prefix}game_importance", U8, note="fmm-editor's name"),
        Field(9, 2, f"{prefix}rival_nation_id", U16, note="0xffff = none"),
        Field(11, 1, UNKNOWN, U8),
        Field(12, 1, f"{prefix}is_ranked", U8),
        Field(13, 2, f"{prefix}world_ranking", U16),
        Field(15, 2, f"{prefix}ranking_points", U16),
        Field(17, 2, UNKNOWN, U16),
    ), is_head=True)
    end = Record(f"nation_{sex}_team_end", 11, (Field(0, 11, UNKNOWN, RAW),), is_head=True)
    coeff = CountedList(f"{prefix}coefficients", U8, _COEFFICIENT, scalar=True, max_count=32)
    return Conditional(f"{sex}_team", flag, (body, coeff, end),
                       present=lambda head: head[f"has_{sex}_team"] == 1)


def _nation_fmm27(row: Dict[str, Any], offset: int) -> Dict[str, Any]:
    out = {k: row[k] for k in ("id", "uid", "name", "nationality", "code", "continent_id",
                               "capital_city_id", "national_stadium_id")}
    out["offset"] = offset
    out["state_of_development"] = row["state_of_development"]
    out["region_id"] = row["region_id"]
    for prefix, sex in (("", "men"), ("women_", "women")):
        out[f"has_{sex}_team"] = bool(row[f"has_{sex}_team"])
        if not row[f"has_{sex}_team"]:
            continue
        rival = row[f"{prefix}rival_nation_id"]
        out[f"{prefix}rival_nation_id"] = rival if 0 < rival <= 4096 else None
        out[f"{prefix}is_ranked"] = bool(row[f"{prefix}is_ranked"])
        out[f"{prefix}world_ranking"] = row[f"{prefix}world_ranking"]
        out[f"{prefix}ranking_points"] = row[f"{prefix}ranking_points"]
        out[f"{prefix}coefficients"] = [round(c, 4) for c in row[f"{prefix}coefficients"]]
    out["languages"] = row["languages"]
    return out


NATIONS_TABLE_FMM27 = TableDef(
    name="nations",
    segments=(
        NATION_HEAD,
        PString("name", null_terminated=True, terminator=0xFF),
        PString("nationality", null_terminated=True, terminator=0xFF),
        PString("code", null_terminated=False),
        NATION_TAIL,
        NATION_INFO_FMM27,
        CountedList("languages", U8, LANGUAGE_SKILL, max_count=32),
        _team("men", ""),
        _team("women", "women_"),
    ),
    locator=locate_nations,
    invariant=lambda row, i: row["id"] == i,
    post_process=_nation_fmm27,
)


def nations_table(mm: Any) -> TableDef:
    """The nation table's declaration for this save's format."""
    return NATIONS_TABLE_FMM27 if save_format(mm) == FMM27 else NATIONS_TABLE


def scrape_nations(mm: Any) -> Dict[int, Dict[str, Any]]:
    """{nation_id: record} for every nation in the save."""
    return {r["id"]: r for r in nations_table(mm).scrape(mm)}


def nations_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """[(start, end)] covering the nations table, count frame included."""
    return table_spans(mm, nations_table(mm))
