#!/usr/bin/env python3
"""`matches` -- our clubs' matches this season, one row per match, each in full.

A count-framed array of variable-length rows (shape A). The table holds the season's matches
of the managed club and its reserve side, in the order they were played, and is emptied at
the July rollover:

    header  [count u8]                     matches in the table
    row     [head, 8 B]                    home, away, competition, day
            [n u8][n x event, 17 B]        the match's events, as the game lists them
            [body, 5,093 B]                everything else, fixed width

so a row is `5,102 + 17 n` bytes and the next row starts where this one ends. The body holds
the same match from OUR club's side and repeats the head -- `[club][opponent][competition]
[home flag][home][away][day]` -- which is the row's invariant: a row whose body does not
repeat its head is not a row, and the walk stops there.

BODY, 5,093 bytes:

      +0  BODY_HEAD, 78 B         our side, the match header, attendance, Player of the Match
     +78  50 x event, 17 B        the event list again, in 50 preallocated slots; the first n
                                  equal the counted list, the rest are unwritten or stale
    +928  2 x TEAM block          home then away, each [77 B team head]
                                  [20 x player slot, 62 B][46 B team tail]
   +3654  TAIL, 1,439 B           our side's kick-off formation string and its 11 slots

A player slot is preallocated: an unused one keeps its slot number (`posOrder`) and has tid
0xffffffff. Sixteen slots are always used, eighteen in most competitions, twenty in
friendlies. Each team head carries that side's eleven full-time positions in posOrder order;
the tail adds OUR side's kick-off formation. The body's `club_tid` is the managed club or its
reserve side, whichever played.

Found by any row -- a row's body carries the formation marker at a fixed offset, and the
row's own head/body repeat proves it -- then walked back to row 0, whose count byte must
declare exactly the rows the walk reads (`scrape_matches`). An empty table (after the July
rollover, or on a career's first day) has no row to seed from, so it is not located:
`scrape_matches` returns [] and the caller decides whether that is plausible for the date.
"""
import datetime
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..core import (CountedList, Field, FixedList, HEX2, PAD, RAW, Record, Struct, TableDef,
                    U8, U16, U32, UNKNOWN)
from ..core.primitives import pitch_position
from .save_header import FMM27, save_format
from ..save import cache_key as _cache_key

__all__ = [
    "BODY_HEAD",
    "EVENT",
    "EVENT_TYPE",
    "MATCH_HEAD",
    "MATCHES_TABLE",
    "MATCHES_TABLE_FMM27",
    "EVENT_TYPE_FMM27",
    "MatchTableError",
    "PLAYER_SLOT",
    "TEAM",
    "TEAM_HEAD",
    "TEAM_TAIL",
    "MATCH_TAIL",
    "check_against_fixtures",
    "locate_matches",
    "matches_table_spans",
    "scrape_matches",
]

EVENT_SLOTS = 50                  # preallocated event slots in the body
PLAYER_SLOTS = 20                 # preallocated player slots per side
NO_PLAYER = 0xFFFFFFFF
FORMATION_MARKER = bytes([0x76, 0xB9, 0xF4, 0x07])

# Event type byte -> name. 0x07/0x08 are a penalty shootout, decoded from the one fixture in
# the archive that went to one: Frem v Midtjylland, Sydbank Pokalen, 2022-10-25. The match
# record says 0-0 after extra time, all ten events are stamped at minute 120, and resolving
# each taker's club as at 2022 splits them home 4 scored / 1 missed against away 3 scored /
# 2 missed -- five kicks a side, Frem through 4-3. The arithmetic only closes if 0x07 is the
# conversion and 0x08 the miss. A single shootout cannot prove the byte means "shootout
# kick" rather than "goal after 90+30"; if one ever shows up outside minute 120, revisit.
EVENT_TYPE = {
    0x01: "goal", 0x02: "own_goal", 0x03: "penalty", 0x04: "missed_penalty",
    0x05: "red_card", 0x06: "injury",
    0x07: "shootout_goal", 0x08: "shootout_miss",
    0x29: "disallowed_goal",
}

MATCH_HEAD = Record("match_head", 8, [
    Field(0, 2, "home_tid", U16),
    Field(2, 2, "away_tid", U16),
    Field(4, 2, "comp_id",  U16),
    Field(6, 2, "day",      U16, note="day-of-year, 0-based"),
])

