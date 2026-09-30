#!/usr/bin/env python3
"""`training` -- the Club Squad > Training page: every player's training focus.

One row per person, in a count-framed array a fixed distance after the Player Progress pool
(`tables/player_progress.py`):

    header  [count u32]            the person count (32,966 on every Frem save, 34,312 on
                                   Bucaspor) -- the same count the person table declares
    row k   61 bytes, for person tid k

    +0   tid u32                   == the row index; 0xffffffff = an unused row
    +4   uid u32
    +8   u8                        unread
    +9   u32                       unread; money-like, a round number (50,000, 80,000)
    +13  u32                       unread; money-like, a little under +9
    +17  u32                       unread; non-zero on the rows whose Progress bar shows a
                                   green fill
    +21  intensity u16             the Int column: 3 = high (the red icon), 2 = normal;
                                   1 and 0 also occur
    +23  focus_role u16            the Focus Role, in the role ids of `ROLES`; 0xffff on a
                                   member of staff
    +25  u16                       0 on a player, 0xffff on a member of staff
    +27  focus_attribute u16       the Attr column, in the codes of `ATTRIBUTE_FOCUS`
    +29  focus_band u8             the Focus Pos, as the pair the match slot array uses
    +30  focus_column u8           (`core.primitives.pitch_position`)
    +31  30 bytes                  unread: nine u16 (the fourth reads 135 on every row), and
                                   from +49 three [day-of-year u16][year u16] dates

Read against the Training page of frem-2027-06-15, all 34 squad rows on screen: role,
position, attribute and intensity agree on every row. A player attribute snapshot's `role`
(`tables/player_lists.py`) is this Focus Role as it was on the snapshot's date.

Located from the save's own structure: the first four rows hold tids 0-3 and the count in
front is a plausible person count; the scrape then requires every row's tid to be its index
or 0xffffffff.
"""
import re
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..core.primitives import pitch_position
from ..core import Field, RAW, Record, TableDef, U16, U32, U8, UNKNOWN, table_spans
from ..save import cache_key as _cache_key
from .player_progress import PROGRESS_ROW, locate_player_progress

__all__ = [
    "ATTRIBUTE_FOCUS",
    "ROLES",
    "ROLES_INFERRED",
    "TRAINING_ROW",
    "TRAINING_TABLE",
    "focus_position",
    "locate_training",
    "scrape_training",
    "training_table_spans",
]

NO_PERSON = 0xFFFFFFFF
NO_ROLE = 0xFFFF

# The Focus Role (and a player attribute snapshot's role), by id. The ids run in position
# order -- 0-1 GK, 2 SW, 3-4 full-back, 5-7 DC, 8-12 wide, 13-17 central midfield, 18-24
# striker -- and 25-32 follow as a second set. Ids in ROLES_INFERRED are placed by their
# position block and their holders' attributes rather than read off the game's screens.
ROLES = {0: "Goalkeeper", 1: "Sweeper Keeper", 2: "Sweeper", 3: "Full-Back", 4: "Wing-Back",
         5: "Central Defender", 6: "Ball Playing Defender", 7: "No-Nonsense Centre-Back",
         8: "Wide Midfielder", 9: "Winger", 10: "Inverted Winger", 11: "Defensive Winger",
         12: "Inside Forward", 13: "Central Midfielder", 14: "Deep Lying Playmaker",
         15: "Ball Winning Midfielder", 16: "Box to Box Midfielder", 17: "Advanced Playmaker",
         18: "Poacher", 19: "Target Forward", 20: "Deep Lying Forward", 21: "Advanced Forward",
         22: "Complete Forward", 23: "Pressing Forward", 24: "Trequartista", 25: "Libero",
         26: "Shadow Striker", 27: "Inverted Wing-Back", 28: "Defensive Full-Back",
         29: "Anchor", 30: "Defensive Midfielder", 31: "Attacking Midfielder",
         32: "Roaming Playmaker"}
ROLES_INFERRED = frozenset({2, 8, 11, 18, 20, 22, 23, 24, 27, 28, 29, 31})

