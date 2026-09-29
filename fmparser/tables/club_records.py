#!/usr/bin/env python3
"""`club_records` -- every club's Club History: league history, Team Records, Player Records.

A count-framed array of variable-length club rows, immediately after the career-history
pool (`tables/history.py`):

    header  [count u16]                       clubs in the table (1,057 Frem, 1,060 Bucaspor)
    row     [club_tid u16]                    ascending through the table
            [n u8][n x league list]           one list per league the club has played in
            [12 x team row]    Team Records   - Overall
            [12 x player row]  Player Records - Overall
            [12 x team row]    Team Records   - this season
            [12 x player row]  Player Records - this season

The record blocks are preallocated and filled in place: an unwritten slot has `comp_cid`
0xffff (team) or `player_tid` 0xffffffff (player), and every other byte of it is the same
filler. A slot is written or not independently of the rest of its block -- a club that has
played no league has no league-position records and still has its cup results.

LEAGUE LIST, 212 bytes: `[cid u16]` then 30 season slots of 7 bytes,

    +0  cid u16        the league (the list's own cid, repeated)
    +2  position u8
    +3  year u16       the season's START year: 2023 = the 2023/24 season
    +5  teams u16      clubs in the league that season

filled from slot 0; an unused slot is seven 0xff bytes.

TEAM ROW, 21 bytes. The club tid is at the END of the row:

    +0   value f32     the metric the record is sorted on, and it VARIES BY CATEGORY: total
                       goals for "highest scoring", goal difference for biggest win/defeat,
                       a league position for the two `table` categories, a run length for
                       the four `streak` categories
    +4   comp_cid u16  0xffff = unwritten
    +6   season u16    the season the record was set; reads 0x07E4 in the per-season table
    +8   day u16       day-of-year, 0-based
    +10  unk10 u16
    +12  unk12 u16     ffff on every row read
    +14  unk14 u8
    +15  club_tid u16  the club; 0xffff on the `table` categories
    +17  opponent_tid u16
    +19  score_for u8  from `club_tid`'s perspective
    +20  score_against u8

For a `streak` category the opponent/score/day bytes are left over from an earlier write
and mean nothing, which is why only a `match` category carries its fixture into the output.

PLAYER ROW, 22 bytes:

    +0   player_tid u32   0xffffffff = unwritten
    +4   value f32        counts (17 goals), ratings (7.37), ages in DAYS (6182 = 16y338d =
                          years*365.25 + days) and money (44,958,444 -> "£45M")
    +8   unk8 u32
    +12  unk12 u32
    +16  unk16 u32        usually ff ff ff ff; slots 1-2 carry a value
    +20  season u16

The slot index IS the category -- no category id is stored. The order is the order the Club
History screens list them, verified slot for slot against Southampton on frem-2026-06-11
(`tests/test_club_records.py`). None of this is a fixture list: a match appears here because
it set a record, once per slot and per table it holds.
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..core import CountedList, F32, Field, FixedList, Record, TableDef, U8, U16, U32

__all__ = [
    "CLUB_RECORDS_TABLE",
    "LEAGUE_LIST",
    "PLAYER_CATEGORIES",
    "PLAYER_ROW",
    "TEAM_CATEGORIES",
    "TEAM_ROW",
    "club_records_table_spans",
    "locate_club_records",
    "scrape_club_records",
]

BLOCK = 12                                   # slots per record block
SEASON_SLOTS = 30                            # season slots per league list
NO_COMP = 0xFFFF                             # an unwritten team slot
NO_PLAYER = 0xFFFFFFFF                       # an unwritten player slot
NO_OPPONENT = 0xFFFF
NO_SCORE = 0xFF
EMPTY_SEASON = b"\xff" * 7

# The record CATEGORIES, in slot order. `kind` says which fields of a team row mean anything:
#   match  -- opponent/score/day/cid are real
#   table  -- a league position; opponent is 0xffff and the score bytes 0xff
#   streak -- `value` is a run length; the opponent/score/day bytes are leftover
TEAM_CATEGORIES = [
    ("highest_league_position", "table"),
    ("lowest_league_position", "table"),
    ("highest_scoring_match", "match"),
    ("highest_scoring_league_match", "match"),
    ("biggest_win", "match"),
    ("biggest_league_win", "match"),
    ("biggest_defeat", "match"),
    ("biggest_league_defeat", "match"),
    ("most_consecutive_wins", "streak"),
    ("most_games_without_defeat", "streak"),
    ("most_games_without_win", "streak"),
    ("most_consecutive_defeats", "streak"),
]

# `unit` is what a player row's `value` is counted in.
PLAYER_CATEGORIES = [
    ("most_goals_in_a_season", "count"),
    ("most_league_goals_in_a_season", "count"),
    ("most_assists_in_a_season", "count"),
    ("highest_average_rating_in_a_season", "rating"),
    ("most_player_of_match_in_a_season", "count"),
    ("most_bookings_in_a_season", "count"),
    ("most_red_cards_in_a_season", "count"),
    ("most_appearances_in_a_season", "count"),
    ("youngest_player", "days"),
    ("oldest_player", "days"),
    ("highest_transfer_fee_paid", "money_gbp"),
    ("highest_transfer_fee_received", "money_gbp"),
]

CLUB_RECORDS_HEADER = Record("club_records_header", 2, [
    Field(0, 2, "count", U16, note="clubs in the table"),
], is_head=True)

CLUB_RECORDS_HEAD = Record("club_records_head", 2, [
    Field(0, 2, "club_tid", U16),
])

LEAGUE_LIST = Record("club_league_list", 2 + 7 * SEASON_SLOTS, [
    Field(0, 2, "cid", U16, note="the league this list is for"),
] + [f for i in range(SEASON_SLOTS) for f in (
    Field(2 + 7 * i, 2, f"cid_{i}",      U16, note="the list's cid, repeated; ffff = unused"),
    Field(4 + 7 * i, 1, f"position_{i}", U8),
    Field(5 + 7 * i, 2, f"year_{i}",     U16, note="the season's start year"),
    Field(7 + 7 * i, 2, f"teams_{i}",    U16),
)])

# Field order is OUTPUT order: `season` sits at +20 in the player row and is emitted before
# the three unknowns.
TEAM_ROW = Record("club_team_record", 21, [
    Field(0,  4, "value",         F32),
    Field(4,  2, "comp_cid",      U16, note="0xffff = unwritten slot"),
    Field(6,  2, "season",        U16, note="0x07E4 in the per-season table"),
    Field(8,  2, "day",           U16, note="day-of-year, 0-based"),
    Field(10, 2, "unk10",         U16),
    Field(12, 2, "unk12",         U16),
    Field(14, 1, "unk14",         U8),
    Field(15, 2, "club_tid",      U16, note="0xffff on the `table` categories"),
    Field(17, 2, "opponent_tid",  U16),
    Field(19, 1, "score_for",     U8),
    Field(20, 1, "score_against", U8),
])

PLAYER_ROW = Record("club_player_record", 22, [
    Field(0,  4, "player_tid", U32, note="0xffffffff = unwritten slot"),
    Field(4,  4, "value",      F32),
    Field(20, 2, "season",     U16),
    Field(8,  4, "unk8",       U32),
    Field(12, 4, "unk12",      U32),
    Field(16, 4, "unk16",      U32, note="ffffffff on most rows; slots 1-2 carry a value"),
])

_BLOCKS = (("team_overall", TEAM_ROW), ("player_overall", PLAYER_ROW),
           ("team_season", TEAM_ROW), ("player_season", PLAYER_ROW))


def locate_club_records(mm: Any) -> Optional[Tuple[int, int]]:
    """(base, count): the count is the u16 immediately after the history pool."""
    from .history import history_end          # local: keeps numpy off this module's import path
    try:
        at = history_end(mm)
    except Exception:
        return None
    return at + CLUB_RECORDS_HEADER.span, struct.unpack_from("<H", mm, at)[0]


CLUB_RECORDS_TABLE = TableDef(
    name="club_records",
    segments=(
        CLUB_RECORDS_HEAD,
        CountedList("leagues", U8, LEAGUE_LIST, max_count=SEASON_SLOTS),
    ) + tuple(FixedList(name, row, BLOCK) for name, row in _BLOCKS),
    locator=locate_club_records,
    include_offset=True,
)


def club_records_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """The table's span, its u16 count included."""
    return [(s - CLUB_RECORDS_HEADER.span, e)
            for s, e in CLUB_RECORDS_TABLE.spans(mm, include_count_header=False)]


