#!/usr/bin/env python3
"""`staff_attributes` — the 39-byte Staff Attributes table.

Located on a 39-byte dense index grid (`id2 == slot_index`).
Declared by a `[>= 8 x 0xFF][count u32]` frame (4,642 on Frem, 5,697 on Bucaspor).
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..save import cache_key as _cache_key
from ..schema import Field, Record, U16, U32, U8, UNKNOWN
from .engine import FixedTableDef

__all__ = [
    "FORMATION_SLOTS",
    "HIDDEN_OFFSETS",
    "STAFF",
    "STAFF_ATTRS",
    "STAFF_FIELDS",
    "STAFF_FORMATION_SLOTS",
    "STAFF_GRID_STRIDE",
    "STAFF_HIDDEN_OFFSETS",
    "STAFF_STRIDE",
    "STAFF_TABLE",
    "formation_catalog",
    "locate_staff",
    "reputation_tier",
    "scrape_staff_attributes",
    "staff_table",
    "style",
]

STAFF_STRIDE = 39
STAFF_GRID_STRIDE = 78

STAFF_ATTRS = {
    14: "attacking_intent",
    15: "financial_control",
    16: "outfield_coaching",
    17: "goalkeeping_coaching",
    19: "discipline",
    21: "judging_ability",
    22: "judging_potential",
    23: "people_management",
    25: "motivating",
    29: "tactical_knowledge",
    30: "youth_coaching",
}

STAFF_HIDDEN_OFFSETS = {
    18: "hidden_s18",
    20: "hidden_s20",
    24: "hidden_s24",
    26: "hidden_s26",
    27: "hidden_s27",
    28: "hidden_s28",
}

STAFF_FORMATION_SLOTS = {
    31: "formation_preferred",
    32: "formation_attacking",
    33: "formation_defensive",
}

FORMATION_SLOTS = STAFF_FORMATION_SLOTS
HIDDEN_OFFSETS = STAFF_HIDDEN_OFFSETS
_ATTRS = STAFF_ATTRS

STAFF = Record("staff_attribute", STAFF_STRIDE, [
    Field(0,  4, "id2", U32, note="the info record's +64 link"),
    Field(4,  2, "ca", U16, note="never surfaced -- immersion rule"),
    Field(6,  2, "pa", U16, note="never surfaced -- immersion rule"),
    Field(8,  2, "home_reputation", U16),
    Field(10, 2, "current_reputation", U16),
    Field(12, 2, "world_reputation", U16),
    *[Field(o, 1, n, U8, group="attrs") for o, n in STAFF_ATTRS.items()],
    *[Field(o, 1, n, U8, group="hidden") for o, n in STAFF_HIDDEN_OFFSETS.items()],
    *[Field(o, 1, n, U8, group="formation") for o, n in STAFF_FORMATION_SLOTS.items()],
    *[Field(o, 1, UNKNOWN, U8)
      for o in range(14, 31) if o not in {**STAFF_ATTRS, **STAFF_HIDDEN_OFFSETS}],
    *[Field(o, 1, UNKNOWN, U8) for o in range(34, 39)],   # five catalog indices, undecoded
])

STAFF_FIELDS = (("ca", "pa", "home_reputation", "current_reputation", "world_reputation",
                 "reputation_tier")
                + tuple(_ATTRS.values()) + tuple(HIDDEN_OFFSETS.values())
                + tuple(FORMATION_SLOTS.values()) + ("style",))

_TIER_BANDS = ((3000, "Regional"), (5800, "National"), (10**9, "Continental"))
_STYLE_BANDS = ((7, "Defensive"), (13, "Normal"), (20, "Attacking"))


def style(attacking_intent: Optional[int]) -> Optional[str]:
    """Displayed manager Style from `attacking_intent`, or None. DERIVED, not stored."""
    if attacking_intent is None:
        return None
    for ceiling, label in _STYLE_BANDS:
        if attacking_intent <= ceiling:
            return label
    return None


def reputation_tier(world_rep: Optional[int]) -> Optional[str]:
    """Displayed manager reputation tier from `world_reputation`, or None."""
    if world_rep is None:
        return None
    for ceiling, label in _TIER_BANDS:
        if world_rep < ceiling:
            return label
    return None


_CATALOG_MARKER = bytes.fromhex("76b9f407")
_CATALOG_STRIDE = 1262


def formation_catalog(mm: Any) -> List[str]:
    """The 21 formation templates in declaration order -> ['4-4-2', '4-4-2 Diamond', ...]."""
    pos = mm.find(_CATALOG_MARKER)
    if pos == -1:
        return []
    start = pos - 16
    names = []
    for i in range(21):
        o = start + i * _CATALOG_STRIDE
        raw = mm[o + 20:o + 70]
        end = raw.find(b"\x00")
        chunk = raw[:end] if end != -1 else raw
        try:
            names.append(chunk.decode("latin-1").strip())
        except UnicodeDecodeError:
            names.append(f"Formation {i}")
    return names


_STAFF_CACHE: Dict[str, Optional[Tuple[int, int]]] = {}


def _candidates_staff(mm: Any) -> np.ndarray:
    a = np.frombuffer(mm, dtype=np.uint8)
    n = a.size - STAFF_STRIDE
    m = np.ones(n, dtype=bool)
    for d in STAFF_ATTRS:
        v = a[d:n + d]
        m &= (v >= 1) & (v <= 20)
    for d in FORMATION_SLOTS:
        m &= a[d:n + d] < 21
    return np.flatnonzero(m)


def _valid_staff(mm: Any, o: int, n: int) -> bool:
    if o + STAFF_STRIDE > n:
        return False
    ca = int.from_bytes(mm[o + 4:o + 6], "little")
    pa = int.from_bytes(mm[o + 6:o + 8], "little")
    if not (0 <= ca <= pa <= 200):
        return False
    for d in STAFF_ATTRS:
        if not (1 <= mm[o + d] <= 20):
            return False
    for d in FORMATION_SLOTS:
        if mm[o + d] >= 21:
            return False
    return True


def locate_staff(mm: Any) -> Optional[Tuple[int, int]]:
    """(base, declared_count) for the 39-byte staff attributes table, or None."""
    key = _cache_key(mm)
    if key in _STAFF_CACHE:
        return _STAFF_CACHE[key]
    n = len(mm)
    for o in _candidates_staff(mm).tolist()[:4000]:
        if not _valid_staff(mm, o, n):
            continue
        k = int.from_bytes(mm[o:o + 4], "little")
        if not (0 <= k < 1_000_000):
            continue
        base = o - k * STAFF_STRIDE
        if base < 12:
            continue
        if not all(mm[base - 4 - 1 - j] == 0xFF for j in range(8)):
            continue
        count = int.from_bytes(mm[base - 4:base], "little")
        if not (0 < count < 1_000_000) or k >= count:
            continue
        if base + count * STAFF_STRIDE > n:
            continue
        if all(int.from_bytes(mm[base + j * STAFF_STRIDE:base + j * STAFF_STRIDE + 4], "little") == j
               for j in range(min(count, 50))):
            res = (base, count)
            _STAFF_CACHE[key] = res
            return res
    _STAFF_CACHE[key] = None
    return None


staff_table = locate_staff


def _process_staff(rec: Dict[str, Any], offset: int) -> Optional[Dict[str, Any]]:
    ca, pa = rec.get("ca", 0), rec.get("pa", 0)
    if not (0 <= ca <= pa <= 200):
        return None
    for attr in STAFF_ATTRS.values():
        val = rec.get(attr, 0)
        if not (1 <= val <= 20):
            return None
    for fslot in FORMATION_SLOTS.values():
        if rec.get(fslot, 0) >= 21:
            return None

    row = {"id2": rec["id2"], "offset": offset}
    for f, v in rec.items():
        if f != "id2":
            row[f] = v
    row["reputation_tier"] = reputation_tier(rec["world_reputation"])
    row["style"] = style(rec["attacking_intent"])
    return row


STAFF_TABLE = FixedTableDef(
    name="staff_attributes",
    record_schema=STAFF,
    locator=locate_staff,
    include_offset=True,
    post_process=_process_staff,
)


def scrape_staff_attributes(mm: Any, id2s: Any, lo: Optional[int] = None, hi: Optional[int] = None) -> Dict[int, Dict[str, Any]]:
    """{id2: record} for each id in `id2s` that has a staff attribute record."""
    wanted = {i for i in id2s if i not in (None, 0, 0xFFFFFFFF)}
    if not wanted:
        return {}
    all_staff = STAFF_TABLE.id_map(mm, key_field="id2")
    if lo is None and hi is None:
        return {i: all_staff[i] for i in wanted if i in all_staff}
    return {i: all_staff[i] for i in wanted if i in all_staff and lo <= all_staff[i]["offset"] < hi}
