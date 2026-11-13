#!/usr/bin/env python3
"""`player_achievements` — the Player Achievements screen: one row per achievement, every
player's in one log. FMM27 and FMM22, the same layout.

The last table of the block after the club titles (`docs/parser/unread/end_block.md`),
right in front of the player lists:

    [u32 100,000][100,000 x 24 B][u8 0]   then the player lists

The 100,000 is a capacity. Rows fill from the front in the order the achievements happen,
and a freed slot is reused (93 empty slots among the used ones on frem-2023-07-02), so a row
number is not an id and the used rows need not be one run; an empty slot is
`00 ffffffff 00000000 ff x 14 00`. Each player's rows are chained by `next_row` (in-degree
at most 1, always to a row of the same player); what points at the first of them is not
read, and is not needed to read the whole table.

`kind` names the achievement, checked on the screen on truro-2026-11-16
(`docs/parser/unread/player_achievements.md`):

    2    a final won ("Community Shield Winner": Declan Rice, Arsenal)
    1    a final lost ("Community Shield Runner-Up": Enzo Fernandez, Man City)
    32   "Manager Sacked" (Jarrod Bowen, West Ham)
    128  an award (`award_id`): Player of the Month, Footballer of the Year

FMM22's careers, run longer, show the rest (frem-2030-06-30):

    4    a league won ("3F Superliga Winner")
    8    promoted ("Promoted from NordicBet Liga")
    16   relegated ("Relegated from 3F Superliga")
    64   "Club Bankrupt"
    512  "Global Team of the Year" (no competition, no award id)

The screen's category (World, Continental, Domestic, Major, Minor, Adverse) and the season's
format ("2029/30" for a club, "2030" for a national team) are not stored; nor is a date.

**How it is found.** Between the club titles and the player lists, the one u32 100,000 whose
100,000 slots read as a log: every used slot's tid a person, its year byte 1970 + 50 to
1970 + 99, and every `next_row` a used row of the same player, none reached twice. What
follows the slots varies: one `00` on most saves, 53 bytes naming Frem's stadium on
frem-2030-06-30.
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..core import Field, Record, TableDef, U8, U16, U32, UNKNOWN
from ..save import cache_key as _cache_key
from .save_header import FMM22, FMM27, save_format

__all__ = ["ACHIEVEMENT", "KINDS", "PLAYER_ACHIEVEMENTS_TABLE", "locate_player_achievements",
           "player_achievements_table_spans", "scrape_player_achievements"]

CAPACITY = 100_000
EMPTY = bytes([0]) + b"\xff" * 4 + b"\x00" * 4 + b"\xff" * 14 + b"\x00"
NONE16, NONE32 = 0xFFFF, 0xFFFFFFFF
HEADER = struct.pack("<I", CAPACITY)
KINDS = {1: "runner_up", 2: "winner", 4: "league_won", 8: "promoted", 16: "relegated",
         32: "manager_sacked", 64: "club_bankrupt", 128: "award",
         512: "global_team_of_the_year"}

ACHIEVEMENT = Record("player_achievement", 24, (
    Field(0,  1, "year", U8, note="years since 1970: 56 is 2026"),
    Field(1,  4, "tid", U32, note="the player"),
    Field(5,  4, "kind", U32, note="1 runner-up, 2 winner, 32 manager sacked, 128 award"),
    Field(9,  2, "cid", U16, note="the competition; ffff for an award with none"),
    Field(11, 2, UNKNOWN, U16, note="ffff on every row"),
    Field(13, 2, "club_tid", U16, note="his club at the time"),
    Field(15, 4, "award_id", U32, note="on an award; ffffffff otherwise"),
    Field(19, 4, "next_row", U32, note="his next achievement's row; ffffffff on his last"),
    Field(23, 1, UNKNOWN, U8, note="0 on every row"),
))
W = ACHIEVEMENT.span

_CACHE: Dict[Any, Optional[Tuple[int, List[int]]]] = {}


def _check(mm: Any, base: int) -> Optional[List[int]]:
    """The used rows if the slots at `base` hold a valid log, else None."""
    from .person_info import locate_person_info
    persons = (locate_person_info(mm) or (0, 0))[1]
    last = base + (CAPACITY - 1) * W
    if mm[last:last + W] != EMPTY and not 50 <= mm[last] < 100:
        return None
    used, tids = [], {}
    for k in range(CAPACITY):
        o = base + k * W
        if mm[o:o + W] == EMPTY:
            continue
        tid = struct.unpack_from("<I", mm, o + 1)[0]
        if tid >= persons or not 50 <= mm[o] < 100:
            return None
        used.append(k)
        tids[k] = tid
    seen = set()
    for k in used:
        nxt = struct.unpack_from("<I", mm, base + k * W + 19)[0]
        if nxt == NONE32:
            continue
        if nxt in seen or tids.get(nxt) != tids[k]:
            return None
        seen.add(nxt)
    return used


def locate_player_achievements(mm: Any) -> Optional[Tuple[int, int]]:
    """[(row, 1)] for every used slot, or None: the 100,000 slots ending one byte before the
    first player list. [] is a located, empty log."""
    key = _cache_key(mm)
    if key not in _CACHE:
        _CACHE[key] = _locate(mm)
    res = _CACHE[key]
    return [(res[0] + k * W, 1) for k in res[1]] if res else None


def _locate(mm: Any) -> Optional[Tuple[int, List[int]]]:
    """(slot 0, the used slots' indices), or None: the one u32 100,000 between the club
    titles and the player lists whose 100,000 slots read as a log and end before the
    lists."""
    if save_format(mm) not in (FMM22, FMM27):
        return None
    from .club_titles import club_titles_table_spans
    from .player_lists import locate_player_lists
    titles, lists = club_titles_table_spans(mm), locate_player_lists(mm)
    if not titles or not lists:
        return None
    lo, hi = titles[0][1], lists[0][0]
    found = []
    i = mm.find(HEADER, lo, hi)
    while i >= 0:
        base = i + 4
        if base + CAPACITY * W <= hi:
            used = _check(mm, base)
            if used is not None:
                found.append((base, used))
        i = mm.find(HEADER, i + 1, hi)
    return found[0] if len(found) == 1 else None


def player_achievements_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """The whole pool, its u32 capacity and every slot, used or not."""
    if locate_player_achievements(mm) is None:
        return []
    base = _CACHE[_cache_key(mm)][0]
    return [(base - 4, base + CAPACITY * W)]


def _post(rec: Dict[str, Any], off: int) -> Dict[str, Any]:
    out = {"row": None, **rec}
    out["year"] = 1970 + rec["year"]
    out["kind_name"] = KINDS.get(rec["kind"])
    for f, none in (("cid", NONE16), ("award_id", NONE32), ("next_row", NONE32)):
        if out.get(f) == none:
            out[f] = None
    return out


PLAYER_ACHIEVEMENTS_TABLE = TableDef(name="player_achievements", segments=(ACHIEVEMENT,),
                                     locator=locate_player_achievements, post_process=_post)


def scrape_player_achievements(mm: Any) -> List[Dict[str, Any]]:
    """Every used slot, in slot order, each with its `row` (the index `next_row` points at).
    Raises `ValueError` when not located; [] is a located, empty log."""
    runs = locate_player_achievements(mm)
    if runs is None:
        raise ValueError("player_achievements: no 100,000-slot log one byte before the "
                         "player lists")
    base, used = _CACHE[_cache_key(mm)]
    rows = PLAYER_ACHIEVEMENTS_TABLE.scrape(mm)
    if len(rows) != len(used):
        raise ValueError(f"player_achievements: read {len(rows)} of {len(used)} rows")
    for r, k in zip(rows, used):
        r["row"] = k
    return rows
