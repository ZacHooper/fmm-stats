#!/usr/bin/env python3
"""
Player attributes: own-squad (exact, from the snapshot) and league-wide (estimated,
from the global record + the frozen model).

Two record sources:
  - SQUAD SNAPSHOT (~62 MB, managed club only): full names + all 23 attributes on the
    raw 1-20 scale + feet. Exact. -> own_squad(), attr_record(), decode().
  - GLOBAL RECORD (~4-6.5 MB, every player): keyed by SID, holds positions, feet,
    CA/PA, reputation and 9 exact attributes; the other 14 are entangled 0-255 bytes
    decoded by the frozen model. -> record_for(), estimate_player().
"""
import re
import struct

from .regions import (SNAPSHOT_LO, SNAPSHOT_HI, CLUB_MARKER, ATTR_LO, ATTR_HI,
                       LEAGUE_COMP_IDS)
from .reference import info_offset
from . import model

POSITIONS = ["GK", "SW", "DL", "DC", "DR", "DMC", "ML", "MC", "MR",
             "AML", "AMC", "AMR", "ST", "DML", "DMR"]

# ---------------- own squad: names ----------------
_NAME_LEN = re.compile(rb"([\x03-\x20])\x00\x00\x00")
_FULLNAME = re.compile(r"[A-ZÀ-ſ][\w'. À-ſ-]{2,}$")


def own_squad(mm, lo=SNAPSHOT_LO, hi=SNAPSHOT_HI):
    """{player_tid: full_name} for the managed club's squad."""
    out, pos = {}, lo
    while True:
        i = mm.find(CLUB_MARKER, pos)
        if i == -1 or i > hi:
            break
        pos = i + 1
        tid = int.from_bytes(mm[i - 8:i - 4], "little")
        if not (1000 < tid < 70000):
            continue
        win = mm[i - 280:i]
        for m in _NAME_LEN.finditer(win):
            L = m.group(1)[0]
            s = m.end()
            cand = win[s:s + L]
            if len(cand) != L:
                continue
            try:
                txt = cand.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if " " in txt and _FULLNAME.match(txt) and not any(c.isdigit() for c in txt):
                out.setdefault(tid, txt)
                break
    return out


# ---------------- own squad: exact attributes (snapshot) ----------------
CONFIRMED = {0: "Aerial", 1: "Agility", 2: "Communication", 3: "Handling",
             4: "Kicking", 5: "Throwing", 6: "Reflexes", 7: "Crossing",
             8: "Dribbling", 10: "Passing", 11: "Shooting", 12: "Tackling",
             13: "Technique", 14: "Aggression", 15: "Creativity", 16: "Decisions",
             17: "Leadership", 18: "Movement", 19: "Positioning", 20: "Teamwork",
             21: "Pace", 22: "Stamina", 23: "Strength"}


def attr_record(mm, tid):
    """Own-squad exact record: {'attrs':[36], 'positions':{}, 'feet':(l,r), 'M'}."""
    le = struct.pack("<I", tid)
    pos = SNAPSHOT_LO
    while True:
        i = mm.find(le, pos)
        if i == -1 or i > SNAPSHOT_HI:
            return None
        pos = i + 1
        if mm[i + 8:i + 12] == CLUB_MARKER:
            M = i + 8
            attrs = list(mm[M - 59:M - 23])
            posb = list(mm[M - 23:M - 8])
            positions = {POSITIONS[k]: v for k, v in enumerate(posb) if v > 1}
            feet = (mm[M + 33], mm[M + 34])
            return {"attrs": attrs, "positions": positions, "feet": feet, "M": M}


def preferred_foot(feet):
    l, r = feet
    if l >= 16 and r >= 16 and abs(l - r) <= 3:
        return "Either"
    if l > r:
        return "Left only" if r <= 7 else "Left"
    if r > l:
        return "Right only" if l <= 7 else "Right"
    return "Either" if l >= 16 else "Right"


def decode(attrs):
    """{attribute: value} for the 23 confirmed own-squad attributes."""
    return {name: attrs[i] for i, name in CONFIRMED.items()}


# ---------------- global record (all players) ----------------
# offset relative to positions start P (= SID_hit + 42) -> exact attribute
ATTR_OFFSETS = {
    -29: "Aerial", -25: "Teamwork", -24: "Pace", -23: "Strength",
    -22: "Stamina", -21: "Technique", -19: "Aggression", -16: "Leadership",
    -5: "Agility",
}
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
    pos = ATTR_LO
    while True:
        i = mm.find(sid, pos)
        if i == -1 or i > ATTR_HI:
            return None
        pos = i + 1
        P = i + 42
        if P % RECORD != P_PHASE:
            continue
        seg = mm[P:P + 15]
        if not _valid_positions(seg):
            continue
        left, right = mm[P + 15], mm[P + 16]
        ca = int.from_bytes(mm[P + 17:P + 19], "little")
        pa = int.from_bytes(mm[P + 19:P + 21], "little")
        rep = int.from_bytes(mm[P + 21:P + 23], "little")
        if not (0 <= left <= 20 and 0 <= right <= 20):
            continue
        if not (0 < ca <= pa <= 200):
            continue
        positions = {POSITIONS[k]: v for k, v in enumerate(seg) if v > 1}
        attrs = {name: mm[P + rel] for rel, name in ATTR_OFFSETS.items()}
        return {"sid": sid.hex(), "P": P, "positions": positions,
                "feet": {"left": left, "right": right},
                "ca": ca, "pa": pa, "reputation": rep, "attributes": attrs}


# ---------------- full 23-attr estimation ----------------
EXACT_SINGLE = {"Pace": -24, "Strength": -23, "Stamina": -22, "Technique": -21,
                "Aggression": -19, "Leadership": -16, "Agility": -5}
ATTR_ORDER = ["Aerial", "Crossing", "Dribbling", "Shooting", "Passing", "Tackling",
              "Technique", "Aggression", "Creativity", "Decisions", "Leadership",
              "Movement", "Positioning", "Teamwork", "Pace", "Stamina", "Strength",
              "Agility", "Handling", "Kicking", "Reflexes", "Communication", "Throwing"]


def fwd_of(positions):
    top = max(positions, key=positions.get) if positions else ""
    if top in ("ST", "AML", "AMR", "AMC"):
        return 1.0
    if top in ("ML", "MR", "MC", "DMC", "DML", "DMR"):
        return 0.5
    return 0.0


def estimate_player(mm, rec):
    """Full 23-attr set for one global record: {attr: {'val','est'}}, is_gk, fwd."""
    import math
    P, ca, pa = rec["P"], rec["ca"], rec["pa"]
    is_gk = int(rec["positions"].get("GK", 0) == 20)
    fwd = fwd_of(rec["positions"])
    mean9 = sum(rec["attributes"].values()) / len(rec["attributes"])
    out = {}
    for attr, off in EXACT_SINGLE.items():
        out[attr] = {"val": mm[P + off], "est": False}
    tw = math.floor((mm[P - 25] + mm[P - 9]) / 2)
    out["Teamwork"] = {"val": max(1, min(20, tw)), "est": False}
    for attr in model.ESTIMATED_ATTRS:
        out[attr] = {"val": model.predict(attr, mm, P, ca, pa, mean9, fwd), "est": True}
    return out, is_gk, fwd


def league_tids(season):
    """Distinct player TIDs across the first team's competitions."""
    tids = set()
    for m in season:
        if m.get("comp_id") in LEAGUE_COMP_IDS:
            for side in ("home_xi", "away_xi"):
                tids.update(p["tid_int"] for p in m[side])
    return sorted(tids)
