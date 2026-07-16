#!/usr/bin/env python3
"""
League-wide player data from the GLOBAL attribute record (~4.0-6.5 MB region).

Unlike `attrs.py` (which reads the Bucaspor-only squad snapshot at ~62 MB), this
locates ANY player's record — opponents included — via their SID.

How it works (all validated on 23 Bucaspor players whose values we know from the
snapshot; every one matched exactly on positions/feet/CA/PA):
  - Read the player's SID (4 bytes) from the info-field (`info.py`, offset +60).
  - Find the SID in the ~4-6.5 MB region; the player's record has, at SID+42:
        SID+42 .. +56   15 position ratings (GK..DMR; 20 = natural)
        SID+57 / +58    left / right foot (0-20)
        SID+59 (u16)    CA        SID+61 (u16)  PA   (CA <= PA always)
        SID+63 (u16)    reputation
  - Confirmed visible attributes sit at fixed offsets before the positions block
    (P = SID+42): see ATTR_OFFSETS. These 9 calibrated to >=19/23 exact.

NOT yet resolved in this record (follow-up): the technical/attacking cluster
(Crossing, Dribbling, Passing, Shooting, Tackling, Creativity, Decisions,
Movement, Positioning) and the GK cluster (Handling, Kicking, Reflexes,
Communication, Throwing). FMM combines some (Shooting = Finishing+Long Shots,
Aerial = Heading+Jumping) so no single byte equals the displayed value; the GK
visibles appear to live in a different record. Our OWN squad has all of these
via `attrs.py`; this module fills in opponents for the confirmed fields.
"""
import struct
from fmtool import Save
from info import info_offset

POSITIONS = ["GK", "SW", "DL", "DC", "DR", "DMC", "ML", "MC", "MR",
             "AML", "AMC", "AMR", "ST", "DML", "DMR"]

# offset relative to positions start P (= SID+42) -> attribute (calibrated, 23 players)
ATTR_OFFSETS = {
    -29: "Aerial", -25: "Teamwork", -24: "Pace", -23: "Strength",
    -22: "Stamina", -21: "Technique", -19: "Aggression", -16: "Leadership",
    -5: "Agility",
}

REGION_LO, REGION_HI = 3_800_000, 6_600_000
# Records are a FIXED 78-byte grid (every inter-player gap is a multiple of 78).
# The positions block sits at grid phase P % 78 == 57 for all 28 known players, so
# a valid record must have (SID_hit + 42) % 78 == 57. This rejects off-grid SID
# collisions (the SID is only 2 unique bytes, so it appears as stray data too).
RECORD = 78
P_PHASE = 57


def _valid_positions(seg):
    return len(seg) == 15 and all(1 <= b <= 20 for b in seg) and max(seg) == 20


def record_for(mm, tid):
    """Locate a player's global attribute record via SID. Returns a dict or None."""
    io = info_offset(mm, tid)
    if io is None:
        return None
    sid = mm[io + 60:io + 64]
    pos = REGION_LO
    while True:
        i = mm.find(sid, pos)
        if i == -1 or i > REGION_HI:
            return None
        pos = i + 1
        P = i + 42
        if P % RECORD != P_PHASE:      # must sit on the 78-byte record grid
            continue
        seg = mm[P:P + 15]
        if not _valid_positions(seg):
            continue
        left, right = mm[P + 15], mm[P + 16]
        ca = int.from_bytes(mm[P + 17:P + 19], "little")
        pa = int.from_bytes(mm[P + 19:P + 21], "little")
        rep = int.from_bytes(mm[P + 21:P + 23], "little")
        # structural sanity: feet 0-20, 0 < CA <= PA <= 200
        if not (0 <= left <= 20 and 0 <= right <= 20):
            continue
        if not (0 < ca <= pa <= 200):
            continue
        positions = {POSITIONS[k]: v for k, v in enumerate(seg) if v > 1}
        attrs = {name: mm[P + rel] for rel, name in ATTR_OFFSETS.items()}
        return {"sid": sid.hex(), "P": P, "positions": positions,
                "feet": {"left": left, "right": right},
                "ca": ca, "pa": pa, "reputation": rep,
                "attributes": attrs}


if __name__ == "__main__":
    import json
    import sys
    s = Save()
    if len(sys.argv) > 1:  # single TID
        tid = int(sys.argv[1])
        print(json.dumps(record_for(s.mm, tid), ensure_ascii=False, indent=2))
        sys.exit(0)
    # whole league: every distinct player TID in league/cup/playoff matches
    season = json.load(open("season_data.json"))
    tids = set()
    for m in season:
        if m.get("comp_id") in (228, 227, 117):
            for side in ("home_xi", "away_xi"):
                tids.update(p["tid_int"] for p in m[side])
    out, hit = {}, 0
    for tid in sorted(tids):
        r = record_for(s.mm, tid)
        if r:
            out[str(tid)] = r
            hit += 1
    json.dump(out, open("league_attrs.json", "w"), ensure_ascii=False, indent=1)
    print(f"{hit}/{len(tids)} league players resolved -> league_attrs.json")
