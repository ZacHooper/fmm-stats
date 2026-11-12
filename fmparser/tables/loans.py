#!/usr/bin/env python3
"""`loans` — every loan in the world: who, to which club, from when to when.

A pool of 25-byte slots after the contract grid, `[u16 0][u32 capacity]` in front:

    capacity     6,243 on every FMM22 save (Frem and Bucaspor), 6,637 on Truro
    used         1,962 on frem-2021-06-27, 2,312 on frem-2026-06-11, 3,010 on truro-2026-08-08

A used slot is one loan, `[tid u32][club u16][start][end][wage_pct][1][flag][u32][u32]`; its
person points back at it with `person_index.loan_slot`, and every used slot is pointed at by
exactly the person it names. An empty slot is always the same 25 bytes (`EMPTY`). The parent
club is the person's own `club_tid`; `club_tid` here is the club he is on loan at.

On frem-2026-06-11 the 11 Frem players the player progress table marks as out on loan are
the 11 with a slot whose parent is Frem or its reserves; the four slots whose `club_tid` is
Frem are the players on loan to Frem, from Granada and three reserve sides.

**How it is found.** The pool has no 0xFF frame, and on frem-2030-06-22 it does not start
where the contract grid's span ends, so it is found by its back-links: the first person
with a `loan_slot` gives a candidate base wherever his tid occurs after the contract grid,
and the base is accepted only if every linked person's slot holds his tid and every other
slot below the capacity is `EMPTY`.
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..core import DATE, Field, Record, TableDef, RAW, U8, U16, U32, UNKNOWN
from ..save import cache_key as _cache_key

__all__ = ["EMPTY", "LOAN", "LOANS_HEADER", "LOANS_TABLE", "loans_table_spans", "locate_loans",
           "scrape_loans"]

LOAN = Record("loan", 25, (
    Field(0,  4, "tid", U32, note="the player; ffffffff on an empty slot"),
    Field(4,  2, "club_tid", U16, note="the club he is on loan at"),
    Field(6,  4, "start", DATE),
    Field(10, 4, "end", DATE, note="the season's end on most loans"),
    Field(14, 1, "wage_pct", U8, note="the share of his wage the loan club pays, 0-100: the "
                                      "contract card's 'Loan 0% (£0 (p/a))'"),
    Field(15, 1, UNKNOWN, U8, note="1 on every slot (Roberts's card says 'Can be recalled')"),
    Field(16, 1, "option", U8, note="1 on a third of loans; the u32 after it is then "
                                    "money-sized (1,656 to 75,000,000)"),
    Field(17, 4, UNKNOWN, U32, note="with option 0: 0, or numbers like 1,508,051 that the "
                                    "transfer band also holds on loans and are not money"),
    Field(21, 4, UNKNOWN, RAW, note="0 on FMM22; 0 or ffffffff on FMM27"),
))

LOANS_HEADER = Record("loans_header", 6, (
    Field(0, 2, UNKNOWN, U16, note="0"),
    Field(2, 4, "capacity", U32, note="6,243 on FMM22, 6,637 on FMM27"),
))

EMPTY = bytes.fromhex("ffffffffffff0000b3070000b307000100ffffffffffffffff")

_CACHE: Dict[Any, Optional[Tuple[int, int]]] = {}


def _links(mm: Any) -> List[Tuple[int, int]]:
    from .person_index import scrape_person_index
    return [(t, r["loan_slot"]) for t, r in enumerate(scrape_person_index(mm))
            if r["loan_slot"] != 0xFFFF]


def locate_loans(mm: Any) -> Optional[Tuple[int, int]]:
    """(slot 0, capacity), or None: the base where every linked person's slot holds his tid
    and every other slot up to the capacity in front is `EMPTY`."""
    key = _cache_key(mm)
    if key in _CACHE:
        return _CACHE[key]
    from . import first_record, table_spans
    res = None
    links = _links(mm)
    lo = table_spans(mm, "contracts")[0][0]
    hi = first_record(mm, "surnames")
    if links and lo is not None and hi is not None:
        tid0, slot0 = links[0]
        hit = mm.find(struct.pack("<I", tid0), lo, hi)
        while hit != -1 and res is None:
            base = hit - slot0 * LOAN.span
            if base >= lo + LOANS_HEADER.span and all(
                    struct.unpack_from("<I", mm, base + s * LOAN.span)[0] == t for t, s in links):
                cap = struct.unpack_from("<I", mm, base - 4)[0]
                used = {s for _, s in links}
                if (max(used) < cap and base + cap * LOAN.span <= hi
                        and all(mm[base + s * LOAN.span:base + (s + 1) * LOAN.span] == EMPTY
                                for s in range(cap) if s not in used)):
                    res = (base, cap)
            hit = mm.find(struct.pack("<I", tid0), hit + 1, hi)
    _CACHE[key] = res
    return res


def loans_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """The pool, its 6-byte header included."""
    loc = locate_loans(mm)
    return [(loc[0] - LOANS_HEADER.span, loc[0] + loc[1] * LOAN.span)] if loc else []


def _slot(rec: Dict[str, Any], off: int) -> Optional[Dict[str, Any]]:
    return None if rec["tid"] == 0xFFFFFFFF else rec


LOANS_TABLE = TableDef(name="loans", segments=(LOAN,), locator=locate_loans,
                       header=LOANS_HEADER, include_offset=True, post_process=_slot)


def scrape_loans(mm: Any) -> List[Dict[str, Any]]:
    """Every used slot, in slot order, with its `slot` number. Raises `ValueError` when the
    pool is not located."""
    loc = locate_loans(mm)
    if loc is None:
        raise ValueError("loans: no slot pool after the contract grid that every "
                         "person_index.loan_slot points into")
    out = []
    for rec in LOANS_TABLE.scrape(mm):
        off = rec.pop("offset")
        out.append({"slot": (off - loc[0]) // LOAN.span, **rec})
    return out