# `side` is the event player's own team (0 home, 1 away) on every event read, own goals
# included -- 3,653 of 3,653 over 30 saves. The event's tid is always a player of the match.
EVENT = Record("match_event", 17, [
    Field(0, 1, "b0",        U8,  note="unnamed; carried into staging.match_events"),
    Field(1, 1, "type_byte", U8,  note="EVENT_TYPE"),
    Field(2, 1, "minute",    U8,  note="0-based: the game shows minute + 1"),
    Field(3, 1, "added",     U8,  note="added time, in minutes"),
    Field(4, 1, "side",      U8,  note="0 home, 1 away: the event player's team"),
    Field(5, 4, "tid",       U32),
    Field(9, 8, UNKNOWN,     RAW, note="two u32; ffffffff on 80% of events, never a tid "
                                       "of the match"),
])

# `player_of_match` is a player of the match on every row and holds the match's top rating
# on 98.4% of them: the game's own Player of the Match, not a derived maximum.
BODY_HEAD = Record("match_body_head", 78, [
    Field(0,  2, "club_tid",        U16, note="our side: the managed club or its reserves"),
    Field(2,  2, "opponent_tid",    U16),
    Field(4,  2, "club_comp_id",    U16, note="= head comp_id"),
    Field(6,  1, "home_flag",       U8,  note="1 when club_tid is at home"),
    Field(7,  2, "header_home_tid", U16, note="= head home_tid"),
    Field(9,  2, "header_away_tid", U16, note="= head away_tid"),
    Field(11, 2, "header_day",      U16, note="= head day"),
    Field(13, 2, "year",            U16),
    Field(15, 4, "attendance",      U32),
    Field(19, 33, UNKNOWN, RAW, note="four u8, then four 8-byte rows [u16 x3][ffff]"),
    Field(52, 11, UNKNOWN, PAD),
    Field(63, 4, "player_of_match", U32),
    Field(67, 11, UNKNOWN, RAW),
])

# `positions` is the side's eleven positions at full time, in posOrder order: the team sheet
# the post-match stats screen shows, which the game re-sorts by position after an in-match
# change. +6 holds the same 22 bytes, or 0xff throughout on friendlies and reserve fixtures.
# `corners`, `clear_cut_chances` and `offsides` are the side's counts on the match stats
# screen; the screen's other team figures are sums of the player slots.
TEAM_HEAD = Record("match_team_head", 77, [
    Field(0,  3, UNKNOWN, RAW),
    Field(3,  1, "goals_against", U8, note="= the other team block's goals"),
    Field(4,  1, "corners", U8),
    Field(5,  1, "clear_cut_chances", U8),
    Field(6,  22, UNKNOWN, RAW, note="= positions, or all 0xff"),
    Field(28, 2, UNKNOWN, RAW),
    Field(30, 22, "positions", RAW, note="11 x (band, column): primitives.pitch_position"),
    Field(52, 1, "goals", U8, note="the side's score, own goals for it included"),
    Field(53, 15, UNKNOWN, RAW),
    Field(68, 1, "offsides", U8),
    Field(69, 8, UNKNOWN, RAW),
])

# The player's line for the match. `condition` (+3) is a match-fitness percentage; an unused
# substitute reads 0xff in friendlies and reserve fixtures and has a condition (and a rating
# of 6) in competitive matches. `subOn`/`subOff` are minutes, 0xff when the player was not
# substituted. `sentOff` is the minute the player was sent off, 0xff when he was not; it is
# set for a second-yellow dismissal too, which raises no red-card event.
_STATS = {
    0: "assists", 3: "condition", 4: "crossA", 5: "crossC", 8: "dribbles",
    10: "goals", 11: "headA", 12: "headW", 16: "intercept", 19: "subOn",
    20: "sentOff", 21: "subOff", 22: "mistakes", 23: "mistGoal", 25: "passA", 26: "passC",
    27: "keyPass", 32: "rating", 35: "shotA", 36: "shotO", 41: "posOrder",
    48: "tackA", 49: "tackW", 53: "yellow",
}
PLAYER_SLOT = Record("match_player_slot", 62, [
    *[Field(off, 1, name, U8) for off, name in _STATS.items()],
    Field(28, 2, "sid", HEX2, note="2 bytes here -- the PERSON record's sid is 4"),
    Field(42, 4, "tid", U32, note="0xffffffff = unused slot"),
    Field(1,  2, UNKNOWN, RAW),
    Field(6,  2, UNKNOWN, RAW),
    Field(9,  1, UNKNOWN, RAW),
    Field(13, 3, UNKNOWN, RAW),
    Field(17, 2, UNKNOWN, RAW),
    Field(24, 1, UNKNOWN, RAW),
    Field(30, 2, UNKNOWN, RAW),
    Field(33, 2, UNKNOWN, RAW),
    Field(37, 4, UNKNOWN, RAW),
    Field(46, 2, UNKNOWN, RAW),
    Field(50, 3, UNKNOWN, RAW),
    Field(54, 8, UNKNOWN, RAW, note="two u32; ffffffff on 80% of slots, never a tid of "
                                    "the match"),
])

