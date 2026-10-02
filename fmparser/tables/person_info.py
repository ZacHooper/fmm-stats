#!/usr/bin/env python3
"""`person_info` — the Person / Info Spine table (32,966 Frem / 34,312 Bucaspor).

Declared by `[8 x 0xFF][count u32]` at ~572 KB, then one header byte (`01` on every save),
then the records in tid order from 0 -- a career-constant pool, walked by declaration with
`tid == slot index` as the invariant. Each record:

  [68 B head]                                   PERSON_INFO: identity, club, personality
  [17 B]                                        PERSON_MID: four u32 ids (0xffffffff = none)
                                                and a 0/1 flag, unnamed
  [u8 n][n x (language_id u16, level u8)]       languages; level 0..10 (255 on 7%)
  [u16 m][m x 8 B]                              relationships: a club (kind 1) or a person
                                                (kind 3) this person is linked to
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..core import primitives as P
from ..save import cache_key as _cache_key
from ..core import (CountedList, DATE, Field, HEX4, PAD, RAW, Record, TableDef, U16, U32, U8,
                    UNKNOWN, table_spans)

__all__ = [
    "DOB_YEAR_HI",
    "DOB_YEAR_LO",
    "INFO_HEAD",
    "INFO_LAYOUT",
    "NAME_ID_MAX",
    "NO_CLUB",
    "NO_NICKNAME",
    "PERSONALITY",
    "PERSON_FIELDS",
    "PERSON_INFO",
    "PERSON_INFO_TABLE",
    "PERSON_LANGUAGE",
    "PERSON_MID",
    "RELATIONSHIP",
    "info_offset",
    "locate_person_info",
    "person_info_table_spans",
    "scrape_person_info",
    "scrape_players",
]

NO_CLUB = P.NO_ID16
NO_NICKNAME = b"\xff\xff\xff\xff"
DOB_YEAR_LO = 1955
DOB_YEAR_HI = 2030
NAME_ID_MAX = 65536

# The 8 personality bytes at info+52..59, in order.
PERSONALITY = (
    "adaptability",
    "ambition",
    "determination",
    "loyalty",
    "pressure",
    "professionalism",
    "sportsmanship",
    "temperament",
)

# Identity fields contributed by the INFO record
PERSON_FIELDS = PERSONALITY + (
    "international_caps",
    "international_goals",
    "u21_caps",
    "u21_goals",
    "joined_date",
    "second_nationality_id",
    "ethnicity",
)

# The INFO record fixed 68-byte head
PERSON_INFO = Record("person_info", 68, (
    Field(0, 4, "tid", U32),
    Field(4, 4, "uid", U32),
    Field(8, 4, "first_name_id", U32),
    Field(12, 4, "last_name_id", U32),
    Field(16, 4, "common_name_id", U32),
    Field(20, 4, "dob", DATE),
    Field(24, 2, "nationality_id", U16),
    Field(26, 2, "second_nationality_id", U16),
    Field(28, 1, "ethnicity", U8),
    Field(29, 4, UNKNOWN, RAW),
    Field(33, 1, "type_flag", U8),
    Field(34, 4, "unknown_date", DATE),
    Field(38, 1, "international_caps", U8),
    Field(39, 1, "international_goals", U8),
    Field(40, 1, "u21_caps", U8),
    Field(41, 1, "u21_goals", U8),
    Field(42, 4, "club_tid", U32),
    Field(46, 4, "joined_date", DATE),
    Field(50, 2, UNKNOWN, RAW),
    *(Field(52 + i, 1, n, U8) for i, n in enumerate(PERSONALITY)),
    Field(60, 4, "sid", HEX4),
    Field(64, 4, "id2", U32),
), is_head=True)

INFO_LAYOUT = PERSON_INFO
INFO_HEAD = PERSON_INFO.span

# Bytes +68..+84, between the head and the language list.
PERSON_MID = Record("person_mid", 17, (
    Field(0, 4, UNKNOWN, U32),       # four ids, 0xffffffff on 94-98% of people
    Field(4, 4, UNKNOWN, U32),
    Field(8, 4, UNKNOWN, U32),
    Field(12, 4, UNKNOWN, U32),
    Field(16, 1, UNKNOWN, U8),       # 0 / 1
), is_head=True)

PERSON_LANGUAGE = Record("person_language", 3, (
    Field(0, 2, "language_id", U16),
    Field(2, 1, "level", U8, note="0..10; 255 on 7%"),
), is_head=True)

RELATIONSHIP = Record("relationship", 8, (
    Field(0, 1, UNKNOWN, U8),        # 1..4
    Field(1, 1, "target_kind", U8, note="1 = club (tid < club count), 3 = person (tid)"),
    Field(2, 4, "target_id", U32, note="0xffffffff = none"),
    Field(6, 1, UNKNOWN, U8),
    Field(7, 1, UNKNOWN, U8),        # 50 / 100 / 75 / 60 / 90 ...
), is_head=True)

_HEADER = 1                         # the byte after the count, 01 on every save
_PERSON_INFO_CACHE: Dict[Any, Optional[Tuple[int, int]]] = {}


def _record_end(mm: Any, rec: int) -> Optional[int]:
    """Where the record at `rec` ends, from its two counted lists; None if it overruns."""
    n = len(mm)
    langs = rec + PERSON_INFO.span + PERSON_MID.span
    if langs >= n:
        return None
    rels = langs + 1 + 3 * mm[langs]
    if rels + 2 > n:
        return None
    end = rels + 2 + 8 * int.from_bytes(mm[rels:rels + 2], "little")
    return end if end <= n else None


_CHECK_ROWS = 3


def _is_table(mm: Any, rec: int, count: int) -> bool:
    """The table's own invariant on its first rows: tid 0, 1, 2, each record ending where
    its counted lists say, so a stray `tid 0` cannot pass."""
    for slot in range(min(count, _CHECK_ROWS)):
        if rec is None or rec + 4 > len(mm) or \
                int.from_bytes(mm[rec:rec + 4], "little") != slot:
            return False
        rec = _record_end(mm, rec)
    return count >= 1


def locate_person_info(mm: Any) -> Optional[Tuple[int, int]]:
    """(record 0, declared_count) for the person table, or None.

    The first `[>= 8 x 0xFF][count u32][01]` frame whose rows start tid 0, 1, 2 -- the
    table's own invariant, so no count range or file window is assumed.
    """
    key = _cache_key(mm)
    if key in _PERSON_INFO_CACHE:
        return _PERSON_INFO_CACHE[key]
    res, pos, n = None, 0, len(mm)
    while res is None:
        idx = mm.find(b"\xff" * 8, pos)
        if idx == -1:
            break
        p = idx + 8
        while p < n and mm[p] == 0xFF:
            p += 1
        if p + 5 <= n and mm[p + 4] == _HEADER:
            count = int.from_bytes(mm[p:p + 4], "little")
            if _is_table(mm, p + 5, count):
                res = (p + 5, count)
        pos = p
    _PERSON_INFO_CACHE[key] = res
    return res


def _normalise(rec: Dict[str, Any]) -> Dict[str, Any]:
    """The spine's value rules: sentinels to None, an out-of-range club to NO_CLUB."""
    if rec["second_nationality_id"] in (0, 0xFFFF):
        rec["second_nationality_id"] = None
    if rec["club_tid"] > 0xFFFF:
        rec["club_tid"] = NO_CLUB
    return rec


