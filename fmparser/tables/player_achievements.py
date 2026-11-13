#!/usr/bin/env python3
"""`player_achievements` — the Player Achievements screen: one row per achievement, every
player's in one log. FMM27 only so far.

The last table of the block after the club titles (`docs/parser/unread/end_block.md`),
right in front of the player lists:

    [u32 100,000][100,000 x 24 B][u8 0]   then the player lists

The 100,000 is a capacity. Rows fill from the front in the order the achievements happen,
so a row number is not an id; an empty slot is `00 ffffffff 00000000 ff x 14 00`. Each
player's rows are chained oldest first by `next_row`; what points at the first of them is
not read, and is not needed to read the whole table.

`kind` names the achievement, checked on the screen on truro-2026-11-16
(`docs/parser/unread/player_achievements.md`):

    2    a final won ("Community Shield Winner": Declan Rice, Arsenal)
    1    a final lost ("Community Shield Runner-Up": Enzo Fernandez, Man City)
    32   "Manager Sacked" (Jarrod Bowen, West Ham)
    128  an award (`award_id`): Player of the Month, Footballer of the Year

The screen's category (World, Continental, Domestic, Major, Minor, Adverse) and season are
not stored; nor is a date.

**How it is found.** One byte before the first player list, the 100,000 slots end; the u32
in front of them must be 100,000, the used rows must be one run from the front with every
slot after it empty, every tid a person, and every `next_row` a later row of the same
player.
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..core import Field, Record, TableDef, U8, U16, U32, UNKNOWN
from ..save import cache_key as _cache_key
from .save_header import FMM27, save_format

__all__ = ["ACHIEVEMENT", "KINDS", "PLAYER_ACHIEVEMENTS_TABLE", "locate_player_achievements",
           "player_achievements_table_spans", "scrape_player_achievements"]

CAPACITY = 100_000
EMPTY = bytes([0]) + b"\xff" * 4 + b"\x00" * 4 + b"\xff" * 14 + b"\x00"
NONE16, NONE32 = 0xFFFF, 0xFFFFFFFF
KINDS = {1: "runner_up", 2: "winner", 32: "manager_sacked", 128: "award"}

ACHIEVEMENT = Record("player_achievement", 24, (
    Field(0,  1, UNKNOWN, U8, note="0x38 on every row"),
    Field(1,  2, "tid", U16, note="the player"),
    Field(3,  2, UNKNOWN, U16, note="0 on every row"),
    Field(5,  4, "kind", U32, note="1 runner-up, 2 winner, 32 manager sacked, 128 award"),
    Field(9,  2, "cid", U16, note="the competition; ffff for an award with none"),
    Field(11, 2, UNKNOWN, U16, note="ffff on every row"),
    Field(13, 2, "club_tid", U16, note="his club at the time"),
    Field(15, 4, "award_id", U32, note="on an award; ffffffff otherwise"),
    Field(19, 4, "next_row", U32, note="his next achievement's row; ffffffff on his last"),
    Field(23, 1, UNKNOWN, U8, note="0 on every row"),
))
W = ACHIEVEMENT.span

_CACHE: Dict[Any, Optional[Tuple[int, int]]] = {}


def _check(mm: Any, base: int) -> Optional[int]:
    """The used-row count if the slots at `base` hold a valid log, else None."""
    used = 0
    while used < CAPACITY and mm[base + used * W] == 0x38:
        used += 1
    rest = base + used * W
    if mm[rest:base + CAPACITY * W] != EMPTY * (CAPACITY - used):
        return None
    from .person_info import locate_person_info
    persons = (locate_person_info(mm) or (0, 0))[1]
    tids = [struct.unpack_from("<H", mm, base + k * W + 1)[0] for k in range(used)]
    if any(t >= persons for t in tids):
        return None
    for k in range(used):
        nxt = struct.unpack_from("<I", mm, base + k * W + 19)[0]
        if nxt != NONE32 and not (k < nxt < used and tids[nxt] == tids[k]):
            return None
    return used


def locate_player_achievements(mm: Any) -> Optional[Tuple[int, int]]:
    """(row 0, used rows) on FMM27, or None: the 100,000 slots ending one byte before the
    first player list."""
    key = _cache_key(mm)
    if key in _CACHE:
        return _CACHE[key]
    res = None
    if save_format(mm) == FMM27:
        from .player_lists import locate_player_lists
        lists = locate_player_lists(mm)
        if lists:
            end = lists[0][0] - 1
            base = end - CAPACITY * W
            if (base >= 4 and mm[end] == 0
                    and struct.unpack_from("<I", mm, base - 4)[0] == CAPACITY):
                used = _check(mm, base)
                if used is not None:
                    res = (base, used)
    _CACHE[key] = res
    return res


def player_achievements_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """The whole pool, its u32 capacity and every slot, used or not."""
    loc = locate_player_achievements(mm)
    return [(loc[0] - 4, loc[0] + CAPACITY * W)] if loc else []


def _post(rec: Dict[str, Any], off: int) -> Dict[str, Any]:
    out = {k: v for k, v in rec.items()}
    out["kind_name"] = KINDS.get(rec["kind"])
    for f, none in (("cid", NONE16), ("award_id", NONE32), ("next_row", NONE32)):
        if out.get(f) == none:
            out[f] = None
    return out


PLAYER_ACHIEVEMENTS_TABLE = TableDef(name="player_achievements", segments=(ACHIEVEMENT,),
                                     locator=locate_player_achievements, post_process=_post)


def scrape_player_achievements(mm: Any) -> List[Dict[str, Any]]:
    """Every used row, in the order stored (the order they happened), each with its `row`.
    Raises `ValueError` when not located; [] is a located, empty log."""
    loc = locate_player_achievements(mm)
    if loc is None:
        raise ValueError("player_achievements: no 100,000-slot log one byte before the "
                         "player lists")
    rows = PLAYER_ACHIEVEMENTS_TABLE.scrape(mm)
    if len(rows) != loc[1]:
        raise ValueError(f"player_achievements: read {len(rows)} of {loc[1]} rows")
    return [{"row": k, **r} for k, r in enumerate(rows)]
