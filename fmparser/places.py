#!/usr/bin/env python3
"""
Stadiums and cities — capacity, and real latitude/longitude.

Both tables sit together at ~12.8-13.8 MB, and the club record's `stadium_id` is the way in:
club -> stadium -> city -> coordinates. Layouts from nyongrand/fmm-editor's FMM26 `Stadium`
and `City`; see docs/agent-context/fmm-editor-record-comparison.md.

Verified against reality, not just against plausibility:
  * stadium 157 (AaB) = "Aalborg Portland Park", capacity 13,800 — the real figure;
  * stadium 177 (FCK) = "Parken", capacity 38,065 — the real figure, to the seat;
  * city 51  = 57.0488N,  9.9217E = Aalborg;
  * city 58  = 55.6761N, 12.5683E = Copenhagen;
  * ids start at 0 with Belgian cities, and Ghent/Bruges/Antwerp all land correctly.

Neither window is hard-coded: both are discovered structurally, because every offset in
regions.py drifts per save and per career (CLAUDE.md's region-first rule).
"""
import struct

import numpy as np

from . import primitives as P
from . import records as RD
from .schema import F32, Field, Record, U8, U16, U32, UNKNOWN

# Stadium: [Id u32][Uid u32][CityId u16][Capacity u32][Expansion u32][len u32][name][00]
_STADIUM_HEADER = 18

# DECLARATION ONLY -- the record is variable-length (a length-prefixed name follows), so this
# is the fixed head and `is_head=True` says so. Nothing walks it: stadiums are a SEEDED CHAIN
# (shape E), located by a record's length field landing exactly on the next record.
# `scrape_stadiums` still reads the head itself, because it has to interleave the reads with
# the plausibility tests that decide whether this IS a record -- those tests are locating, and
# locating stays out of the layout.
STADIUM_HEAD = Record("stadium_head", _STADIUM_HEADER, (
    Field(0,  4, "id", U32),
    Field(4,  4, "uid", U32),
    Field(8,  2, "city_id", U16),
    Field(10, 4, "capacity", U32),
    Field(14, 4, "expansion_capacity", U32),
), is_head=True)
# City is fixed-width, and unlike the stadium record it is fully declared. Layout from
# fmm-editor's FMM26 `City`; ids 51 and 58 are Aalborg and Copenhagen to four decimal places.
CITY_RECORD = 20

CITY = Record("city", CITY_RECORD, [
    Field(0,  2, "id",         U16, note="== the slot index; that is what bounds the walk"),
    Field(2,  4, "uid",        U32),
    Field(6,  2, "nation_id",  U16, note="0 on 31 real cities with good coordinates"),
    Field(8,  4, "latitude",   F32),
    Field(12, 4, "longitude",  F32),
    Field(16, 1, "attraction", U8),
    Field(17, 2, "region_id",  U16),
    Field(19, 1, UNKNOWN,      U8),
])

_LAT_RANGE = (-60.0, 80.0)
_LON_RANGE = (-180.0, 180.0)


# ---------------------------------------------------------------- stadiums
def _stadium_at(mm, o, n):
    """Parse a stadium record at `o`, returning (rec, next_offset) or (None, None)."""
    if o < 0 or o + _STADIUM_HEADER + 4 > n:
        return None, None
    ln = P.u32(mm, o + _STADIUM_HEADER)
    if not (1 <= ln <= 120) or o + _STADIUM_HEADER + 4 + ln + 1 > n:
        return None, None
    raw = mm[o + _STADIUM_HEADER + 4:o + _STADIUM_HEADER + 4 + ln]
    if mm[o + _STADIUM_HEADER + 4 + ln] != 0:      # names are NUL-terminated
        return None, None
    try:
        name = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None, None
    if not name or not any(c.isalpha() for c in name):
        return None, None
    cap, exp = P.u32(mm, o + 10), P.u32(mm, o + 14)
    if cap > 300_000 or exp > 300_000:
        return None, None
    rec = {"id": P.u32(mm, o), "uid": P.u32(mm, o + 4), "city_id": P.u16(mm, o + 8),
           "capacity": cap, "expansion_capacity": exp, "name": name, "offset": o}
    return rec, o + _STADIUM_HEADER + 4 + ln + 1


def _chain_len(mm, o, n, limit=40):
    """How many stadium records chain consecutively from `o` (capped)."""
    k = 0
    while k < limit:
        rec, nxt = _stadium_at(mm, o, n)
        if rec is None:
            break
        o = nxt
        k += 1
    return k


def scrape_stadiums(mm, min_chain=25):
    """{stadium_id: record} for every stadium in the save.

    Found by chaining: a real record's length field lands exactly on the next record, so a
    run of `min_chain` consecutive valid records is not something noise produces. We seed the
    walk from the FIRST such run rather than from a constant -- seeds are scanned in address
    order, so the first one that chains is the earliest record boundary in the table.

    Ids come back dense from 0 (`len(out) == max(out) + 1`), which is the check that the seed
    landed on the table's first record and not partway in; scripts/audit_records.py asserts
    it.
    """
    n = len(mm)
    a = np.frombuffer(mm, dtype=np.uint8)
    # candidate seeds: a plausible name-length u32 at +18, cheap to vectorise
    end = n - 200
    ln = (a[_STADIUM_HEADER:end].astype(np.uint32)
          | (a[_STADIUM_HEADER + 1:end + 1].astype(np.uint32) << 8)
          | (a[_STADIUM_HEADER + 2:end + 2].astype(np.uint32) << 16)
          | (a[_STADIUM_HEADER + 3:end + 3].astype(np.uint32) << 24))
    seeds = np.flatnonzero((ln >= 3) & (ln <= 60))
    out, seen_start = {}, None
    for o in seeds.tolist():
        if _chain_len(mm, o, n) >= min_chain:
            seen_start = o
            break
    if seen_start is None:
        return out
    o = seen_start
    while True:
        rec, nxt = _stadium_at(mm, o, n)
        if rec is None:
            break
        out.setdefault(rec["id"], rec)
        o = nxt
    return out