PERSON_INFO_TABLE = TableDef(
    name="person_info",
    segments=(
        PERSON_INFO,
        PERSON_MID,
        CountedList("languages", U8, PERSON_LANGUAGE, max_count=64),
        CountedList("relationships", U16, RELATIONSHIP, max_count=1024),
    ),
    locator=locate_person_info,
    invariant=lambda rec, slot: rec["tid"] == slot,
    post_process=lambda rec, off: _normalise(rec),
)

_SPINE = tuple(f.name for f in PERSON_INFO.fields if f.emits)


def person_info_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """[(start, end)]: the count frame and header byte, then every record."""
    loc = locate_person_info(mm)
    if not loc:
        return []
    (base, end), = table_spans(mm, PERSON_INFO_TABLE, include_count_header=False)
    start = base - _HEADER - 4
    while start > 0 and mm[start - 1] == 0xFF:
        start -= 1
    return [(start, end)]


def _decode_info(mm: Any, base: int) -> Dict[str, Any]:
    """Decode one 68-byte head at `base` into the spine's identity dict."""
    return _normalise(PERSON_INFO.read(mm, base))


def scrape_person_info(mm: Any) -> Dict[int, Dict[str, Any]]:
    """The identity spine: {tid: head fields}, every person in the table."""
    return {r["tid"]: {k: r[k] for k in _SPINE} for r in PERSON_INFO_TABLE.scrape(mm)}


scrape_players = scrape_person_info


def info_offset(mm: Any, tid: int) -> Optional[int]:
    """Offset of a player's info record, or None.

    Located by searching the file for the tid's bytes rather than walking the table, and
    validated on the nickname field at +16 -- the NO_NICKNAME sentinel or a plausible name id
    (below NAME_ID_MAX); the sentinel is not required, since a player who has a nickname
    carries a real id there -- and on a DOB year at +22 of 1955..2012. That year gate is
    narrower than the table walk's DOB_YEAR_LO..DOB_YEAR_HI: a player born after 2012 is not
    found here.
    """
    le = struct.pack("<I", tid)
    pos = 0
    while True:
        i = mm.find(le, pos)
        if i == -1:
            return None
        pos = i + 1
        nick = mm[i + 16:i + 20]
        if nick != NO_NICKNAME and int.from_bytes(nick, "little") >= NAME_ID_MAX:
            continue
        year = int.from_bytes(mm[i + 22:i + 24], "little")
        if 1955 <= year <= 2012:
            return i
