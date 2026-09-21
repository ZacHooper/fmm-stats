#!/usr/bin/env python3
"""
Staff attribute records: coaching ability, reputation, the FORMATION TRIPLE and Style.

The info record carries TWO link fields, which is what BUGS #14 missed for four rounds:

    info +60  PlayerId -> the PLAYER attribute record (ffffffff for staff)
    info +64  ID2      -> the STAFF  attribute record   <-- this one

Staff records sit on the same 78-byte grid as player records but are a different layout; the
two validators are disjoint (0 of 2,315 staff-shaped records also validate as player records).

LAYOUT — the record is exactly 39 bytes, from the stride between consecutive records
(3,896 of 4,209 gaps; 4,657 of 5,097 on the Turkish save, rest are multiples):

    +0  id2 u32 | +4 ca u16 | +6 pa u16 | +8/+10/+12 home/current/world reputation u16
    +14..+30    17 attribute bytes (1-20) -- 10 displayed, 7 hidden
    +31..+33    formation triple: preferred / attacking / defensive, catalog indices
                (60% of managers carry the SAME shape in all three -- an unremarkable
                default, not a parser fault)
    +34..+38    5 catalog indices, UNDECODED

Knowing the extent is what solved Style: there is nowhere left in 39 bytes for a 3-valued
enum, so Style must be derived. It is a banding of `+14` (`attacking_intent`), one of the
seven hidden attributes.

WHY `+14` IS NOT AN n=7 FALSE POSITIVE. It orders the 7 ground-truth managers correctly, which
on its own is worth nothing — BUGS #14's `-140` candidate did exactly that and was noise. It
was confirmed on four independent cuts, none of which could be fitted after the fact:
  1. managers BUGS #14 Round 3 had ALREADY labelled attacking land in the top 15% (p < 1e-3);
  2. controlling for quality, the top 20 by world reputation orders Klopp/Nagelsmann high and
     Simeone/Mourinho lowest of the twenty;
  3. cross-career — the same people carry the same values on the Turkish save;
  4. both band edges were PREDICTED for 7 managers off frem-2026-07-02 and then read in game,
     7/7 correct. This is what killed the attractive cut-at-11 reading.
A rival `+14 - +20` also fits the 7 and is REJECTED: out of sample it calls Mourinho attacking.

**The numbers behind all four are in `tests/test_staff_records.py`, as data rather than
prose** — they are executable there and cannot rot. The hunt's history is BUGS #14.

`style()` bands in thirds: <=7 Defensive, 8-13 Normal, >=14 Attacking — 26/45/30% of 1,278
real club managers.

`+34..+38` is real structure, not padding: a 15-value index space DISJOINT from the formation
triple's, mutually independent (~9% pairwise agreement vs ~7% chance) and independent of the
triple (~5%). Naming it needs ground truth we lack. Job Status is unlocated and out of scope.

CA/PA are read because the record carries them, and fall under the same immersion rule as
players': never surfaced. `reputation_tier` is the safe derivative.
"""
import struct

import numpy as np

from . import primitives as P
from . import records as RD
from .save import cache_key as _cache_key
from .schemas.staff import (
    FORMATION_SLOTS,
    HIDDEN_OFFSETS,
    STAFF,
    STAFF_ATTRS,
    STAFF_FORMATION_SLOTS,
    STAFF_GRID_STRIDE,
    STAFF_HIDDEN_OFFSETS,
    STAFF_STRIDE,
    _STYLE_BANDS,
    _TIER_BANDS,
    reputation_tier,
    style,
)
from .tables import STAFF_TABLE

_ATTRS = STAFF_ATTRS

# Everything a staff record contributes downstream, named once so extract.py, the loader and
# the mart cannot drift apart. `ca`/`pa` ride along (the record carries them) and are subject
# to the same immersion rule as players': never surfaced. `reputation_tier` is the safe
# derivative to show instead.
STAFF_FIELDS = (("ca", "pa", "home_reputation", "current_reputation", "world_reputation",
                 "reputation_tier")
                + tuple(_ATTRS.values()) + tuple(HIDDEN_OFFSETS.values())
                + tuple(FORMATION_SLOTS.values()) + ("style",))

RECORD = STAFF_GRID_STRIDE  # same grid as the player attribute record (78B)
_CATALOG_MARKER = bytes.fromhex("76b9f407")
_CATALOG_STRIDE = 1262

# Style and reputation bands are declared in schemas/staff.py