# ---------------------------------------------------------------- cities
def scrape_cities(mm):
    """{city_id: record} with real latitude/longitude.

    The table is fixed-width, so it is located by the one thing that cannot be coincidence at
    scale: thousands of consecutive 20-byte records whose two float32s are a valid
    (latitude, longitude) pair. That run only SEEDS the walk; its extent comes from the
    table's own invariant (id == slot index) -- see the comment on the walk below.

    Rows are dense and contiguous from id 0, so `len(out) == max(out) + 1` always holds;
    scripts/audit_records.py asserts it.
    """
    a = np.frombuffer(mm, dtype=np.uint8)
    n = a.size
    best = (0, 0)                     # (run length, start offset)
    for phase in range(4):
        cnt = (n - phase) // 4
        v = np.frombuffer(a[phase:phase + cnt * 4].tobytes(), dtype="<f4")
        lat, lon = v[:-1], v[1:]
        with np.errstate(invalid="ignore"):
            m = ((lat >= _LAT_RANGE[0]) & (lat <= _LAT_RANGE[1])
                 & (lon >= _LON_RANGE[0]) & (lon <= _LON_RANGE[1])
                 & (np.abs(lat) > 1e-3) & (np.abs(lon) > 1e-3))
        idx = np.flatnonzero(m)
        if idx.size < 200:
            continue
        off = phase + idx * 4
        # The table's signature is not "lots of coordinates in one area" -- plenty of
        # unrelated regions pass a loose lat/lon test -- it is a long run of records spaced
        # EXACTLY one record apart. Take the longest such run.
        step = np.diff(off) == CITY_RECORD
        run = 0
        for i, ok in enumerate(step.tolist()):
            if ok:
                run += 1
                if run > best[0]:
                    best = (run, int(off[i + 1 - run]))
            else:
                run = 0
    if best[0] < 200:
        return {}
    start = best[1] - 8               # lat sits at +8 within the record
    # The run only pins the densest STRETCH, not the table's extent. Bounding the walk with a
    # miss counter instead made the row count a function of the tolerance constant: at 40 it
    # emitted 3 records that are not cities at all and dropped 31 that are, and every one of
    # those 31 is referenced by a stadium. So bound it by the table's OWN invariant instead.
    #
    # The invariant: the table is a dense fixed-width array and `id` IS the slot index. It
    # held for 10,925/10,925 records inside the run on frem-2024-11-10, which is what makes
    # it safe to walk on: the first slot whose id != its index is past the end, full stop.
    # No tolerance, no false positives, and rows the coordinate test would reject are kept
    # (31 real cities carry nation_id 0 with good coordinates).
    anchor = _slot_zero(mm, start, n)
    if anchor is None:
        return {}
    out, k = {}, 0
    while anchor + CITY_RECORD * (k + 1) <= n:
        o = anchor + CITY_RECORD * k
        if P.u16(mm, o) != k:         # id != slot index -> past the end of the table
            break
        rec = RD.read(mm, CITY, o)
        # The coordinate test is MEANING, not layout, so it stays here rather than in the
        # declaration: a slot with no real coordinates keeps its row and reads NULL, instead
        # of vanishing and leaving a stadium pointing at nothing.
        placed = (_LAT_RANGE[0] <= rec["latitude"] <= _LAT_RANGE[1]
                  and _LON_RANGE[0] <= rec["longitude"] <= _LON_RANGE[1])
        rec["latitude"] = round(rec["latitude"], 6) if placed else None
        rec["longitude"] = round(rec["longitude"], 6) if placed else None
        rec["offset"] = o
        out[k] = rec
        k += 1
    return out


def _slot_zero(mm, start, n):
    """Offset of city id 0, from the seed run, or None.

    Majority vote over `offset - CITY_RECORD * id` across the run: every record in a dense
    array agrees on where slot 0 is, so a stray hit cannot outvote the table. 10,925 of
    10,928 seed records agreed on frem-2024-11-10; the 3 that did not are the false
    positives this replaces.
    """
    votes = {}
    o = start
    while o + CITY_RECORD <= n and o < start + CITY_RECORD * 4000:
        lat, lon = struct.unpack("<ff", mm[o + 8:o + 16])
        if (_LAT_RANGE[0] <= lat <= _LAT_RANGE[1]
                and _LON_RANGE[0] <= lon <= _LON_RANGE[1]
                and abs(lat) > 1e-3 and abs(lon) > 1e-3):
            base = o - CITY_RECORD * P.u16(mm, o)
            if base >= 0:
                votes[base] = votes.get(base, 0) + 1
        o += CITY_RECORD
    if not votes:
        return None
    base, hits = max(votes.items(), key=lambda kv: kv[1])
    return base if hits >= 200 else None
