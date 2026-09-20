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
    """The 13 bytes after HomeReputation, as a dict.

    Read from the `tail` group of `PLAYER`, so the global-record shape is defined in exactly
    one place -- which is now a declaration rather than this function. The `bool` cast stays
    here: it is meaning, not layout.
    """
    rec = RD.read_group(mm, PLAYER, _base(P), "tail")
    rec["international_retired"] = bool(rec["international_retired"])
    return rec


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


# THE ENTANGLED SOURCE BYTES, carried raw.
#
# These are the 16 slots FMM22 stores as a wrapped 0-255 value rather than a plain 1-20 one:
# the technical and goalkeeping attributes. `model.FROZEN` turns them into displayed values,
# and until 2026-09-17 that was the ONLY form that reached the store -- the parser decided what
# the number was and threw the evidence away.
#
# That is the wrong split of responsibilities. Estimation is a MODELLING concern, not a
# scraping one: keeping only the model's output means every retrain needs a full re-extract
# (~25 minutes) before it can even be scored. With the bytes in the store, the training set is
# a query -- raw bytes on one side, and on the other the exact values our own squad carries
# from the managed-club snapshot, already flagged `estimated = false`.
#
# Named `<attribute>_src` because the byte is the SOURCE of the attribute, not the attribute.
# Nothing is derived from them here.
SRC_OFFSETS = {-34: "crossing_src", -33: "dribbling_src", -32: "tackling_src",
               -31: "finishing_src", -30: "long_shot_src", -27: "passing_src",
               -26: "decision_src", -12: "creativity_src", -11: "movement_src",
               -10: "positioning_src", -7: "handling_src", -6: "kicking_src",
               -4: "aerial_gk_src", -3: "reflexes_src", -2: "communication_src",
               -1: "throwing_src"}


# The remaining nine PLAIN 1-20 bytes, stored raw as well.
#
# Seven of them (Pace..Agility) equal their displayed value, so this looks redundant -- but
# two do not, and those two are why this exists. FMM22's displayed "Aerial" is a function of
# the Heading AND Jumping bytes, and "Teamwork" is floor((Unselfishness + WorkRate) / 2). The
# raw Heading and Unselfishness bytes were therefore reachable ONLY through the parser's own
# derivation, which is precisely the coupling we are removing: the estimation model needs
# them (they are two of the nine `mean9` averages), so a model retrained against the store
# could not reproduce the parser without them.
#
# With these, staging.players carries all 34 attribute slots of the record verbatim, and
# nothing downstream has to go back to the save to refit anything.
PLAIN_OFFSETS = {-29: "heading_src", -25: "unselfishness_src", -24: "pace_src",
                 -23: "strength_src", -22: "stamina_src", -21: "technique_src",
                 -19: "aggression_src", -16: "leadership_src", -5: "agility_src"}


# ---------------------------------------------------------------------------
# THE RECORD, as one declaration.
#
# ANCHOR. The record runs P-42 .. P+35 and every note in this project describes its fields
# relative to `P`, the SID marker the locator finds -- `P-38`, `P+28`. `anchor=42` keeps both
# spellings: the declaration is in RECORD coordinates (offset = 42 + rel) and
# `base = P - PLAYER.anchor` does the subtraction once, instead of at every call site. Mixing
# the two is a bug this project has already had.
#
# ALIASES. `PLAIN_OFFSETS` and `ATTR_OFFSETS` name the IDENTICAL nine bytes -- the raw byte
# and the value the screen shows, which differ for exactly two of the nine (Aerial is a
# function of Heading AND Jumping; Teamwork is floor((Unselfishness + WorkRate) / 2)).
# `scripts/audit_records.py` could not declare both, because the second set trips the overlap
# check, so it silently omitted `PLAIN_OFFSETS` -- a table the parser reads that its audit
# could not see. `alias=True` says "this re-reads bytes already covered", which is the truth,
# and the audit now sees all four blocks.
#
# The four blocks are GROUPS because their emission order is the output's key order, and
# `attributes.json`/`players.json` are written without `sort_keys`.
PLAYER = Record("player_attribute", RECORD, [
    Field(0, 4, "sid", HEX4),
    # docs/agent-context/history-chain-pointers.md: the career-history table holds no id of
    # its own, and THIS is the link that joins it -- the pointer runs from the attribute
    # record into the history slab, not the other way.
    Field(4, 4, "history_link_P38", U32),
    *[Field(42 + rel, 1, n, U8, group="src") for rel, n in SRC_OFFSETS.items()],
    *[Field(42 + rel, 1, n, U8, group="hidden") for rel, n in HIDDEN_OFFSETS.items()],
    *[Field(42 + rel, 1, n, U8, group="attrs") for rel, n in ATTR_OFFSETS.items()],
    *[Field(42 + rel, 1, n, U8, group="plain", alias=True)
      for rel, n in PLAIN_OFFSETS.items()],
    Field(42, 15, "positions", RAW, note="15 position-rating bytes, decoded to a dict"),
    Field(57, 1, "foot_left", U8),
    Field(58, 1, "foot_right", U8),
    Field(59, 2, "ca", U16, note="never surfaced -- immersion rule"),
    Field(61, 2, "pa", U16, note="never surfaced -- immersion rule"),
    # named `reputation` downstream, not `home_reputation`: value_model.py is fitted on that
    # column name. It IS home reputation; the name is left alone on purpose.
    Field(63, 2, "reputation", U16),
    Field(65, 2, "current_reputation", U16, group="tail"),
    Field(67, 2, "world_reputation", U16, group="tail"),
    Field(69, 1, "international_retired", U8, group="tail"),
    Field(70, 2, UNKNOWN, U16),   # P+28..29: a real non-zero u16 in FMM22 that FMM26
                                  # documents as "always 0x0000". Repetitive, looks like a
                                  # flags/enum field. Unidentified, so never surfaced.
    Field(72, 1, "squad_number", U8, group="tail"),
    Field(73, 1, "preferred_squad_number", U8, group="tail"),
    Field(74, 2, "height_cm", U16, group="tail"),
    Field(76, 2, "weight_kg", U16, group="tail"),
], anchor=42)


def _base(P):
    """Record start from the SID marker. One subtraction, stated once."""
    return P - PLAYER.anchor


def named_attributes(mm, P):
    """The 9 bytes behind the displayed attributes ATTR_OFFSETS names."""
    return RD.read_group(mm, PLAYER, _base(P), "attrs")


def plain_bytes(mm, P):
    """The nine plain 1-20 bytes that back the displayed exact attributes, raw."""
    return RD.read_group(mm, PLAYER, _base(P), "plain")


def source_bytes(mm, P):
    """The 16 entangled 0-255 attribute bytes, raw and undecoded."""
    return RD.read_group(mm, PLAYER, _base(P), "src")


def hidden_attributes(mm, P):
    """The 9 attribute bytes the player screen does not show, as a dict.

    Shared by both record readers. Nothing is DERIVED from these -- they are carried so that
    identification and modelling work is a query rather than a re-extract, and none of them
    is surfaced in the app.
    """
    return RD.read_group(mm, PLAYER, _base(P), "hidden")


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
        attrs = named_attributes(mm, P)
        return {"sid": sid.hex(), "P": P, "positions": positions,
                "feet": {"left": left, "right": right},
                "ca": ca, "pa": pa, "reputation": rep, "attributes": attrs,
                **record_tail(mm, P), **hidden_attributes(mm, P),
                **source_bytes(mm, P), **plain_bytes(mm, P)}


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
