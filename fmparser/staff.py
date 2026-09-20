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
from .schema import Field, Record, U8, U16, U32, UNKNOWN

# Offsets relative to the record start (= the ID2 u32).
_ATTRS = {
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
# +14..+30 is a block of SEVENTEEN attribute bytes (1-20). Ten are the coaching values the
# Manager Profile screen shows; the remaining seven are hidden, because the other seven values
# on that screen are the personality block on the INFO record, not this one. Of the hidden
# ones only +14 carries a MEANING -- as `attacking_intent`, on the evidence in the module
# docstring, because Style is banded from it. The other six are PARSED but not named, as
# `hidden_s*` (see HIDDEN_OFFSETS below): carrying a value we cannot name costs nothing and is
# what identification work needs, whereas guessing a name is how `-140` became a Style
# candidate.

# The six HIDDEN attributes. `+14..+30` is seventeen 1-20 bytes; `_ATTRS` names the ten the
# Manager Profile screen shows and `attacking_intent`, which Style is banded from. These are
# the remaining six. All six read 1-20 for 100% of 4,210 staff records -- the same shape as
# the named ones -- so they are attributes we cannot name, not bytes we are unsure about.
#
# Carried rather than discarded, for the same reason as the player record's hidden block: we
# already know what KIND of thing they are, and a column in the store is what identification
# work needs. Named by offset so the name claims nothing: `hidden_s27` is staff record `+27`.
#
# `+27` is the one worth attacking first -- it is the only one with a distinctive
# distribution (85% of staff read 1-4, mean 3.0, against ~10 for the other five), so a small
# ground-truth set would separate it. The other five are unremarkably centred near 10.
HIDDEN_OFFSETS = {18: "hidden_s18", 20: "hidden_s20", 24: "hidden_s24",
                  26: "hidden_s26", 27: "hidden_s27", 28: "hidden_s28"}

FORMATION_SLOTS = {31: "formation_preferred",
                   32: "formation_attacking",
                   33: "formation_defensive"}

# Everything a staff record contributes downstream, named once so extract.py, the loader and
# the mart cannot drift apart. `ca`/`pa` ride along (the record carries them) and are subject
# to the same immersion rule as players': never surfaced. `reputation_tier` is the safe
# derivative to show instead.
STAFF_FIELDS = (("ca", "pa", "home_reputation", "current_reputation", "world_reputation",
                 "reputation_tier")
                + tuple(_ATTRS.values()) + tuple(HIDDEN_OFFSETS.values())
                + tuple(FORMATION_SLOTS.values()) + ("style",))

RECORD = 78          # same grid as the player attribute record
_CATALOG_MARKER = bytes.fromhex("76b9f407")
_CATALOG_STRIDE = 1262

# World-reputation bands for the displayed tier. Derived from the 7 ground-truth managers
# (Regional 1387/2278, National 5309-5736, Continental 5974) -- the boundaries sit in the
# gaps, so this is a DERIVED label, not a field the save asserts. Widen it if a manager ever
# lands on the wrong side.
_TIER_BANDS = ((3000, "Regional"), (5800, "National"), (10**9, "Continental"))

# Style bands over `attacking_intent` (+14). DERIVED, like reputation_tier -- the save stores
# the 1-20 attribute, not the label. Thirds of the scale; see the docstring for why, and for
# why the Defensive edge (7 vs anything up to 11) is the part still to confirm.
_STYLE_BANDS = ((7, "Defensive"), (13, "Normal"), (20, "Attacking"))

# The record as ONE declaration, built from the offset tables above rather than retyping them
# -- `_ATTRS`, `HIDDEN_OFFSETS` and `FORMATION_SLOTS` stay the source of truth because they
# are what the evidence in the docstring is written against.
#
# The field ORDER here is the output order and is load-bearing: `staff.json` is written
# without `sort_keys`, so re-sorting this list changes the file. It reproduces the order
# `_parse` built its dict in.
#
# Note the last five bytes. `+34..+38` is real structure -- a 15-value index space disjoint
# from the formation triple's -- and it is declared UNKNOWN rather than left out, because a
# byte that is neither named nor declared is a byte we are stepping over by accident. Knowing
# the record is EXACTLY 39 bytes is what settled Style: there is nowhere left in it for a
# 3-valued enum, so Style has to be derived, and it is.
STAFF = Record("staff_attribute", 39, [
    Field(0,  4, "id2", U32, note="the info record's +64 link"),
    Field(4,  2, "ca", U16, note="never surfaced -- immersion rule"),
    Field(6,  2, "pa", U16, note="never surfaced -- immersion rule"),
    Field(8,  2, "home_reputation", U16),
    Field(10, 2, "current_reputation", U16),
    Field(12, 2, "world_reputation", U16),
    *[Field(o, 1, n, U8, group="attrs") for o, n in _ATTRS.items()],
    *[Field(o, 1, n, U8, group="hidden") for o, n in HIDDEN_OFFSETS.items()],
    *[Field(o, 1, n, U8, group="formation") for o, n in FORMATION_SLOTS.items()],
    # the seven bytes of +14..+30 that `_ATTRS`/`HIDDEN_OFFSETS` do not claim would show up
    # here; today they claim all seventeen, so this list is empty and must stay empty.
    *[Field(o, 1, UNKNOWN, U8)
      for o in range(14, 31) if o not in {**_ATTRS, **HIDDEN_OFFSETS}],
    *[Field(o, 1, UNKNOWN, U8) for o in range(34, 39)],   # five catalog indices, undecoded
])


def style(attacking_intent):
    """Displayed manager Style from `attacking_intent`, or None. DERIVED, not stored."""
    if attacking_intent is None:
        return None
    for ceiling, label in _STYLE_BANDS:
        if attacking_intent <= ceiling:
            return label
    return None


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
    """(base, declared_count) for the staff attribute grid, or None.

    THE TABLE IS A DENSE ARRAY AND `id2 == slot index`, on 4642/4642 slots for Frem and
    5697/5697 for Bucaspor. This contradicts what this module used to claim -- see
    `scrape_staff_attributes` -- and the contradiction is resolved by the stride: the record
    is 39 bytes, not the player record's 78. Read at 78 the ids come out 0, 2, 4, ... and
    `id2 == slot` holds on exactly 1 slot, which is what "multi-segment" was inferred from.

    Located from any one validated record rather than from a constant: if a record at `o`
    carries `id2 == k` then record 0 is at `o - k * 39`, and the count-frame in front of it
    confirms the guess. The frame is then checked against the grid itself -- every declared
    slot must satisfy `id2 == slot` -- so a wrong base fails loudly instead of returning a
    plausible half-table.
    """
    # `save.cache_key`, never `id(mm)`: CPython reuses the id of a freed object, so a loop
    # over saves gets served the previous save's base -- and a stale ABSOLUTE OFFSET is the
    # worst kind of stale, it walks into the middle of an unrelated record.
    key = _cache_key(mm)
    if key in _STAFF_TABLE_CACHE:
        return _STAFF_TABLE_CACHE[key]
    found = None
    n = len(mm)
    for o in _candidates(mm).tolist()[:4000]:
        if not _valid(mm, o, n):
            continue
        k = int.from_bytes(mm[o:o + 4], "little")
        if not (0 <= k < 1_000_000):
            continue
        base = o - k * STAFF_STRIDE
        if base < _STAFF_FRAME:
            continue
        if not all(mm[base - 4 - 1 - j] == 0xFF for j in range(8)):
            continue
        count = int.from_bytes(mm[base - 4:base], "little")
        if not (0 < count < 1_000_000) or k >= count:
            continue
        if base + count * STAFF_STRIDE > n:
            continue
        if all(int.from_bytes(mm[base + j * STAFF_STRIDE:base + j * STAFF_STRIDE + 4],
                              "little") == j for j in range(count)):
            found = (base, count)
            break
    _STAFF_TABLE_CACHE[key] = found
    return found


def scrape_staff_attributes(mm, id2s, lo=None, hi=None):
    """{id2: record} for each id in `id2s` that has a staff attribute record.

    Looked up BY ARITHMETIC when the grid can be located -- `id2` IS the slot index, so the
    record is at `base + id2 * 39` and there is nothing to search. Falls back to the old key
    search over shape-matched candidates if the table cannot be framed.

    THE CORRECTION THIS CARRIES. That fallback used to be the whole story, justified like
    this: "the records sit on the same 78-byte stride as player attribute records but the
    table is MULTI-SEGMENT, so its phase resets: of the 7 ground-truth managers, consecutive
    offsets differ by 19,929 and 8,541 bytes, neither a multiple of 78." The observation was
    right and the conclusion was wrong -- the stride is 39, and 19,929 and 8,541 are exactly
    511 and 219 records of it. There are no segments and no phase resets; there was an
    off-by-a-factor-of-two in the stride, and "a grid walk is provably impossible" followed
    from it. The arithmetic agrees with the key search on every record the search finds
    (4,449/4,449 on Frem and 5,462/5,462 on Bucaspor, zero disagreements) and additionally
    rejects one Frem hit whose id2 lies past the declared end of the table.
    """
    wanted = {i for i in id2s if i not in (None, 0, 0xFFFFFFFF)}
    if not wanted:
        return {}
    n = len(mm)
    out = {}
    table = staff_table(mm)
    if table is not None:
        base, count = table
        for id2 in sorted(wanted):
            if not (0 <= id2 < count):
                continue          # past the table's own declared end: not a record
            o = base + id2 * STAFF_STRIDE
            if (lo is not None and not (lo <= o < hi)) or not _valid(mm, o, n):
                continue
            out[id2] = _parse(mm, o)
        return out
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