def formation_catalog(mm):
    """The 21 formation templates in declaration order -> ['4-4-2', '4-4-2 Diamond', ...].

    Located structurally: the marker also appears on every match record's formation string,
    so we take the longest run of marker hits spaced exactly one record apart rather than
    trusting an absolute offset (which drifts per save and per career).
    """
    hits, pos = [], 0
    while True:
        j = mm.find(_CATALOG_MARKER, pos)
        if j == -1:
            break
        hits.append(j)
        pos = j + 1
    best, run = [], []
    for h in hits:
        if run and h - run[-1] == _CATALOG_STRIDE:
            run.append(h)
        else:
            run = [h]
        if len(run) > len(best):
            best = list(run)
    names = []
    for h in best:
        raw = mm[h + 4:h + 4 + 32].split(b"\x00")[0]
        try:
            names.append(raw.decode("utf-8"))
        except UnicodeDecodeError:
            names.append(None)
    return names


def _valid(mm, o, n):
    """Structural validation of a staff record at `o`."""
    if o < 0 or o + 40 > n:
        return False
    ca = int.from_bytes(mm[o + 4:o + 6], "little")
    pa = int.from_bytes(mm[o + 6:o + 8], "little")
    if not (0 < ca <= pa <= 200):
        return False
    for d in (*_ATTRS, *HIDDEN_OFFSETS):
        if not (1 <= mm[o + d] <= 20):
            return False
    return all(mm[o + d] < 21 for d in FORMATION_SLOTS)


def _candidates(mm):
    """Offsets whose bytes satisfy the staff-record shape, as a numpy array.

    Vectorised so the whole file is testable at once: the table's location is DISCOVERED
    rather than hard-coded, because every window in regions.py drifts per save and per career
    (CLAUDE.md's region-first rule). This over-counts -- it tests every byte offset instead of
    walking the grid, so a shifted neighbour of a real record can also pass -- which is why
    every candidate is re-validated and keyed by id before use.
    """
    a = np.frombuffer(mm, dtype=np.uint8)
    n = a.size - 40
    if n <= 0:
        return np.empty(0, dtype=np.int64)
    u16 = lambda d: (a[d:n + d].astype(np.uint32)
                     | (a[d + 1:n + d + 1].astype(np.uint32) << 8))
    ca, pa = u16(4), u16(6)
    m = (ca > 0) & (ca <= pa) & (pa <= 200)
    for d in (*_ATTRS, *HIDDEN_OFFSETS):
        v = a[d:n + d]
        m &= (v >= 1) & (v <= 20)
    for d in FORMATION_SLOTS:
        m &= a[d:n + d] < 21
    return np.flatnonzero(m)


def _discover_window(mm, margin=50_000):
    """(lo, hi) around the densest cluster of staff-shaped records."""
    idx = _candidates(mm)
    if idx.size == 0:
        return 0, 0
    breaks = np.flatnonzero(np.diff(idx) > 200_000)
    starts = np.concatenate(([0], breaks + 1))
    ends = np.concatenate((breaks, [idx.size - 1]))
    s, e = max(zip(starts, ends), key=lambda se: se[1] - se[0])
    return max(0, int(idx[s]) - margin), int(idx[e]) + margin


def _parse(mm, o):
    """One staff record, read FROM the declaration.

    Seeded with `id2` and `offset` so `offset` keeps its place as the second key -- `id2` is
    then overwritten with the same value by `read_into`, which costs one read and means the
    declaration stays the only place a field's position is stated.

    `reputation_tier` and `style` are appended afterwards because they are DERIVED labels, not
    fields: the save stores a reputation number and a 1-20 attribute, and the bands that turn
    those into words are a judgement with evidence behind it (see the module docstring and
    `tests/test_staff_records.py`). A layout cannot express that, and should not pretend to.
    """
    rec = RD.read_into({"id2": P.u32(mm, o), "offset": o}, mm, STAFF, o)
    rec["reputation_tier"] = reputation_tier(rec["world_reputation"])
    rec["style"] = style(rec["attacking_intent"])
    return rec


STAFF_STRIDE = 39
_STAFF_FRAME = 12          # [8 x 0xFF][count u32] in front of record 0
_STAFF_TABLE_CACHE = {}


def staff_table(mm):
    """(base, declared_count) for the staff attribute grid, or None."""
    return STAFF_TABLE.locator(mm)


def scrape_staff_attributes(mm, id2s, lo=None, hi=None):
    """{id2: record} for each id in `id2s` that has a staff attribute record."""
    wanted = {i for i in id2s if i not in (None, 0, 0xFFFFFFFF)}
    if not wanted:
        return {}
    all_staff = STAFF_TABLE.id_map(mm, key_field="id2")
    if lo is None and hi is None:
        return {i: all_staff[i] for i in wanted if i in all_staff}
    return {i: all_staff[i] for i in wanted if i in all_staff and lo <= all_staff[i]["offset"] < hi}