TEAM_TAIL = Record("match_team_tail", 46, [
    Field(0,  16, UNKNOWN, RAW),
    Field(16, 4,  UNKNOWN, PAD),
    Field(20, 26, UNKNOWN, RAW),
])

# The tail is OUR side's kick-off shape: the formation string and its 11 (band, column)
# slots in the formation's own slot order. It does not say which player took which slot: the
# team sheet (posOrder) is the full-time one, so after an in-match change it no longer lines
# up with these slots -- each player's position is the team head's `positions`
# (docs/parser/matches.md). +220..+1182 is a grid of u16 coordinates.
# +1196..+1283 is eleven 8-byte rows, one per kick-off slot in that slot order: five bytes
# then 00 00 00, the first two a role family (inside forward 81 42, full-back 01 23 / 41 22).
MATCH_TAIL = Record("match_tail", 1439, [
    Field(0,    5,   UNKNOWN, RAW),
    Field(5,    4,   UNKNOWN, PAD),
    Field(9,    4,   UNKNOWN, RAW),
    Field(13,   4,   UNKNOWN, PAD),
    Field(17,   4,   UNKNOWN, RAW),
    Field(21,   4,   UNKNOWN, PAD),
    Field(25,   1,   UNKNOWN, RAW),
    Field(26,   7,   UNKNOWN, PAD),
    Field(33,   4,   UNKNOWN, PAD, note="the formation marker 76 b9 f4 07"),
    Field(37,   32,  "formation", RAW, note="ASCII, zero-padded: '4-2-3-1'"),
    Field(69,   22,  "kickoff_positions", RAW, note="11 x (band, column): the formation's slots"),
    Field(91,   13,  UNKNOWN, PAD),
    Field(104,  20,  UNKNOWN, RAW),
    Field(124,  96,  UNKNOWN, PAD),
    Field(220,  963, UNKNOWN, RAW),
    Field(1183, 5,   UNKNOWN, PAD),
    Field(1188, 3,   UNKNOWN, RAW),
    Field(1191, 5,   UNKNOWN, PAD),
    Field(1196, 4,   UNKNOWN, RAW),
    Field(1200, 4,   UNKNOWN, PAD),
    Field(1204, 77,  UNKNOWN, RAW),
    Field(1281, 14,  UNKNOWN, PAD),
    Field(1295, 61,  UNKNOWN, RAW),
    Field(1356, 13,  UNKNOWN, PAD),
    Field(1369, 70,  UNKNOWN, RAW),
])


# One team's block; the body holds two, home then away.
TEAM = Struct("match_team", TEAM_HEAD, FixedList("players", PLAYER_SLOT, PLAYER_SLOTS),
              TEAM_TAIL)
_BODY_SEGMENTS = (BODY_HEAD, FixedList("event_slots", EVENT, EVENT_SLOTS),
                  FixedList("teams", TEAM, 2), MATCH_TAIL)
BODY_SPAN = BODY_HEAD.span + EVENT_SLOTS * EVENT.span + 2 * TEAM.span + MATCH_TAIL.span
MARKER_AT = BODY_SPAN - MATCH_TAIL.span + 33          # the formation marker, in the body
ROW_FIXED = MATCH_HEAD.span + 1 + BODY_SPAN            # a row is ROW_FIXED + 17 n


