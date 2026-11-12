#!/usr/bin/env python3
"""`team_history` — every team-of-the-period the game has picked: Team of the Week, Team of
the Year, Squad of the Season, Dream Team, Players' Select, Best XI.

Straight after the award history (`award_history.py`):

    [count u32]                            0 on day one, 845 on frem-2026-06-11, 4 on truro-2026-08-08
    per team, 316 bytes:
      [award_id u32][day u16][year u16]    the award (an awards row) and the date
      11 x 28 B                            the eleven: person, name ids, club, rating

Every row's award is a team award on every save measured (All-Star XI included). A
club of ffffffff is none. A player's name ids are his as
they were when picked (9,268 of 9,295 still his own on frem-2026-06-11).
"""
from typing import Any, Dict, List, Optional, Tuple

from ..core import DATE, F32, Field, FixedList, Record, TableDef, U32, UNKNOWN
from ..save import cache_key as _cache_key
from .award_history import award_history_table_spans

__all__ = ["TEAM_HEAD", "TEAM_PLAYER", "TEAM_HISTORY_TABLE", "locate_team_history",
           "scrape_team_history", "team_history_table_spans"]

TEAM_HEAD = Record("team_head", 8, (
    Field(0, 4, "award_id", U32, note="an awards row: a team award"),
    Field(4, 4, "date", DATE, note="the week or season the team is for"),
), is_head=True)

TEAM_PLAYER = Record("team_player", 28, (
    Field(0,  4, "person_tid", U32, note="ffffffff on an unfilled place"),
    Field(4,  4, "first_name_id", U32, note="his name as it was"),
    Field(8,  4, "last_name_id", U32),
    Field(12, 4, "common_name_id", U32),
    Field(16, 4, "club_tid", U32),
    Field(20, 4, "rating", F32, note="6.0-10.0"),
    Field(24, 4, UNKNOWN, U32, note="0 on every place measured"),
))

STRIDE = TEAM_HEAD.span + 11 * TEAM_PLAYER.span
_CACHE: Dict[Any, Optional[Tuple[int, int]]] = {}


def locate_team_history(mm: Any) -> Optional[Tuple[int, int]]:
    """(team 0, count): the u32 count straight after the award history."""
    key = _cache_key(mm)
    if key in _CACHE:
        return _CACHE[key]
    res = None
    spans = award_history_table_spans(mm)
    if spans:
        at = spans[-1][1]
        res = (at + 4, int.from_bytes(mm[at:at + 4], "little"))
    _CACHE[key] = res
    return res


TEAM_HISTORY_TABLE = TableDef(
    name="team_history",
    segments=(TEAM_HEAD, FixedList("players", TEAM_PLAYER, 11)),
    locator=locate_team_history,
)


def team_history_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """The table, its u32 count included."""
    loc = locate_team_history(mm)
    return [(loc[0] - 4, loc[0] + loc[1] * STRIDE)] if loc else []


def _post(rec: Dict[str, Any]) -> Dict[str, Any]:
    for p in rec["players"]:
        p["rating"] = round(p["rating"], 4)
    return rec


def scrape_team_history(mm: Any) -> List[Dict[str, Any]]:
    """Every team, in stored order. Raises `ValueError` when not located, when the walk is
    short, or when a team names an award the awards table doesn't have."""
    from .awards import locate_awards
    loc = locate_team_history(mm)
    if loc is None:
        raise ValueError("team_history: the award history is not located")
    rows = [_post(r) for r in TEAM_HISTORY_TABLE.scrape(mm)]
    if len(rows) != loc[1]:
        raise ValueError(f"team_history: walk read {len(rows)} of {loc[1]} declared")
    awards = locate_awards(mm)[1]
    if any(r["award_id"] >= awards for r in rows):
        raise ValueError("team_history: a team names no award")
    return rows
