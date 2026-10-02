#!/usr/bin/env python3
"""`clubs` — the club table, 11,331 slots on Frem (12,278 on Bucaspor).

It follows the round-name table directly: `[0xFF x 6][count u32]`, then the records in tid
order, walked by declaration with `tid == slot index` (CLUB_TABLE). Slots 0.. are national
teams, stored club-shaped. `scrape_clubs` reports every club's whole record.
"""
from typing import Any, Dict, Optional, Tuple

from ..core import primitives as P
from ..core import (CountedList, Field, I32, PAD, PString, RAW, Record, TableDef, U8, U16,
                    U32, UNKNOWN)
from ..save import cache_key as _cache_key
from .rounds import ROUNDS_TABLE


def after_frame(mm: Any, end: int, width: int) -> Optional[Tuple[int, int]]:
    """(record 0, count) for a table that follows another table ending at `end`: a run of
    0xFF, then a `width`-byte count. None if no 0xFF run is there."""
    p = end
    while p < len(mm) and mm[p] == 0xFF:
        p += 1
    if p == end or p + width > len(mm):
        return None
    return p + width, int.from_bytes(mm[p:p + width], "little")

class ClubTableError(Exception):
    """The club table could not be located, or its walk did not read every slot it declares."""


def locate_clubs(mm: Any) -> Optional[Tuple[int, int]]:
    """(record 0, declared count): the frame right after the round-name table, whose record 0
    is tid 0."""
    spans = ROUNDS_TABLE.spans(mm)
    loc = after_frame(mm, spans[-1][1], 4) if spans else None
    if loc is None or P.u32(mm, loc[0]) != 0:
        return None
    return loc


# The byte after a long or short name: 00 after a name, FF after an empty one (a blank slot).
NAME_END = Record("name_end", 1, (Field(0, 1, UNKNOWN, RAW),), is_head=True)

CLUB_HEAD = Record("club_head", 8, (
    Field(0, 4, "tid", U32),
    Field(4, 4, "uid", I32),
), is_head=True)


def _kit_fields(k):
    base = 16 + 22 * k
    return (Field(base, 2, UNKNOWN, RAW),               # two flag bytes
            *(Field(base + 2 + 2 * i, 2, f"kit{k}_{i}", U16) for i in range(10)))


# The club record's fixed first stretch, after the three names. Field order from
# nyongrand/fmm-editor's FMM26 `Club` (docs/agent-context/fmm-editor-record-comparison.md),
# verified on the Danish Superliga: league_id reads 2 for every top-flight club, attendances
# rank the clubs by size, and the colours decode to the right kits. A colour is RGB555
# (0x7FFF is white). `based_id` is the nation whose league the club plays in and `nation_id`
# the club's home nation; they differ on 72 clubs (Cardiff City: England, Wales; The New
# Saints, of Oswestry: Wales, England; FC Balzers: Switzerland, Liechtenstein).
CLUB_TRAILER = Record("club_trailer", 167, (
    Field(0, 2, "based_id", U16),
    Field(2, 2, "nation_id", U16),
    *(Field(4 + 2 * i, 2, f"colour_{i}", U16) for i in range(6)),
    *(f for k in range(6) for f in _kit_fields(k)),
    Field(148, 1, "status", U8),
    Field(149, 1, "academy", U8),
    Field(150, 1, "facilities", U8),
    Field(151, 2, "att_avg", U16, note="named from fmm-editor; not attendance (docs/TODO.md)"),
    Field(153, 2, "att_min", U16),
    Field(155, 2, "att_max", U16),
    Field(157, 1, "reserves", U8),
    Field(158, 2, "league_id", U16),
    Field(160, 2, "other_division", U16, note="0xffff when league_id is the club's league"),
    Field(162, 1, "other_last_position", U8),
    Field(163, 2, "stadium_id", U16),
    Field(165, 2, "last_league", U16),
), is_head=True)

_BYTE = Record("club_byte", 1, (Field(0, 1, "value", U8),), is_head=True)

CLUB_STANDING = Record("club_standing", 23, (
    Field(0, 1, "league_pos", U8),
    Field(1, 2, "reputation", U16),
    Field(3, 20, UNKNOWN, RAW),
), is_head=True)

AFFILIATE = Record("club_affiliate", 21, (
    Field(0, 4, UNKNOWN, RAW),
    Field(4, 4, "club1_tid", U32),
    Field(8, 4, "club2_tid", U32),
    Field(12, 2, "start_day", U16),
    Field(14, 2, "start_year", U16),
    Field(16, 2, "end_day", U16),
    Field(18, 2, "end_year", U16),
    Field(20, 1, UNKNOWN, RAW),
), is_head=True)

_TID = Record("club_squad_slot", 4, (Field(0, 4, "tid", U32),), is_head=True)

