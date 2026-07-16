#!/usr/bin/env python3
"""
Resolve club TID -> club name for FMM22 saves.

Club records live in the ~10-14 MB region as standalone, FF-padded records:
  [TID:u32][UID:u32][len:u32][long name][len:u32][short name][len:u32][code]...
UIDs are large (senior clubs ~7e7, reserves ~2e8). We resolve a TID by finding an
occurrence whose following bytes form a valid record (plausible UID + length-prefixed
UTF-8 name).
"""
import struct
from fmtool import Save


def _valid_name(b):
    try:
        txt = b.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if any(ord(c) < 0x20 for c in txt):
        return None
    if sum(c.isalpha() for c in txt) < 2:
        return None
    return txt


def _short_after(mm, j):
    """A club stores its short name right after the long name (allow a 1-byte pad).
    Returns the short name, or None. This is the signature that separates a real
    club record from a geographic-region record (whose long name is followed by
    non-length bytes)."""
    for pad in (0, 1):
        ln = int.from_bytes(mm[j + pad:j + pad + 4], "little")
        if 2 <= ln <= 60:
            sh = _valid_name(mm[j + pad + 4:j + pad + 4 + ln])
            if sh:
                return sh
    return None


def resolve_club(mm, tid, want="long"):
    """Return the club name for a TID, or None. want='long'|'short'.
    Requires the full club shape (long name followed by a valid short name) so
    regions/stadiums/name-table collisions are rejected."""
    le = struct.pack("<I", tid)
    pos = 0
    while True:
        i = mm.find(le, pos)
        if i == -1:
            return None
        pos = i + 1
        # UID sanity only (real club UIDs range from ~1e3 to ~2e8; the club-shape
        # check below is what actually rejects regions/stadiums/name collisions).
        uid = int.from_bytes(mm[i + 4:i + 8], "little")
        if not (1 <= uid <= 400_000_000):
            continue
        ln = int.from_bytes(mm[i + 8:i + 12], "little")
        if not (2 <= ln <= 60):
            continue
        long_name = _valid_name(mm[i + 12:i + 12 + ln])
        if not long_name:
            continue
        short_name = _short_after(mm, i + 12 + ln)
        if not short_name:            # not a club record (e.g. a region)
            continue
        return short_name if want == "short" else long_name


def build_map(mm, tids, want="long"):
    return {t: resolve_club(mm, t, want) for t in tids}


if __name__ == "__main__":
    import json, sys
    s = Save()
    want = sys.argv[1] if len(sys.argv) > 1 else "long"
    season = json.load(open("season_data.json"))
    tids = sorted({m["home_tid"] for m in season} | {m["away_tid"] for m in season})
    m = build_map(s.mm, tids, want)
    for t in tids:
        print(f"  {t:>6}  {m[t]}")
    print(f"\n{sum(v is not None for v in m.values())}/{len(tids)} club TIDs resolved")
