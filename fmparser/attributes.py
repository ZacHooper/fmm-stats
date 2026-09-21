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
import math
import re
import struct

from .regions import CLUB_MARKER, ATTR_LO, ATTR_HI, LEAGUE_COMP_IDS
from .reference import info_offset
from . import model

from . import records as RD
from .schema import Field, HEX4, RAW, Record, U8, U16, U32, UNKNOWN
from .tables.player_attributes import (
    ATTR_OFFSETS,
    HIDDEN_OFFSETS,
    PLAIN_OFFSETS,
    PLAYER,
    PLAYER_ATTRIBUTES_TABLE,
    POSITIONS,
    RECORD,
    SRC_OFFSETS,
    _valid_positions,
)

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


class SnapshotNotFound(Exception):
    """The managed squad snapshot could not be located, and there is no window behind it."""


def snapshot_bounds(mm, margin=5000, marker=CLUB_MARKER):
    """Locate the squad-snapshot region adaptively (it drifts as the save grows).

    Club markers also appear in the match region (team-total records), so we can't
    just take the densest cluster. The snapshot is the marker cluster whose markers
    are preceded by real player NAMES. `marker` is the managed club marker
    (careers.Career.club_marker).

    RAISES if it cannot find the region. There is deliberately no window behind this: the
    old fallback returned `regions.SNAPSHOT_LO/HI`, 62.3-63.2 MB, which is the DEFAULT
    career's snapshot and nobody else's -- so a career whose snapshot sits elsewhere got a
    plausible empty answer instead of an error. A locator that has failed should say so.
    """

    hits, pos = [], 0
    while True:
        i = mm.find(marker, pos)
        if i == -1:
            break
        hits.append(i)
        pos = i + 1
    if not hits:
        raise SnapshotNotFound(
            f"the managed club marker {marker.hex()} does not appear in this save -- "
            f"wrong career? (careers.py), or the save is not an FMM22 .fms")
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
        raise SnapshotNotFound(
            f"found {len(hits)} club markers but no cluster is preceded by player names, "
            f"so none of them is the squad snapshot")
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
    discovery FAILS is skipped rather than blowing the union open across half the file --
    which is legitimate per marker (a career need not have a reserve side) but not for all
    of them, so an empty union raises.

    This used to detect failure by comparing the returned window against the static
    SNAPSHOT_LO/HI sentinel. That worked only because the fallback returned a value
    recognisable as "no answer" -- an exception says the same thing without requiring the
    caller to know the constant."""
    los, his = [], []
    for m in markers:
        try:
            lo, hi = snapshot_bounds(mm, marker=m)
        except SnapshotNotFound:
            continue
        los.append(lo)
        his.append(hi)
    if not los:
        raise SnapshotNotFound(
            f"none of the {len(list(markers))} club markers resolves to a squad snapshot")
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
# Schema and offsets are defined in fmparser.tables.player_attributes

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
def record_for(mm, tid):
    """Locate a player's global attribute record via SID. Returns a dict or None."""
    io = info_offset(mm, tid)
    if io is None:
        return None
    sid = mm[io + 60:io + 64].hex()
    return PLAYER_ATTRIBUTES_TABLE.id_map(mm, key_field="sid").get(sid)


# ---------------- full 23-attr estimation ----------------
EXACT_SINGLE = {"Pace": -24, "Strength": -23, "Stamina": -22, "Technique": -21,
                "Aggression": -19, "Leadership": -16, "Agility": -5}
ATTR_ORDER = ["Aerial", "Crossing", "Dribbling", "Shooting", "Passing", "Tackling",
              "Technique", "Aggression", "Creativity", "Decisions", "Leadership",
              "Movement", "Positioning", "Teamwork", "Pace", "Stamina", "Strength",
              "Agility", "Handling", "Kicking", "Reflexes", "Communication", "Throwing"]


# The two PLAIN-BYTE composites. Neither is a fit: both are closed forms over bytes that are
# already 1-20, so they need no model and no CA. Kept here as the SINGLE declaration -- the
# generated SQL in load_duckdb builds its expression from these numbers rather than repeating
# them, so the Python and the database cannot drift.
#
#   Teamwork  floor((unselfishness + work_rate) / 2)      EXACT   -- 98.0%
#   Aerial    floor(0.24*heading + 0.76*jumping + 0.8)    ESTIMATE -- 88.7%
#
# That difference is load-bearing: Teamwork's `_est` flag is FALSE and Aerial's must stay TRUE.
#
# Both weight sets were GRID-SEARCHED against exact matches on 840 truth rows / 86 players,
# 5 folds held out by player, and each fold picked the same point. Teamwork is the control: the
# search returns 0.48/+0.1 -- i.e. it independently rediscovers the halving formula we already
# knew, at the same 98.0% -- which is why the Aerial number is believable rather than a lucky
# search. Aerial went 72.0% -> 88.7% on the same rows and the same protocol; the improvement
# comes from 17 distinct players with only 1 made worse.
#
# HEIGHT WAS TESTED AND REJECTED. It is the obvious third term and it does not help: added to
# a least-squares fit it LOSES (67.5% -> 59.8%), and the grid search chooses a height weight of
# exactly 0.0 in all five folds. `jumping` appears to carry the physical part already. Weight,
# strength and agility were tested the same way and also rejected.
#
# Residual error is concentrated at the top: nothing predicts 17 or 18, which is 18 of 840 rows.
TEAMWORK_W = (0.50, 0.50, 0.0)
AERIAL_W = (0.24, 0.76, 0.8)


def _composite(w, a, b):
    wa, wb, off = w
    return max(1, min(20, int(math.floor(wa * a + wb * b + off))))


def teamwork(unselfishness, work_rate):
    """Displayed Teamwork from the two plain bytes. Exact, not an estimate."""
    return _composite(TEAMWORK_W, unselfishness, work_rate)


def aerial(heading, jumping):
    """Displayed Aerial from the two plain bytes. An ESTIMATE (~71% exact), not a fact."""
    return _composite(AERIAL_W, heading, jumping)


def fwd_of(positions):
    top = max(positions, key=positions.get) if positions else ""
    if top in ("ST", "AML", "AMR", "AMC"):
        return 1.0
    if top in ("ML", "MR", "MC", "DMC", "DML", "DMR"):
        return 0.5
    return 0.0


def estimate_player(mm, rec):
    """Full 23-attr set for one global record: {attr: {'val','est'}}, is_gk, fwd."""
    P, ca, pa = rec["P"], rec["ca"], rec["pa"]
    is_gk = int(rec["positions"].get("GK", 0) == 20)
    fwd = fwd_of(rec["positions"])
    mean9 = sum(rec["attributes"].values()) / len(rec["attributes"])
    out = {}
    for attr, off in EXACT_SINGLE.items():
        out[attr] = {"val": mm[P + off], "est": False}
    out["Teamwork"] = {"val": teamwork(mm[P - 25], mm[P - 9]), "est": False}
    out["Aerial"] = {"val": aerial(mm[P - 29], mm[P - 28]), "est": True}
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
