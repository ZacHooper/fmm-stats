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

FMM27 stores fmm-editor's FMM26 `People` record (44,960 on Truro), framed the same way:

  [26 B]                                        PERSON_INFO_FMM27: tid .. nationality
  [u16 k][k x nation u16]                       other nationalities (FMM22: one slot)
  [42 B]                                        PERSON_REST_FMM27: as FMM22's head from
                                                ethnicity on, but caps and goals are i16
  [13 B]                                        PERSON_MID_FMM27: three u32 ids and a u8
  [5 B][2 B only if its i32 is -1]              PERSON_FLAG_FMM27, unnamed
  [u8 n][n x 3 B], [u8 n][n x 3 B]              default and other languages
  [u16 m][m x 8 B]                              relationships: the favoured clubs and people

`person_table(mm)` is the declaration for the save's format (`save_header.save_format`).
"""
from typing import Any, Dict, List, Optional, Tuple

from ..core import primitives as P
from ..save import cache_key as _cache_key
from ..core import (Conditional, CountedList, DATE, Field, HEX4, I16, I32, PAD, RAW, Record,
                    TableDef, U16, U32, U8, UNKNOWN, table_spans)
from .save_header import FMM27, save_format

__all__ = [
    "INFO_HEAD",
    "INFO_LAYOUT",
    "NO_CLUB",
    "PERSONALITY",
    "PERSON_FIELDS",
    "PERSON_INFO",
    "PERSON_INFO_TABLE",
    "PERSON_INFO_TABLE_FMM27",
    "PERSON_LANGUAGE",
    "PERSON_MID",
    "RELATIONSHIP",
    "locate_person_info",
    "person_table",
    "person_info_table_spans",
    "scrape_person_info",
    "scrape_players",
]

NO_CLUB = P.NO_ID16

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


def _record_end(table: TableDef, mm: Any, rec: int) -> Optional[int]:
    """Where the record at `rec` ends, read through the table's own segments; None if it
    overruns."""
    n, pos = len(mm), rec
    for seg in table.segments:
        if isinstance(seg, Record):
            pos += seg.span
            if pos > n:
                return None
        else:
            res = seg.read(mm, pos, n)
            if res is None:
                return None
            pos = res[1]
    return pos


_CHECK_ROWS = 3


def _is_table(table: TableDef, mm: Any, rec: int, count: int) -> bool:
    """The table's own invariant on its first rows: tid 0, 1, 2, each record ending where
    its counted lists say, so a stray `tid 0` cannot pass."""
    for slot in range(min(count, _CHECK_ROWS)):
        if rec is None or rec + 4 > len(mm) or \
                int.from_bytes(mm[rec:rec + 4], "little") != slot:
            return False
        rec = _record_end(table, mm, rec)
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
            if _is_table(person_table(mm), mm, p + 5, count):
                res = (p + 5, count)
        pos = p
    _PERSON_INFO_CACHE[key] = res
    return res


def _normalise(rec: Dict[str, Any]) -> Dict[str, Any]:
    """The spine's value rules: sentinels to None, an out-of-range club to NO_CLUB."""
    if rec.get("second_nationality_id") in (0, 0xFFFF):
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

# FMM27: fmm-editor's FMM26 `People` record. Offsets of PERSON_REST_FMM27 are from the end of
# the other-nationality list.
PERSON_INFO_FMM27 = Record("person_info_fmm27", 26, (
    Field(0, 4, "tid", U32),
    Field(4, 4, "uid", U32),
    Field(8, 4, "first_name_id", U32),
    Field(12, 4, "last_name_id", U32),
    Field(16, 4, "common_name_id", U32),
    Field(20, 4, "dob", DATE),
    Field(24, 2, "nationality_id", U16),
))

OTHER_NATIONALITY = Record("person_other_nationality", 2, (
    Field(0, 2, "nation_id", U16),
), is_head=True)

