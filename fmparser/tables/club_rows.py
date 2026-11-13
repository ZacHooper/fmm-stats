#!/usr/bin/env python3
"""`club_rows` — one row per club, straight after the staff rows (`staff_rows.py`).

    [count u16 = the club count]           11,331 on Frem, 12,278 on Bucaspor, 9,830 on Truro
    per row, k = club tid k:
      50 B (FMM22) / 131 B (FMM27)         the row
      [n u8]                               0 or 1
      n x 66 B (FMM22) / n x 68 B (FMM27)  the extra block

The walk ends exactly on a u16 equal to the player-attribute count (26,505 on Frem, 36,344
on Truro), the count in front of the per-player block that follows. That landing, on every
save of both games, is the table's extent proof.

The row's first u32 is the club's **transfer budget** in pounds: Truro's reads 10,000 on
truro-2026-07-25, the Club Finances screen's "Transfer Budget £10,000" that day (Frem reads
1,030,284 on frem-2026-06-11).

**Recent results.** Twelve bytes (+117 FMM27, +36 FMM22) hold the club's last six results,
`[goals for][goals against]` each, oldest first, `ff ff` for none; a u8 ten bytes earlier
counts the season's matches, friendlies included. On truro-2026-11-16 Truro's read 2-0, 1-0,
6-0, 3-2, 1-0, 1-2 (Slough to Herne Bay) and 25 matches. Against the world fixture list the
count is exact for every club on the four Truro saves and the six results for 98%; the rest
are shoot-out games, where the pair is the shoot-out score on most and not yet explained on
29 clubs of 1,689. On FMM22 (whose fixture list spans two seasons) 80-86% agree. The rest of
the row is open.

The extra block is set for 232 clubs on frem-2021-06-27,
growing to 474 by frem-2030-06-22, and for 1,088 to 1,298 on Truro. On FMM22 it holds an f32
at +5 that neighbouring clubs of one nation share (1.45 on four Albanian clubs, 7.17 on
Afghanistan and Bahrain), then u32s that count up across those clubs (177, 178, 179, ...):
the shape of a ranking or coefficient table, not yet matched to a screen.
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..core import CountedList, Field, Record, TableDef, RAW, U8, U32, UNKNOWN
from ..save import cache_key as _cache_key
from .save_header import FMM27, save_format

__all__ = ["CLUB_ROW", "CLUB_ROW_FMM27", "CLUB_ROW_EXTRA", "CLUB_ROW_EXTRA_FMM27",
           "CLUB_ROWS_TABLE", "CLUB_ROWS_TABLE_FMM27", "club_rows_extra_count", "club_rows_table_spans",
           "locate_club_rows", "scrape_club_rows"]

CLUB_ROW = Record("club_row", 50, (
    Field(0,  4,  "transfer_budget", U32, note="pounds, as the Club Finances screen shows it"),
    Field(4,  22, UNKNOWN, RAW, note="mostly 0"),
    Field(26, 1,  "matches_played", U8, note="this season's matches, friendlies included"),
    Field(27, 9,  UNKNOWN, RAW, note="mostly 0"),
    Field(36, 12, "recent_scores", RAW, note="the last six results, [goals for][against] each, "
                                             "oldest first; ff ff = no match"),
    Field(48, 2,  UNKNOWN, RAW, note="0 on most clubs"),
), is_head=True)

CLUB_ROW_FMM27 = Record("club_row_fmm27", 131, (
    Field(0,   4,   "transfer_budget", U32, note="pounds: Truro's 10,000 is the Club Finances "
                                               "screen's £10,000 on truro-2026-07-25"),
    Field(4,   103, UNKNOWN, RAW, note="mostly 0"),
    Field(107, 1,   "matches_played", U8, note="this season's matches, friendlies included: "
                                              "every club's played fixtures, four Truro saves"),
    Field(108, 9,   UNKNOWN, RAW, note="mostly 0"),
    Field(117, 12,  "recent_scores", RAW, note="the last six results, [goals for][against] "
                                               "each, oldest first; ff ff = no match"),
    Field(129, 2,   UNKNOWN, RAW, note="0 on most clubs"),
), is_head=True)

CLUB_ROW_EXTRA = Record("club_row_extra", 66, (
    Field(0, 5,  UNKNOWN, RAW, note="01 00 00 00 00 on the rows measured"),
    Field(5, 4,  UNKNOWN, RAW, note="an f32 shared by neighbouring clubs of one nation"),
    Field(9, 57, UNKNOWN, RAW, note="u32s counting up across those clubs, then zeros"),
))

CLUB_ROW_EXTRA_FMM27 = Record("club_row_extra_fmm27", 68, (
    Field(0, 7,  UNKNOWN, RAW),
    Field(7, 4,  UNKNOWN, RAW, note="an f32 (4.0, 3.5, 7.5 on the rows measured)"),
    Field(11, 57, UNKNOWN, RAW, note="u32s"),
))

_CACHE: Dict[Any, Optional[Tuple[int, int, int]]] = {}


def _parts(mm: Any) -> Tuple[Record, Record]:
    if save_format(mm) == FMM27:
        return CLUB_ROW_FMM27, CLUB_ROW_EXTRA_FMM27
    return CLUB_ROW, CLUB_ROW_EXTRA


def _walk_end(mm: Any, base: int, count: int) -> Optional[int]:
    row, extra = _parts(mm)
    pos = base
    for _ in range(count):
        if pos + row.span >= len(mm):
            return None
        n = mm[pos + row.span]
        if n > 1:
            return None
        pos += row.span + 1 + n * extra.span
    return pos


def locate_club_rows(mm: Any) -> Optional[Tuple[int, int]]:
    """(row 0, count): a u16 equal to the club count where the staff rows end, whose rows
    end exactly on a u16 equal to the player-attribute count. None otherwise."""
    key = _cache_key(mm)
    if key in _CACHE:
        loc = _CACHE[key]
        return loc[:2] if loc else None
    from .player_attributes import locate_player_attributes
    from .staff_rows import _club_count, staff_rows_end
    res = None
    at, clubs, players = staff_rows_end(mm), _club_count(mm), locate_player_attributes(mm)
    if at is not None and clubs and players:
        count = struct.unpack_from("<H", mm, at)[0]
        end = _walk_end(mm, at + 2, count) if count == clubs else None
        if end is not None and struct.unpack_from("<H", mm, end)[0] == players[1]:
            res = (at + 2, count, end)
    _CACHE[key] = res
    return res[:2] if res else None


def _scores(raw: Any) -> List[List[int]]:
    """[[for, against], ...] oldest first, the empty `ff ff` pairs dropped."""
    b = bytes.fromhex(raw) if isinstance(raw, str) else bytes(raw)
    return [[b[i], b[i + 1]] for i in range(0, len(b), 2) if b[i] != 0xFF]


def _post(rec: Dict[str, Any], off: int) -> Dict[str, Any]:
    return {"transfer_budget": rec["transfer_budget"],
            "matches_played": rec["matches_played"],
            "recent_scores": _scores(rec["recent_scores"])}


def club_rows_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """The rows, their u16 count included."""
    if locate_club_rows(mm) is None:
        return []
    base, _, end = _CACHE[_cache_key(mm)]
    return [(base - 2, end)]


CLUB_ROWS_TABLE = TableDef(
    name="club_rows",
    segments=(CLUB_ROW, CountedList("extra", U8, CLUB_ROW_EXTRA, max_count=1)),
    locator=locate_club_rows, post_process=_post)
CLUB_ROWS_TABLE_FMM27 = TableDef(
    name="club_rows",
    segments=(CLUB_ROW_FMM27, CountedList("extra", U8, CLUB_ROW_EXTRA_FMM27, max_count=1)),
    locator=locate_club_rows, post_process=_post)


def club_rows_extra_count(mm: Any) -> int:
    """How many clubs carry the extra block."""
    row, extra = _parts(mm)
    base, count = locate_club_rows(mm)
    pos, n = base, 0
    for _ in range(count):
        k = mm[pos + row.span]
        n += k
        pos += row.span + 1 + k * extra.span
    return n


def scrape_club_rows(mm: Any) -> List[Dict[str, Any]]:
    """Every row, row k for club tid k: its transfer budget. Raises `ValueError` when not
    located."""
    loc = locate_club_rows(mm)
    if loc is None:
        raise ValueError("club_rows: no club count after the staff rows that lands on the "
                         "player-attribute count")
    table = CLUB_ROWS_TABLE_FMM27 if save_format(mm) == FMM27 else CLUB_ROWS_TABLE
    rows = table.scrape(mm)
    if len(rows) != loc[1]:
        raise ValueError(f"club_rows: walk read {len(rows)} of {loc[1]} rows")
    return rows