# FMM27 (truro-2026-08-08, three rows: two friendlies and a league match). The row keeps
# FMM22's shape -- [head][n u8][n x event, 17 B][body] -- with a 10-byte head (the year
# follows the day) and a 5,665-byte body: the 78-byte body head, the 50 event slots, two
# 1,648-byte team blocks and a 1,441-byte tail, so the formation marker is still at the
# tail's +33. A row is 5,676 + 17 n bytes.
#
# The event record is FMM22's, its type codes are not: 01 goal, 24 the goal's assist (same
# minute), 26 yellow card, 27 an error leading to a goal (at the minute the other side
# scores; its player's slot reads 1 in `mistakes` and `mistGoal`), 2f a clear-cut chance (one
# per chance in the team head's count; a scored one is followed by its goal at the same
# minute). 17, 18 and 29 are unnamed: 17 and 18 come with a goal, 29 after a chance. `b0` is
# the event player's slot index (posOrder - 1).
EVENT_TYPE_FMM27 = {0x01: "goal", 0x24: "assist", 0x26: "yellow_card",
                    0x27: "error_leading_to_goal", 0x2F: "clear_cut_chance"}

MATCH_HEAD_FMM27 = Record("match_head_fmm27", 10, [
    Field(0, 2, "home_tid", U16),
    Field(2, 2, "away_tid", U16),
    Field(4, 2, "comp_id",  U16),
    Field(6, 2, "day",      U16, note="day-of-year, 0-based"),
    Field(8, 2, "year",     U16),
])

BODY_HEAD_FMM27 = Record("match_body_head_fmm27", 78, [
    Field(0,  2, "club_tid",        U16, note="our side: the managed club or its reserves"),
    Field(2,  2, "opponent_tid",    U16),
    Field(4,  2, "club_comp_id",    U16, note="= head comp_id"),
    Field(6,  1, "home_flag",       U8,  note="1 when club_tid is at home"),
    Field(7,  2, "header_home_tid", U16, note="= head home_tid"),
    Field(9,  2, "header_away_tid", U16, note="= head away_tid"),
    Field(11, 2, "header_year",     U16, note="= head year"),
    Field(13, 2, UNKNOWN,           U16, note="= the year on every row read"),
    Field(15, 4, "attendance",      U32),
    Field(19, 33, UNKNOWN, RAW, note="four u8, then four 8-byte rows [u16 x3][ffff]"),
    Field(52, 11, UNKNOWN, RAW),
    Field(63, 4, "player_of_match", U32),
    Field(67, 11, UNKNOWN, RAW),
])

# The side's own counters, as the match stats screen shows them. Shots, shots on target,
# tackles won and yellow cards on that screen are sums of the player slots; headers won is
# both a counter here and the slots' sum.
TEAM_HEAD_FMM27 = Record("match_team_head_fmm27", 80, [
    Field(0,  4, UNKNOWN, RAW),
    Field(4,  1, "corners", U8),
    Field(5,  1, "clear_cut_chances", U8),
    Field(6,  22, UNKNOWN, RAW, note="all 0xff on every row read"),
    Field(28, 1, "fouls", U8),
    Field(29, 1, "fouls_against", U8, note="= the other team block's fouls"),
    Field(30, 22, "positions", RAW, note="11 x (band, column): primitives.pitch_position"),
    Field(52, 1, "goals", U8, note="the side's score"),
    Field(53, 2, UNKNOWN, RAW),
    Field(55, 1, "headers_won", U8),
    Field(56, 6, UNKNOWN, RAW),
    Field(62, 4, "manager_tid", U32, note="the side's manager (a staff tid)"),
    Field(66, 2, UNKNOWN, RAW),
    Field(68, 1, "offsides", U8),
    Field(69, 2, "passes_attempted", U16),
    Field(71, 2, "passes_completed", U16),
    Field(73, 1, "crosses_attempted", U8),
    Field(74, 1, UNKNOWN, RAW),
    Field(75, 1, "crosses_completed", U8),
    Field(76, 3, UNKNOWN, RAW),
    Field(79, 1, "goals_against", U8, note="= the other team block's goals"),
])

