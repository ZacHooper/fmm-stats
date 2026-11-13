#!/usr/bin/env python3
"""`team_selections` — every team's matchday squad, in its formation's slot order.

Straight after the [formations](formations.py), both games:

    [u16 count][count x slot]      slot k belongs to team tid k

    FMM27  105 B = [u8][26 x u32 tid]      17,804 slots on every Truro save
    FMM22  589 B = [u8][147 x u32 tid]     14,506 on every Frem save, 15,288 on Bucaspor

`ffffffff` is an empty place. A team that has not picked a side has every place empty: 581
of 17,804 slots are filled on truro-2026-07-22, 1,362 on 16 Nov; 567 and 1,375 on
frem-2021-06-27 and frem-2026-06-11. 1,321 of 1,362 filled slots on 16 Nov hold only players
in team k's squad array (`clubs`), the rest one who has since left.

**FMM27's 26 places**, checked against Truro's Tactics – Captain screen on truro-2026-11-16:

     0-10   the starting XI, in the tactic's slot order (slot 0 the keeper; the slots'
            positions are the formation's codes, `formations`)
    11-19   the substitutes, S1 first: up to nine (Maidenhead's seven are places 11-17;
            Truro names five; 438 of 690 full team sheets on 16 Nov use all nine)
    20-25   the captains: the captain on the pitch, then the screen's five in order

**FMM22's 147**: filled slots hold 14, 18 or 20 tids at the front, a few a single tid
further in; not checked against a screen.

The u8 in front is 14 on Truro's slot; across slots 0, 2, 6, 8, 15, 16, 17. Not named.

**How it is found.** The u16 straight after the last formation is the count; the walk
refuses the table unless every place in every slot is empty or a u16-sized tid (other tables
store a person's tid in a u16; bucaspor-2023-04-01 holds 13 tids above the person index's
34,312, people created since the database), and the slots end before the contract grid.
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..core import Field, FixedList, Record, TableDef, U8, U16, U32, UNKNOWN
from ..save import cache_key as _cache_key
from .save_header import FMM27, save_format

__all__ = ["TEAM_SELECTIONS_HEADER", "TEAM_SELECTIONS_TABLE", "TEAM_SELECTIONS_TABLE_FMM27",
           "locate_team_selections", "places", "scrape_team_selections",
           "team_selections_table_spans"]

EMPTY = 0xFFFFFFFF
PLACES = {FMM27: 26}
PLACES_FMM22 = 147

TEAM_SELECTIONS_HEADER = Record("team_selections_header", 2, (
    Field(0, 2, "count", U16, note="the slot count: 17,804 Truro, 14,506 Frem"),
))

SELECTION_HEAD = Record("team_selection", 1, (
    Field(0, 1, UNKNOWN, U8, note="14 on Truro's slot; 0, 2, 6, 8, 15-17 elsewhere"),
), is_head=True)

SELECTION_PLACE = Record("team_selection_place", 4, (
    Field(0, 4, "tid", U32, note="a person; ffffffff empty"),
))


def places(mm: Any) -> int:
    return PLACES.get(save_format(mm), PLACES_FMM22)


_CACHE: Dict[Any, Optional[Tuple[int, int]]] = {}


_MAX_TID = 0xFFFF


def locate_team_selections(mm: Any) -> Optional[Tuple[int, int]]:
    """(slot 0, count), or None: the u16 after the formations, accepted only if every place
    of every slot is empty or a u16-sized tid and the slots end before the contract grid."""
    key = _cache_key(mm)
    if key in _CACHE:
        return _CACHE[key]
    from . import table_spans
    from .formations import locate_formations, STRIDE
    res = None
    fm = locate_formations(mm)
    grid = table_spans(mm, "contracts")
    if fm and grid:
        at = fm[0] + fm[1] * STRIDE
        n, width = struct.unpack_from("<H", mm, at)[0], places(mm)
        base, stride = at + 2, 1 + 4 * width
        if n and base + n * stride <= grid[0][0]:
            ok = all(t == EMPTY or t <= _MAX_TID
                     for k in range(n)
                     for t in struct.unpack_from(f"<{width}I", mm, base + k * stride + 1))
            if ok:
                res = (base, n)
    _CACHE[key] = res
    return res


def team_selections_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """The slots, their u16 count included."""
    loc = locate_team_selections(mm)
    return [(loc[0] - 2, loc[0] + loc[1] * (1 + 4 * places(mm)))] if loc else []


TEAM_SELECTIONS_TABLE = TableDef(
    name="team_selections",
    segments=(SELECTION_HEAD, FixedList("places", SELECTION_PLACE, PLACES_FMM22)),
    locator=locate_team_selections, header=TEAM_SELECTIONS_HEADER)

TEAM_SELECTIONS_TABLE_FMM27 = TableDef(
    name="team_selections",
    segments=(SELECTION_HEAD, FixedList("places", SELECTION_PLACE, PLACES[FMM27])),
    locator=locate_team_selections, header=TEAM_SELECTIONS_HEADER)


def scrape_team_selections(mm: Any) -> List[Dict[str, Any]]:
    """Every team with at least one place filled, in slot (= team tid) order: `team_tid`,
    the u8 in front (`unknown_0`) and `places`, every place in stored order with None for
    an empty one. FMM27's `places` is always 26 long; FMM22's ends at its last filled place.
    Raises `ValueError` when not located."""
    loc = locate_team_selections(mm)
    if loc is None:
        raise ValueError("team_selections: no slot pool after the formations")
    base, n = loc
    width = places(mm)
    stride = 1 + 4 * width
    fmm27 = save_format(mm) == FMM27
    out = []
    for k in range(n):
        o = base + k * stride
        tids = struct.unpack_from(f"<{width}I", mm, o + 1)
        if all(t == EMPTY for t in tids):
            continue
        row = [None if t == EMPTY else t for t in tids]
        if not fmm27:
            row = row[:max(i for i, t in enumerate(row) if t is not None) + 1]
        out.append({"team_tid": k, "unknown_0": mm[o], "places": row})
    return out
