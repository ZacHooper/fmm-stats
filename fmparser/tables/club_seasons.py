#!/usr/bin/env python3
"""`club_seasons` — the managed club's record, season by season: its league line (position,
played, won, lost, drawn, goals, points) and the cups it played.

Straight after the tactic history (`tactic_history.py`), in a pool of 50 slots:

    [u8 k]                        seasons stored, less one: the last is the season in progress
    k + 1 seasons, each:
      [cup_count u8][club_tid u16][year u16]           SEASON_HEAD
      cup_count x 11 B                                  CUP_RUN: one per cup played
      14 B                                              LEAGUE_LINE
    then 50 - (k + 1) empty slots of 19 bytes (`EMPTY`)

`year` is the season's start year (2025 = 2025/26). The league line is the table as it
stands: on frem-2026-06-11 the 2025 line is 3rd, 32 played, 14 won, 7 lost, 11 drawn, 44-27,
53 points, which is exactly what the world fixture list gives for Frem's two 2025/26 league
stages (22 + 10 games). Note the stored order: won, lost, drawn. On every season measured,
points = 3 x won + drawn. A season not started has `cid` ffff and zeros. On a finished
season `position_index` is the final position (0 in all four of Frem's title seasons); mid
season it is not the table position (Truro reads 17 after its opener, standing 4th-7th).

A cup run names the cup (Sydbank Pokalen, EURO Cup, European Champions Cup on Frem) and two
u16s not yet read; the second is a round-name id ("Second Round", "Quarter Final") on most
runs but not all.

**How it is found.** The byte after the tactic history is `k`; the locator walks the k + 1
seasons and accepts them only if every one names the same club and the rest of the 50 slots
are `EMPTY`.
"""
from typing import Any, Dict, List, Optional, Tuple

from ..core import Field, Record, TableDef, RAW, U8, U16, UNKNOWN
from ..save import cache_key as _cache_key

__all__ = ["CUP_RUN", "LEAGUE_LINE", "SEASON_HEAD", "CLUB_SEASONS_TABLE", "SLOTS",
           "club_seasons_table_spans", "locate_club_seasons", "scrape_club_seasons"]

SLOTS = 50

SEASON_HEAD = Record("club_season_head", 5, (
    Field(0, 1, "cup_count", U8, note="cup runs that follow"),
    Field(1, 2, "club_tid", U16, note="the managed club"),
    Field(3, 2, "year", U16, note="the season's start year"),
), is_head=True)

CUP_RUN = Record("club_season_cup", 11, (
    Field(0, 2, "cid", U16, note="the cup"),
    Field(2, 2, UNKNOWN, U16, note="the club again"),
    Field(4, 2, UNKNOWN, U16, note="the year again"),
    Field(6, 2, UNKNOWN, U16, note="ffff on most runs"),
    Field(8, 2, UNKNOWN, U16, note="a round-name id on most runs (Second Round, Quarter Final)"),
    Field(10, 1, UNKNOWN, RAW, note="ff"),
))

LEAGUE_LINE = Record("club_season_league", 14, (
    Field(0,  1, UNKNOWN, U8, note="0"),
    Field(1,  2, "cid", U16, note="the league; ffff before the season's first game"),
    Field(3,  1, "position_index", U8, note="final position on a finished season, 0 = 1st; "
                                            "not the table position mid-season"),
    Field(4,  1, "played", U8),
    Field(5,  1, "won", U8),
    Field(6,  1, "lost", U8, note="lost before drawn, as stored"),
    Field(7,  1, "drawn", U8),
    Field(8,  2, "goals_for", U16),
    Field(10, 2, "goals_against", U16),
    Field(12, 2, "points", U16, note="3 x won + drawn on every season measured"),
), is_head=True)

EMPTY = bytes.fromhex("00ffffb30700ffff0000000000000000000000")
EMPTY_SPAN = SEASON_HEAD.span + LEAGUE_LINE.span


class CupRuns:
    """The season's cup runs: `cup_count` items, the count being the season head's first
    byte, five bytes before the list."""
    name = "cups"

    def read(self, mm: Any, offset: int, limit: int) -> Optional[Tuple[Dict[str, Any], int]]:
        n = mm[offset - SEASON_HEAD.span]
        end = offset + n * CUP_RUN.span
        if end > limit:
            return None
        return {"cups": [CUP_RUN.read(mm, offset + i * CUP_RUN.span) for i in range(n)]}, end

    def instances(self, mm: Any, offset: int) -> List[Tuple[Record, int]]:
        n = mm[offset - SEASON_HEAD.span]
        return [(CUP_RUN, offset + i * CUP_RUN.span) for i in range(n)]


_CACHE: Dict[Any, Optional[Tuple[int, int]]] = {}


def _walk_end(mm: Any, base: int, count: int) -> Tuple[int, set]:
    pos, clubs = base, set()
    for _ in range(count):
        n, club = mm[pos], int.from_bytes(mm[pos + 1:pos + 3], "little")
        clubs.add(club)
        pos += SEASON_HEAD.span + n * CUP_RUN.span + LEAGUE_LINE.span
    return pos, clubs


def locate_club_seasons(mm: Any) -> Optional[Tuple[int, int]]:
    """(season 0, seasons stored), or None unless the seasons name one club and the rest of
    the 50 slots are empty."""
    key = _cache_key(mm)
    if key in _CACHE:
        return _CACHE[key]
    from .tactic_history import tactic_history_table_spans
    res = None
    spans = tactic_history_table_spans(mm)
    if spans:
        at = spans[0][1]
        count = mm[at] + 1
        base = at + 1
        end, clubs = _walk_end(mm, base, count)
        if len(clubs) == 1 and count <= SLOTS and all(
                mm[end + i * EMPTY_SPAN:end + (i + 1) * EMPTY_SPAN] == EMPTY
                for i in range(SLOTS - count)):
            res = (base, count)
    _CACHE[key] = res
    return res


def club_seasons_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """The pool, its count byte and empty slots included."""
    loc = locate_club_seasons(mm)
    if not loc:
        return []
    end, _ = _walk_end(mm, loc[0], loc[1])
    return [(loc[0] - 1, end + (SLOTS - loc[1]) * EMPTY_SPAN)]


def _post(rec: Dict[str, Any], off: int) -> Dict[str, Any]:
    league = {k: rec[k] for k in ("position_index", "played", "won", "lost", "drawn",
                                  "goals_for", "goals_against", "points")}
    league = {"cid": rec["cid"], **league}
    return {"club_tid": rec["club_tid"], "year": rec["year"],
            "cups": [{"cid": c["cid"]} for c in rec["cups"]], "league": league}


CLUB_SEASONS_TABLE = TableDef(
    name="club_seasons",
    segments=(SEASON_HEAD, CupRuns(), LEAGUE_LINE),
    locator=locate_club_seasons,
    post_process=_post,
)


def scrape_club_seasons(mm: Any) -> List[Dict[str, Any]]:
    """Every stored season, oldest first. Raises `ValueError` when not located."""
    loc = locate_club_seasons(mm)
    if loc is None:
        raise ValueError("club_seasons: the pool after the tactic history does not read")
    rows = CLUB_SEASONS_TABLE.scrape(mm)
    if len(rows) != loc[1]:
        raise ValueError(f"club_seasons: walk read {len(rows)} of {loc[1]} seasons")
    return rows
