#!/usr/bin/env python3
"""`player_form` — the Player Form page: one line per player of the managed club per
competitive match of the season. FMM27 only so far.

In the block after the club titles (`docs/parser/unread/end_block.md`), behind three 50-slot
pools:

    [u8 n][50 x 12 B]   [u8 n][50 x 6 B]   [u8 n][50 x 7 B]      the pools (n <= 50)
    [u16 n][n x 26 B]                                            FORM_LINE: this table
    [u8 0][u32 N][N x 72 B]                                      a row per player, by tid

**What a line is.** For each competitive match (league and cups; not friendlies) the game
writes a line for every player in the managed club's squad that day, whether he played or
not: 0 lines on truro-2026-07-22 and -07-25 (friendlies only), 27 on -08-08 (the league
opener), 548 on -11-16 (20 matches). They are the Player Form page: Omar Bogle's 20 lines
on 16 Nov are the 20 matches of his page in order, rating, goals, assists, morale arrow,
player-of-the-match star, yellow card and substitution arrows all agreeing.

`rating` is the match rating (1-10) when he played, 0 when he did not; 11, 12 and 15 are
status codes on lines of players outside the matchday squad (injured? ineligible? not yet
named). `goals` is goals conceded on a goalkeeper's line. Joined to the match table on
player, opponent and meeting, 357 of the 359 lines of players in a match's 16 agree on
rating, goals (conceded for keepers), assists and yellow cards; the two others are Caleb
Roberts on the bench, reading 12.

**How it is found.** From the club titles' end, the three pools (each count <= 50), then the
u16 count; the walk must land on a `00` and a u32 N whose N 72-byte rows have strictly
ascending tids (`docs/parser/unread/player_rows.md`), every save. Every line's tid must be a
person.
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..core import Field, Record, TableDef, RAW, U8, U16, U32, UNKNOWN
from ..save import cache_key as _cache_key
from .save_header import FMM27, save_format

__all__ = ["FORM_LINE", "PLAYER_FORM_TABLE", "locate_player_form", "player_form_table_spans",
           "scrape_player_form"]

POOLS = ((12, 50), (6, 50), (7, 50))   # (slot width, slots) of the three pools in front
ROW = 72                                # the per-player rows that follow

FORM_LINE = Record("player_form_line", 26, (
    Field(0,  4, "tid", U32, note="the player (the managed club's squad that day)"),
    Field(4,  2, "opponent_tid", U16),
    Field(6,  1, UNKNOWN, U8, note="2 or 3; not home/away, not the competition"),
    Field(7,  3, "match_id", RAW, note="u24, counting up through the season"),
    Field(10, 2, "home_tid", U16, note="the home side: the opponent away, us at home"),
    Field(12, 6, UNKNOWN, RAW, note="0 on most lines; a byte 1 or 8 at +14 on a few"),
    Field(18, 1, "morale", U8, note="1-20 at the match: the form page's MI arrow"),
    Field(19, 1, "rating", U8, note="1-10 played; 0 not involved; 11, 12, 15 status codes"),
    Field(20, 1, "goals", U8, note="goals conceded on a goalkeeper's line"),
    Field(21, 1, "assists", U8),
    Field(22, 1, "player_of_match", U8, note="1: the form chart's star"),
    Field(23, 1, "yellow_cards", U8),
    Field(24, 1, UNKNOWN, U8, note="0 on every line measured"),
    Field(25, 1, "substitution", U8, note="9 came on, 10 went off; 4 and 16 seen once each"),
))

_CACHE: Dict[Any, Optional[Tuple[int, int]]] = {}


def locate_player_form(mm: Any) -> Optional[Tuple[int, int]]:
    """(line 0, count) on FMM27, or None: the u16-counted list behind the three pools after
    the club titles, accepted only if it lands on `00` and a tid-ascending run of 72-byte
    rows."""
    key = _cache_key(mm)
    if key in _CACHE:
        return _CACHE[key]
    res = None
    if save_format(mm) == FMM27:
        from .club_titles import club_titles_table_spans
        from .person_info import locate_person_info
        spans = club_titles_table_spans(mm)
        p = spans[0][1] if spans else None
        for width, slots in POOLS:
            if p is None or mm[p] > slots:
                p = None
                break
            p += 1 + width * slots
        if p is not None:
            n = struct.unpack_from("<H", mm, p)[0]
            base, end = p + 2, p + 2 + n * FORM_LINE.span
            ok = end + 5 <= len(mm) and mm[end] == 0
            if ok:
                rows = struct.unpack_from("<I", mm, end + 1)[0]
                r0 = end + 5
                ok = 0 < rows and r0 + rows * ROW <= len(mm)
                last = -1
                for k in range(rows if ok else 0):
                    tid = struct.unpack_from("<I", mm, r0 + k * ROW)[0]
                    if tid <= last:
                        ok = False
                        break
                    last = tid
            if ok and n:
                persons = (locate_person_info(mm) or (0, 0))[1]
                ok = all(struct.unpack_from("<I", mm, base + k * FORM_LINE.span)[0] < persons
                         for k in range(n))
            if ok:
                res = (base, n)
    _CACHE[key] = res
    return res


def player_form_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """The lines, their u16 count included."""
    loc = locate_player_form(mm)
    return [(loc[0] - 2, loc[0] + loc[1] * FORM_LINE.span)] if loc else []


def _post(rec: Dict[str, Any], off: int) -> Dict[str, Any]:
    out = dict(rec)
    raw = rec["match_id"]
    out["match_id"] = int.from_bytes(bytes.fromhex(raw) if isinstance(raw, str) else raw,
                                     "little")
    return out


PLAYER_FORM_TABLE = TableDef(name="player_form", segments=(FORM_LINE,),
                             locator=locate_player_form, post_process=_post)


def scrape_player_form(mm: Any) -> List[Dict[str, Any]]:
    """Every line, in the order stored (match by match). Raises `ValueError` when not
    located; [] is a located, empty table (no competitive match played yet)."""
    if locate_player_form(mm) is None:
        raise ValueError("player_form: no u16-counted list behind the pools after the club "
                         "titles that lands on the per-player rows")
    return PLAYER_FORM_TABLE.scrape(mm)
