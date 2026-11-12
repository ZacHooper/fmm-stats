#!/usr/bin/env python3
"""`saved_tactics` — the user's saved tactics: a name, and a role for every position.

Straight after the person stamps (`person_stamps.py`), in a block that belongs to the
user's club:

    60 B                                  unread (a money-sized u64 at +40)
    [u32 n][n x 14 B]                     n people, each [tid u32] + 10 bytes, unread:
                                          6 on frem-2026-06-11, 3 on Bucaspor, 0 on Truro
    [u16 count][count x 59 B]             the saved tactics: 1 on a day-one save,
                                          15 on truro-2026-08-08, 30 on frem-2026-06-11

A tactic is `[gk_role u8][ff]`, then ten `[role u8][u8][ff]` slots for the outfield
positions in the formation's own order, then the name the user gave it (26 bytes,
NUL-padded, "4-1-2-1-2", "uber tactic") and a flag byte, 0 or 1. Truro's "4-1-2-1-2" holds
3, 3, 5, 5 for its DR, DL, DC, DC (Full-Back, Full-Back, Central Defender, Central
Defender, codes FMM27 keeps from FMM22); the midfield and attack codes are FMM27's own, not
yet pinned to a screen. The formation's positions are not in the record.

**How it is found.** At the person stamps' end, skip the 60-byte block and the counted
14-byte entries; the u16 there counts the tactics. The locator refuses it unless every
tactic reads: an `ff` after the goalkeeper's role and after every slot, a printable name
padded with NULs, a flag of 0 or 1.
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..core import Field, FixedList, Record, TableDef, RAW, U8, UNKNOWN
from ..save import cache_key as _cache_key

__all__ = ["ROLE_SLOT", "SAVED_TACTIC", "SAVED_TACTICS_TABLE", "locate_saved_tactics",
           "saved_tactics_table_spans", "scrape_saved_tactics"]

PREFIX = 60          # the unread block in front of the counted entries
PERSON_ENTRY = 14    # [tid u32] + 10 bytes, unread

ROLE_SLOT = Record("tactic_role_slot", 3, (
    Field(0, 1, "role", U8, note="the role code for this position"),
    Field(1, 1, UNKNOWN, U8, note="0 or 1"),
    Field(2, 1, UNKNOWN, RAW, note="ff on every slot"),
))

TACTIC_HEAD = Record("tactic_head", 2, (
    Field(0, 1, "gk_role", U8, note="0, Goalkeeper, on every tactic measured"),
    Field(1, 1, UNKNOWN, RAW, note="ff"),
), is_head=True)

TACTIC_TAIL = Record("tactic_tail", 27, (
    Field(0,  26, "name", RAW, note="the name the user gave it, NUL-padded"),
    Field(26, 1, "flag", U8, note="0 or 1"),
), is_head=True)

SAVED_TACTIC = (TACTIC_HEAD, FixedList("roles", ROLE_SLOT, 10), TACTIC_TAIL)
STRIDE = TACTIC_HEAD.span + 10 * ROLE_SLOT.span + TACTIC_TAIL.span

_CACHE: Dict[Any, Optional[Tuple[int, int]]] = {}


def _valid(rec: bytes) -> bool:
    if rec[1] != 0xFF or any(rec[2 + 3 * i + 2] != 0xFF for i in range(10)):
        return False
    name = rec[32:58]
    text = name.split(b"\0")[0]
    if not text or any(c < 32 or c > 126 for c in text) or any(name[len(text):]):
        return False
    return rec[58] in (0, 1)


def locate_saved_tactics(mm: Any) -> Optional[Tuple[int, int]]:
    """(tactic 0, count), or None when the block after the person stamps doesn't read."""
    key = _cache_key(mm)
    if key in _CACHE:
        return _CACHE[key]
    from .person_stamps import PERSON_STAMP, locate_person_stamps
    res = None
    stamps = locate_person_stamps(mm)
    if stamps is not None:
        at = stamps[0] + stamps[1] * PERSON_STAMP.span + PREFIX
        n = struct.unpack_from("<I", mm, at)[0]
        at += 4 + n * PERSON_ENTRY
        if n < 1000 and at + 2 <= len(mm):
            count = struct.unpack_from("<H", mm, at)[0]
            base = at + 2
            if 0 < count < 1000 and base + count * STRIDE <= len(mm) and all(
                    _valid(bytes(mm[base + k * STRIDE:base + (k + 1) * STRIDE]))
                    for k in range(count)):
                res = (base, count)
    _CACHE[key] = res
    return res


def saved_tactics_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """The tactics, their u16 count included."""
    loc = locate_saved_tactics(mm)
    return [(loc[0] - 2, loc[0] + loc[1] * STRIDE)] if loc else []


def _post(rec: Dict[str, Any], off: int) -> Dict[str, Any]:
    return {"name": rec["name"].split(b"\0")[0].decode("ascii"),
            "gk_role": rec["gk_role"],
            "roles": [slot["role"] for slot in rec["roles"]],
            "flag": rec["flag"]}


SAVED_TACTICS_TABLE = TableDef(name="saved_tactics", segments=SAVED_TACTIC,
                               locator=locate_saved_tactics, post_process=_post)


def scrape_saved_tactics(mm: Any) -> List[Dict[str, Any]]:
    """Every saved tactic, in stored order. Raises `ValueError` when not located."""
    loc = locate_saved_tactics(mm)
    if loc is None:
        raise ValueError("saved_tactics: the block after the person stamps does not read")
    rows = SAVED_TACTICS_TABLE.scrape(mm)
    if len(rows) != loc[1]:
        raise ValueError(f"saved_tactics: walk read {len(rows)} of {loc[1]} declared")
    return rows
