#!/usr/bin/env python3
"""`history` -- the career-history pool: every player's season-by-season club list.

A fixed pool of 16-byte records, allocated when the database is created and never resized
(265,423 in every Frem save, 295,648 on Bucaspor), after a u32 count:

    header  [count u32]
    record  +0  u8   season code: end_year = 1971 + code
            +1  u8   appearances
            +2  u8   goals (conceded, for a goalkeeper)
            +3  u8   assists
            +4  u8   unnamed; 0 on every record before the career, then 0..7, never above +1
            +5  u8   unnamed; the same, 0..26
            +6  u16  average rating x100 (0 before the career)
            +8  u16  club tid (0xffff = none)
            +10 u16  transfer fee code: ffff none, fffe loan, fffd / 0 free, else £000s
                     (`mart.transfers` reads it as the fee of the move AWAY from this club)
            +12 u32  NEXT RECORD INDEX in this record's chain; 0xFFFFFFFF ends the chain

One record is one line of the in-game Player History screen: a season, the club it was
played at and that season's numbers. A player's records are one chain, starting at the
record his attribute record points at (`history_head`, `tables/player_attributes.py`);
nothing in this table names a player. The first record is the debut line: the oldest season
the pool holds for him, at his origin club. A season played during the
career is appended into a recycled record anywhere in the pool, so a chain jumps.

The invariant is that the pointers form a forest -- every record on exactly one chain
(`core.forest`) -- checked on every record.

The 8 bytes after the last record (`21 04 81 00 xx 00 00 00` on every save) are not claimed:
they read as neither a record nor part of the club-records grid that follows.

What the parser emits is the pool as stored: every record, column-wise, and each player's
head. Reading a player's chain is done after the parse, over these records
(`load_duckdb.py`).
"""
import dataclasses
import struct
from collections import Counter
from typing import Any, Dict, Optional, Tuple

from ..core import Field, LinkedTableDef, Record, U8, U16, U32
from ..save import cache_key as _cache_key
from .player_attributes import PLAYER

__all__ = [
    "END",
    "HISTORY_HEADER",
    "HISTORY_ROW",
    "HISTORY_TABLE",
    "history_end",
    "history_heads",
    "locate_history",
    "scrape_history",
]

END = 0xFFFFFFFF

HISTORY_HEADER = Record("history_header", 4, [
    Field(0, 4, "count", U32, note="records in the pool"),
], is_head=True)

HISTORY_ROW = Record("history_row", 16, [
    Field(0,  1, "season",  U8,  note="end_year = 1971 + code"),
    Field(1,  1, "apps",    U8),
    Field(2,  1, "goals",   U8,  note="conceded, for a goalkeeper"),
    Field(3,  1, "assists", U8),
    Field(4,  1, "unk4",    U8,  note="0 before the career; never more than apps"),
    Field(5,  1, "unk5",    U8,  note="0 before the career; never more than apps"),
    Field(6,  2, "rating",  U16, note="average rating x100; 0 before the career"),
    Field(8,  2, "club",    U16, note="club tid; 0xffff = none"),
    Field(10, 2, "fee",     U16, note="ffff none, fffe loan, fffd / 0 free, else £000s"),
    Field(12, 4, "next",    U32, note="next record index in this chain; 0xFFFFFFFF ends it"),
])

_STRIDE = HISTORY_ROW.span
_NEXT_AT = HISTORY_ROW.field("next").offset
_CACHE: Dict[str, Optional[Tuple[int, int]]] = {}


