#!/usr/bin/env python3
"""
Resolve competition ID -> name for FMM22 saves.

Each match header stores a competition ID as a u16 at `date_off - 3` (immediately
before the [home][away][day][year][att] core). Competition records live in the
~13 MB region with the shape:
    [compID:u16][UID:u32][len:u32][long name][len][short name][len][code]...
"""
import struct
from fmtool import Save


def comp_id_at(mm, date_off):
    """The competition id for a match, given its header date_off."""
    return int.from_bytes(mm[date_off - 3:date_off - 1], "little")


def resolve_comp(mm, cid, want="long"):
    """Return the competition name for an id, or None."""
    le = struct.pack("<H", cid)
    pos = 0
    while True:
        i = mm.find(le, pos)
        if i == -1:
            return None
        pos = i + 1
        uid = int.from_bytes(mm[i + 2:i + 6], "little")
        if not (1000 <= uid <= 300_000_000):
            continue
        ln = int.from_bytes(mm[i + 6:i + 10], "little")
        if not (3 <= ln <= 45):
            continue
        try:
            long_name = mm[i + 10:i + 10 + ln].decode("utf-8")
        except UnicodeDecodeError:
            continue
        if not (long_name and long_name[0].isupper()
                and sum(c.isalpha() for c in long_name) >= 3):
            continue
        # require a valid short name to follow (comp shape; rejects collisions).
        # NB: comp short names can start with a digit ("2. League White Group").
        j = i + 10 + ln
        for pad in (0, 1):
            ln2 = int.from_bytes(mm[j + pad:j + pad + 4], "little")
            if 3 <= ln2 <= 45:
                try:
                    short = mm[j + pad + 4:j + pad + 4 + ln2].decode("utf-8")
                except UnicodeDecodeError:
                    short = None
                if short and short[0].isalnum() and sum(c.isalpha() for c in short) >= 2:
                    return short if want == "short" else long_name
        # no short name -> not a competition record, keep searching
    return None


_CACHE = {}


def name_for(mm, cid, want="long"):
    key = (cid, want)
    if key not in _CACHE:
        _CACHE[key] = resolve_comp(mm, cid, want)
    return _CACHE[key]


if __name__ == "__main__":
    import json
    from season_extract import match_anchors, parse_header
    s = Save()
    anchors = match_anchors(s.mm)
    import collections
    tally = collections.Counter()
    for a in anchors:
        h = parse_header(s.mm, a)
        if h:
            tally[comp_id_at(s.mm, h["date_off"])] += 1
    for cid, c in tally.most_common():
        print(f"  id={cid:>5}  x{c:<3}  {name_for(s.mm, cid)}")
