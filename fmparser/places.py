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

# Stadium: [Id u32][Uid u32][CityId u16][Capacity u32][Expansion u32][len u32][name][00]
_STADIUM_HEADER = 18
# City is fixed-width: [Id u16][Uid u32][NationId u16][lat f32][lon f32][attr u8][region u16][u8]
CITY_RECORD = 20

_LAT_RANGE = (-60.0, 80.0)
_LON_RANGE = (-180.0, 180.0)
# consecutive unreadable rows before we call it the end of the table
_CITY_GAP_TOLERANCE = 40


def _u16(mm, o):
    return int.from_bytes(mm[o:o + 2], "little")


def _u32(mm, o):
    return int.from_bytes(mm[o:o + 4], "little")


# ---------------------------------------------------------------- stadiums
def _stadium_at(mm, o, n):
    """Parse a stadium record at `o`, returning (rec, next_offset) or (None, None)."""
    if o < 0 or o + _STADIUM_HEADER + 4 > n:
        return None, None
    ln = _u32(mm, o + _STADIUM_HEADER)
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
    cap, exp = _u32(mm, o + 10), _u32(mm, o + 14)
    if cap > 300_000 or exp > 300_000:
        return None, None
    rec = {"id": _u32(mm, o), "uid": _u32(mm, o + 4), "city_id": _u16(mm, o + 8),
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
    walk from the longest such run rather than from a constant.
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
        if seen_start is not None and o < seen_start:
            continue
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
    (latitude, longitude) pair.
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
    out = {}
    # Walk both ways from the run: the run only pins the densest stretch, and the table has
    # gaps (rows whose coordinates are unset). Tolerate a short break rather than stopping at
    # the first one, which truncated the table to a tenth of its real size.
    for direction in (1, -1):
        o = start if direction == 1 else start - CITY_RECORD
        misses = 0
        while 0 <= o and o + CITY_RECORD <= n and misses < _CITY_GAP_TOLERANCE:
            lat, lon = struct.unpack("<ff", mm[o + 8:o + 16])
            nat = _u16(mm, o + 6)
            if (_LAT_RANGE[0] <= lat <= _LAT_RANGE[1]
                    and _LON_RANGE[0] <= lon <= _LON_RANGE[1]
                    and 1 <= nat <= 250):
                misses = 0
                cid = _u16(mm, o)
                out.setdefault(cid, {
                    "id": cid, "uid": _u32(mm, o + 2), "nation_id": nat,
                    "latitude": round(lat, 6), "longitude": round(lon, 6),
                    "attraction": mm[o + 16], "region_id": _u16(mm, o + 17), "offset": o,
                })
            else:
                misses += 1
            o += direction * CITY_RECORD
    return out