# The club's STAFF list excludes the manager, which is what makes mart.club_managers exact:
# of the staff whose info record points at this club, the one missing from here is the man
# in charge (verified on all 7 ground-truth clubs). `main_club_tid` is the parent club: every
# reserve side carries one and it resolves exactly (Frem's 7296 -> 346); first teams mostly
# hold a negative value, not decoded.
CLUB_STAFF = Record("club_staff", 123, (
    *(Field(4 * i, 4, f"staff_{i}", U32) for i in range(11)),
    Field(44, 4, "main_club_tid", U32),
    Field(48, 1, "club_type", U8),
    Field(49, 74, UNKNOWN, RAW),
), is_head=True)

_TAIL_ITEM = Record("club_tail_item", 9, (Field(0, 9, UNKNOWN, RAW),), is_head=True)

# `[tid u32][uid i32]`, three names (NAME_END after long and short, none after the code), then
# the trailer: 167 fixed bytes, `[u32 8][8 B]`, 23 bytes, the affiliates `[u16 n][n x 21]`,
# the squad `[u16 40][40 x tid]`, the staff block, and `[u16 m][m x 9 B]`.
CLUB_TABLE = TableDef(
    name="clubs",
    segments=(
        CLUB_HEAD,
        PString("name", allow_empty=True),
        NAME_END,
        PString("short", allow_empty=True),
        NAME_END,
        PString("code", allow_empty=True),
        CLUB_TRAILER,
        CountedList("block_167", U32, _BYTE, scalar=True, max_count=64),
        CLUB_STANDING,
        CountedList("affiliates", U16, AFFILIATE, max_count=64),
        CountedList("squad", U16, _TID, scalar=True, max_count=64),
        CLUB_STAFF,
        CountedList("tail", U16, _TAIL_ITEM, max_count=4096),
    ),
    locator=locate_clubs,
    invariant=lambda rec, slot: rec["tid"] == slot,
)

_CLUB_ROWS_CACHE: Dict[Any, list] = {}


def _club_rows(mm: Any) -> list:
    """Every declared club slot, in tid order."""
    key = _cache_key(mm)
    if key not in _CLUB_ROWS_CACHE:
        loc = locate_clubs(mm)
        if loc is None:
            raise ClubTableError("club table not found after the round-name table")
        rows = CLUB_TABLE.scrape(mm)
        if len(rows) != loc[1]:
            raise ClubTableError(f"club table walk read {len(rows)} of {loc[1]} declared "
                                 f"slots (record 0 at {loc[0]})")
        _CLUB_ROWS_CACHE[key] = rows
    return _CLUB_ROWS_CACHE[key]


def scrape_clubs(mm: Any) -> Dict[int, Dict[str, Any]]:
    """{tid: club} for every declared slot: the whole record, names and trailer (`_club`)."""
    return {r["tid"]: _club(r) for r in _club_rows(mm)}


_CLUBS_END_CACHE: Dict[Any, int] = {}


def clubs_end(mm: Any) -> int:
    """Where the club table ends -- and the competition table's frame begins."""
    key = _cache_key(mm)
    if key not in _CLUBS_END_CACHE:
        _CLUBS_END_CACHE[key] = CLUB_TABLE.spans(mm)[0][1]
    return _CLUBS_END_CACHE[key]


_NO_ID = (0, 0xFFFF, 0xFFFFFFFF)


def _rgb(c):
    """RGB555 u16 -> '#rrggbb'."""
    return "#%02x%02x%02x" % (((c >> 10) & 0x1f) << 3, ((c >> 5) & 0x1f) << 3, (c & 0x1f) << 3)


def _club(row):
    """One club record: its names, uid, league membership and the whole trailer. A club is
    a league member when `other_division` is FFFF and `league_id` names a league."""
    code, main = row["league_id"], row["main_club_tid"]
    league = code if (row["other_division"] == 0xFFFF and code and code != 0xFFFF) else None
    return {
        "tid": row["tid"], "uid": row["uid"], "name": row["name"], "short": row["short"],
        "league_cid": league, "country": row["based_id"],
        "based_id": row["based_id"], "nation_id": row["nation_id"],
        "colours": [_rgb(row[f"colour_{i}"]) for i in range(6)],
        # 6 kits of 10 colours; stored whole because which slot is home vs away is not
        # established.
        "kits": [[_rgb(row[f"kit{k}_{i}"]) for i in range(10)] for k in range(6)],
        "status": row["status"], "academy": row["academy"], "facilities": row["facilities"],
        "att_avg": row["att_avg"], "att_min": row["att_min"], "att_max": row["att_max"],
        "reserves": row["reserves"], "league_id": row["league_id"],
        "other_division": row["other_division"],
        "other_last_position": row["other_last_position"],
        "stadium_id": row["stadium_id"], "last_league": row["last_league"],
        "league_pos": row["league_pos"], "reputation": row["reputation"],
        "affiliates": row["affiliates"],
        "squad": [t for t in row["squad"] if t not in _NO_ID],
        "staff": [t for t in (row[f"staff_{i}"] for i in range(11)) if t not in _NO_ID],
        "main_club_tid": main if 0 < main < 70000 else None,
        "club_type": row["club_type"],
    }
