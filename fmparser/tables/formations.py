#!/usr/bin/env python3
"""`formations` — the game's 21 stock formations, each with the position of its 11 slots.

Between the rule files and the contract grid, straight in front of the
[team selections](team_selections.py), both games:

    21 x 1,262 B, no count, no frame; each opens with the u32 0x07f4b976

A record is the tactic layout the game also uses for the managed club's saved tactics and
for the tactic in each of our matches: the u32, the name (`4-4-2`, `4-4-2 Diamond`, `3-4-3
DM` …, 32 bytes, NUL-padded), then 11 u16 position codes, slot 0 the goalkeeper, then 1,204
bytes not read (repeated position codes, a run of 01 bytes, `[u16][u16]` grids). Staff records
index this list by position (`staff.formation_preferred`); FMM22 stores it in a different
order (4-4-2 first, FMM27 3-4-3 first).

**A position code** is a row bit in the low 7 bits (0x01 goalkeeper, 0x04 defence, 0x08
defensive midfield, 0x10 midfield, 0x20 attacking midfield, 0x40 attack) and one lane bit
in bits 7-11, five lanes across the pitch from right to left: 0x800 right, 0x400 inside
right, 0x200 centre, 0x100 inside left, 0x080 left. 4-4-2's back four is `0804` (DR), `0084`
(DL), `0404`, `0104`; a back three `0404`, `0204`, `0104`. Pinned on four teams' Tactics –
Formation screens (`tests/test_team_selections_evidence.py`). The game labels every inner
lane C (all three centre-backs "DC"), which is what `primitives.pitch_position` emits for the
match table's copies of these codes; the parser emits the codes as stored.

**How it is found.** The first `76 b9 f4 07` in the save, then records for as long as each
opens with it; the team selections' count follows the last one.
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..core import Field, FixedList, Record, TableDef, RAW, U16, U32, UNKNOWN
from ..save import cache_key as _cache_key

__all__ = ["FORMATION", "FORMATION_SLOTS", "FORMATIONS_TABLE", "MARKER", "STRIDE",
           "formations_table_spans", "locate_formations", "scrape_formations"]

MARKER = bytes.fromhex("76b9f407")
STRIDE = 1262
SLOTS = 11

FORMATION = Record("formation", 36, (
    Field(0, 4, UNKNOWN, U32, note="0x07f4b976 on every record, saved tactics too"),
    Field(4, 32, "name", RAW, note="NUL-padded latin-1"),
), is_head=True)

FORMATION_SLOT = Record("formation_slot", 2, (
    Field(0, 2, "position", U16, note="row bit (0-6) | lane bit (7-11)"),
))

FORMATION_TAIL = Record("formation_tail", STRIDE - FORMATION.span - SLOTS * 2, (
    Field(0, STRIDE - FORMATION.span - SLOTS * 2, UNKNOWN, RAW,
          note="the codes again, eleven 01 bytes, [u16][u16] grids"),
))

FORMATION_SLOTS = FixedList("slots", FORMATION_SLOT, SLOTS)

_CACHE: Dict[Any, Optional[Tuple[int, int]]] = {}


def locate_formations(mm: Any) -> Optional[Tuple[int, int]]:
    """(record 0, count), or None: the first marker, and every record after it that opens
    with the marker too."""
    key = _cache_key(mm)
    if key in _CACHE:
        return _CACHE[key]
    res = None
    base = mm.find(MARKER)
    if base != -1:
        n = 0
        while mm[base + n * STRIDE:base + n * STRIDE + 4] == MARKER:
            n += 1
        res = (base, n)
    _CACHE[key] = res
    return res


def formations_table_spans(mm: Any) -> List[Tuple[int, int]]:
    loc = locate_formations(mm)
    return [(loc[0], loc[0] + loc[1] * STRIDE)] if loc else []


FORMATIONS_TABLE = TableDef(name="formations",
                            segments=(FORMATION, FORMATION_SLOTS, FORMATION_TAIL),
                            locator=locate_formations)


def _name(mm: Any, o: int) -> str:
    raw = bytes(mm[o + 4:o + FORMATION.span])
    return raw.split(b"\0", 1)[0].decode("latin-1").strip()


def scrape_formations(mm: Any) -> List[Dict[str, Any]]:
    """Every formation in stored order: its index (what staff records hold), name and the 11
    position codes. Raises `ValueError` when not located."""
    loc = locate_formations(mm)
    if loc is None:
        raise ValueError("formations: no 76 b9 f4 07 record in the save")
    base, n = loc
    return [{"index": i, "name": _name(mm, base + i * STRIDE),
             "positions": list(struct.unpack_from(f"<{SLOTS}H", mm,
                                                  base + i * STRIDE + FORMATION.span))}
            for i in range(n)]
