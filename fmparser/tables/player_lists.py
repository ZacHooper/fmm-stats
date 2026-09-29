#!/usr/bin/env python3
"""`player_lists` -- 66 preallocated lists of 100 player entries: each season's world list
and our club's squad, season by season.

    region  66 x list
    list    [100 x entry][trailer, 14 bytes]
    entry   [8 x PString][tail, 168 bytes]

An entry's strings are the player's full name, first name, last name, "", last name, the
club's short name, "", and the competition name. An unused entry has eight empty strings
and a fixed template tail with `player_tid` 0xffffffff, so it is exactly 200 bytes; a list
of them is 20,014.

The 66 lists are three groups, by index:

     0-30   world lists, one per season of the career, 100 players each
    31-61   our club's squad, one list per season (first team and reserves, under their
            own club markers, and players loaned in); filled from 31
    62-65   two copies of a (world, club) pair, not yet identified

A list's trailer is written when its season ends: `season` is that season's end year, and
reads 0xffff while the season is in progress. Our club's current squad is the last filled
list of 31-61, the one with the 0xffff trailer. Every save of both careers, day one
included, holds exactly 66 lists.

TAIL, 168 bytes, from the end of the strings:

    +0   28 bytes      unread: two u16, four [day-of-year u16][year u16] dates, 8 bytes
    +28  36 bytes      attributes: the 23 displayed attributes at the indices of `ATTRIBUTES`,
                       13 bytes unread among them
    +64  15 x u8       position ratings, in `player_attributes.POSITIONS` order
    +79  player_tid u32
    +83  u32           unread
    +87  club_tid u16  the club holding the player's registration
    +89  loan_club_tid u16  the club he is on loan to; 0xffff = not on loan
    +91  value u32     transfer value
    +95  25 bytes      unread
    +120 foot_left u8, +121 foot_right u8
    +122 46 bytes      unread

`club_tid`/`loan_club_tid` read together are the four-byte "club marker" a player's own
record carries: `[club][ffff]` for a player owned by the club, `[parent][club]` for one on
loan there.

Located from an empty list -- 100 template entries, whose tails carry `14 01 00 0a 00` at
exactly 200-byte gaps -- then walked: forward list by list to the last list that parses,
and backward by reading each entry's strings from their end (every string is length-
prefixed, so the start of the strings that end at a given byte is exact).
"""
import re
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..core import Field, PString, RAW, Record, TableDef, U8, U16, U32, UNKNOWN
from ..save import cache_key as _cache_key
from .player_attributes import POSITIONS

__all__ = [
    "ATTRIBUTES",
    "CLUB_LISTS",
    "ENTRY_TAIL",
    "LISTS",
    "PLAYER_LISTS_TABLE",
    "PLAYER_LIST_TRAILERS_TABLE",
    "TRAILER",
    "locate_player_lists",
    "player_lists_table_spans",
    "scrape_player_lists",
]

LISTS = 66                                   # lists in the region, on every save
PER_LIST = 100                               # entries per list
CLUB_LISTS = range(31, 62)                   # our club's squad, one list per season
NO_CLUB = 0xFFFF
NO_PLAYER = 0xFFFFFFFF                     # an unused entry
STRINGS = ("full_name", "first_name", "last_name", "string_3", "last_name_2", "club",
           "string_6", "competition")
EMPTY_TAIL_MARK = b"\x14\x01\x00\x0a\x00"    # at tail +121 of an unused entry
_MARK_AT = 32 + 121                          # from an unused entry's start: 8 empty strings + 121
_EMPTY_ENTRY = 200
_MAX_STRING = 100

# The attributes at their index in the 36-byte block at tail +28.
ATTRIBUTES = {
    0: "Aerial", 1: "Agility", 2: "Communication", 3: "Handling",
    4: "Kicking", 5: "Throwing", 6: "Reflexes", 7: "Crossing",
    8: "Dribbling", 10: "Passing", 11: "Shooting", 12: "Tackling",
    13: "Technique", 14: "Aggression", 15: "Creativity", 16: "Decisions",
    17: "Leadership", 18: "Movement", 19: "Positioning", 20: "Teamwork",
    21: "Pace", 22: "Stamina", 23: "Strength",
}
_ATTR_AT = 28


def _tail_fields() -> List[Field]:
    fields = [Field(0, _ATTR_AT, UNKNOWN, RAW)]
    for i in range(36):
        name = ATTRIBUTES.get(i)
        fields.append(Field(_ATTR_AT + i, 1, f"attr_{name.lower()}" if name else UNKNOWN,
                            U8 if name else RAW))
    fields += [Field(64 + k, 1, f"pos_{p.lower()}", U8) for k, p in enumerate(POSITIONS)]
    fields += [
        Field(79, 4, "player_tid", U32),
        Field(83, 4, UNKNOWN, RAW),
        Field(87, 2, "club_tid", U16, note="the club holding the registration"),
        Field(89, 2, "loan_club_tid", U16, note="the club he is on loan to; 0xffff = none"),
        Field(91, 4, "value", U32, note="transfer value"),
        Field(95, 25, UNKNOWN, RAW),
        Field(120, 1, "foot_left", U8),
        Field(121, 1, "foot_right", U8),
        Field(122, 46, UNKNOWN, RAW),
    ]
    return fields


