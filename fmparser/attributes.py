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
# Length-prefixed name, [3, 64] BYTES. The old cap was 0x20 = 32 bytes, one single byte
# above the longest name actually in the squad ('Frederik Vestergaard Kristensen', 31
# bytes) — and these are UTF-8 bytes, so accented names hit it sooner than their character
# count suggests. _FULLNAME below still validates the shape, so the wider cap admits longer
# real names without admitting junk.
_NAME_LEN = re.compile(rb"([\x03-\x40])\x00\x00\x00")
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
        if name:
            # LAST copy wins, not the first. The save keeps SEVERAL squad-list copies per
            # player from successive writes, and the freshest is the highest-offset one —
            # the same fact `attr_record` below is built on ("returning the first copy showed
            # pre-development attributes"). This function took the FIRST, so when a loan
            # converts to a permanent deal it kept reading a stale LOAN-shaped copy and the
            # player stayed `loaned_in` forever. Mounir Secka (tid 26779) has three copies on
            # frem-2026-03-22 — two LOAN at 61,439,685 / 61,457,553 and the real OWNED
            # `[346][ffff]` at 61,479,005 — and we were reporting the first.
            #
            # Measured across all 22 Frem saves and BOTH squad markers: one flip (Secka, on
            # 2025-11-30 and 2026-03-22), zero tids added or lost. Bucaspor unchanged.
            out[tid] = {"name": name, "loaned_in": loaned_in, "parent_club_tid": parent}
    return out


def own_squad(mm, lo=None, hi=None, marker=CLUB_MARKER):
    """{player_tid: full_name} for the managed club's squad (owned + loaned-in).
    Thin wrapper over own_squad_full for callers that only need names."""
    return {t: v["name"] for t, v in own_squad_full(mm, lo, hi, marker).items()}


def loan_marker(managed_tid, parent_tid):
    """The 4-byte marker that anchors a LOANED-IN player's exact attribute record:
    `[parent_club_tid][managed_tid]`, both u16 LE — the loan pair from own_squad_full's
    squad-LIST pattern, reused because it turns out to anchor the ATTRIBUTE record too.

    An owned player's record sits at `tid + 8` under CLUB_MARKER (`[club][0xffff]`).
    attr_record()/attr_records() only ever tested that shape, so a loanee's record —
    real, exact, and carrying `value` — was invisible: neither attr_record's default
    marker nor any (club, 0xffff) marker in squad_markers matches it. Confirmed
    byte-for-byte on the 2024-11-10 frem snapshot: Emil Rosberg Møller (parent 344,
    us 346) has `58 01 5a 01` sitting at the identical M offset where an owned
    player like Adam Jakobsen has `5a 01 ff ff` — same attrs/positions/feet/value
    layout around it, decoding to sane 1-20 attributes and a plausible transfer fee
    (confirmed for all 5 current loanees). See docs/agent-context/loan-value-marker.md."""
    return struct.pack("<HH", parent_tid, managed_tid)


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


def squad_snapshot_bounds(mm, markers):
    """Union of the per-marker snapshot windows.

    The first-team and reserve squad lists are written as separate marker clusters and can
    land in different places, so a single marker's window may not cover both. A marker whose
    discovery FAILED (snapshot_bounds fell back to the static SNAPSHOT_LO/HI window) is
    skipped rather than blowing the union open across half the file."""
    los, his = [], []
    for m in markers:
        lo, hi = snapshot_bounds(mm, marker=m)
        if (lo, hi) == (SNAPSHOT_LO, SNAPSHOT_HI):     # discovery failed -> ignore
            continue
        los.append(lo)
        his.append(hi)
    if not los:
        return SNAPSHOT_LO, SNAPSHOT_HI
    return min(los), max(his)


def attr_records(mm, tid, bounds=None, markers=(CLUB_MARKER,)):
    """{marker: freshest record} — one entry per club marker this tid appears under.

    A player who has moved between the first team and the reserves keeps a snapshot record
    under BOTH club markers. The copy under the club he is CURRENTLY in is live; the other
    is frozen at the moment he left that squad list. Verified against an in-game screen
    (2023-07-01): Hervé Buur reads Pace 10 under the first-team marker — his value when he
    dropped to the reserves ten months earlier — and Pace 16, the real figure, under the
    reserve marker. Callers pick by the player's current club (see extract.build_database);
    within a single marker the freshest copy is still the LAST one, as in attr_record."""
    lo, hi = bounds or squad_snapshot_bounds(mm, markers)
    le = struct.pack("<I", tid)
    out, pos = {}, lo
    while True:
        i = mm.find(le, pos)
        if i == -1 or i > hi:
            return out
        pos = i + 1
        m = bytes(mm[i + 8:i + 12])
        if m in markers:
            M = i + 8
            posb = list(mm[M - 23:M - 8])
            out[m] = {"attrs": list(mm[M - 59:M - 23]),
                      "positions": {POSITIONS[k]: v for k, v in enumerate(posb) if v > 1},
                      "feet": (mm[M + 33], mm[M + 34]),
                      "M": M,
                      "value": int.from_bytes(mm[M + 4:M + 8], "little")}


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

