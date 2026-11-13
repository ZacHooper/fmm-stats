#!/usr/bin/env python3
"""`player_season_stats` — the Player History screen's "This Season" panel: every player's
appearances, goals, assists, cards, player-of-the-match awards and rating total this season,
split by kind of competition. FMM27 and FMM22, the same layout.

Straight after the nickname id-table (`names.py`), in front of the career-history pool:

    6 blocks x [one 9 B row per player-attribute record]       no count, no frame

Row `block * players + k` belongs to player-attribute record k (the `sid`, the same order as
`player_attributes` and `player_status`); nothing points at a row, its position is the key.
The blocks, checked on truro-2026-11-16 against Omar Bogle's and Ben Starkie's Player History
screens and every Truro player's league line in our matches:

    0  club_season       the history screen's current-season line: league + cup + continental,
                         and matches for a club's B team (Valladolid B, VfB Stuttgart II)
    1  league            "League"
    2  cup               "Cup": every domestic cup together (FA Cup + FA Trophy)
    3  continental       "Continental"
    4  non_competitive   "Non Competitive": friendlies and reserve matches
    5  international     "International"

So block 0 >= block 1 + 2 + 3, field by field, on every row of every save measured (equal
unless the player has turned out for a B team). A row with no appearances is all zero. The
average rating on screen is `rating_total / apps`, truncated to two places (20 / 3 = 6.66).
The season is the current one only; past seasons are the history pool's lines.

**How it is found.** The nickname id-table's end, then six blocks of the player-attribute
count, which must end before the history pool's count; every non-empty row has
apps <= rating_total <= 10 x apps, and block 0 covers blocks 1-3 on every player. What follows
the six blocks, up to the history pool, is not this table (inline-named records,
`docs/parser/unread/named_records.md`).
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..core import Field, Record, TableDef, U8, U16
from ..save import cache_key as _cache_key

__all__ = ["BLOCKS", "SEASON_STATS_ROW", "PLAYER_SEASON_STATS_TABLE",
           "locate_player_season_stats", "player_season_stats_table_spans",
           "scrape_player_season_stats"]

BLOCKS = ("club_season", "league", "cup", "continental", "non_competitive", "international")

SEASON_STATS_ROW = Record("player_season_stats_row", 9, (
    Field(0, 1, "apps", U8),
    Field(1, 1, "goals", U8),
    Field(2, 1, "assists", U8),
    Field(3, 1, "conceded", U8, note="goals conceded, goalkeepers; 0 for the rest"),
    Field(4, 2, "rating_total", U16, note="the match ratings summed; / apps is Av R"),
    Field(6, 1, "yellows", U8),
    Field(7, 1, "reds", U8),
    Field(8, 1, "player_of_match", U8),
))
W = SEASON_STATS_ROW.span
EMPTY = bytes(W)

_CACHE: Dict[Any, Optional[Tuple[int, int, List[int]]]] = {}


def _fields(mm: Any, o: int) -> Tuple[int, ...]:
    a, g, s, c, r, y, red, pom = struct.unpack_from("<BBBBHBBB", mm, o)
    return a, g, s, c, r, y, red, pom


def _check(mm: Any, base: int, players: int) -> Optional[List[int]]:
    """The non-empty rows' indices if the six blocks at `base` read as season stats."""
    used = []
    for k in range(len(BLOCKS) * players):
        o = base + k * W
        if mm[o:o + W] == EMPTY:
            continue
        apps, rating = mm[o], struct.unpack_from("<H", mm, o + 4)[0]
        if not 1 <= apps <= rating <= 10 * apps:
            return None
        used.append(k)
    for k in range(players):
        total = _fields(mm, base + k * W)
        parts = [_fields(mm, base + (b * players + k) * W) for b in (1, 2, 3)]
        if any(sum(p[i] for p in parts) > total[i] for i in range(8)):
            return None
    return used


def _locate(mm: Any) -> Optional[Tuple[int, int, List[int]]]:
    from .history import HISTORY_HEADER, locate_history
    from .names import NAME_ID_STRIDE, locate_nicknames
    from .player_attributes import locate_player_attributes
    nick, hist, attrs = locate_nicknames(mm), locate_history(mm), locate_player_attributes(mm)
    if not nick or not hist or not attrs:
        return None
    base, players = nick[0] + nick[1] * NAME_ID_STRIDE, attrs[1]
    if base + len(BLOCKS) * players * W > hist[0] - HISTORY_HEADER.span:
        return None
    used = _check(mm, base, players)
    return (base, players, used) if used is not None else None


def locate_player_season_stats(mm: Any) -> Optional[List[Tuple[int, int]]]:
    """[(row, 1)] for every non-empty row, or None. [] is located with no matches played."""
    key = _cache_key(mm)
    if key not in _CACHE:
        _CACHE[key] = _locate(mm)
    res = _CACHE[key]
    return [(res[0] + k * W, 1) for k in res[2]] if res else None


def player_season_stats_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """All six blocks, empty rows included."""
    if locate_player_season_stats(mm) is None:
        return []
    base, players, _ = _CACHE[_cache_key(mm)]
    return [(base, base + len(BLOCKS) * players * W)]


PLAYER_SEASON_STATS_TABLE = TableDef(name="player_season_stats", segments=(SEASON_STATS_ROW,),
                                     locator=locate_player_season_stats)


def scrape_player_season_stats(mm: Any) -> List[Dict[str, Any]]:
    """Every non-empty row, block by block and in player-attribute order within a block, each
    with its `sid` (the attribute record, as `player_status.json` writes it) and `block`.
    Raises `ValueError` when not located."""
    if locate_player_season_stats(mm) is None:
        raise ValueError("player_season_stats: no six blocks of season stats after the "
                         "nickname id-table")
    base, players, used = _CACHE[_cache_key(mm)]
    rows = PLAYER_SEASON_STATS_TABLE.scrape(mm)
    if len(rows) != len(used):
        raise ValueError(f"player_season_stats: read {len(rows)} of {len(used)} rows")
    out = []
    for r, k in zip(rows, used):
        block, sid = divmod(k, players)
        out.append({"sid": struct.pack("<I", sid).hex(), "block": BLOCKS[block], **r})
    return out