ENTRY_TAIL = Record("player_list_entry", 168, _tail_fields())

TRAILER = Record("player_list_trailer", 14, [
    Field(0, 1, UNKNOWN, RAW),
    Field(1, 2, "season", U16, note="end year of the list's season; 0xffff = in progress"),
    Field(3, 11, UNKNOWN, RAW),
])

_CACHE: Dict[Any, Optional[List[Tuple[int, int]]]] = {}


def _entry_end(mm: Any, o: int) -> Optional[int]:
    for _ in range(len(STRINGS)):
        if o + 4 > len(mm):
            return None
        n = struct.unpack_from("<I", mm, o)[0]
        if n > _MAX_STRING:
            return None
        o += 4 + n
    o += ENTRY_TAIL.span
    return o if o <= len(mm) else None


def _list_end(mm: Any, start: int) -> Optional[int]:
    o = start
    for _ in range(PER_LIST):
        o = _entry_end(mm, o)
        if o is None:
            return None
    o += TRAILER.span
    return o if o <= len(mm) else None


def _string_starts(mm: Any, end: int, k: int) -> List[int]:
    """Every offset from which k length-prefixed strings end exactly at `end`."""
    if k == 0:
        return [end]
    out = []
    for n in range(_MAX_STRING + 1):
        p = end - n - 4
        if p < 0:
            break
        if struct.unpack_from("<I", mm, p)[0] == n:
            out.extend(_string_starts(mm, p, k - 1))
    return out


def _list_before(mm: Any, start: int) -> Optional[int]:
    """The start of the list whose trailer ends at `start`, or None when no list does."""
    ends = [start - TRAILER.span]
    for _ in range(PER_LIST):
        nxt = set()
        for e in ends:
            nxt.update(_string_starts(mm, e - ENTRY_TAIL.span, len(STRINGS)))
        ends = list(nxt)
        if not ends:
            return None
    fits = [p for p in ends if _list_end(mm, p) == start]
    return fits[0] if len(fits) == 1 else None


def _empty_list(mm: Any) -> Optional[int]:
    """The start of the first list whose 100 entries are all unused."""
    gap = _EMPTY_ENTRY
    for m in re.finditer(re.escape(EMPTY_TAIL_MARK), mm):
        h = m.start()
        if mm[h - gap:h - gap + 5] == EMPTY_TAIL_MARK:
            continue                                 # not the first entry of its run
        if all(mm[h + gap * k:h + gap * k + 5] == EMPTY_TAIL_MARK for k in range(PER_LIST)):
            return h - _MARK_AT
    return None


def locate_player_lists(mm: Any) -> Optional[List[Tuple[int, int]]]:
    """[(start, 100)] for every list, in order, or None."""
    key = _cache_key(mm)
    if key in _CACHE:
        return _CACHE[key]
    res = None
    anchor = _empty_list(mm)
    if anchor is not None:
        first = anchor
        while (prev := _list_before(mm, first)) is not None:
            first = prev
        starts, o = [], first
        while (end := _list_end(mm, o)) is not None:
            starts.append(o)
            o = end
        res = [(s, PER_LIST) for s in starts]
    _CACHE[key] = res
    return res


def _locate_trailers(mm: Any) -> Optional[List[Tuple[int, int]]]:
    runs = locate_player_lists(mm)
    if not runs:
        return None
    return [(_list_end(mm, s) - TRAILER.span, 1) for s, _ in runs]


PLAYER_LISTS_TABLE = TableDef(
    name="player_lists",
    segments=tuple(PString(s, allow_empty=True, max_len=_MAX_STRING) for s in STRINGS)
    + (ENTRY_TAIL,),
    locator=locate_player_lists,
    include_offset=True,
)

PLAYER_LIST_TRAILERS_TABLE = TableDef(
    name="player_list_trailers",
    segments=(TRAILER,),
    locator=_locate_trailers,
    include_offset=True,
)


def player_lists_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """One span per list, its trailer included."""
    return [(s, _list_end(mm, s)) for s, _ in (locate_player_lists(mm) or [])]


def scrape_player_lists(mm: Any) -> List[Dict[str, Any]]:
    """[{index, offset, season, entries}] for the 66 lists; `entries` holds the used ones,
    each with its `slot` in the list. Raises `ValueError` if the region does not read as 66
    lists of 100 entries."""
    runs = locate_player_lists(mm)
    if not runs or len(runs) != LISTS:
        raise ValueError(f"player_lists: {len(runs or [])} lists located, not {LISTS}")
    rows = PLAYER_LISTS_TABLE.scrape(mm)
    trailers = PLAYER_LIST_TRAILERS_TABLE.scrape(mm)
    if len(rows) != LISTS * PER_LIST or len(trailers) != LISTS:
        raise ValueError(f"player_lists: read {len(rows)} entries and {len(trailers)} "
                         f"trailers, not {LISTS * PER_LIST} and {LISTS}")
    out = []
    for i, ((start, _), tr) in enumerate(zip(runs, trailers)):
        entries = []
        for slot, r in enumerate(rows[i * PER_LIST:(i + 1) * PER_LIST]):
            if r["player_tid"] != NO_PLAYER:
                entries.append(dict(r, slot=slot))
        out.append({"index": i, "offset": start, "season": tr["season"], "entries": entries})
    return out
