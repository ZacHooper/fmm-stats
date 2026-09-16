#!/usr/bin/env python3
"""
Staff attribute records: coaching ability, reputation, and the FORMATION TRIPLE.

This is the record BUGS #14 spent four rounds failing to find. The mistake was assuming a
manager's tactical data hung off his info record; it does not. There is a second,
separately-keyed table:

    info record  +60  PlayerId  -> the PLAYER attribute record (ffffffff for staff)
    info record  +64  ID2       -> the STAFF  attribute record   <-- this one

`+64` was carried in docs as "unexplained u32" (fmm-editor calls it `Unknown6b`). Anchoring
on it lands every one of the 7 ground-truth managers on a record whose bytes reproduce all
10 of their coaching attributes exactly. `data/rough-guide.md`'s "Editing managers / staff
attributes" section describes this record from the hex-editing side and is what pointed here.

Staff records share the 78-byte grid with player attribute records but are a different
layout, and the two validators are disjoint: sweeping the whole file, 0 of 2,315 staff-shaped
records also validate as player records.

**The formation triple.** `+31/+32/+33` are indices into the 21-entry formation catalog, and
they are the manager's preferred / attacking / defensive shapes — the same three fields
FM2026's in-game editor exposes. Evidence:
  * `+31` matches the in-game Manager Profile formation for all 7 ground-truth managers
    (Frederiksen 18 = 5-2-2-1, Machin 17 = 5-2-1-2, Marsch 0 = 4-4-2, ...);
  * across 3,224 staff records, 99.4% have all three bytes in [0,20] against a 57% base rate
    for three adjacent bytes in the same region;
  * 60% of managers carry the same shape in all three slots (an unremarkable default), and
    the variants are footballing-coherent - Thorup 4-1-2-2-1 / 4-2-3-1 attacking / 5-3-2
    defensive.

NOT in this record: Style (Attacking/Normal/Defensive) and Job Status. Style is not present
at any offset in -300..+400 as a byte, nibble or 2-bit field. One candidate at -140 was
rejected: it splits the 7 known managers perfectly but its values are 25/25/25/25 across
3,340 staff records, i.e. noise, and ~1 such false positive was expected from the number of
offsets tested.

CA/PA are read here because the record carries them, and are subject to the same immersion
rule as players': keep them out of anything surfaced. `reputation_tier` is the safe
derivative -- world reputation orders Regional < National < Continental cleanly on the
ground-truth set.
"""
import struct

import numpy as np

# Offsets relative to the record start (= the ID2 u32).
_ATTRS = {
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
# +14, +18, +20, +24, +26, +27, +28 are attribute-shaped (1-20) but have no ground truth
# behind them -- the Manager Profile screen shows 17 values and all 17 are accounted for by
# _ATTRS plus the personality block on the info record. Left unnamed rather than guessed.

FORMATION_SLOTS = {31: "formation_preferred",
                   32: "formation_attacking",
                   33: "formation_defensive"}

# Everything a staff record contributes downstream, named once so extract.py, the loader and
# the mart cannot drift apart. `ca`/`pa` ride along (the record carries them) and are subject
# to the same immersion rule as players': never surfaced. `reputation_tier` is the safe
# derivative to show instead.
STAFF_FIELDS = (("ca", "pa", "home_reputation", "current_reputation", "world_reputation",
                 "reputation_tier")
                + tuple(_ATTRS.values()) + tuple(FORMATION_SLOTS.values()))

RECORD = 78          # same grid as the player attribute record
_CATALOG_MARKER = bytes.fromhex("76b9f407")
_CATALOG_STRIDE = 1262

# World-reputation bands for the displayed tier. Derived from the 7 ground-truth managers
# (Regional 1387/2278, National 5309-5736, Continental 5974) -- the boundaries sit in the
# gaps, so this is a DERIVED label, not a field the save asserts. Widen it if a manager ever
# lands on the wrong side.
_TIER_BANDS = ((3000, "Regional"), (5800, "National"), (10**9, "Continental"))


def reputation_tier(world_reputation):
    """Displayed reputation tier from world reputation, or None."""
    if world_reputation is None:
        return None
    for ceiling, label in _TIER_BANDS:
        if world_reputation < ceiling:
            return label
    return None


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
    for d in _ATTRS:
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
    for d in _ATTRS:
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
    u16 = lambda d: int.from_bytes(mm[o + d:o + d + 2], "little")
    rec = {
        "id2": int.from_bytes(mm[o:o + 4], "little"),
        "offset": o,
        "ca": u16(4), "pa": u16(6),
        "home_reputation": u16(8),
        "current_reputation": u16(10),
        "world_reputation": u16(12),
    }
    rec.update({name: mm[o + d] for d, name in _ATTRS.items()})
    rec.update({name: mm[o + d] for d, name in FORMATION_SLOTS.items()})
    rec["reputation_tier"] = reputation_tier(rec["world_reputation"])
    return rec


def scrape_staff_attributes(mm, id2s, lo=None, hi=None):
    """{id2: record} for each id in `id2s` that has a staff attribute record.

    Looked up BY KEY, not by walking the grid. The records sit on the same 78-byte stride as
    player attribute records but the table is MULTI-SEGMENT, so its phase resets: of the 7
    ground-truth managers, consecutive offsets differ by 19,929 and 8,541 bytes, neither a
    multiple of 78. A `+= RECORD` sweep therefore desynchronises at the first segment break
    and silently drops most of the table (it found 2 of 7 known managers). Searching the
    4-byte key inside the discovered window is both correct and collision-resistant, because
    every hit is then validated structurally.
    """
    wanted = {i for i in id2s if i not in (None, 0, 0xFFFFFFFF)}
    if not wanted:
        return {}
    n = len(mm)
    out = {}
    for o in _candidates(mm).tolist():
        if lo is not None and not (lo <= o < hi):
            continue
        id2 = int.from_bytes(mm[o:o + 4], "little")
        # Keyed on an id the info spine actually claims: that is what makes a candidate list
        # this loose safe, and it drops the shifted-neighbour false positives for free.
        if id2 not in wanted or id2 in out:
            continue
        if _valid(mm, o, n):
            out[id2] = _parse(mm, o)
    return out


def staff_id2(mm, info_offset):
    """The staff-record key for an info record, or None if it looks unset."""
    v = int.from_bytes(mm[info_offset + 64:info_offset + 68], "little")
    return None if v in (0, 0xFFFFFFFF) else v