# The record does not stop at the reputation we read at P+21. It runs `P-42 … P+35` —
# exactly the 78-byte grid above — and the last 13 bytes were simply never parsed. Field
# order confirmed against nyongrand/fmm-editor's FMM26 `Player` struct; see
# docs/agent-context/fmm-editor-record-comparison.md.
#
# The `reputation` we have always read at P+21 is specifically HOME reputation; the name is
# left alone because value_model.py is fitted on that column.
#
# Verified on frem-2024-11-10 over 26,518 records: height median 182cm (min 153), weight
# median 73kg (min 55), and goalkeepers average 188.2cm/78.2kg against 180.4/71.8 for
# outfielders — the check to re-run if these ever look wrong.
def record_tail(mm, P):
    """The 13 bytes after HomeReputation, as a dict. Shared by both record readers so the
    global-record shape is defined in exactly one place."""
    u16 = lambda off: int.from_bytes(mm[P + off:P + off + 2], "little")
    return {
        "current_reputation": u16(23),
        "world_reputation": u16(25),
        "international_retired": bool(mm[P + 27]),
        # P+28..29 is a real non-zero u16 in FMM22 that FMM26 documents as "always 0x0000".
        # Highly repetitive, looks like a flags/enum field. Unidentified, so not surfaced.
        "squad_number": mm[P + 30],
        "preferred_squad_number": mm[P + 31],
        "height_cm": u16(32),
        "weight_kg": u16(34),
    }


# ---------------------------------------------------------------------------
# The HIDDEN attributes.
#
# 18 bytes in this record hold a 1-20 attribute; ATTR_OFFSETS names 9 (what the player screen
# shows, plus Teamwork's two halves). These are the other 9, named from fmm-editor's
# `FMMLibrary/Player.cs`, which declares all 34 attribute slots in read order from `P-34`.
#
# Why the order is trusted rather than assumed:
#   1. All seven offsets we confirmed independently against in-game values land exactly where
#      it predicts -- Pace P-24, Strength P-23, Stamina P-22, Technique P-21, Aggression P-19,
#      Leadership P-16, Agility P-5.
#   2. FMM22 stores 18 of the 34 slots as a plain 1-20 value and the other 16 as a wrapped
#      0-255 encoding, with no overlap -- and the split is EXACTLY along fmm-editor's semantic
#      line: the plain 18 are the ability-independent attributes, the encoded 16 are the
#      technical and goalkeeping ones. A partition that clean cannot come from a mis-aligned
#      order. (The encoded 16 are what `model.FROZEN` below decodes; they are not computed at
#      display time. At matched ability the Finishing byte peaks at ST, the Tackling byte at
#      DC, and the five GK bytes put GK ~80 points clear of every outfield position -- so the
#      ordering is confirmed slot by slot, not just at the seven anchors.)
#
# Semantic checks agree where they can discriminate: P-28 vs height_cm r=+0.79 (Strength, the
# strongest named physical, manages +0.30) -- that is Jumping; P-8 tracks Technique at +0.65 vs
# Stamina +0.20, the signature of Flair; P-13/P-14 correlate +0.57 with each other, as the two
# dead-ball attributes should. Consistency (P-20) and InjuryProne (P-17) are UNCONFIRMED: only
# 39 players have enough rated matches to measure rating spread, and the 89 injury rows show
# the injured group up on every attribute, so that test is confounded by minutes. Those two
# rest on the structural argument alone.
#
# Two departures from fmm-editor's names, both ground-truth-backed for FMM22: P-29 stays
# `Aerial` (Player.cs says Heading; the FMM22 UI says Aerial), and Teamwork is still derived
# from P-25 + P-9 (Player.cs says Unselfishness and WorkRate). P-9 is now also carried alone --
# a sub-attribute we only see averaged is one we cannot study.
HIDDEN_OFFSETS = {-28: "jumping", -20: "consistency", -18: "big_match",
                  -17: "injury_prone", -15: "versatility", -14: "set_pieces",
                  -13: "penalty", -9: "work_rate", -8: "flair"}


def hidden_attributes(mm, P):
    """The 9 attribute bytes the player screen does not show, as a dict.

    Shared by both record readers. Nothing is DERIVED from these -- they are carried so that
    identification and modelling work is a query rather than a re-extract, and none of them
    is surfaced in the app.
    """
    return {name: mm[P + rel] for rel, name in HIDDEN_OFFSETS.items()}


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
                "ca": ca, "pa": pa, "reputation": rep, "attributes": attrs,
                **record_tail(mm, P), **hidden_attributes(mm, P)}


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
