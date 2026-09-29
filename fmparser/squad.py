#!/usr/bin/env python3
"""The managed club's squad: names, exact attributes, feet and transfer value.

Read from the manager's lists in the player-list table (`tables/player_lists.py`, lists
31-61: the Manager's Best Eleven pool of each season, every player who played for the
manager). Each entry is the player's Scrapbook Profile as of the entry's date -- the 23
displayed attributes exactly, his feet and value -- with a four-byte club marker:

    [club_tid u16][ffff]            owned by `club_tid`
    [parent_tid u16][club_tid u16]  on loan at `club_tid` from `parent_tid`

A player has one entry per season he played for the manager. The freshest entry for a
(player, marker) pair is the one with the latest entry date, and its date travels with it
(`as_of`): an entry is rewritten while the player plays, then frozen, and how far its
attributes can be trusted falls with its age (agreement with the attributes stored on the
player's own record: 84% at under a month, ~80% to seven months, ~60% at nine or more).
A player who has not played for the manager has no entry.
"""
import datetime
import struct
from typing import Any, Dict, List, Optional, Tuple

from .careers import resolve_career
from .save import cache_key as _cache_key
from .tables.player_lists import ATTRIBUTES, CLUB_LISTS, NO_CLUB, scrape_player_lists

# Default club marker (managed club TID u16 LE + 0xFFFF)
CLUB_MARKER = resolve_career().club_marker

_CACHE: Dict[Any, List[Dict[str, Any]]] = {}


def loan_marker(managed_tid: int, parent_tid: int) -> bytes:
    """The marker of a player loaned IN: `[parent_club_tid][managed_tid]`, both u16 LE."""
    return struct.pack("<HH", parent_tid, managed_tid)


def entry_marker(entry: Dict[str, Any]) -> bytes:
    """The four-byte club marker an entry carries."""
    return struct.pack("<HH", entry["club_tid"], entry["loan_club_tid"])


def club_entries(mm: Any) -> List[Dict[str, Any]]:
    """Every used entry of our club's squad lists, oldest list first."""
    key = _cache_key(mm)
    if key not in _CACHE:
        _CACHE[key] = [dict(e, list_index=lst["index"])
                       for lst in scrape_player_lists(mm) if lst["index"] in CLUB_LISTS
                       for e in lst["entries"]]
    return _CACHE[key]


def entry_date(entry: Dict[str, Any]) -> datetime.date:
    """The date the entry was last written."""
    return datetime.date(entry["entry_year"], 1, 1) + datetime.timedelta(entry["entry_day"])


def _fresher(new: Dict[str, Any], old: Optional[Dict[str, Any]]) -> bool:
    """`new` supersedes `old`: a later entry date, or the same date in a later list."""
    return old is None or (entry_date(new), new["list_index"]) >= (entry_date(old),
                                                                    old["list_index"])


def _record(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {"attrs": {name: entry[f"attr_{name.lower()}"] for name in ATTRIBUTES.values()},
            "feet": (entry["foot_left"], entry["foot_right"]),
            "value": entry["value"],
            "as_of": entry_date(entry).isoformat(),
            "offset": entry["offset"],
            "list_index": entry["list_index"]}


def own_squad_full(mm: Any, marker: bytes = CLUB_MARKER) -> Dict[int, Dict[str, Any]]:
    """{tid: {'name', 'loaned_in', 'parent_club_tid'}} for the players under `marker`'s club:
    owned by it, or on loan to it. The freshest entry wins."""
    club = int.from_bytes(marker[:2], "little")
    out: Dict[int, Dict[str, Any]] = {}
    src: Dict[int, Dict[str, Any]] = {}
    for e in club_entries(mm):
        t = e["player_tid"]
        if e["club_tid"] == club and e["loan_club_tid"] == NO_CLUB:
            row = {"name": e["full_name"], "loaned_in": False, "parent_club_tid": None}
        elif e["loan_club_tid"] == club:
            row = {"name": e["full_name"], "loaned_in": True, "parent_club_tid": e["club_tid"]}
        else:
            continue
        if _fresher(e, src.get(t)):
            out[t], src[t] = row, e
    return out


def attr_records(mm: Any, tid: int,
                 markers: Tuple[bytes, ...] = (CLUB_MARKER,)) -> Dict[bytes, Dict[str, Any]]:
    """{marker: freshest record} -- one entry per marker this tid appears under, in the
    order the markers first appear. A record is {'attrs': {attribute: value}, 'feet':
    (left, right), 'value', 'as_of' (the entry date, ISO), 'offset', 'list_index'}."""
    out: Dict[bytes, Dict[str, Any]] = {}
    src: Dict[bytes, Dict[str, Any]] = {}
    for e in club_entries(mm):
        if e["player_tid"] == tid:
            m = entry_marker(e)
            if m in markers and _fresher(e, src.get(m)):
                out[m], src[m] = _record(e), e
    return out


def attr_record(mm: Any, tid: int, marker: bytes = CLUB_MARKER) -> Optional[Dict[str, Any]]:
    """The freshest record of `tid` under `marker`, or None."""
    return attr_records(mm, tid, (marker,)).get(marker)