def _base_votes(mm: Any) -> Dict[int, Tuple[int, int]]:
    """{base: (votes, reach)} for every base the pool could start at.

    A record still in its first position points at the one after it, so two neighbouring
    records k, k+1 hold k+1 and k+2 at `+12`, and fix the pool's base at `q - 12 - 16k` for
    the offset q of the first pointer. Any one such pair names a candidate; the true base is
    named by every record the game has not moved. `reach` is the highest record index the
    pairs naming a base point at: a pool starting there must hold at least `reach + 1`."""
    import numpy as np
    n = len(mm)
    votes: Counter = Counter()
    reach: Dict[int, int] = {}
    lag = _STRIDE // 4                           # the next row's pointer, in u32 steps
    for align in range(4):
        col = np.frombuffer(mm, dtype="<u4", offset=align, count=(n - align) // 4)
        v, w = col[:-lag], col[lag:]
        hit = np.flatnonzero((w - v == 1) & (v > 0) & (v < END - 1))
        base = align + 4 * hit - _NEXT_AT - _STRIDE * (v[hit].astype(np.int64) - 1)
        to = w[hit].astype(np.int64)
        keep = base >= HISTORY_HEADER.span
        base, to = base[keep], to[keep]
        order = np.argsort(base, kind="stable")
        base, to = base[order], to[order]
        ks, first, cs = np.unique(base, return_index=True, return_counts=True)
        if len(ks):
            top = np.maximum.reduceat(to, first)
            for k, c, t in zip(ks.tolist(), cs.tolist(), top.tolist()):
                votes[k] += c
                reach[k] = max(reach.get(k, 0), t)
        del col, v, w
    return {k: (c, reach[k]) for k, c in votes.items()}


def _pointers_fit(mm: Any, base: int, count: int) -> bool:
    """Every record's pointer is a record index or the end marker, and no record is pointed
    at twice: the forest check's cheap half, vectorised, run before the whole check."""
    import numpy as np
    nxt = np.frombuffer(mm, dtype="<u4", count=count * 4, offset=base)[_NEXT_AT // 4::4]
    live = nxt[nxt != END]
    ok = bool(len(live) == 0 or (live.max() < count
                                 and np.bincount(live, minlength=count).max() <= 1))
    del nxt, live
    return ok


def locate_history(mm: Any) -> Optional[Tuple[int, int]]:
    """(base, count) for the history pool, or None.

    Candidates come from `_base_votes`, most-named first. One is the pool when the count in
    front of it fits the file and holds every record the pairs naming it point at, and every
    one of its records' pointers passes the forest check."""
    key = _cache_key(mm)
    if key in _CACHE:
        return _CACHE[key]
    res = None
    for base, (_, reach) in sorted(_base_votes(mm).items(), key=lambda kv: -kv[1][0]):
        count = struct.unpack_from("<I", mm, base - HISTORY_HEADER.span)[0]
        if count <= reach or base + count * _STRIDE > len(mm):
            continue
        if not _pointers_fit(mm, base, count):
            continue
        probe = dataclasses.replace(HISTORY_TABLE, locator=lambda _mm, r=(base, count): r)
        if probe.check(mm).ok:
            res = (base, count)
            break
    _CACHE[key] = res
    return res


HISTORY_TABLE = LinkedTableDef(
    name="history",
    row=HISTORY_ROW,
    next_field="next",
    locator=locate_history,
    header=HISTORY_HEADER,
    end=END,
)


def history_heads(mm: Any, info: Dict[int, Dict[str, Any]],
                  attrs: Dict[str, Dict[str, Any]]) -> Dict[int, int]:
    """{tid: history_head} for every person with a player attribute record: the row his
    chain starts at, as stored. A head outside the pool (a player with no history yet) is
    emitted as stored too."""
    head = PLAYER.field("history_head")
    out = {}
    for tid, p in info.items():
        rec = attrs.get(p["sid"])
        if rec is not None:
            out[tid] = PLAYER.read_field(mm, head, rec["offset"])
    return out


def scrape_history(mm: Any, info: Dict[int, Dict[str, Any]],
                   attrs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """{base, count, header, rows, heads}: the whole pool column-wise, plus each player's
    head row. Raises `LinkedTableError` if the pool is not located or is not a forest."""
    out = HISTORY_TABLE.scrape(mm)
    out["heads"] = {str(t): h for t, h in history_heads(mm, info, attrs).items()}
    return out


def history_end(mm: Any) -> int:
    """The offset one past the pool's last row."""
    return HISTORY_TABLE.spans(mm)[-1][1]