PERSON_REST_FMM27 = Record("person_rest_fmm27", 42, (
    Field(0, 1, "ethnicity", U8),
    Field(1, 4, UNKNOWN, RAW),
    Field(5, 1, "type_flag", U8),
    Field(6, 4, "unknown_date", DATE),
    Field(10, 2, "international_caps", I16),
    Field(12, 2, "international_goals", I16),
    Field(14, 1, "u21_caps", U8),
    Field(15, 1, "u21_goals", U8),
    Field(16, 4, "club_tid", U32),
    Field(20, 4, "joined_date", DATE),
    Field(24, 2, UNKNOWN, RAW),
    *(Field(26 + i, 1, n, U8) for i, n in enumerate(PERSONALITY)),
    Field(34, 4, "sid", HEX4),
    Field(38, 4, "id2", U32),
), is_head=True)

PERSON_MID_FMM27 = Record("person_mid_fmm27", 13, (
    Field(0, 4, UNKNOWN, U32),       # three ids, 0xffffffff on most people
    Field(4, 4, UNKNOWN, U32),
    Field(8, 4, UNKNOWN, U32),
    Field(12, 1, UNKNOWN, U8),
), is_head=True)

# Unnamed: a u8 and an i32, then a 2-byte tail only when the i32 is -1 (8,148 of 44,960 on
# Truro). The i32 is named only so the segment can test it.
PERSON_FLAG_FMM27 = Record("person_flag_fmm27", 5, (
    Field(0, 1, UNKNOWN, U8),
    Field(1, 4, "flag_i32", I32),
), is_head=True)

PERSON_FLAG_TAIL_FMM27 = Record("person_flag_tail_fmm27", 2, (
    Field(0, 2, UNKNOWN, I16),
), is_head=True)

PERSON_INFO_TABLE_FMM27 = TableDef(
    name="person_info",
    segments=(
        PERSON_INFO_FMM27,
        CountedList("other_nationality_ids", U16, OTHER_NATIONALITY, scalar=True, max_count=16),
        PERSON_REST_FMM27,
        PERSON_MID_FMM27,
        Conditional("flag", PERSON_FLAG_FMM27, PERSON_FLAG_TAIL_FMM27,
                    present=lambda head: head["flag_i32"] == -1),
        CountedList("default_languages", U8, PERSON_LANGUAGE, max_count=64),
        CountedList("other_languages", U8, PERSON_LANGUAGE, max_count=64),
        CountedList("relationships", U16, RELATIONSHIP, max_count=1024),
    ),
    locator=locate_person_info,
    invariant=lambda rec, slot: rec["tid"] == slot,
    post_process=lambda rec, off: _normalise(rec),
)


def person_table(mm: Any) -> TableDef:
    """The person table's declaration for this save's format."""
    return PERSON_INFO_TABLE_FMM27 if save_format(mm) == FMM27 else PERSON_INFO_TABLE


_SPINE = tuple(f.name for f in PERSON_INFO.fields if f.emits)
# FMM27's spine is its head as stored, in file order: the other nationalities are a list
_SPINE_FMM27 = (tuple(f.name for f in PERSON_INFO_FMM27.fields if f.emits)
                + ("other_nationality_ids",)
                + tuple(f.name for f in PERSON_REST_FMM27.fields if f.emits))


def person_info_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """[(start, end)]: the count frame and header byte, then every record."""
    loc = locate_person_info(mm)
    if not loc:
        return []
    (base, end), = table_spans(mm, person_table(mm), include_count_header=False)
    start = base - _HEADER - 4
    while start > 0 and mm[start - 1] == 0xFF:
        start -= 1
    return [(start, end)]


def _decode_info(mm: Any, base: int) -> Dict[str, Any]:
    """Decode one 68-byte head at `base` into the spine's identity dict."""
    return _normalise(PERSON_INFO.read(mm, base))


def scrape_person_info(mm: Any) -> Dict[int, Dict[str, Any]]:
    """The identity spine: {tid: head fields}, every person in the table."""
    table = person_table(mm)
    spine = _SPINE_FMM27 if table is PERSON_INFO_TABLE_FMM27 else _SPINE
    return {r["tid"]: {k: r[k] for k in spine} for r in table.scrape(mm)}


scrape_players = scrape_person_info