# FMM22's one-byte stats in FMM22's order, but the run from condition to the substitution
# minutes starts 3 bytes earlier and everything from mistakes on 1 byte later. There is no
# assists byte: no slot byte reads 1 for each of the five players with an assist event, so
# a player's assists are his `24` events. `xg_x100` is the
# player's expected goals x 100: Maidenhead's slots sum to 27 (the screen's 0.27), Truro's
# to 217 (the screen's 2.18: the screen sums unrounded values). `yellow` is set on a booked
# player, whose +6 then reads 7.
_STATS_FMM27 = {
    0: "condition", 1: "crossA", 2: "crossC", 5: "dribbles", 7: "goals", 8: "headA",
    9: "headW", 13: "intercept", 16: "subOn", 17: "sentOff", 18: "subOff",
    23: "mistakes", 24: "mistGoal", 26: "passA", 27: "passC", 28: "keyPass", 33: "rating", 36: "shotA", 37: "shotO",
    42: "posOrder", 49: "tackA", 50: "tackW", 54: "yellow",
}
PLAYER_SLOT_FMM27 = Record("match_player_slot_fmm27", 70, [
    *[Field(off, 1, name, U8) for off, name in _STATS_FMM27.items()],
    Field(29, 2, "sid", HEX2, note="2 bytes here -- the PERSON record's sid is 4"),
    Field(43, 4, "tid", U32, note="0xffffffff = unused slot"),
    Field(63, 2, "xg_x100", U16, note="expected goals x 100"),
    Field(3,  2, UNKNOWN, RAW),
    Field(6,  1, UNKNOWN, RAW, note="7 on a booked player"),
    Field(10, 3, UNKNOWN, RAW),
    Field(14, 2, UNKNOWN, RAW),
    Field(19, 4, UNKNOWN, RAW, note="ffffffff on a starter; a substitute's own value"),
    Field(25, 1, UNKNOWN, RAW, note="20 on every slot read"),
    Field(31, 2, UNKNOWN, RAW),
    Field(34, 2, UNKNOWN, RAW),
    Field(38, 4, UNKNOWN, RAW),
    Field(47, 2, UNKNOWN, RAW),
    Field(51, 3, UNKNOWN, RAW, note="+51 reads the side: 0 home, 1 away"),
    Field(55, 8, UNKNOWN, RAW, note="two u32, ffffffff on every slot read"),
    Field(65, 2, UNKNOWN, RAW, note="u16; non-zero on players with key passes"),
    Field(67, 3, UNKNOWN, RAW),
])

TEAM_TAIL_FMM27 = Record("match_team_tail_fmm27", 168, [
    Field(0, 168, UNKNOWN, RAW),
])

MATCH_TAIL_FMM27 = Record("match_tail_fmm27", 1441, [
    Field(0,    33,  UNKNOWN, RAW),
    Field(33,   4,   UNKNOWN, PAD, note="the formation marker 76 b9 f4 07"),
    Field(37,   32,  "formation", RAW, note="ASCII, zero-padded: '4-1-2-1-2'"),
    Field(69,   22,  "kickoff_positions", RAW, note="11 x (band, column): the formation's slots"),
    Field(91,   1350, UNKNOWN, RAW),
])

TEAM_FMM27 = Struct("match_team_fmm27", TEAM_HEAD_FMM27,
                    FixedList("players", PLAYER_SLOT_FMM27, PLAYER_SLOTS), TEAM_TAIL_FMM27)
_BODY_SEGMENTS_FMM27 = (BODY_HEAD_FMM27, FixedList("event_slots", EVENT, EVENT_SLOTS),
                        FixedList("teams", TEAM_FMM27, 2), MATCH_TAIL_FMM27)


class _Layout:
    """How one game version frames a row: the head, the body's span and where the formation
    marker sits in it, and where the body repeats the head."""
    def __init__(self, head, body_head, team, tail, repeat_at, repeat):
        self.head = head
        self.body_span = body_head.span + EVENT_SLOTS * EVENT.span + 2 * team.span + tail.span
        self.marker_at = self.body_span - tail.span + 33
        self.row_fixed = head.span + 1 + self.body_span
        self.repeat_at = repeat_at          # body offset of the three repeated u16s
        self.repeat = repeat                # head offsets of the values they repeat


_LAYOUT = _Layout(MATCH_HEAD, BODY_HEAD, TEAM, MATCH_TAIL, 7, (0, 2, 6))
_LAYOUT_FMM27 = _Layout(MATCH_HEAD_FMM27, BODY_HEAD_FMM27, TEAM_FMM27, MATCH_TAIL_FMM27,
                        7, (0, 2, 8))
assert (_LAYOUT.body_span, _LAYOUT.marker_at, _LAYOUT.row_fixed) == (BODY_SPAN, MARKER_AT,
                                                                     ROW_FIXED)
assert (_LAYOUT_FMM27.body_span, _LAYOUT_FMM27.row_fixed) == (5665, 5676)


def _layout(mm: Any) -> _Layout:
    return _LAYOUT_FMM27 if save_format(mm) == FMM27 else _LAYOUT


class MatchTableError(ValueError):
    """The match table was located but does not walk as its count declares."""