# The Attr column's abbreviation, by the code at +27: the codes read off the Training page.
# 0, 2, 4, 10, 12, 13 and 15 also occur and are not yet named.
ATTRIBUTE_FOCUS = {1: "CRO", 3: "PAS", 5: "TAC", 6: "HAN", 8: "AIR", 9: "REF", 11: "CRE",
                   14: "POS", 17: "STR", 18: "PAC", 19: "STA"}

TRAINING_ROW = Record("training_row", 61, [
    Field(0,  4, "tid",             U32, note="== the row index; 0xffffffff = unused row"),
    Field(4,  4, "uid",             U32),
    Field(8,  1, UNKNOWN,           U8),
    Field(9,  4, UNKNOWN,           U32),
    Field(13, 4, UNKNOWN,           U32),
    Field(17, 4, UNKNOWN,           U32),
    Field(21, 2, "intensity",       U16, note="3 = high, 2 = normal"),
    Field(23, 2, "focus_role",      U16, note="ROLES; 0xffff on staff"),
    Field(25, 2, UNKNOWN,           U16, note="0 on a player, 0xffff on staff"),
    Field(27, 2, "focus_attribute", U16, note="ATTRIBUTE_FOCUS"),
    Field(29, 1, "focus_band",      U8,  note="the match slot array's band byte"),
    Field(30, 1, "focus_column",    U8,  note="the match slot array's column byte"),
    Field(31, 30, UNKNOWN,          RAW),
])

_STRIDE = TRAINING_ROW.span
_MIN_PERSONS, _MAX_PERSONS = 10_000, 200_000
# Rows 0-3 with tids 0-3: the table's first four rows, whatever sits between them.
_HEAD = re.compile(b"".join(struct.pack("<I", k) + (b".{%d}" % (_STRIDE - 4) if k < 3 else b"")
                            for k in range(4)), re.S)
_SEARCH = 8_000_000             # bytes after the Player Progress pool to search
_CACHE: Dict[Any, Optional[Tuple[int, int]]] = {}


def locate_training(mm: Any) -> Optional[Tuple[int, int]]:
    """(base, count) of the training table, or None: the first place after Player Progress
    where rows 0-3 hold tids 0-3 behind a plausible person count."""
    key = _cache_key(mm)
    if key in _CACHE:
        return _CACHE[key]
    res = None
    run = locate_player_progress(mm)
    lo = run[0] + run[1] * PROGRESS_ROW.span if run else 4
    for m in _HEAD.finditer(mm, lo, min(len(mm), lo + _SEARCH)):
        base = m.start()
        n = struct.unpack_from("<I", mm, base - 4)[0]
        if _MIN_PERSONS <= n <= _MAX_PERSONS and base + n * _STRIDE <= len(mm):
            res = (base, n)
            break
    _CACHE[key] = res
    return res


TRAINING_TABLE = TableDef(
    name="training",
    segments=(TRAINING_ROW,),
    locator=locate_training,
    fields=("tid", "intensity", "focus_role", "focus_attribute", "focus_band", "focus_column"),
)


def training_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """The byte span of the table, count included."""
    (start, end), = table_spans(mm, TRAINING_TABLE, include_count_header=False)
    return [(start - 4, end)]


def focus_position(band: int, column: int) -> Optional[str]:
    """The Focus Pos as a position code ('DR', 'DMC', 'ST', ...), or None."""
    pos = pitch_position(band, column)
    return "ST" if pos == "FC" else pos


def scrape_training(mm: Any) -> List[Dict[str, Any]]:
    """Every player's row, in tid order: {tid, intensity, focus_role, focus_attribute,
    focus_position}. Unused rows and staff (no role) are left out. Raises `ValueError` if
    the table is not located or a row's tid is neither its index nor unused."""
    rows = TRAINING_TABLE.scrape(mm)
    if not rows:
        raise ValueError("training: the table is not located")
    out = []
    for k, r in enumerate(rows):
        if r["tid"] == NO_PERSON:
            continue
        if r["tid"] != k:
            raise ValueError(f"training: row {k} holds tid {r['tid']}")
        if r["focus_role"] == NO_ROLE:
            continue
        out.append({"tid": r["tid"], "intensity": r["intensity"],
                    "focus_role": r["focus_role"], "focus_attribute": r["focus_attribute"],
                    "focus_position": focus_position(r["focus_band"], r["focus_column"])})
    return out
