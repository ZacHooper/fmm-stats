#!/usr/bin/env python3
"""`player_status` — one block per player, straight after the club rows (`club_rows.py`):
the clubs interested in him, his morale and his form. FMM27 only so far.

    [count u32 = the player-attribute count]   36,344 on Truro
    per block, block k = attribute record k:
      35 B   head, 7 interested-club slots, morale, form (the last five ratings), flags
      22 / 46 B            STATUS_EVENT, only where the head's last byte is 1 (below)
      [n u8][n x 5 B]      STATUS_ITEM
      83 B   STATUS_TAIL   a u32, then a date reading 1 Jan 2000 on every block, then 60 B

The walk ends exactly on a u16 n followed by n 4-byte slots (1,706, all `ff` on the three
Truro saves), then more of the chain up to the rule files. Every block's tail date reads
`01 00 d0 07`, which the locator checks on each block: a walk that misreads one length
fails there, not at the end.

**Interested clubs.** Seven u16 club tids, `ffff` empty. Lewis Colwell's block on
truro-2026-07-25 names Salisbury and Oxford City, the two clubs his Player Contract screen
lists under Interested Clubs. 1,385 players have at least one. A few name their own club
(Haaland, Saka, Kimmich), not yet explained.

**Morale**, 1-20: the arrow beside each name on the Club Squad screen. Green from 15,
yellow 12-14, orange 10-11, red at 7 (Truro and Dorking Wanderers, 25 Jul 2026).

**Form**, five u8, the last five match ratings, most recent last, `ff` for no match: the
Club Squad screen's Form column, ten Truro players.

**The event.** About one block in a thousand (27 on 22 Jul, 68 on 8 Aug) carries a 22-byte
record, or a 46-byte one when its byte +21 is 1: two u16, `ffff`, a kind byte (0, 2 or 4),
a 2025/26 date, then kind-dependent bytes; the long form holds a second dated record. What
it records is open (a transfer or contract event, by its dates).

FMM22 stores the same block with a 6-byte head and the date last; its walk is not proved
(`docs/parser/unread/person_chain.md`).
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..core import (CountedList, DATE, Field, FixedList, Record, TableDef, RAW, U8, U16, U32,
                    UNKNOWN)
from ..save import cache_key as _cache_key
from .save_header import FMM27, save_format

__all__ = ["STATUS_HEAD", "MORALE", "FORM_SLOT", "STATUS_FLAGS", "CLUB_SLOT", "STATUS_EVENT", "STATUS_EVENT_LONG", "STATUS_ITEM", "STATUS_TAIL",
           "PLAYER_STATUS_TABLE", "locate_player_status", "player_status_table_spans",
           "scrape_player_status"]

NULL_DATE = b"\x01\x00\xd0\x07"
NONE16 = 0xFFFF
NO_MATCH = 0xFF

STATUS_HEAD = Record("player_status_head", 6, (
    Field(0, 5, UNKNOWN, RAW, note="0 on every block measured"),
    Field(5, 1, UNKNOWN, U8, note="0, 3 or 4"),
), is_head=True)

CLUB_SLOT = Record("player_status_club", 2, (
    Field(0, 2, "club_tid", U16, note="a club interested in him; ffff = empty"),
))

MORALE = Record("player_status_morale", 1, (
    Field(0, 1, "morale", U8, note="1-20: the Club Squad screen's arrow"),
), is_head=True)

FORM_SLOT = Record("player_status_form", 1, (
    Field(0, 1, "rating", U8, note="a match rating; ff = no match"),
))

STATUS_FLAGS = Record("player_status_flags", 9, (
    Field(0, 8, UNKNOWN, RAW, note="ff on every block measured"),
    Field(8, 1, "has_event", U8, note="1 when STATUS_EVENT follows"),
), is_head=True)

STATUS_EVENT = Record("player_status_event", 22, (
    Field(0, 2, UNKNOWN, U16, note="ffff, or a small number (19, 29, 40)"),
    Field(2, 2, UNKNOWN, U16, note="ffff, or 1-3"),
    Field(4, 2, UNKNOWN, U16, note="ffff, or a number like 1,461"),
    Field(6, 1, UNKNOWN, U8, note="0, 2 or 4: the event's kind"),
    Field(7, 2, UNKNOWN, RAW),
    Field(9, 4, UNKNOWN, DATE, note="a 2025/26 date"),
    Field(13, 7, UNKNOWN, RAW, note="05, then kind-dependent bytes"),
    Field(20, 1, UNKNOWN, U8, note="03 or ff in this form"),
    Field(21, 1, UNKNOWN, U8, note="0 in this form; 1 in the long form"),
))

STATUS_EVENT_LONG = Record("player_status_event_long", 46, (
    Field(0, 20, UNKNOWN, RAW, note="as STATUS_EVENT's first 20 bytes"),
    Field(20, 1, UNKNOWN, U8, note="2 or 3"),
    Field(21, 1, UNKNOWN, U8, note="1 in this form"),
    Field(22, 1, UNKNOWN, U8),
    Field(23, 4, UNKNOWN, DATE, note="a second 2025/26 date"),
    Field(27, 19, UNKNOWN, RAW, note="u32s, then ffffffff"),
))

STATUS_ITEM = Record("player_status_item", 5, (
    Field(0, 1, UNKNOWN, U8, note="0 on every item measured"),
    Field(1, 1, UNKNOWN, U8, note="small, 22-40 on most items"),
    Field(2, 1, UNKNOWN, U8, note="0"),
    Field(3, 1, UNKNOWN, U8, note="small"),
    Field(4, 1, UNKNOWN, U8, note="small"),
))

STATUS_TAIL = Record("player_status_tail", 83, (
    Field(0, 4, UNKNOWN, U32, note="0 to millions; 18,225 on two Truro players"),
    Field(4, 15, UNKNOWN, RAW, note="mostly 0"),
    Field(19, 4, UNKNOWN, DATE, note="1 Jan 2000 (01 00 d0 07) on every block measured"),
    Field(23, 60, UNKNOWN, RAW, note="a byte, a 2026 date, then dates reading 1971 and zeros"),
))


class Event:
    """The optional event record: none, or 22 / 46 bytes as its byte +21 says."""
    name = "event"

    def _record(self, mm: Any, offset: int) -> Optional[Record]:
        if not mm[offset - 1]:
            return None
        return STATUS_EVENT_LONG if mm[offset + 21] == 1 else STATUS_EVENT

    def read(self, mm: Any, offset: int, limit: int) -> Optional[Tuple[Dict[str, Any], int]]:
        rec = self._record(mm, offset)
        end = offset + (rec.span if rec else 0)
        return (None, end) if end > limit else ({}, end)

    def instances(self, mm: Any, offset: int) -> List[Tuple[Record, int]]:
        rec = self._record(mm, offset)
        return [(rec, offset)] if rec else []


SEGMENTS = (STATUS_HEAD, FixedList("interested", CLUB_SLOT, 7), MORALE,
            FixedList("form", FORM_SLOT, 5), STATUS_FLAGS, Event(),
            CountedList("items", U8, STATUS_ITEM, max_count=16), STATUS_TAIL)
EVENT_AT = STATUS_HEAD.span + 7 * CLUB_SLOT.span + MORALE.span + 5 + STATUS_FLAGS.span

_CACHE: Dict[Any, Optional[Tuple[int, int, int]]] = {}


def _block_end(mm: Any, pos: int) -> Optional[int]:
    """Where the block at `pos` ends, or None when its tail date is not 1 Jan 2000."""
    p = pos + EVENT_AT
    if mm[p - 1]:
        if mm[p - 1] != 1:
            return None
        p += STATUS_EVENT_LONG.span if mm[p + 21] == 1 else STATUS_EVENT.span
    p += 1 + mm[p] * STATUS_ITEM.span
    if mm[p + 19:p + 23] != NULL_DATE:
        return None
    return p + STATUS_TAIL.span


def locate_player_status(mm: Any) -> Optional[Tuple[int, int]]:
    """(block 0, count) on FMM27: a u32 equal to the player-attribute count where the club rows
    end, whose blocks each end on the null date and together end on a u16-counted run of
    4-byte slots before the rule files. None otherwise, and on FMM22."""
    key = _cache_key(mm)
    if key in _CACHE:
        loc = _CACHE[key]
        return loc[:2] if loc else None
    res = None
    if save_format(mm) == FMM27:
        from . import first_record
        from .club_rows import club_rows_table_spans
        from .player_attributes import locate_player_attributes
        spans, players = club_rows_table_spans(mm), locate_player_attributes(mm)
        rules = first_record(mm, "rule_files")
        if spans and players and rules:
            at = spans[0][1]
            count = struct.unpack_from("<I", mm, at)[0]
            pos = at + 4 if count == players[1] else None
            for _ in range(count if pos else 0):
                pos = _block_end(mm, pos)
                if pos is None or pos > rules:
                    break
            if pos is not None and pos + 2 <= rules:
                n = struct.unpack_from("<H", mm, pos)[0]
                if pos + 2 + 4 * n <= rules:
                    res = (at + 4, count, pos)
    _CACHE[key] = res
    return res[:2] if res else None


def player_status_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """The blocks, their u32 count included."""
    if locate_player_status(mm) is None:
        return []
    base, _, end = _CACHE[_cache_key(mm)]
    return [(base - 4, end)]


def _post(rec: Dict[str, Any], off: int) -> Dict[str, Any]:
    return {"interested_club_tids": [c["club_tid"] for c in rec["interested"]
                                     if c["club_tid"] != NONE16],
            "morale": rec["morale"],
            "form": [None if f["rating"] == NO_MATCH else f["rating"] for f in rec["form"]]}


PLAYER_STATUS_TABLE = TableDef(name="player_status", segments=SEGMENTS,
                               locator=locate_player_status, post_process=_post)


def scrape_player_status(mm: Any) -> List[Dict[str, Any]]:
    """Every block, block k for attribute record k. Raises `ValueError` when not located."""
    loc = locate_player_status(mm)
    if loc is None:
        raise ValueError("player_status: no player-count block after the club rows whose "
                         "every block ends on the null date")
    out = PLAYER_STATUS_TABLE.scrape(mm)
    if len(out) != loc[1]:
        raise ValueError(f"player_status: walk read {len(out)} of {loc[1]} blocks")
    return out