def _body(mm: Any, p: int) -> Optional[int]:
    """Where the body of a row starting at `p` begins, or None if no row starts there:
    the body must repeat the head and carry the formation marker."""
    lay = _layout(mm)
    if p < 1 or p + lay.row_fixed > len(mm):
        return None
    n = mm[p + lay.head.span]
    b = p + lay.head.span + 1 + n * EVENT.span
    if n > EVENT_SLOTS or b + lay.body_span > len(mm):
        return None
    home, away, comp = struct.unpack_from("<3H", mm, p)
    club, opp, comp2 = struct.unpack_from("<3H", mm, b)
    repeated = struct.unpack_from("<3H", mm, b + lay.repeat_at)
    if (home == away or {club, opp} != {home, away} or comp2 != comp
            or mm[b + 6] != (club == home)
            or repeated != tuple(struct.unpack_from("<H", mm, p + o)[0] for o in lay.repeat)
            or mm[b + lay.marker_at:b + lay.marker_at + 4] != FORMATION_MARKER):
        return None
    return b


def _row_before(mm: Any, p: int) -> Optional[int]:
    """The row that ends exactly at `p`, or None."""
    lay = _layout(mm)
    for n in range(EVENT_SLOTS + 1):
        q = p - lay.row_fixed - n * EVENT.span
        if q >= 1 and mm[q + lay.head.span] == n and _body(mm, q) is not None:
            return q
    return None


_CACHE: Dict[str, Optional[Tuple[int, int]]] = {}


def locate_matches(mm: Any) -> Optional[Tuple[int, int]]:
    """(row 0, declared count), or None when the table holds no row to find.

    Seeded from the first formation marker that sits in a real row, then walked back row by
    row; the byte before row 0 is the count."""
    key = _cache_key(mm)
    if key in _CACHE:
        return _CACHE[key]
    found = None
    lay = _layout(mm)
    i = mm.find(FORMATION_MARKER)
    while i != -1 and found is None:
        b = i - lay.marker_at
        for n in range(EVENT_SLOTS + 1):
            p = b - lay.head.span - 1 - n * EVENT.span
            if p >= 1 and mm[p + lay.head.span] == n and _body(mm, p) == b:
                found = p
                break
        i = mm.find(FORMATION_MARKER, i + 1)
    if found is not None:
        while True:
            q = _row_before(mm, found)
            if q is None:
                break
            found = q
        found = (found, mm[found - 1])
    _CACHE[key] = found
    return found


def _repeats_head(row: Dict[str, Any], index: int) -> bool:
    return ({row["club_tid"], row["opponent_tid"]} == {row["home_tid"], row["away_tid"]}
            and row["club_comp_id"] == row["comp_id"]
            and (row["header_home_tid"], row["header_away_tid"], row["header_day"])
            == (row["home_tid"], row["away_tid"], row["day"]))


MATCHES_TABLE = TableDef(
    name="matches",
    segments=(MATCH_HEAD, CountedList("events", U8, EVENT, max_count=EVENT_SLOTS))
    + _BODY_SEGMENTS,
    locator=locate_matches,
    include_offset=True,
    invariant=_repeats_head,
)


def _repeats_head_fmm27(row: Dict[str, Any], index: int) -> bool:
    return ({row["club_tid"], row["opponent_tid"]} == {row["home_tid"], row["away_tid"]}
            and row["club_comp_id"] == row["comp_id"]
            and (row["header_home_tid"], row["header_away_tid"], row["header_year"])
            == (row["home_tid"], row["away_tid"], row["year"]))


MATCHES_TABLE_FMM27 = TableDef(
    name="matches",
    segments=(MATCH_HEAD_FMM27, CountedList("events", U8, EVENT, max_count=EVENT_SLOTS))
    + _BODY_SEGMENTS_FMM27,
    locator=locate_matches,
    include_offset=True,
    invariant=_repeats_head_fmm27,
)


def _table(mm: Any) -> TableDef:
    return MATCHES_TABLE_FMM27 if save_format(mm) == FMM27 else MATCHES_TABLE


def matches_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """The table's span, its count byte included."""
    return [(s - 1, e) for s, e in _table(mm).spans(mm, include_count_header=False)]