def _league_history(club: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for lst in club["leagues"]:
        for i in range(SEASON_SLOTS):
            if lst[f"cid_{i}"] == NO_COMP and lst[f"year_{i}"] == 0xFFFF:
                continue
            out.append({"club_tid": club["club_tid"], "cid": lst[f"cid_{i}"],
                        "year": lst[f"year_{i}"], "position": lst[f"position_{i}"],
                        "teams": lst[f"teams_{i}"]})
    return out


def scrape_club_records(mm: Any, table: Optional[TableDef] = None) -> Dict[str, List[Dict[str, Any]]]:
    """{team_records, player_records, league_history}: every written slot of every club.

    Raises `ValueError` if the table is not located, if the walk reads fewer clubs than the
    count declares, or if the club tids do not ascend -- the walk is then misframed, and
    nothing it read can be trusted."""
    table = table or CLUB_RECORDS_TABLE
    runs = table.runs(mm)
    if not runs:
        raise ValueError("club_records: table not located")
    clubs = table.scrape(mm)
    if len(clubs) != runs[0][1]:
        raise ValueError(f"club_records: read {len(clubs)} of {runs[0][1]} clubs; "
                         "the walk is misframed")
    tids = [c["club_tid"] for c in clubs]
    if any(a >= b for a, b in zip(tids, tids[1:])):
        raise ValueError("club_records: club tids do not ascend; the walk is misframed")
    team, player, leagues = [], [], []
    for c in clubs:
        club = c["club_tid"]
        pos = c["offset"] + CLUB_RECORDS_HEAD.span + 1 + len(c["leagues"]) * LEAGUE_LIST.span
        for name, row in _BLOCKS:
            table = name.split("_")[1]
            for k, r in enumerate(c[name]):
                off = pos + k * row.span
                if row is TEAM_ROW:
                    if r["comp_cid"] == NO_COMP:
                        continue
                    cat, kind = TEAM_CATEGORIES[k]
                    out = {"offset": off, "club_tid": club, "table": table, "slot": k,
                           "category": cat, "kind": kind}
                    out.update((f, r[f]) for f in ("value", "comp_cid", "season", "day",
                                                   "unk10", "unk12", "unk14"))
                    if (kind == "match" and r["opponent_tid"] != NO_OPPONENT
                            and r["score_for"] != NO_SCORE and r["score_against"] != NO_SCORE):
                        out.update(opponent_tid=r["opponent_tid"], score_for=r["score_for"],
                                   score_against=r["score_against"])
                    else:
                        out.update(opponent_tid=None, score_for=None, score_against=None)
                    team.append(out)
                else:
                    if r["player_tid"] == NO_PLAYER:
                        continue
                    cat, unit = PLAYER_CATEGORIES[k]
                    out = {"offset": off, "club_tid": club, "table": table, "slot": k,
                           "category": cat, "unit": unit}
                    out.update(r)
                    player.append(out)
            pos += BLOCK * row.span
        leagues.extend(_league_history(c))
    return {"team_records": team, "player_records": player, "league_history": leagues}
