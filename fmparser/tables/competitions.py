#!/usr/bin/env python3
"""`competitions` — the competition table, 1,372 slots on Frem (1,371 on Bucaspor).

It follows the club table directly: `[0xFF x 6][count u16]`, then the records in cid order,
walked by declaration with `cid == slot index` (COMP_TABLE). 100 slots are blank: empty
names, a placeholder uid.
"""
from typing import Any, Dict, Optional, Tuple

from ..core import CountedList, Field, PAD, PString, Record, TableDef, U8, U16, U32, UNKNOWN
from ..save import cache_key as _cache_key
from .clubs import NAME_END, after_frame, clubs_end

# `type_id` (the byte immediately after the 3 name strings) is the REAL field; it is carried
# raw on every competition record and is what code should branch on (`type_id in (0, 1)` for a round-robin league).
#
# COMP_TYPES is a DISPLAY label for the handful of type_ids anchored against named, verified
# competitions, nothing more. It is not a closed enum and the parser does not validate
# against it: at minimum 3, 4, 5, 7, 10, 11, 12, 13, 14, 15, 21, 22, 23, 26, 28, 29, 30, 36,
# 37, 38, 39 are all real (Carabao Cup, FA Trophy, European Championship, Copa América,
# African Cup of Nations, national Super Cups, youth leagues, All-Star exhibitions), and
# every unlabelled value falls through to `type_N` rather than getting a guessed name.
# Naming a type_id requires the same sourcing as any other field -- an upstream definition
# or repeated ground truth -- not an inference from one competition that happened to carry
# it, which is why 21 ("continental_cup", read off a single chat observation) is NOT here.
# Calibrated on Turkey: top-flight league(0), league(228)/play-off(227)=1, cup(117)=2,
# reserve league(1370)=8, friendly(65)=9. 0 and 1 are BOTH round-robin leagues (0 = a
# nation's top flight, e.g. 3F Superliga / Bundesliga / Serie A; 1 = the divisions below it).
COMP_TYPES = {0: "league", 1: "league", 2: "cup", 8: "reserve_league", 9: "friendly"}
def locate_competitions(mm: Any) -> Optional[Tuple[int, int]]:
    """(record 0, declared count): the frame right after the club table, whose record 0 is
    cid 0."""
    loc = after_frame(mm, clubs_end(mm), 2)
    if loc is None or int.from_bytes(mm[loc[0]:loc[0] + 2], "little") != 0:
        return None
    return loc


COMP_HEAD = Record("comp_head", 6, (
    Field(0, 2, "cid", U16),
    Field(2, 4, "uid", U32),
), is_head=True)

COMP_TRAILER = Record("comp_trailer", 14, (
    Field(0,  1, "type", U8),
    Field(1,  2, "continent", U16),
    Field(3,  2, "nation", U16),
    Field(5,  2, "fg_colour", U16),
    Field(7,  2, "bg_colour", U16),
    Field(9,  2, "reputation", U16),
    Field(11, 1, "level", U8),
    Field(12, 2, "parent_cid", U16),
), is_head=True)

COMP_REF_ENTRY = Record("comp_ref_entry", 8, (
    Field(0, 4, "ref", U32),
    Field(4, 2, "season", U16),
    Field(6, 1, "ordinal", U8),
    Field(7, 1, UNKNOWN, PAD),
))

COMP_HISTORY_TAIL = Record("comp_history_tail", 21, (
    Field(0,  4, UNKNOWN, PAD),
    Field(4,  4, UNKNOWN, PAD),
    Field(8,  4, UNKNOWN, PAD),
    Field(12, 2, "season_0", U16),
    Field(14, 2, "season_1", U16),
    Field(16, 2, "season_2", U16),
    Field(18, 2, UNKNOWN, PAD),
    Field(20, 1, UNKNOWN, PAD),
), is_head=True)

# The competition table, 1,372 slots on Frem: `[cid u16][uid u32]`, three strings (a
# NAME_END byte after the long and short names, none after the code), the 14-byte trailer, a counted
# reference list and a 21-byte tail. A blank slot (100 of them) has empty names and the
# same shape, uid a `2,000,000,000 + n` placeholder.
#
# `refs` is `[u32 n][n x 8 B]`: the count's top three bytes are zero on all 46,641 slots in
# the archive (maximum 134). The list is an explicit entrant list for the 24 competitions
# that carry one: `ref > 0` is a club UID (resolve by uid, never tid -- 1,095 values also
# match an unrelated club's tid), `ref < 0` read signed is a national team, `-ref` its
# nation uid; 0xFFFFFFFF is an empty slot. MLS lists its 28 clubs, Copa Libertadores its
# entrants over two seasons with a domestic placing, Copa America CONMEBOL's ten nations.
COMP_TABLE = TableDef(
    name="competitions",
    segments=(
        COMP_HEAD,
        PString("name", allow_empty=True),
        NAME_END,
        PString("short", allow_empty=True),
        NAME_END,
        PString("code", allow_empty=True),
        COMP_TRAILER,
        CountedList("refs", U32, COMP_REF_ENTRY, max_count=4096),
        COMP_HISTORY_TAIL,
    ),
    locator=locate_competitions,
    invariant=lambda rec, slot: rec["cid"] == slot,
)


def _comp(row):
    """The competition dict for a named slot."""
    nation, parent = row["nation"], row["parent_cid"]
    return {"cid": row["cid"], "uid": row["uid"], "name": row["name"], "short": row["short"],
            "code": row["code"], "type": COMP_TYPES.get(row["type"], f"type_{row['type']}"),
            "type_id": row["type"], "nation_id": None if nation == 0xFFFF else nation,
            "reputation": row["reputation"], "level": row["level"],
            "parent_cid": None if parent == 0xFFFF else parent}


class CompTableError(Exception):
    """The competition table could not be located, or its walk did not read every slot it
    declares. Raised, never swallowed: a short read means the format changed -- go and read
    the bytes."""


_COMP_ROWS_CACHE: Dict[Any, list] = {}


def _comp_rows(mm: Any) -> list:
    """Every declared competition slot, blanks included, in cid order."""
    key = _cache_key(mm)
    if key not in _COMP_ROWS_CACHE:
        loc = locate_competitions(mm)
        if loc is None:
            raise CompTableError("competition table not found after the club table")
        rows = COMP_TABLE.scrape(mm)
        if len(rows) != loc[1]:
            raise CompTableError(f"competition table walk read {len(rows)} of {loc[1]} "
                                 f"declared slots (record 0 at {loc[0]})")
        _COMP_ROWS_CACHE[key] = rows
    return _COMP_ROWS_CACHE[key]


def scrape_competitions(mm: Any) -> Dict[int, Dict[str, Any]]:
    """{cid: competition} for every named slot (blank slots are left out)."""
    return {r["cid"]: _comp(r) for r in _comp_rows(mm) if r["name"]}


def comp_refs(mm: Any, cid: int) -> list:
    """[{ref, season, ordinal}] -- the competition's counted reference list (see COMP_TABLE),
    in file order. Empty for a blank slot, a competition with none, or a cid past the table."""
    rows = _comp_rows(mm)
    return rows[cid]["refs"] if 0 <= cid < len(rows) else []
