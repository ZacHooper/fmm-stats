#!/usr/bin/env python3
"""`player_rows` — one 72-byte row per player, by tid, straight after the Player Form lines
(`player_form.py`). FMM27 only so far.

    [u8 0][u32 n][n x 72 B]          n = 36,343 (Jul-Aug) / 36,345 (16 Nov) on Truro

**league_ability** (+20, u16) is the player's current ability on his league's own scale:
within a league it tracks current ability almost exactly (median r = 0.95 over 100
leagues; 0.954 in Truro's league, 595 players), across leagues not at all, and it moves when
ability moves (r = 0.75 between saves). Truro's squad orders by it as the Coach Report's
ability stars do (3.5 stars 59-74, 2.5 stars 53, 0.5 stars 35, 16 Nov). It is derived from
ability: presentation treats it as the site's Level %ile is treated (`[immersion]`); the
parser reads it as stored.

Not named: four u32 player-table indexes at +4 and two more inside +48, each column a random
permutation of the players redrawn between saves (engine working state); +22, set only on
players aged 21 or under (20-118, updated in batches, not potential, not days to a
birthday); six u32 at +24, `ffffffff` on most players and 100 on the 7,389 of Truro's and
nearby leagues. See `docs/parser/unread/player_rows.md`.

**How it is found.** Where the Player Form lines end: a `00`, then the u32 count, then rows
whose tids rise strictly, every one (`player_form.locate_player_form` checks the same run).
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..core import Field, Record, TableDef, RAW, U16, U32, UNKNOWN
from ..save import cache_key as _cache_key

__all__ = ["PLAYER_ROW", "PLAYER_ROWS_TABLE", "locate_player_rows", "player_rows_table_spans",
           "scrape_player_rows"]

PLAYER_ROW = Record("player_row", 72, (
    Field(0,  4,  "tid", U32, note="ascending"),
    Field(4,  16, UNKNOWN, RAW, note="four player-table indexes, random, redrawn between saves"),
    Field(20, 2,  "league_ability", U16, note="current ability on the league's scale"),
    Field(22, 2,  UNKNOWN, U16, note="players aged 21 or under only (20-118); ffff otherwise"),
    Field(24, 24, UNKNOWN, RAW, note="six u32: ffffffff, or 100 on Truro's and nearby leagues"),
    Field(48, 24, UNKNOWN, RAW, note="two indexes, two of +24's values, the two indexes again"),
))

_CACHE: Dict[Any, Optional[Tuple[int, int]]] = {}


def locate_player_rows(mm: Any) -> Optional[Tuple[int, int]]:
    """(row 0, count), or None: behind the Player Form lines, which are located only when
    this run's tids rise strictly."""
    key = _cache_key(mm)
    if key in _CACHE:
        return _CACHE[key]
    from .player_form import FORM_LINE, locate_player_form
    res = None
    form = locate_player_form(mm)
    if form:
        end = form[0] + form[1] * FORM_LINE.span
        res = (end + 5, struct.unpack_from("<I", mm, end + 1)[0])
    _CACHE[key] = res
    return res


def player_rows_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """The rows, the `00` and the u32 count in front included."""
    loc = locate_player_rows(mm)
    return [(loc[0] - 5, loc[0] + loc[1] * PLAYER_ROW.span)] if loc else []


PLAYER_ROWS_TABLE = TableDef(name="player_rows", segments=(PLAYER_ROW,),
                             locator=locate_player_rows)


def scrape_player_rows(mm: Any) -> List[Dict[str, Any]]:
    """Every row, in tid order: tid and league_ability. Raises `ValueError` when not
    located."""
    loc = locate_player_rows(mm)
    if loc is None:
        raise ValueError("player_rows: not located (the Player Form lines in front were not)")
    rows = PLAYER_ROWS_TABLE.scrape(mm)
    if len(rows) != loc[1]:
        raise ValueError(f"player_rows: read {len(rows)} of {loc[1]} rows")
    return rows
