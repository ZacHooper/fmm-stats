#!/usr/bin/env python3
"""`tactic_history` — tactic setups the game has recorded for the user: a name, and a role
for every position. Not tactics the user saved (the Truro career has none).

Straight after the person stamps (`person_stamps.py`), in a block that belongs to the
user's club:

    60 B                                  unread (a money-sized u64 at +40)
    [u32 n][n x 14 B]                     n people, each [tid u32] + 10 bytes, unread:
                                          6 on frem-2026-06-11, 3 on Bucaspor, 0 on Truro
    [u16 count][count x 59 B]             the records: 1 on a career's first save, 5 then
                                          15 as Truro's first weeks are played, 30 on both
                                          frem-2026-06-11 and frem-2030-06-22 (a cap)

A record is `[gk_role u8][ff]`, then ten `[role u8][u8][ff]` slots for the outfield
positions in the formation's own order, then a 26-byte NUL-padded name and a flag byte, 0
or 1. Most names are formations (one record for each of 5-2-1-2, 4-4-2 Diamond, 5-1-2-2,
4-2-4, 4-1-2-1-2 on Truro); the rest are "uber tactic", in both careers, so a name the game
gives rather than one a user typed. On truro-2026-08-08 the "uber tactic" records carry the
roles of the user's 4-1-2-1-2 with small changes between them, and the last record is that
4-1-2-1-2: a history of setups, roughly one per formation picked plus snapshots as roles
change. On Frem, full at 30, the last record is not the formation Frem's matches use.

Truro's 4-1-2-1-2 holds 3, 3, 5, 5 for its DR, DL, DC, DC (Full-Back, Full-Back, Central
Defender, Central Defender, codes FMM27 keeps from FMM22); the midfield and attack codes are
FMM27's own, not yet pinned to a screen. The formation's positions are not in the record.

**How it is found.** At the person stamps' end, skip the 60-byte block and the counted
14-byte entries; the u16 there counts the records. The locator refuses it unless every
record reads: an `ff` after the goalkeeper's role and after every slot, a printable name
padded with NULs, a flag of 0 or 1.
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..core import Field, FixedList, Record, TableDef, RAW, U8, UNKNOWN
from ..save import cache_key as _cache_key

__all__ = ["ROLE_SLOT", "TACTIC_RECORD", "TACTIC_HISTORY_TABLE", "locate_tactic_history",
           "tactic_history_table_spans", "scrape_tactic_history"]

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
    Field(0,  26, "name", RAW, note="NUL-padded: a formation ('4-1-2-1-2') or 'uber tactic'"),
    Field(26, 1, "flag", U8, note="0 or 1"),
), is_head=True)

TACTIC_RECORD = (TACTIC_HEAD, FixedList("roles", ROLE_SLOT, 10), TACTIC_TAIL)
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


def locate_tactic_history(mm: Any) -> Optional[Tuple[int, int]]:
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


def tactic_history_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """The tactics, their u16 count included."""
    loc = locate_tactic_history(mm)
    return [(loc[0] - 2, loc[0] + loc[1] * STRIDE)] if loc else []


def _post(rec: Dict[str, Any], off: int) -> Dict[str, Any]:
    return {"name": rec["name"].split(b"\0")[0].decode("ascii"),
            "gk_role": rec["gk_role"],
            "roles": [slot["role"] for slot in rec["roles"]],
            "flag": rec["flag"]}


TACTIC_HISTORY_TABLE = TableDef(name="tactic_history", segments=TACTIC_RECORD,
                               locator=locate_tactic_history, post_process=_post)


def scrape_tactic_history(mm: Any) -> List[Dict[str, Any]]:
    """Every record, in stored order. Raises `ValueError` when not located."""
    loc = locate_tactic_history(mm)
    if loc is None:
        raise ValueError("tactic_history: the block after the person stamps does not read")
    rows = TACTIC_HISTORY_TABLE.scrape(mm)
    if len(rows) != loc[1]:
        raise ValueError(f"tactic_history: walk read {len(rows)} of {loc[1]} declared")
    return rows
