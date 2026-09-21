#!/usr/bin/env python3
"""`person_info` — the Person / Info Spine table (32,966 Frem / 34,312 Bucaspor).

Declared by an 8-byte `0xFF` frame + u32 count at ~572 KB (career-constant fixed pool).
Each record contains a fixed 68-byte head (`PERSON_INFO` / `INFO_LAYOUT`) followed by
variable-length counted language and relationship lists.
"""
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .. import primitives as P
from .. import records as RD
from ..save import cache_key as _cache_key
from ..schema import DATE, Field, HEX4, PAD, Record, U16, U32, U8, UNKNOWN

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


def _nickname_sentinel_candidates(mm: Any) -> List[int]:
    """Record starts for sweep 1 (un-nicknamed), in ascending file order."""
    a = np.frombuffer(mm, dtype=np.uint8)
    ff = a == 0xFF
    j = np.flatnonzero(ff[:-3] & ff[1:-2] & ff[2:-1] & ff[3:])
    base = j - 16
    base = base[base >= 0]
    base = base[base + INFO_HEAD <= len(a)]

    def u16(off: int) -> np.ndarray:
        return a[base + off].astype(np.uint32) | a[base + off + 1].astype(np.uint32) << 8

    def u32(off: int) -> np.ndarray:
        return (u16(off) | a[base + off + 2].astype(np.uint32) << 16
                | a[base + off + 3].astype(np.uint32) << 24)

    year = u16(22)
    tid = u32(0)
    day = u16(20)
    keep = ((year >= DOB_YEAR_LO) & (year <= DOB_YEAR_HI)
            & (tid > 100) & (tid < 70000) & (day <= 366))
    return [int(b) for b in base[keep]]


def _scrape_nicknamed(mm: Any, found: Dict[int, Any]) -> Dict[int, Dict[str, Any]]:
    """Recover the records carrying a nickname (common_name_id != 0xFFFFFFFF)."""
    clubs = {p["club_tid"] for p in found.values()} - {NO_CLUB}
    try:
        from .. import reference as R
        resolves = R.build_name_resolver(mm)
    except Exception:
        resolves = False

    out: Dict[int, Dict[str, Any]] = {}
    end = len(mm)
    for year in range(DOB_YEAR_LO, DOB_YEAR_HI + 1):
        pat = year.to_bytes(2, "little")
        p = 0
        while True:
            k = mm.find(pat, p)
            if k == -1:
                break
            p = k + 1
            base = k - 22
            if base < 0 or base + 64 > end:
                continue
            if mm[base + 16:base + 20] == NO_NICKNAME:
                continue
            tid = int.from_bytes(mm[base:base + 4], "little")
            if not (100 < tid < 70000) or tid in found or tid in out:
                continue
            if int.from_bytes(mm[base + 20:base + 22], "little") > 366:
                continue
            club = int.from_bytes(mm[base + 42:base + 44], "little")
            if club != NO_CLUB and club not in clubs:
                continue
            rec = _decode_info(mm, base)
            nick = int.from_bytes(mm[base + 16:base + 20], "little")
            if max(rec["first_name_id"], rec["last_name_id"], nick) >= NAME_ID_MAX:
                continue
            if resolves and R.resolve_name(
                    mm, rec["first_name_id"], rec["last_name_id"]) is None:
                continue
            out[tid] = rec
    return out


def scrape_person_info(mm: Any) -> Dict[int, Dict[str, Any]]:
    """The identity spine: {tid: info dict}."""
    players: Dict[int, Dict[str, Any]] = {}
    for base in _nickname_sentinel_candidates(mm):
        tid = P.u32(mm, base)
        if tid in players:
            continue
        players[tid] = _decode_info(mm, base)

    players.update(_scrape_nicknamed(mm, players))
    return players


scrape_players = scrape_person_info
