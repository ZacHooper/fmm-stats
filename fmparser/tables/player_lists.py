#!/usr/bin/env python3
"""`player_lists` -- 66 preallocated lists of 100 player entries: the pools behind the
game's World Best XI and Manager's Best Eleven screens, season by season and all-time.

Each entry is a snapshot of the player as he was in the season that earned it -- name, club,
the 23 attributes, positions, value and that season's numbers -- because the screens show
him as he was then, after he has moved on, declined or retired.

    region  66 x list
    list    [100 x entry][trailer, 14 bytes]
    entry   [8 x PString][tail, 168 bytes]

An entry's strings are the player's full name, first name, last name, "", last name, the
club's short name, "", and the competition name. An unused entry has eight empty strings
and a fixed template tail with `player_tid` 0xffffffff, so it is exactly 200 bytes; a list
of them is 20,014.

The 66 lists are three groups, by index:

     0-30   the World Best XI pool, one per season of the career: 100 players, from whom
            the game's World Best XI screen for that year picks its eleven by position
            (all eleven, for 2024, 2025 and 2026, verified against the screen on
            frem-2027-06-15). The list of the season in progress fills as it is played.
    31-61   the Manager's Best Eleven pool, one per season: every player who played for
            the MANAGER that season (first team and reserves under their own club
            markers, loanees under their parent club), filled from 31. It follows the
            manager, not the club, and keeps players who have since left (2022 and 2026
            elevens verified against the screen on frem-2027-06-15)
    62-65   62 and 64: the All-Time pool behind World Best XI - All-Time (all eleven
            verified), each entry frozen in the season that earned its place ("Torino -
            2023"). 63 and 65: the pool behind All-Time Manager's Best Eleven (all eleven
            verified, "Frem - 2025", "FC Kobenhavn (loan) 2021"). In each pair one copy
            carries this season's entries (the screen's "New Entry") and the other the
            pool as of the end of last season

A list's trailer is written when its season ends: `season` is that season's end year, and
reads 0xffff while the season is in progress. Our club's current squad is the last filled
list of 31-61, the one with the 0xffff trailer. Every save of both careers, day one
included, holds exactly 66 lists.

TAIL, 168 bytes, from the end of the strings. An entry is what the game's Scrapbook Profile
shows (verified field by field on Ernest Nuamah's and Mikkel Andersson's 2022 entries), as of the
entry's date:

    +0   colour_1, colour_2 u16   the club's colours, RGB555
    +4   4 bytes, +12 8 bytes     three dates that read 1 Jan 2021 (the career's "no date";
                                  one is the loan end the profile shows)
    +8   entry_day, entry_year    the entry's last write: the 1st of each month while its
                                  season runs, then frozen
    +20  age u8, then 7 bytes unread
    +28  36 bytes: the 23 attributes at the indices of `ATTRIBUTES`, condition (24),
         morale (25), the last five match ratings (26-30, the most recent last), avg_rating f32 (31); 9 and 35
         unread
    +64  15 x u8                  position ratings, in `player_attributes.POSITIONS` order
    +79  player_tid u32, +83 u32 unread
    +87  club_tid u16             the club holding the player's registration
    +89  loan_club_tid u16        the club he is on loan to; 0xffff = not on loan
    +91  value u32                transfer value
    +99  wage u32                 weekly wage (x52 is the profile's yearly figure, ~1%)
    +108 caps, intl_goals, u21_caps, u21_goals u8
    +112 apps, goals, conceded (goalkeepers), assists, yellows u8 -- the season to the
         entry's date, competitive first-team matches (257/257 against our match data)
    +120 foot_left u8, +121 foot_right u8
    unread: +95 4 bytes, +103 5 bytes, +117 3 bytes, +122 46 bytes

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

from ..core import F32, Field, PString, RAW, Record, TableDef, U8, U16, U32, UNKNOWN
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


# The attribute block's other bytes, by index (the Scrapbook Profile screen, verified on
# Ernest Nuamah's 2022 entry: condition 87%, morale Superb, form 7-9-8-9-7, av. rating 7.50).
_BLOCK = {24: ("condition", U8, "percent"), 25: ("morale", U8, "1-20; 20 = Superb, 17 = Very Good"),
          26: ("form_1", U8, "the last five match ratings in screen order; form_5 is the "
                                 "most recent (Mikkel Andersson 8-7-8-8-6)"),
          27: ("form_2", U8, ""), 28: ("form_3", U8, ""), 29: ("form_4", U8, ""),
          30: ("form_5", U8, "")}


def _tail_fields() -> List[Field]:
    fields = [
        Field(0, 2, "colour_1", U16, note="the club's colours, RGB555"),
        Field(2, 2, "colour_2", U16),
        Field(4, 4, UNKNOWN, RAW),
        Field(8, 2, "entry_day", U16, note="the entry's last write, day-of-year 0-based"),
        Field(10, 2, "entry_year", U16),
        Field(12, 8, UNKNOWN, RAW),
        Field(20, 1, "age", U8, note="at the entry's date"),
        Field(21, 7, UNKNOWN, RAW),
    ]
    i = 0
    while i < 36:
        if i == 31:
            fields.append(Field(_ATTR_AT + 31, 4, "avg_rating", F32,
                                note="average match rating, all competitions"))
            i += 4
            continue
        name = ATTRIBUTES.get(i)
        if name:
            fields.append(Field(_ATTR_AT + i, 1, f"attr_{name.lower()}", U8))
        elif i in _BLOCK:
            n, kind, note = _BLOCK[i]
            fields.append(Field(_ATTR_AT + i, 1, n, kind, note=note))
        else:
            fields.append(Field(_ATTR_AT + i, 1, UNKNOWN, RAW))
        i += 1
    fields += [Field(64 + k, 1, f"pos_{p.lower()}", U8) for k, p in enumerate(POSITIONS)]
    fields += [
        Field(79, 4, "player_tid", U32),
        Field(83, 4, UNKNOWN, RAW),
        Field(87, 2, "club_tid", U16, note="the club holding the registration"),
        Field(89, 2, "loan_club_tid", U16, note="the club he is on loan to; 0xffff = none"),
        Field(91, 4, "value", U32, note="transfer value"),
        Field(95, 4, UNKNOWN, RAW),
        Field(99, 4, "wage", U32, note="weekly wage; x52 = the screen's yearly figure"),
        Field(103, 5, UNKNOWN, RAW),
        Field(108, 1, "caps", U8, note="international caps, at the entry's date"),
        Field(109, 1, "intl_goals", U8),
        Field(110, 1, "u21_caps", U8),
        Field(111, 1, "u21_goals", U8),
        Field(112, 1, "apps", U8, note="the season to the entry's date: competitive, "
                                       "first team"),
        Field(113, 1, "goals", U8),
        Field(114, 1, "conceded", U8, note="goalkeepers only"),
        Field(115, 1, "assists", U8),
        Field(116, 1, "yellows", U8),
        Field(117, 3, UNKNOWN, RAW),
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
