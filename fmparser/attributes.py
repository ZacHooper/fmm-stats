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


def _name_before(mm, marker_i):
    """The player's full name from the record body preceding a club marker, or None.
    (First length-prefixed 'First Last' that looks like a Turkish full name.)"""
    win = mm[marker_i - 280:marker_i]
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
            return txt
    return None


def snapshot_bounds(mm, margin=5000, marker=CLUB_MARKER):
    """Locate the squad-snapshot region adaptively (it drifts as the save grows).

    Club markers also appear in the match region (team-total records), so we can't
    just take the densest cluster. The snapshot is the marker cluster whose markers
    are preceded by real player NAMES. Returns (lo, hi) or the static window if
    discovery fails. `marker` is the managed club marker (careers.Career.club_marker)."""
    hits, pos = [], 0
    while True:
        i = mm.find(marker, pos)
        if i == -1:
            break
        hits.append(i)
        pos = i + 1
    if not hits:
        return SNAPSHOT_LO, SNAPSHOT_HI
    clusters, cur = [], [hits[0]]
    for h in hits[1:]:
        if h - cur[-1] < 50_000:
            cur.append(h)
        else:
            clusters.append(cur)
            cur = [h]
    clusters.append(cur)
    best, best_score = None, 0
    for c in clusters:
        score = sum(1 for i in c[:12] if _name_before(mm, i))
        if score > best_score:
            best, best_score = c, score
    if not best:
        return SNAPSHOT_LO, SNAPSHOT_HI
    return max(0, best[0] - margin), best[-1] + margin


def own_squad_full(mm, lo=None, hi=None, marker=CLUB_MARKER):
    """{tid: {'name', 'loaned_in', 'parent_club_tid'}} for the managed club's squad,
    INCLUDING loaned-IN players.

    Squad records in the snapshot embed the managed club id (marker[:2] as u16) two ways:
      * OWNED : `… [club_id][ff ff] …`  — the full CLUB_MARKER; the tid sits 8 bytes before.
      * LOAN  : `… [parent_club_id][club_id] …` (no ff ff) — the player is on loan TO us; the
        tid sits 10 bytes before and the owning club is the u16 immediately before club_id.
    Searching the 2-byte club id (not the 4-byte marker) catches both; a valid tid range +
    a real name before the record reject coincidental hits. (own_squad greps only the 4-byte
    marker, so it silently dropped loanees — this is the general version.)"""
    if lo is None or hi is None:
        lo, hi = snapshot_bounds(mm, marker=marker)
    club_le = marker[:2]                       # managed club tid, u16 LE (e.g. 5a 01 = 346)
    out, pos = {}, lo
    while True:
        j = mm.find(club_le, pos, hi)
        if j == -1:
            break
        pos = j + 1
        if mm[j + 2:j + 4] == b"\xff\xff":     # OWNED: tid 8 bytes before the marker
            tid = int.from_bytes(mm[j - 8:j - 4], "little")
            loaned_in, parent = False, None
        else:                                  # LOAN: tid 10 before; owner is the u16 before
            tid = int.from_bytes(mm[j - 10:j - 6], "little")
            loaned_in = True
            parent = int.from_bytes(mm[j - 2:j], "little")
            if not (1 <= parent < 70000):      # not a plausible club id -> coincidental hit
                continue
        if not (1000 < tid < 70000):
            continue
        name = _name_before(mm, j)
        if name and tid not in out:
            out[tid] = {"name": name, "loaned_in": loaned_in, "parent_club_tid": parent}
    return out


def own_squad(mm, lo=None, hi=None, marker=CLUB_MARKER):
    """{player_tid: full_name} for the managed club's squad (owned + loaned-in).
    Thin wrapper over own_squad_full for callers that only need names."""
    return {t: v["name"] for t, v in own_squad_full(mm, lo, hi, marker).items()}


# ---------------- own squad: exact attributes (snapshot) ----------------
CONFIRMED = {0: "Aerial", 1: "Agility", 2: "Communication", 3: "Handling",
             4: "Kicking", 5: "Throwing", 6: "Reflexes", 7: "Crossing",
             8: "Dribbling", 10: "Passing", 11: "Shooting", 12: "Tackling",
             13: "Technique", 14: "Aggression", 15: "Creativity", 16: "Decisions",
             17: "Leadership", 18: "Movement", 19: "Positioning", 20: "Teamwork",
             21: "Pace", 22: "Stamina", 23: "Strength"}


def attr_record(mm, tid, bounds=None, marker=CLUB_MARKER):
    """Own-squad exact record: {'attrs':[36], 'positions':{}, 'feet':(l,r), 'M', 'value'}.

    The save keeps SEVERAL snapshot copies of each squad member (successive squad-list
    writes); the earlier copies are STALE and the freshest matches the in-game UI. Within
    the primary snapshot region the freshest copy is the LAST (highest-offset) one, so we
    return that — returning the first copy showed pre-development attributes (verified
    against in-game screens: e.g. Seyhun Shooting 14→16). A minority of players whose live
    copy lives in a separate secondary list (~600 KB later, outside snapshot_bounds) still
    resolve to their freshest in-region copy; see docs/ATTRIBUTE_DECODING.md.

    `value` is the player's transfer value (u32 at M+4; Sertgöz 2000 = £2K, Seyhun
    98221 ≈ £100K, both confirmed in-game)."""
    lo, hi = bounds or snapshot_bounds(mm, marker=marker)
    le = struct.pack("<I", tid)
    pos = lo
    found = None
    while True:
        i = mm.find(le, pos)
        if i == -1 or i > hi:
            return found
        pos = i + 1
        if mm[i + 8:i + 12] == marker:
            M = i + 8
            attrs = list(mm[M - 59:M - 23])
            posb = list(mm[M - 23:M - 8])
            positions = {POSITIONS[k]: v for k, v in enumerate(posb) if v > 1}
            feet = (mm[M + 33], mm[M + 34])
            value = int.from_bytes(mm[M + 4:M + 8], "little")
            found = {"attrs": attrs, "positions": positions, "feet": feet,
                     "M": M, "value": value}


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
RECORD = 78   # records sit on a 78-byte grid, but its phase is save-dependent
              # (shifts as the file grows), so we validate structurally, not by phase.


def _valid_positions(seg):
    return len(seg) == 15 and all(1 <= b <= 20 for b in seg) and max(seg) == 20


def record_for(mm, tid):
    """Locate a player's global attribute record via SID. Returns a dict or None.

    The record is identified structurally (valid 15-position block + feet 0-20 +
    0 < CA <= PA <= 200), NOT by absolute grid phase — the phase drifts between
    saves. Verified byte-identical to the phase-filtered version on the known save,
    and it resolves the larger/newer saves where the phase had shifted."""
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
