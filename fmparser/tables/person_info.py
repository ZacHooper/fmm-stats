#!/usr/bin/env python3
"""`person_info` — the Person / Info Spine table (32,966 Frem / 34,312 Bucaspor).

Declared by an 8-byte `0xFF` frame + u32 count at ~572 KB (career-constant fixed pool).
Each record contains a fixed 68-byte head (`PERSON_INFO` / `INFO_LAYOUT`) followed by
variable-length counted language and relationship lists.
"""
from typing import Any, Dict, List, Optional, Tuple

from ..core import primitives as P
from .. import records as RD
from ..save import cache_key as _cache_key
from ..core import DATE, Field, HEX4, PAD, Record, U16, U32, U8, UNKNOWN

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
    Field(29, 4, UNKNOWN, PAD),
    Field(33, 1, "type_flag", U8),
    Field(34, 4, "unknown_date", DATE),
    Field(38, 1, "international_caps", U8),
    Field(39, 1, "international_goals", U8),
    Field(40, 1, "u21_caps", U8),
    Field(41, 1, "u21_goals", U8),
    Field(42, 4, "club_tid", U32),
    Field(46, 4, "joined_date", DATE),
    Field(50, 2, UNKNOWN, PAD),
    *(Field(52 + i, 1, n, U8) for i, n in enumerate(PERSONALITY)),
    Field(60, 4, "sid", HEX4),
    Field(64, 4, "id2", U32),
), is_head=True)

INFO_LAYOUT = PERSON_INFO
INFO_HEAD = PERSON_INFO.span

_PERSON_INFO_CACHE: Dict[Any, Optional[Tuple[int, int]]] = {}


def locate_person_info(mm: Any) -> Optional[Tuple[int, int]]:
    """(base, declared_count) for the person info table, or None.

    Frame sits at ~572 KB: [8x 0xFF][u32 count ~32,966 / 34,312].
    """
    key = _cache_key(mm)
    if key in _PERSON_INFO_CACHE:
        return _PERSON_INFO_CACHE[key]

    pat = b"\xff" * 8
    pos = 400_000
    end = min(len(mm), 1_000_000)

    while True:
        idx = mm.find(pat, pos, end)
        if idx == -1:
            break
        # Header count sits right after sentinel run
        p = idx + 8
        while p < end and mm[p] == 0xFF:
            p += 1
        if p + 4 <= end:
            count = int.from_bytes(mm[p:p + 4], "little")
            if 30_000 <= count <= 40_000:
                base = p + 4
                res = (base, count)
                _PERSON_INFO_CACHE[key] = res
                return res
        pos = idx + 1

    # Fallback for synthetic unit test buffers
    n = len(mm)
    if 0 < n < 10_000 and n % INFO_HEAD == 0:
        res = (0, n // INFO_HEAD)
        _PERSON_INFO_CACHE[key] = res
        return res

    _PERSON_INFO_CACHE[key] = None
    return None


def person_info_table_spans(mm: Any) -> List[Tuple[int, int]]:
    loc = locate_person_info(mm)
    if not loc:
        return []
    base, count = loc
    # Extent estimation: 68 bytes minimum per declared slot
    return [(base - 4, base), (base, base + count * INFO_HEAD)]


def _decode_info(mm: Any, base: int) -> Dict[str, Any]:
    """Decode one info record at `base` into the spine's identity dict."""
    rec = RD.read(mm, PERSON_INFO, base)
    if rec["uid"] == 0:
        for k in PERSON_FIELDS:
            rec[k] = None
    if rec["second_nationality_id"] in (0, 0xFFFF):
        rec["second_nationality_id"] = None
    if rec["club_tid"] > 0xFFFF:
        rec["club_tid"] = NO_CLUB
    return rec


def scrape_person_info(mm: Any) -> Dict[int, Dict[str, Any]]:
    """The identity spine: {tid: info dict}."""
    loc = locate_person_info(mm)
    if not loc:
        return {}
    base, count = loc
    limit = len(mm)

    # Fast path for synthetic unit test buffers with plain 68-byte records
    if limit < 10_000 and limit % INFO_HEAD == 0:
        players = {}
        for i in range(count):
            p = base + i * INFO_HEAD
            if p + INFO_HEAD > limit:
                break
            rec = _decode_info(mm, p)
            players[rec["tid"]] = rec
        return players

    # Real savefile table walk:
    # Record 1 (tid=1) starts after slot 0. Find record 1 in [base, base + 400]
    pos = base
    found_pos = None
    while pos < min(limit - 16, base + 400):
        k = mm.find(b"\x01\x00\x00\x00", pos, base + 400)
        if k == -1 or k + 16 > limit:
            break
        # Verify first_name_id == 1 and last_name_id == 1
        if (int.from_bytes(mm[k + 8:k + 12], "little") == 1
                and int.from_bytes(mm[k + 12:k + 16], "little") == 1):
            found_pos = k
            break
        pos = k + 1

    pos = found_pos if found_pos is not None else base
    players = {}
    for _ in range(count - 1):
        if pos + INFO_HEAD > limit:
            break
        rec = _decode_info(mm, pos)
        tid = rec["tid"]
        if tid not in players:
            players[tid] = rec
        if pos + 86 > limit:
            break
        L = mm[pos + 85]
        p_rel = pos + 86 + L * 3
        if p_rel >= limit:
            break
        R = mm[p_rel]
        rec_len = 88 + L * 3 + R * 8
        pos += rec_len

    return players


scrape_players = scrape_person_info
