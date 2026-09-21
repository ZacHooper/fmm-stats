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
from .schemas.places import CITY, CITY_RECORD, STADIUM_HEAD, STADIUM_HEADER
from .tables import CITIES_TABLE
_STADIUM_HEADER = STADIUM_HEADER

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
    raw = bytes(mm[o + _STADIUM_HEADER + 4:o + _STADIUM_HEADER + 4 + ln])
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
    """{city_id: record} with real latitude/longitude."""
    return CITIES_TABLE.id_map(mm, key_field="id")