_EVENT_KEYS = ("b0", "type_byte", "minute", "added", "side", "tid")
_TEAM_HEAD_KEYS = ("corners", "clear_cut_chances", "offsides")
_TEAM_HEAD_KEYS_FMM27 = ("corners", "clear_cut_chances", "offsides", "fouls", "headers_won",
                         "passes_attempted", "passes_completed", "crosses_attempted",
                         "crosses_completed", "manager_tid")


def _positions(pairs: bytes) -> Optional[List[str]]:
    """Eleven (band, column) pairs as position codes; None if any pair is not a position."""
    positions = [pitch_position(pairs[2 * i], pairs[2 * i + 1]) for i in range(11)]
    return None if None in positions else positions


def _match(r: Dict[str, Any], team_keys: Tuple[str, ...] = _TEAM_HEAD_KEYS) -> Dict[str, Any]:
    try:
        date = (datetime.date(r["year"], 1, 1)
                + datetime.timedelta(days=r["day"])).isoformat()
    except ValueError:
        date = None
    home, away = r["teams"]
    return {
        "offset": r["offset"],
        "date": date,
        "comp_id": r["comp_id"],
        "home_tid": r["home_tid"],
        "away_tid": r["away_tid"],
        "club_tid": r["club_tid"],
        "home_flag": r["home_flag"],
        "attendance": r["attendance"],
        "score": {"home": home["goals"], "away": away["goals"]},
        "team_head": {side: {k: t[k] for k in team_keys}
                      for side, t in (("home", home), ("away", away))},
        "player_of_match": r["player_of_match"],
        "formation": r["formation"].rstrip(b"\x00").decode("ascii"),
        "kickoff_positions": _positions(r["kickoff_positions"]),
        "home_positions": _positions(home["positions"]),
        "away_positions": _positions(away["positions"]),
        "events": [{k: e[k] for k in _EVENT_KEYS} for e in r["events"]],
        "home_xi": [p for p in home["players"] if p["tid"] != NO_PLAYER],
        "away_xi": [p for p in away["players"] if p["tid"] != NO_PLAYER],
    }


def check_against_fixtures(matches: List[Dict[str, Any]], fixtures: List[Dict[str, Any]],
                           clubs: Any, since: str, until: str) -> None:
    """Raise `MatchTableError` unless the table holds exactly our clubs' fixtures played in
    (since, until] -- the world fixture list (`tables/fixtures.py`), an independent table.

    `since` is the career's last rollover day on or before the save date (the game empties
    this table on that day) and `until` the save date, both ISO. The two agree match for
    match on every save measured, friendlies included, so a table that is not located while
    the fixture list shows games played is a locator failure, not an empty season."""
    clubs = set(clubs)
    want = {(f["date"], f["home_tid"], f["away_tid"]) for f in fixtures
            if (f["home_tid"] in clubs or f["away_tid"] in clubs)
            and since < f["date"] <= until}
    have = {(m["date"], m["home_tid"], m["away_tid"]) for m in matches}
    if want != have:
        raise MatchTableError(
            f"matches: the table holds {len(have)} matches and the fixture list "
            f"{len(want)} for our clubs since {since}; missing {sorted(want - have)[:3]}, "
            f"unexpected {sorted(have - want)[:3]}")


def scrape_matches(mm: Any) -> List[Dict[str, Any]]:
    """Every match in the table, in the order played. [] when the table is not located.

    Raises `MatchTableError` if the walk reads a different number of rows than the count
    declares -- the walk is then misframed, and nothing it read can be trusted."""
    table = _table(mm)
    runs = table.runs(mm)
    if not runs:
        return []
    base, count = runs[0]
    rows = table.scrape(mm)
    if len(rows) != count:
        raise MatchTableError(f"matches: read {len(rows)} of {count} rows; "
                              "the walk is misframed")
    # The extent, both ends: a row starts at row 0 and none ends there, and none follows
    # the last. Without this a later row taken for row 0 reads the byte before it -- the
    # last byte of a real row, often 0 -- as the count, and walks to an empty table.
    end = base
    if rows:
        end = rows[-1]["offset"] + _layout(mm).row_fixed + EVENT.span * len(rows[-1]["events"])
    if (_body(mm, base) is None or _row_before(mm, base) is not None
            or _body(mm, end) is not None):
        raise MatchTableError(f"matches: the {count} rows from {base} are not the whole table")
    keys = _TEAM_HEAD_KEYS_FMM27 if table is MATCHES_TABLE_FMM27 else _TEAM_HEAD_KEYS
    return [_match(r, keys) for r in rows]
