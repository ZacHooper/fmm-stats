#!/usr/bin/env python3
"""
Reference-data resolvers: club names, competition names, and the player info field.

- Club records (~10-14 MB): [TID:u32][UID:u32][len][long][len][short][len][code].
- Competition records (~13 MB): [cid:u16][UID:u32][len][long][len][short][len][code];
  a match's cid is a u16 at date_off-3.
- Info field (~2.8 MB, rough-guide Step 2): TID, UID, name IDs, DOB, nationality,
  club TID, and the SID at +60 that links a player to their global attribute record
  and their per-match stat blocks.
"""
import collections
from datetime import date, timedelta
from typing import NamedTuple
import struct

import numpy as np

from . import lookups as LK
from . import regions as RG

NATIONS = {173: "Turkey"}


# A club's uid is NOT bounded by the 400,000,000 that gated this scan for its whole life.
# Ground truth, confirmed against two in-game player profiles (2026-09-12): Shawn Beeckaert
# plays for tid 6863, which the game shows as "EM United" -- Erpe-Mere United, uid
# 2,000,004,399, a perfectly well-formed record at byte 10,104,532 that the ceiling threw
# away. Jesús Bernal plays for tid 7153, "Paracuellos" = C.D. Paracuellos Antamira, uid
# 2,000,112,622. We were keeping "Erpe-Mere United Reserves" (uid 200,010,882, under the
# ceiling) while dropping the first team.
#
# This is the THIRD uid gate in this file to be wrong the same way -- see find_comp_record on
# the old `uid >= 1000` rule that silently skipped every top division. The uid is not a range
# to guess at; it is an identifier.
#
# The ceiling is not simply raised, because widening it in place CORRUPTS three real clubs:
# person records match the club shape and win low tids on file order (C Cerro Porteño ->
# 'Ultee', Club Sporting Cristal -> 'Boujemaoui', Club Centro Deportivo Municipal ->
# 'Leemans'). So the band below admits records only for tids nothing else resolved, and only
# with the club trailer marker present. Measured on frem-2026-03-22: 327 clubs recovered,
# 0 existing names changed, 0 person records admitted.
_CLUB_UID_FILL_LO, _CLUB_UID_FILL_HI = 1_900_000_000, 2_100_000_000


def _refdata_window(mm):
    """(lo, hi) for the club/comp reference-data band. Trusted outright, same as every
    other region in regions.py (ATTR_LO/HI, LIGHT_LO/HI, ...) — no runtime fallback to a
    full-file scan. That fallback was tried and measured SLOWER in practice: most
    club_record lookups here are misses (obscure historical/foreign clubs with no record
    in this save at all — extract.py's club_ids includes every club named in every
    player's full career history), and a miss means scanning to end-of-range either way,
    so "windowed, then whole file" costs window-scan PLUS full-file-scan on every miss —
    strictly more work than the unbounded original for the common case. Measured on a real
    4742-club lookup set: fallback version 123s vs unbounded original 116s (SLOWER); window-
    only (this version) is bounded to ~20 MB regardless of hit or miss. See regions.py for
    where the bound comes from (the actual filler-delimited section, not sampled hits) and
    what to do if a future save drifts past it."""
    return RG.REFDATA_LO, min(RG.REFDATA_HI, len(mm))


# ---------------- clubs + competitions: single-pass reference index ----------------
# club_record/find_comp_record used to be independent `mm.find`-per-call scans of the
# ~20 MB REFDATA window — cheap individually, but extract.py resolves ~4700+ club tids
# (every club named in every player's full career history) plus a few hundred comp cids
# in one run, and MOST of those calls are misses that scan to the end of the window
# regardless. That's O(lookups x window) — tens of seconds in a real extract.
#
# _build_refdata_index scans the window ONCE and returns {tid: club_record} and
# {cid: comp_record} for every record it holds, so every lookup after that is an O(1)
# dict.get(). The candidate search itself is vectorized with numpy (same technique as
# history.py's column-wise scan of the history slab): both record shapes put a
# length-prefixed name's length field (u32, small — [2,60] for a club long name, subsuming
# the comp range [3,45]) 4 bytes after their UID, so `np.flatnonzero` on the whole window's
# u32-at-every-offset view finds every plausible record start in one vectorized pass
# (~350k candidates out of 20M positions, <0.1s) before any per-candidate Python
# validation runs. Only the reduced candidate set pays Python-level cost.
#
# No range check on the tid read back from each candidate (an earlier draft guessed
# `100 < tid < 70000` to cut candidate volume and shipped it uncommitted with an unverified
# "validated identical" claim in this comment — it silently dropped 26 real clubs in one
# real save, including Boca Juniors and River Plate, tid 51-78). Trust the same structural
# checks the old per-tid scan always relied on (uid range, decodable name, valid short
# name) instead of a second guess about what a tid can be.
def _valid_name(b, min_alpha=2):
    """Decode a length-prefixed name, or None if it can't be one.

    `min_alpha` guards against random bytes that happen to decode. It is 2 for LONG names,
    but SHORT names are abbreviations and are legitimately allowed a single letter — real
    example: B.93 (tid 334), whose short name "B.93" was being rejected, which threw away the
    club record entirely and left only an unrelated "Player of the Month" award record that
    shares the tid. That surfaced as an award appearing as a player's club in career history.
    """
    try:
        txt = b.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if any(ord(c) < 0x20 for c in txt):
        return None
    if sum(c.isalpha() for c in txt) < min_alpha:
        return None
    return txt


def _short_after(mm, j):
    for pad in (0, 1):
        ln = int.from_bytes(mm[j + pad:j + pad + 4], "little")
        if 2 <= ln <= 60:
            sh = _valid_name(mm[j + pad + 4:j + pad + 4 + ln], min_alpha=1)
            if sh:
                return sh
    return None


# competition type byte (immediately after the 3 name strings). Calibrated on Turkey:
# top-flight league(0), league(228)/play-off(227)=1, cup(117)=2, reserve league(1370)=8,
# friendly(65)=9. type_id 0 and 1 are BOTH round-robin leagues (0 = a nation's top flight,
# e.g. 3F Superliga / Bundesliga / Serie A; 1 = the divisions below it).
#
# This is NOT a small closed enum -- corrected 2026-09-18. `_eval_comp_candidate` used to
# reject any type outside this dict (`_COMP_VALID_TYPES`, now retired), on the unstated
# assumption that only 5 type values existed. They don't: at minimum 3, 4, 5, 7, 10, 11, 12,
# 13, 14, 15, 22, 23, 26, 28, 29, 30, 36, 37, 38, 39 all produce clean, real, football-shaped
# competitions when the type check is dropped (Carabao Cup, FA Trophy, European Championship,
# Copa América, African Cup of Nations, national Super Cups, youth leagues, All-Star
# exhibitions among them) -- confirmed by NAME, not just by passing the other gates. The
# single clearest case: cid 13 "French Regional Divisions" sat in an otherwise fully dense
# 0-12 block and was still being dropped by this gate alone. Only the 5 values below have a
# name sourced with real confidence; every other value falls through to `type_N` in the `rec`
# dict rather than getting a guessed label -- naming the rest properly is future work
# (docs/TODO.md), not blocking their resolution. Nation/continent/reputation/name-shape
# already do the real noise filtering (every actual noise candidate checked failed one of
# those, never type alone), so there is no evidence a type gate was ever needed here.
COMP_TYPES = {0: "league", 1: "league", 2: "cup", 8: "reserve_league", 9: "friendly",
              21: "continental_cup"}
_MIN_COMP_REP = 500          # real loaded comps have reputation >> this (min seen ~12k for a
                             # 6th-tier league; friendlies ~2.6k). ROUND-label records that
                             # collide on small cids ('First Leg', 'Playoff') carry rep 0.
# 45 -> 60 (2026-09-18), matching the club long-name cap (_eval_club_candidate's [2,60]).
# 45 was silently dropping real competitions with long, fully-spelled regional names --
# "Northern Amateur Football League Premier Division" (51), "Chinese National Amateur
# Division North East Group" (52), "United States Soccer Leagues Division Two Playoffs"
# (51) among 40+ confirmed real names in the 46-52 range. No noise candidate in this save
# was ever caught BY the length cap alone (continent/nation/reputation/shape already do
# that work), so narrowing it bought nothing.
_COMP_NAME_CAP = 60

_REFDATA_INDEX_CACHE = {}   # id(mm) -> ({tid: club_record}, {cid: comp_record})
_NATION_BOUNDS_CACHE = {}   # id(mm) -> (lo, hi) of the real nation-name table, padded


def _nation_table_bounds(mm):
    """The real NATION table's byte extent, straight from `lookups.scrape_nations` (its own
    offsets, not a guess) -- padded by 200B either side, comfortably more than one nation's
    own record span (~60-90B: name + nationality + 3-letter code, each length-prefixed) but
    nowhere near the ~2,900B gap to the next real table. Measured 2026-09-18: this file's
    "Danish Reserves Group 1" (cid 1342, the ORIGINAL motivating fix for this whole item)
    sits only 2,905B before the nation table's own first offset -- reusing `scrape_nations`'
    own 4096B cluster-continuity margin here (a different job: finding candidates that
    belong to ONE dense run, not bounding that run's own edges) swallowed it whole and
    broke the fix. 200B is derived from the record shape, not copied from a neighbour's
    unrelated constant.

    WHY THIS EXISTS: `scrape_nations`'s own docstring says it plainly -- "CLUB and
    COMPETITION records share this exact shape [with nation records]", so this scan's
    candidate prefilter proposes every nation's name/nationality/code triplet as a comp (or
    club) candidate too. Confirmed 2026-09-18: "British Virgin Is." (real nation_id 206 per
    `scrape_nations`) was resolving as comp cid 63981 -- a number read from the WRONG byte
    offset for this record type, not a real id at all, just the tail of the PREVIOUS
    nation's own ranking-history array sitting where a comp record's cid/uid would be.
    Only one such collision tripped a comp gate on this save (a length-shape fluke), which
    means an unknown number of others could be silently resolving as fake "competitions"
    with plausible-looking fields, never tripping anything. Excluding the whole known
    region structurally is the fix CLAUDE.md's region-first method calls for -- an
    incidental gate (reputation ceiling, name-length shape) only catches the collisions
    that happen to look wrong, not the ones that don't.
    """
    key = id(mm)
    cached = _NATION_BOUNDS_CACHE.get(key)
    if cached is not None:
        return cached
    offsets = [rec["offset"] for rec in LK.scrape_nations(mm).values()]
    bounds = (min(offsets) - 200, max(offsets) + 200) if offsets else None
    _NATION_BOUNDS_CACHE[key] = bounds
    return bounds


_NAME_TABLE_BOUNDS_CACHE = {}   # id(mm) -> (start, end) of the browse name table, exact


def _name_table_bounds(mm):
    """The real NAME table's (the ~46k-entry flat [len][utf-8] first-name/surname "browse"
    table `_walk_browse` reads for player-name resolution) byte extent -- same collision
    class as `_nation_table_bounds`, one door down: this table sits at the very start of
    the file (`scripts/map_regions.py` independently maps it as `name_table`, entry0@299=
    'Rajagobal'), made of nothing but back-to-back length-prefixed strings, which is
    EXACTLY the shape the comp/club candidate prefilter looks for. Confirmed 2026-09-18:
    comp cid=24931 named 'World' resolved from file offset 897 -- squarely inside this
    table, nowhere near any real competition (which cluster at ~12.6-12.76M on this save) --
    only surfaced once the name-length cap was raised to 60 and the continent gate widened
    to accept the 0xFFFF "no confederation" sentinel, the same two changes that recovered
    75 genuine long-named lower-tier leagues and World Cup/Confederations Cup/Club World
    Championship. No padding needed, unlike the nation table: `_walk_browse` already finds
    this table's own precise start/end by the same walk that reads its contents, not a
    separate candidate scan with its own continuity margin.
    """
    key = id(mm)
    cached = _NAME_TABLE_BOUNDS_CACHE.get(key)
    if cached is not None:
        return cached
    start, end, names = _walk_browse_bounds(mm)
    bounds = (start, end) if names else None
    _NAME_TABLE_BOUNDS_CACHE[key] = bounds
    return bounds


_COMP_TABLE_ANCHOR_CACHE = {}


def _comp_table_anchor(mm):
    """(start, count) for the competition table, read from the file's OWN structure, not a
    tuned constant: the table is preceded by a run of 0xFF filler, then a u16 giving its own
    declared record count, then record 0 begins immediately. Spotted directly in a hex dump
    2026-09-18 -- 0x055c = 1372 on this save, exactly max real cid (1371) + 1.

    This is the anchor for `_walk_comp_table`, which reads the WHOLE table by pure
    arithmetic once `start`/`count` are known -- no plausibility gate needed at all, because
    the walk never depends on a record's content to find the next one. Confirmed by walking
    every one of the 1372 declared records with zero misalignment (cid always equals the
    loop index) and cross-checking against the file's own count: 1272 named + 100 verified-
    blank (namelen 0, a structured placeholder uid) == 1372 exactly.

    The candidate that a bare `_comp_table_anchor` search would find first isn't
    necessarily the real one -- a small preceding 0xFF run plus a plausible count occurs
    coincidentally elsewhere in the file (a 'Team of the Week' id sequence at ~13.7M was one
    such false hit). Confirmed by walking to record 1 and checking its cid reads back as 1
    -- far stronger than trusting the count-range heuristic alone, and self-consistent with
    the very same arithmetic the real walk uses.
    """
    key = id(mm)
    cached = _COMP_TABLE_ANCHOR_CACHE.get(key)
    if cached is not None:
        return cached
    buf = np.frombuffer(mm, dtype=np.uint8)
    is_ff = buf == 0xFF
    d = np.diff(is_ff.astype(np.int8))
    run_starts = np.flatnonzero(d == 1) + 1
    run_ends = np.flatnonzero(d == -1) + 1
    result = None
    for s, e in zip(run_starts.tolist(), run_ends.tolist()):
        if e - s < 6:
            continue
        p = e
        count = int.from_bytes(mm[p:p + 2], "little")
        if not (100 <= count <= 5000):
            continue
        cid0 = int.from_bytes(mm[p + 2:p + 4], "little")
        uid0 = int.from_bytes(mm[p + 4:p + 8], "little")
        if cid0 != 0 or not (1 <= uid0 <= 100_000):
            continue
        namelen0 = int.from_bytes(mm[p + 8:p + 12], "little")
        if not (3 <= namelen0 <= _COMP_NAME_CAP):
            continue
        name0 = mm[p + 12:p + 12 + namelen0]
        if not (name0[:1].isalpha() or name0[:1].isdigit()):
            continue
        try:
            _, next_p = _read_comp_slot(mm, p + 2)
            cid1 = int.from_bytes(mm[next_p:next_p + 2], "little")
        except (IndexError, UnicodeDecodeError):
            continue
        if cid1 == 1:
            result = (p + 2, count)
            break
    _COMP_TABLE_ANCHOR_CACHE[key] = result
    return result


def _read_comp_slot(mm, p):
    """Read ONE competition-table slot at `p` (a `[cid][uid]...` record start) by pure
    arithmetic -- no plausibility gate, no rejection outcome. Returns (rec_or_None, next_p):
    `rec` is None for a genuinely blank/reserved slot (namelen 0 -- confirmed 2026-09-18,
    cid 1242-1337 and 4 scattered per-nation placeholders on this save, uid a structured
    `2,000,000,000 + n` counter distinct from real competitions' `200,000,000 + cid`
    range), and `next_p` is always correct regardless, because the terminator convention
    (one byte after the long name, one after the short name, none after the code) and the
    25+8*history_count trailer extension apply identically whether or not the names are
    empty. See `_walk_comp_table`."""
    cid = int.from_bytes(mm[p:p + 2], "little")
    uid = int.from_bytes(mm[p + 2:p + 6], "little")
    q = p + 6
    ln = int.from_bytes(mm[q:q + 4], "little")
    long = mm[q + 4:q + 4 + ln].decode("utf-8")
    pp = q + 4 + ln + 1
    sl = int.from_bytes(mm[pp:pp + 4], "little")
    short = mm[pp + 4:pp + 4 + sl].decode("utf-8")
    pp = pp + 4 + sl + 1
    cl = int.from_bytes(mm[pp:pp + 4], "little")
    code = mm[pp + 4:pp + 4 + cl].decode("utf-8")
    pp = pp + 4 + cl
    trailer = mm[pp:pp + 14]
    typ, nation = trailer[0], trailer[3]
    rep = int.from_bytes(trailer[9:11], "little")
    level = trailer[11]
    parent = int.from_bytes(trailer[12:14], "little")
    hist_p = pp + 14
    hist_count = int.from_bytes(mm[hist_p:hist_p + 4], "little")
    next_p = hist_p + 25 + 8 * hist_count
    if ln == 0:
        return None, next_p
    rec = {"cid": cid, "uid": uid, "name": long, "short": short, "code": code,
           "type": COMP_TYPES.get(typ, f"type_{typ}"), "type_id": typ,
           "nation_id": None if nation == 255 else nation, "reputation": rep,
           "level": level, "parent_cid": None if parent == 0xFFFF else parent}
    return rec, next_p


def _walk_comp_table(mm):
    """Pure structural walk of the ENTIRE competition table -- no candidate scan, no gates.
    `_comp_table_anchor` gives the table's start and its own declared record count; every
    one of those records is then read by `_read_comp_slot`'s arithmetic alone. Returns
    (comps, n_blank) where `comps` is {cid: rec} for named records only; `n_blank` counts
    genuinely empty slots. Returns (None, None) if the anchor can't be found on this save
    (a different career/format) -- callers fall back to the old candidate-scan-plus-gates
    path in that case.

    Replaces `_eval_comp_candidate`'s whole gate cascade for competitions (2026-09-18):
    once the table's own start/count are known, every record -- named or blank -- resolves
    by arithmetic, with cid checked against the walk's own loop index as the ONE structural
    assertion (a real invariant, not a tuned constant, per CLAUDE.md's region-first method).
    A misalignment raises rather than silently truncating the walk, since a table whose
    OWN declared count and start are known has no legitimate reason to drift.
    """
    anchor = _comp_table_anchor(mm)
    if anchor is None:
        return None, None
    start, count = anchor
    comps = {}
    n_blank = 0
    p = start
    for i in range(count):
        cid = int.from_bytes(mm[p:p + 2], "little")
        if cid != i:
            raise ValueError(f"comp table walk misaligned at slot {i}: read cid={cid}, "
                              f"offset={p}")
        rec, p = _read_comp_slot(mm, p)
        if rec is None:
            n_blank += 1
        else:
            comps[cid] = rec
    return comps, n_blank

# ---- named reject reasons -----------------------------------------------------------
# Both _build_refdata_index and diagnose_refdata_scan (below) call the SAME
# _eval_club_candidate/_eval_comp_candidate functions -- there is exactly one
# implementation of "is this a valid club/comp record", so the real scan and its audit
# cannot silently drift apart the way a hand-copied second walk could.
CLUB_REJECT_UID_RANGE = "uid_outside_admission_bands"
CLUB_REJECT_LONG_LEN = "long_name_length_out_of_range"
CLUB_REJECT_LONG_INVALID = "long_name_undecodable"
CLUB_REJECT_SHORT_INVALID = "short_name_undecodable"
CLUB_REJECT_FILL_NO_MARKER = "fill_tier_missing_trailer_marker"

COMP_REJECT_ALREADY_RESOLVED = "cid_already_resolved"          # not a defect -- excluded
                                                                 # from reject tallies
COMP_REJECT_LONG_LEN = "long_name_length_out_of_range"
COMP_REJECT_LONG_UNDECODABLE = "long_name_undecodable"
COMP_REJECT_LONG_SHAPE = "long_name_shape_invalid"
# The empty-CODE bug (a real, auto-generated competition like "<Nation> Reserves Group <N>"
# has a genuinely empty short code) is FIXED 2026-09-17 -- see the name-walk loop below,
# which now accepts sl==0 for slots 1/2. There used to be a COMP_REJECT_NAME_WALK_SLOT3_EMPTY
# reason naming it specifically; it's retired rather than kept as dead code that can never
# fire again. docs/TODO.md #10 has the before/after.
COMP_REJECT_NAME_WALK_ABORTED = "name_walk_aborted_other"      # any other out-of-range slot
COMP_REJECT_TRAILER_OOB = "trailer_runs_past_buffer_end"
# The type-value whitelist this named (a candidate's type byte outside a 5-value dict) is
# RETIRED 2026-09-18 -- it was rejecting real competitions (cid 13 "French Regional
# Divisions" among ~20 other genuine type values), not filtering noise; see COMP_TYPES'
# comment for the evidence. Kept as a name, not deleted, so old diagnostics/docs referencing
# it still resolve; it can no longer fire.
COMP_REJECT_TYPE = "comp_type_unrecognised"
COMP_REJECT_CONTINENT_SIG = "comp_continent_signature_mismatch"
COMP_REJECT_NATION_RANGE = "comp_nation_id_out_of_range"
COMP_REJECT_REPUTATION_FLOOR = "comp_reputation_below_floor"   # the reputation-floor bug:
                                                                 # a real, low-reputation
                                                                 # competition (e.g. "Danish
                                                                 # Second Division East",
                                                                 # reputation 0) fails a
                                                                 # tuned _MIN_COMP_REP floor
                                                                 # meant to reject name-
                                                                 # collision garbage
COMP_REJECT_SHORT_LONGER_THAN_LONG = "comp_short_name_longer_than_long"  # added 2026-09-18
                                                                 # alongside the reputation
                                                                 # ceiling -- every one of
                                                                 # 1,065 genuine competitions
                                                                 # has len(short) <=
                                                                 # len(long); exactly one
                                                                 # candidate breaks it
                                                                 # ("British Virgin Is." /
                                                                 # "British Virgin Islands",
                                                                 # code "VGB" -- almost
                                                                 # certainly a NATION record
                                                                 # coinciding with this
                                                                 # record's byte shape, same
                                                                 # class of leak as the
                                                                 # continent-tree reputation
                                                                 # outliers above
COMP_REJECT_REPUTATION_IMPLAUSIBLE = "comp_reputation_implausible"  # ceiling, not floor --
                                                                 # added 2026-09-18 alongside
                                                                 # the continent-enum widening.
                                                                 # Every genuine competition
                                                                 # measured tops out at 200
                                                                 # (European Champions Cup);
                                                                 # exactly 4 candidates read
                                                                 # 24,933-29,810 -- "Africa"/
                                                                 # "Europe"/"Asia"/"North
                                                                 # America" with a parent_cid
                                                                 # chain and a single-digit uid,
                                                                 # almost certainly the
                                                                 # unparsed Region table
                                                                 # (docs/TODO.md #9) coinciding
                                                                 # with this record's byte
                                                                 # shape by chance, not a
                                                                 # competition at all


class ClubCandidate(NamedTuple):
    accepted: bool
    reason: object          # None if accepted
    tid: int
    tier: object            # 0 or 1, only if accepted
    rec: object              # dict, only if accepted


class CompCandidate(NamedTuple):
    accepted: bool
    reasons: list            # empty if accepted; a rejected candidate carries >=1
    cid: int
    tier: object             # 0 or 1, only if accepted -- see _eval_comp_candidate
    rec: object              # dict, only if accepted


def _candidate_positions(mm):
    """(lo, hi, nmax, cand) for the club/comp reference-data scan: the window bounds, the
    file length, and the numpy-derived array of absolute offsets whose u32 reads as a
    plausible name-length field (2..60), with room to look back 8 bytes for a club header.
    Both `_build_refdata_index` and `diagnose_refdata_scan` call this so the candidate set
    used for real extraction and the candidate set used for diagnosis are the SAME array."""
    lo, hi = _refdata_window(mm)
    n = hi - lo
    buf = np.frombuffer(mm, dtype=np.uint8, count=n, offset=lo)
    # u32 LE at every offset q within the window (q relative to lo)
    u32 = (buf[:-3].astype(np.uint32) | (buf[1:-2].astype(np.uint32) << 8)
           | (buf[2:-1].astype(np.uint32) << 16) | (buf[3:].astype(np.uint32) << 24))
    # candidate = position of a plausible name-length field: club needs [2,60], comp
    # needs [3,45] — [2,60] covers both, so this one filter serves either branch below.
    # NOTE: this prefilter itself is a tuned constant, same class as the ones it feeds --
    # a record whose length field falls outside [2,60], or that has no length prefix at
    # all, is invisible to every candidate this scan ever considers. See
    # diagnose_refdata_scan's byte-coverage figure, which is the one honest measurement
    # of what this prefilter can never see (currently 1.76% of the window IS a candidate;
    # the rest is either genuinely other content, padding, or exactly this blind spot).
    cand = np.flatnonzero((u32 >= 2) & (u32 <= 60))
    cand = cand[cand >= 8]      # room to look back 8 bytes for the club header (TID+UID)
    # Exclude the real NATION table -- see _nation_table_bounds' docstring. Its
    # name/nationality/code triplets share this exact candidate shape, so without this a
    # nation string can resolve as a fake club or competition under a bogus id read from
    # neighbouring bytes that were never meant to be an id at all.
    nation_bounds = _nation_table_bounds(mm)
    if nation_bounds is not None:
        nlo, nhi = nation_bounds
        cand = cand[(cand + lo < nlo) | (cand + lo > nhi)]
    # Exclude the real NAME (browse) table -- see _name_table_bounds' docstring. Same
    # collision class as the nation table: a flat run of length-prefixed strings at the
    # very start of the file can, rarely, coincidentally satisfy every comp/club gate.
    name_bounds = _name_table_bounds(mm)
    if name_bounds is not None:
        nmlo, nmhi = name_bounds
        cand = cand[(cand + lo < nmlo) | (cand + lo > nmhi)]
    return lo, hi, len(mm), cand


def _eval_club_candidate(mm, q):
    """The club gate cascade for the candidate at length-field offset q, as a pure function
    of (mm, q) -- no dependency on the running `clubs`/`tiers` state, so it can be called
    identically by `_build_refdata_index` (which arbitrates the winner across candidates for
    the same tid) and by `diagnose_refdata_scan` (which tallies every candidate's own
    disposition). Every guard below is the original inline `if` chain, converted to an
    early-return so each has a name -- no condition changed, none reordered.

    No range check on tid itself (an earlier version guessed `100 < tid < 70000` to cut
    candidate volume, but real club tids go as low as 51 — Boca Juniors, River Plate and 24
    others in one real save all sit in [51,78] and would have been silently dropped).
    Structural validation only, matching the old per-tid scan.
    """
    tid = int.from_bytes(mm[q - 8:q - 4], "little")
    uid = int.from_bytes(mm[q - 4:q], "little")
    # TIER 0 is the long-standing gate; TIER 1 is a strictly gap-FILLING second tier for
    # the ~2-billion uid band (see _CLUB_UID_FILL_LO below). A tier-1 record can never
    # displace a tier-0 one, so this cannot change a club name that resolves today.
    primary = 1 <= uid <= 400_000_000
    fill = (not primary
            and _CLUB_UID_FILL_LO <= uid <= _CLUB_UID_FILL_HI
            and tid <= 0xFFFF)
    if not (primary or fill):
        return ClubCandidate(False, CLUB_REJECT_UID_RANGE, tid, None, None)

    ln = int.from_bytes(mm[q:q + 4], "little")
    if not (2 <= ln <= 60):
        return ClubCandidate(False, CLUB_REJECT_LONG_LEN, tid, None, None)
    long_name = _valid_name(mm[q + 4:q + 4 + ln])
    if not long_name:
        return ClubCandidate(False, CLUB_REJECT_LONG_INVALID, tid, None, None)
    short_name = _short_after(mm, q + 4 + ln)
    if not short_name:
        return ClubCandidate(False, CLUB_REJECT_SHORT_INVALID, tid, None, None)

    p = q                        # walk past the 3 length-prefixed strings
    for _ in range(3):
        sl = int.from_bytes(mm[p:p + 4], "little")
        if not (2 <= sl <= 60):
            p += 1
            sl = int.from_bytes(mm[p:p + 4], "little")
        if not (2 <= sl <= 60):
            p = None
            break
        p = p + 4 + sl
    rec = {"name": long_name, "short": short_name,
           # the club's UID -- a second id space, distinct from the tid the rest of the
           # codebase joins on. Carried because a table that references clubs by uid is
           # invisible to any tid search.
           "uid": uid,
           "league": None, "country": None,
           # offset of the trailer (first byte after the 3 names), so client_details() can
           # read the rest of the record without re-locating it. See parse_club_trailer.
           "trailer": p}
    marker = p is not None and mm[p + 160:p + 162] == b"\xff\xff"
    if p is not None:
        rec["country"] = int.from_bytes(mm[p:p + 2], "little")
        if marker:
            code = int.from_bytes(mm[p + 158:p + 160], "little")
            if code and code != 0xffff:
                rec["league"] = code
    # A tier-1 candidate must carry the club trailer marker. Person records match the
    # [tid][uid][len][long][len][short] shape too -- a first name followed by a surname --
    # and without this they fill empty tids with surnames ('Kjell', 'De Vriese',
    # 'Sickinger' at tids 867-876). The marker costs 9 of 336 fills and removes all 9 of
    # those. A wrong club name is worse than a missing one. A trailer-walk failure
    # (p is None) is NOT itself a rejection for a primary-tier candidate -- it is accepted
    # with `trailer`/`league`/`country` left as None, same as the original code.
    if fill and not marker:
        return ClubCandidate(False, CLUB_REJECT_FILL_NO_MARKER, tid, None, None)
    return ClubCandidate(True, None, tid, 0 if primary else 1, rec)


def _club_wins(existing_tier, existing_rec, new_tier, new_rec):
    """True if `new` should replace `existing` in the club index -- prefer the lower tier;
    within a tier, prefer the copy carrying `league`. Extracted so `_build_refdata_index`
    and `diagnose_refdata_scan` classify a structurally-valid-but-outbid candidate
    (SUPERSEDED) identically."""
    if existing_rec is None:
        return True
    if new_tier != existing_tier:
        return new_tier < existing_tier
    return existing_rec["league"] is None and new_rec["league"] is not None


def _eval_comp_candidate(mm, q, nmax, resolved_tiers):
    """The comp gate cascade for the candidate at length-field offset q. `resolved_tiers` is
    a {cid: tier} map, checked via `resolved_tiers.get(cid) == 0` -- short-circuit ONLY when
    the best possible tier is already resolved for this cid, so a later tier-0 candidate can
    still improve on an earlier tier-1 (reputation-floor gap-fill) hit for the same cid. The
    real scan passes the `comp_tiers` dict it's building; the diagnostic passes its own.

    Structural gates (name decode, name walk, buffer bounds, continent/nation/implausible-
    reputation) short-circuit in order, because a later gate is meaningless without the
    earlier one succeeding -- you cannot test reputation on a trailer that was never
    located. Once a candidate clears every structural gate, LOW reputation decides the TIER
    (see below) rather than accept/reject. There used to be a fourth structural gate on the
    trailer's `type` byte; it's retired (2026-09-18, see COMP_TYPES' comment) -- it was
    rejecting real competitions (cid 13 among ~20 confirmed real type values), and every
    actual noise candidate checked was already caught by continent/nation/reputation
    regardless, so it was never doing filtering work of its own.
    """
    cid = int.from_bytes(mm[q - 6:q - 4], "little")
    if resolved_tiers.get(cid) == 0:
        return CompCandidate(False, [COMP_REJECT_ALREADY_RESOLVED], cid, None, None)

    uid = int.from_bytes(mm[q - 4:q], "little")
    ln = int.from_bytes(mm[q:q + 4], "little")
    if not (3 <= ln <= _COMP_NAME_CAP):
        return CompCandidate(False, [COMP_REJECT_LONG_LEN], cid, None, None)
    try:
        long = mm[q + 4:q + 4 + ln].decode("utf-8")
    except UnicodeDecodeError:
        return CompCandidate(False, [COMP_REJECT_LONG_UNDECODABLE], cid, None, None)
    # league names can start with a digit ('3. Division', '2. Bundesliga') or lowercase --
    # real sponsor branding is deliberately lowercase ('cinch Premiership', 'cinch
    # Championship', 'cinch League 1/2' -- the actual Scottish top-flight sponsor since
    # 2022). Widened 2026-09-18; sum(isalpha) >= 3 still does the real noise filtering.
    if not (long and (long[0].isalpha() or long[0].isdigit())
            and sum(c.isalpha() for c in long) >= 3):
        return CompCandidate(False, [COMP_REJECT_LONG_SHAPE], cid, None, None)

    # STRUCTURAL, not sniffed: exactly ONE terminator byte follows the long name and the
    # short name; the code name (last of the three) has none before the trailer. This was
    # a plausibility guess until 2026-09-18 -- "if the next u32 doesn't look like a valid
    # length, assume there's a terminator byte in the way and skip it" -- which is provably
    # ambiguous whenever a short/code name is genuinely EMPTY (length 0, allowed since
    # 2026-09-17 for auto-generated competitions like "<Nation> Reserves Group <N>") and its
    # own preceding terminator byte happens to be 0x00: four zero bytes (imaginary
    # terminator + the true zero-length field) is indistinguishable from the true zero-length
    # field alone, so the guess sees a "plausible" empty name and never skips the terminator,
    # misaligning the trailer by 1 byte. Confirmed on cid 172 "Welsh First Division" -- a
    # real, clean top-flight-adjacent league with reputation 19, silently dropped because its
    # empty code field followed a 0x00 terminator. Removing the guess in favour of the known
    # fixed byte count recovered 134 more real competitions on this save with zero losses and
    # zero changed records elsewhere (verified against the old heuristic candidate-for-
    # candidate).
    p = q + 4 + ln
    names = [long]
    for slot in (1, 2):
        p += 1
        sl = int.from_bytes(mm[p:p + 4], "little")
        ok_len = (1 <= sl <= _COMP_NAME_CAP) or sl == 0
        if not ok_len or p + 4 + sl > nmax:
            return CompCandidate(False, [COMP_REJECT_NAME_WALK_ABORTED], cid, None, None)
        if sl == 0:
            names.append("")
        else:
            try:
                names.append(mm[p + 4:p + 4 + sl].decode("utf-8"))
            except UnicodeDecodeError:
                names.append(None)
        p = p + 4 + sl
    if p + 14 > nmax:
        return CompCandidate(False, [COMP_REJECT_TRAILER_OOB], cid, None, None)

    typ, nation = mm[p], mm[p + 3]
    # `gate` is the ORIGINAL reputation expression. It is NOT the reputation (see below) —
    # it is kept verbatim, and only as an acceptance test, so that which competitions
    # resolve is unchanged by this refactor. Retuning it is a separate, riskier change:
    # this value decides whether a league gets a name at all.
    gate = int.from_bytes(mm[p + 8:p + 10], "little")
    # The real trailer, per fmm-editor's FMM26 `Competition`:
    #   p+0 type u8 | p+1 continent u16 | p+3 nation u16
    #   p+5 fg colour u16 | p+7 bg colour u16
    #   p+9 REPUTATION u16 | p+11 LEVEL u8 | p+12 parent cid u16
    # `gate` reads one byte early, so it is the bg colour's high byte plus reputation<<8 --
    # roughly 256x the real value and contaminated by a colour. It stays monotonic only
    # while reputation < 256, so ordering by it was luck, not design.
    rep = int.from_bytes(mm[p + 9:p + 11], "little")
    level = mm[p + 11]
    parent = int.from_bytes(mm[p + 12:p + 14], "little")
    # trailer signature: nation-bound leagues/cups are [type][continent u16][nation]; friendlies
    # (type 9) are [9][ff][ff][ff]. Anything else is a colliding non-comp record. The gate
    # floor kills rep-0 round-label collisions ('First Leg', 'Playoff').
    #
    # `continent` is a real FIFA-confederation enum, not a Europe-only flag -- corrected
    # 2026-09-18. The check used to hardcode `== 2` on the theory that "this save loads only
    # European competitions"; that theory was never actually true, it just never got tested,
    # because every confederation cup was ALSO being dropped by the (now-retired) type gate,
    # so continent==2-only never got a chance to matter for them.
    # Measured directly off the file: cid 61 Copa Libertadores (continent=5, S. America), 79
    # Oceania Champions League (4), 80 Asian Champions League (1), 81 African Champions
    # League (0), 256 European Champions Cup (2), 732 North American Champions League (3) --
    # all six FIFA confederations, 0-5. Widen to that range rather than removing the check
    # entirely: nation==0 (seen on every coincidental non-comp candidate this widening could
    # otherwise let through) still fails COMP_REJECT_NATION_RANGE regardless.
    # STRUCTURAL gates (continent/nation/implausible-reputation) and the reputation FLOOR are
    # split apart on purpose. Fixed 2026-09-17 (docs/TODO.md #10): a candidate that clears
    # every structural gate and fails ONLY on the low-reputation floor is a real, low-prestige
    # competition, not
    # garbage -- Danish Second Division East (gate=104), Greek Football League North, several
    # Northern Irish/Welsh/Polish regional divisions, all confirmed by name. TIER 0 is the
    # original combined gate; TIER 1 is a strictly gap-filling second tier admitting a
    # candidate ONLY when every structural gate passed and reputation alone didn't -- same
    # shape as the club uid-ceiling fix above (tier 1 never displaces tier 0, never admits a
    # candidate that failed a structural gate). `gate` is the ORIGINAL reputation expression,
    # kept verbatim rather than switched to the real `rep` field below, so this fix touches
    # only the previously-hopeless population and cannot change which cid a tier-0 candidate
    # already resolves to.
    continent = int.from_bytes(mm[p + 1:p + 3], "little")
    structural_reasons = []
    # continent==0xFFFF is the same "no confederation" sentinel already known for type-9
    # friendlies -- corrected 2026-09-18, it isn't actually tied to type 9 at all. Genuinely
    # global competitions use it too: type 6 "Confederations Cup"/"World Cup"/"World Cup
    # Playoff", type 12 "Club World Championship" -- all real, all previously dropped.
    if not (continent <= 5 or typ == 9 or continent == 0xFFFF):
        structural_reasons.append(COMP_REJECT_CONTINENT_SIG)
    if not ((1 <= nation <= 250) or nation == 255):
        structural_reasons.append(COMP_REJECT_NATION_RANGE)
    if rep > 1000:
        structural_reasons.append(COMP_REJECT_REPUTATION_IMPLAUSIBLE)
    if names[1] is not None and len(names[1]) > len(names[0]):
        structural_reasons.append(COMP_REJECT_SHORT_LONGER_THAN_LONG)
    low_reputation = gate < _MIN_COMP_REP
    if structural_reasons:
        # A candidate that fails a structural gate is hopeless regardless of reputation, but
        # low_reputation is still tallied here (comp_reject_candidates/ids) for the
        # "independent gate cost" picture -- never comp_reject_solo, since it isn't alone.
        if low_reputation:
            structural_reasons.append(COMP_REJECT_REPUTATION_FLOOR)
        return CompCandidate(False, structural_reasons, cid, None, None)

    rec = {"cid": cid, "uid": uid, "name": names[0], "short": names[1], "code": names[2],
           "type": COMP_TYPES.get(typ, f"type_{typ}"), "type_id": typ,
           "nation_id": None if nation == 255 else nation, "reputation": rep,
           # 0 = top flight of its nation. Verified: Turkish Super League 0, NordicBet
           # Liga 1, 2. Division 2, 3. Division 3. Confederation-style records carry junk
           # here (100/112) — filter on type before use.
           "level": level,
           "parent_cid": None if parent == 0xFFFF else parent}
    return CompCandidate(True, [], cid, 1 if low_reputation else 0, rec)


def _build_refdata_index(mm):
    key = id(mm)
    cached = _REFDATA_INDEX_CACHE.get(key)
    if cached is not None:
        return cached
    lo, hi, nmax, cand = _candidate_positions(mm)

    clubs = {}
    tiers = {}                  # tid -> which gate admitted the stored record (0 beats 1)
    comps, _n_blank = _walk_comp_table(mm)
    use_walk = comps is not None
    comp_tiers = {}             # cid -> which gate admitted the stored record (0 beats 1)
    if not use_walk:
        comps = {}

    for off in cand.tolist():
        q = off + lo             # absolute offset of the length field

        cc = _eval_club_candidate(mm, q)
        if cc.accepted:
            existing = clubs.get(cc.tid)
            if _club_wins(tiers.get(cc.tid), existing, cc.tier, cc.rec):
                clubs[cc.tid] = cc.rec
                tiers[cc.tid] = cc.tier

        # Competitions come from the pure structural walk above (_walk_comp_table) since
        # 2026-09-18 -- see its docstring. The candidate-scan-plus-gates path
        # (_eval_comp_candidate) only still runs here as a fallback for a save/career where
        # the table's own count-header anchor can't be found.
        if not use_walk:
            comp_cc = _eval_comp_candidate(mm, q, nmax, comp_tiers)
            if comp_cc.accepted:
                if comp_cc.cid not in comp_tiers or comp_cc.tier < comp_tiers[comp_cc.cid]:
                    comps[comp_cc.cid] = comp_cc.rec
                    comp_tiers[comp_cc.cid] = comp_cc.tier

    result = (clubs, comps)
    _REFDATA_INDEX_CACHE[key] = result
    return result


class RefdataDiagnosis(NamedTuple):
    n_window_bytes: int
    n_candidates: int
    club_accepted_tier0: int         # tids WON at tier 0 (winners only, not every hit)
    club_accepted_tier1: int         # tids WON at tier 1
    club_superseded: int             # structurally valid, but an earlier/better candidate
                                       # for the same tid already won
    club_reject_candidates: object   # Counter: reason -> candidate occurrences
    club_reject_ids: object          # Counter: reason -> DISTINCT tids ever rejected for it
    club_rejections: list            # [(offset, tid, reason), ...]
    comp_accepted_tier0: int         # cids WON at tier 0 (every structural gate + the
                                       # reputation floor passed)
    comp_accepted_tier1: int         # cids WON at tier 1 (structural gates passed, low
                                       # reputation -- the reputation-floor fix, 2026-09-17)
    comp_superseded: int             # structurally valid, but an earlier/better candidate
                                       # for the same cid already won
    comp_already_resolved: int        # cid-collision skips -- not a defect signal
    comp_reject_candidates: object    # Counter: reason -> candidate occurrences. The
                                       # STRUCTURAL gates (continent/nation/implausible-
                                       # reputation -- NOT type, retired 2026-09-18) are
                                       # counted INDEPENDENTLY (a candidate failing 2 at once
                                       # counts against both); COMP_REJECT_REPUTATION_FLOOR only
                                       # appears here for a candidate that ALSO failed a
                                       # structural gate -- a low-reputation candidate that
                                       # passes everything else is ACCEPTED at tier 1, not
                                       # rejected, so it never reaches this Counter at all.
    comp_reject_ids: object           # Counter: reason -> DISTINCT cids ever rejected for it
                                       # (same caveat as comp_reject_candidates)
    comp_reject_solo_candidates: object   # Counter: reason -> candidate occurrences whose
                                       # ONLY failed gate is this one -- a candidate here
                                       # passed every other structural gate and would resolve
                                       # today if just this one were relaxed. For the three
                                       # structural gates, this is still the actionable
                                       # number; COMP_REJECT_REPUTATION_FLOOR will read 0
                                       # here now that reputation-only failures are tier-1
                                       # ACCEPTS rather than rejects (kept as a live check
                                       # that the fix didn't regress -- see
                                       # tests/test_refdata_scan.py).
    comp_reject_solo_ids: object      # Counter: reason -> DISTINCT cids, solo-failure basis
    comp_rejections: list             # [(offset, cid, reasons), ...]


def diagnose_refdata_scan(mm):
    """Per-candidate disposition for every position `_build_refdata_index` considers:
    accepted (club and/or comp, with tier for clubs), rejected (one or more named reasons),
    or superseded (structurally valid, but a better/earlier candidate already won that
    tid/cid). Calls `_eval_club_candidate`/`_eval_comp_candidate` -- the SAME functions
    `_build_refdata_index` uses -- so this cannot drift from what the real scan actually
    does.

    Deliberately bypasses `_REFDATA_INDEX_CACHE`: this is for a human (or a script) running
    an audit, not the extract.py hot path, and re-derives the candidate array fresh.

    IMPORTANT: this covers 1.76% of the window on a real save (351,682 of 20,000,000
    bytes) -- one candidate per ~57 bytes. It answers "of the positions that LOOK like a
    name-length field, what happened to each one", not "what is every byte in this
    window". A record whose length field falls outside [2,60], or that has no length
    prefix at all, never becomes a candidate and is invisible here by construction — see
    _candidate_positions' note.

    Reject counts alone are not proof of a real gap, in TWO separate ways this function was
    caught making before shipping -- both now fixed (2026-09-17, docs/TODO.md #10), kept as
    HISTORICAL examples of the caution because the same traps apply to whatever gate is next:
      1. `comp_reject_candidates`/`comp_reject_ids` count a candidate against EVERY gate it
         fails, independently. Before the reputation floor got its own tier,
         COMP_REJECT_REPUTATION_FLOOR showed 9,410 candidates / 1,031 distinct cids that way
         -- but the SOLO count (the same reason, counted only when it was the sole failure)
         showed 47. The other 984 cids also failed type/continent/nation and would never
         have resolved regardless of the floor; a fix could only ever recover the 47 (which
         is exactly why the fix is a TIER, not a relaxed threshold -- see
         _eval_comp_candidate). Use the `solo` Counters for "how many real records would
         this specific fix recover", non-solo only for "how much noise touches this gate".
      2. Even a solo/isolated reject count isn't proof of NEED. Before the empty-CODE bug
         was fixed, its reason hit 164 distinct cids (solo, since a name-walk abort
         short-circuited before any other gate ran) but only ~30 were genuine
         "<Nation> Reserves Group <N>" competitions -- the other ~134 were coincidental
         non-records sharing the same failure shape. Cross-referencing rejected ids against
         ids something else in the save actually REFERENCES (a match's
         comp_id/home_tid/away_tid, a player's club_tid) is what separates a real gap from
         noise -- see scripts/audit_declared_scans.py.
    """
    lo, hi, nmax, cand = _candidate_positions(mm)
    club_reject_candidates, comp_reject_candidates = collections.Counter(), collections.Counter()
    club_reject_id_sets = collections.defaultdict(set)
    comp_reject_id_sets = collections.defaultdict(set)
    comp_reject_solo_candidates = collections.Counter()
    comp_reject_solo_id_sets = collections.defaultdict(set)
    club_rejections, comp_rejections = [], []
    club_accepted_tier0 = club_accepted_tier1 = club_superseded = 0
    comp_accepted_tier0 = comp_accepted_tier1 = comp_superseded = 0
    comp_already_resolved = 0
    clubs_seen, tiers_seen = {}, {}
    comp_tiers_seen = {}

    for off in cand.tolist():
        q = off + lo

        cc = _eval_club_candidate(mm, q)
        if cc.accepted:
            existing = clubs_seen.get(cc.tid)
            prior_tier = tiers_seen.get(cc.tid)
            if _club_wins(prior_tier, existing, cc.tier, cc.rec):
                # A cid/tid can win TWICE across this scan -- first at tier 1, later
                # upgraded by a tier-0 candidate. Counting both wins as separate accepts
                # double-counts that one tid; undo the earlier tier's count on an upgrade
                # so each tid is counted exactly once, in its FINAL tier.
                if prior_tier == 1:
                    club_accepted_tier1 -= 1
                clubs_seen[cc.tid] = cc.rec
                tiers_seen[cc.tid] = cc.tier
                if cc.tier == 0:
                    club_accepted_tier0 += 1
                else:
                    club_accepted_tier1 += 1
            else:
                club_superseded += 1
        else:
            club_reject_candidates[cc.reason] += 1
            club_reject_id_sets[cc.reason].add(cc.tid)
            club_rejections.append((q, cc.tid, cc.reason))

        comp_cc = _eval_comp_candidate(mm, q, nmax, comp_tiers_seen)
        if comp_cc.accepted:
            prior_comp_tier = comp_tiers_seen.get(comp_cc.cid)
            if prior_comp_tier is None or comp_cc.tier < prior_comp_tier:
                # same double-counting trap as the club branch above: undo the earlier
                # tier's count on an upgrade so each cid is counted exactly once
                if prior_comp_tier == 1:
                    comp_accepted_tier1 -= 1
                comp_tiers_seen[comp_cc.cid] = comp_cc.tier
                if comp_cc.tier == 0:
                    comp_accepted_tier0 += 1
                else:
                    comp_accepted_tier1 += 1
            else:
                comp_superseded += 1
        elif comp_cc.reasons == [COMP_REJECT_ALREADY_RESOLVED]:
            comp_already_resolved += 1
        else:
            for r in comp_cc.reasons:
                comp_reject_candidates[r] += 1
                comp_reject_id_sets[r].add(comp_cc.cid)
            if len(comp_cc.reasons) == 1:
                solo = comp_cc.reasons[0]
                comp_reject_solo_candidates[solo] += 1
                comp_reject_solo_id_sets[solo].add(comp_cc.cid)
            comp_rejections.append((q, comp_cc.cid, comp_cc.reasons))

    club_reject_ids = collections.Counter({r: len(ids) for r, ids in club_reject_id_sets.items()})
    comp_reject_ids = collections.Counter({r: len(ids) for r, ids in comp_reject_id_sets.items()})
    comp_reject_solo_ids = collections.Counter(
        {r: len(ids) for r, ids in comp_reject_solo_id_sets.items()})

    return RefdataDiagnosis(hi - lo, len(cand), club_accepted_tier0, club_accepted_tier1,
                             club_superseded, club_reject_candidates, club_reject_ids,
                             club_rejections, comp_accepted_tier0, comp_accepted_tier1,
                             comp_superseded, comp_already_resolved,
                             comp_reject_candidates, comp_reject_ids,
                             comp_reject_solo_candidates, comp_reject_solo_ids,
                             comp_rejections)


# ---------------- club record trailer ----------------
# Everything after the three name strings. Field order from nyongrand/fmm-editor's FMM26
# `Club`; see docs/agent-context/fmm-editor-record-comparison.md. Verified on the Danish
# Superliga: LeagueId reads 2 for every top-flight club (and we know Superliga is cid 2),
# attendances rank the clubs by real size, and the colours decode to the right kits.
#
# A Color is a u16 in RGB555 (r = (c >> 10) & 0x1f, each channel << 3). That is what the
# 0x7FFF flood in this region is -- 0x7FFF is white -- NOT the "sentinel" that BUGS #15
# originally read it as, and not stadium/finance data.
_CLUB_SQUAD_SLOTS = 40      # fixed-size array: exactly 40 for all 10,788 clubs in the save
_CLUB_STAFF_SLOTS = 11
_AFFILIATE_SIZE = 21        # [unk u32][club1 u32][club2 u32][start d/y u16][end d/y u16][unk u8]
_NO_ID = (0, 0xFFFF, 0xFFFFFFFF)


def _rgb(c):
    """RGB555 u16 -> '#rrggbb'."""
    return "#%02x%02x%02x" % (((c >> 10) & 0x1f) << 3, ((c >> 5) & 0x1f) << 3, (c & 0x1f) << 3)


def parse_club_trailer(mm, p):
    """Parse the club record trailer at `p`, or None if it runs off the end.

    NOTE `country` (p+0) and `nation_id` (p+2) are equal for 10,716 of 10,788 clubs and
    differ for 72 — consistent with a based-in vs competes-in split (a Monaco/Derry City
    case), but which is which is NOT verified, so both are kept verbatim.
    """
    u16 = lambda o: int.from_bytes(mm[o:o + 2], "little")
    u32 = lambda o: int.from_bytes(mm[o:o + 4], "little")
    if p is None or p + 200 > len(mm):
        return None
    d = {
        "based_id": u16(p), "nation_id": u16(p + 2),
        "colours": [_rgb(u16(p + 4 + 2 * i)) for i in range(6)],
        # 6 kits of [2 flag bytes][10 colours]; stored whole because which slot is home vs
        # away is not established.
        "kits": [[_rgb(u16(p + 16 + 22 * k + 2 + 2 * i)) for i in range(10)]
                 for k in range(6)],
        "status": mm[p + 148], "academy": mm[p + 149], "facilities": mm[p + 150],
        "att_avg": u16(p + 151), "att_min": u16(p + 153), "att_max": u16(p + 155),
        "reserves": mm[p + 157],
        "league_id": u16(p + 158),
        "other_division": u16(p + 160), "other_last_position": mm[p + 162],
        "stadium_id": u16(p + 163), "last_league": u16(p + 165),
    }
    q = p + 167
    n5 = u32(q)
    if n5 > 4096:
        return d
    q += 4 + n5
    d["league_pos"] = mm[q]; q += 1
    d["reputation"] = u16(q); q += 2
    # 20 bytes we step over WITHOUT having decoded them. Not padding as far as we know --
    # just unread. The affiliate count lands correctly on the far side of it for 11,080
    # clubs, which is what says the width is right; it says nothing about the content.
    # Named here rather than left as a bare `+= 20`, because an undeclared skip is exactly
    # how the player record's last 13 bytes stayed unread for four years.
    _CLUB_TRAILER_UNDECODED = 20
    q += _CLUB_TRAILER_UNDECODED
    naff = u16(q); q += 2
    if naff > 64:
        return d
    affs = []
    for _ in range(naff):
        affs.append({"club1_tid": u32(q + 4), "club2_tid": u32(q + 8),
                     "start_day": u16(q + 12), "start_year": u16(q + 14),
                     "end_day": u16(q + 16), "end_year": u16(q + 18)})
        q += _AFFILIATE_SIZE
    d["affiliates"] = affs
    npl = u16(q); q += 2
    if npl != _CLUB_SQUAD_SLOTS:
        return d                       # shape we do not recognise: stop rather than guess
    d["squad"] = [t for t in (u32(q + 4 * i) for i in range(npl)) if t not in _NO_ID]
    q += 4 * npl
    # The club's STAFF list -- and it EXCLUDES the manager, which is what makes
    # mart.club_managers exact rather than a reputation heuristic: of the staff whose info
    # record points at this club, the one missing from here is the man in charge. Verified
    # on all 7 ground-truth clubs, exactly one candidate each.
    d["staff"] = [t for t in (u32(q + 4 * i) for i in range(_CLUB_STAFF_SLOTS))
                  if t not in _NO_ID]
    q += 4 * _CLUB_STAFF_SLOTS
    main = u32(q)
    # Parent club. EVERY reserve side (club_type 2) carries one and it resolves exactly --
    # "KAA Gent Reserves" -> "KAA Gent", Frem's 7296 -> 346 -- so this is the structural
    # replacement for the hardcoded reserve_tid in careers.py. 186 of 4,291 first teams carry
    # one too (B-teams and the like). The rest hold a negative value we have not decoded
    # (-7298 for Frem, -2685 for AaB), so anything outside a plausible tid range is dropped
    # rather than guessed at.
    d["main_club_tid"] = main if 0 < main < 70000 else None
    d["club_type"] = mm[q + 4]
    return d


def club_details(mm, tid):
    """Full club record (names + the whole trailer) for a tid, or None."""
    rec = _build_refdata_index(mm)[0].get(tid)
    if not rec:
        return None
    out = {"tid": tid, "name": rec["name"], "short": rec["short"],
           "league_cid": rec["league"], "country": rec["country"]}
    t = parse_club_trailer(mm, rec.get("trailer"))
    if t:
        out.update(t)
    return out


def resolve_club(mm, tid, want="long"):
    """Club name for a TID, or None. Requires the full club shape (long name
    followed by a valid short name) so regions/stadiums/collisions are rejected."""
    rec = _build_refdata_index(mm)[0].get(tid)
    if not rec:
        return None
    return rec["short"] if want == "short" else rec["name"]


def club_map(mm, tids, want="long"):
    return {t: resolve_club(mm, t, want) for t in tids}


def club_record(mm, tid, want="long"):
    """A club's record: {'name','short','league','country'} or None.

    `league` is the club's league code, read from `[code u16][ff ff]` at +158 past the
    three name strings (the club.dat model — see docs; verified: Man City=5 English Prem,
    Boldklubben Frem=1147 Danish 3. Division). This is club->league membership that exists
    on day-1, before any match is played. The club DB is split across several file
    segments; the index prefers the copy carrying the league field (secondary copies read
    0 / ff ff), same as the old per-tid scan. `country` is the compete-in country code
    (Denmark=138/0x8a, England=139/0x8b)."""
    rec = _build_refdata_index(mm)[0].get(tid)
    if not rec:
        return None
    return {"name": rec["name"] if want == "long" else rec["short"],
            "short": rec["short"], "league": rec["league"], "country": rec["country"]}


# ---------------- competitions ----------------
def comp_id_at(mm, date_off):
    return int.from_bytes(mm[date_off - 3:date_off - 1], "little")


_COMP_CACHE = {}


def find_comp_record(mm, cid):
    """VALID competition record for `cid` -> full detail dict (with reputation), or None.

    A comp record is `[cid u16][uid u32][len u32][long][len][short][len][code]` then a
    trailer whose bytes we read relative to `p` (the first byte after the 3 strings):
    type @p+0, nation @p+3, REPUTATION (u16) @p+8.

    Small cids (2 = Superliga, 3, 4 ...) collide all over the file, so we cannot trust the
    first byte-match — and the UID is NOT a reliable gate (top divisions carry a tiny UID
    like 6/7/22, lower leagues a ~2-billion one, so the old `uid >= 1000` rule silently
    skipped every top flight and fell through to a bogus record, e.g. cid 2 -> 'Belfort'
    instead of '3F Superliga'). Instead we VALIDATE the record structurally: 3 decodable
    length-prefixed names, a known type byte, and the competition-record TRAILER SIGNATURE
    `[type][0x02][0x00][nation]` (bytes p+1==2, p+2==0) — nation-bound leagues/cups all carry
    it, and it's what separates them from nation/confederation records that would otherwise
    validate (e.g. cid 24 -> 'Ivory Coast' rep 54399, above the Premier League). Friendlies
    (type 9) carry no nation and no signature (`[9,255,255,255]`), so they're allowed through
    a type-9 exception. Reputation (u16 @p+8) must be >= _MIN_COMP_REP, which also kills the
    rep-0 round-label collisions ('First Leg', 'Playoff'). First record passing all of that
    (in file order) wins — see `_build_refdata_index`, which builds this alongside the club
    index in the same single pass over the reference-data window.
    """
    return _build_refdata_index(mm)[1].get(cid)


def league_name(mm, code, want="long"):
    """Name for a club-record league code (e.g. 1147 -> '3. Division', 2 -> '3F Superliga').
    League names can start with a digit ('3. Division', '2. Bundesliga')."""
    r = find_comp_record(mm, code)
    if not r:
        return None
    return (r["short"] or r["name"]) if want == "short" else r["name"]


def resolve_comp(mm, cid, want="long"):
    r = find_comp_record(mm, cid)
    if not r:
        return None
    return (r["short"] or r["name"]) if want == "short" else r["name"]


def comp_name(mm, cid, want="long"):
    key = (id(mm), cid, want)
    if key not in _COMP_CACHE:
        _COMP_CACHE[key] = resolve_comp(mm, cid, want)
    return _COMP_CACHE[key]


def comp_detail(mm, cid):
    """Full competition record: cid, uid, name, short, code, type, type_id, nation_id,
    reputation. See find_comp_record for the structural validation."""
    return find_comp_record(mm, cid)


# ---------------- player info field ----------------
# +16 is the NICKNAME field. FFFFFFFF is the "no nickname" sentinel; a player who HAS one
# carries a real nickname id there. Requiring the sentinel — which this function did for its
# whole life — means only players WITHOUT a nickname can ever be found, which is exactly the
# bug fixed in staging.scrape_players (see docs/agent-context/nickname-players-missing.md).
# It survived there because the fix landed in the spine scraper and this second, independent
# copy of the same anchor was missed. Ground truth, frem-2026-03-22: tids 20905 (Carlos Polo)
# and 19471 (Waldo Rubio) both resolve here now and did not before; 9894 (Christian Tue, no
# nickname) is unchanged.
NO_NICKNAME = b"\xff\xff\xff\xff"
# Nickname ids index the same whole-DB name tables as first/last names; the largest real id
# across a full save is ~32k. Matches staging.NAME_ID_MAX — kept in sync deliberately.
_NICK_ID_MAX = 65536


def info_offset(mm, tid):
    """Offset of a player's info record, or None.

    Located by the TID bytes, then validated on a plausible DOB year at +22 and a nickname
    field at +16 that is either the "no nickname" sentinel or a plausible nickname id. The
    sentinel is NOT required: requiring it hides every player who has a nickname.
    """
    le = struct.pack("<I", tid)
    pos = 0
    while True:
        i = mm.find(le, pos)
        if i == -1:
            return None
        pos = i + 1
        nick = mm[i + 16:i + 20]
        if nick != NO_NICKNAME and int.from_bytes(nick, "little") >= _NICK_ID_MAX:
            continue
        year = int.from_bytes(mm[i + 22:i + 24], "little")
        if 1955 <= year <= 2012:
            return i


def parse_info(mm, tid):
    i = info_offset(mm, tid)
    if i is None:
        return None
    u16 = lambda off: int.from_bytes(mm[i + off:i + off + 2], "little")
    u32 = lambda off: int.from_bytes(mm[i + off:i + off + 4], "little")
    day1, year = u16(20), u16(22)
    try:
        dob = (date(year, 1, 1) + timedelta(days=day1)).isoformat()
    except ValueError:
        dob = None
    nat = u16(24)
    return {
        "tid": u32(0), "uid": u32(4),
        "first_name_id": u32(8), "last_name_id": u32(12),
        "dob": dob,
        "nationality_id": nat, "nationality": NATIONS.get(nat, f"#{nat}"),
        "flag28": mm[i + 28],   # likely 'declared national team' (see docs/BUGS.md #6)
        "club_tid": u16(42),
        "sid": mm[i + 60:i + 62].hex(),
    }


# ---------------- player names (whole DB) ----------------
# Names for EVERY player (not just the managed squad) resolve from the info field's
# first_name_id / last_name_id via two structures near the start of the save:
#   1. the "browse" name table (flat [len u32][utf-8], ~46k entries, nation-grouped) —
#      browse[ordinal] = string;
#   2. two dense id-index tables (16-byte records [browse_ordinal u32][id u32][..][..],
#      sorted by id from 0) — one for first names, one for surnames. name_id indexes these
#      to get the browse ordinal. See docs/agent-context/name-resolution.md.
# The id has no positional relation to the browse table, hence the indirection; the game
# stores names once and links by id. Bases are per-save (offsets differ between careers),
# so everything here is DISCOVERED, not hard-coded.

def _u32(mm, o):
    return int.from_bytes(mm[o:o + 4], "little")


def _walk_browse_bounds(mm):
    """Same discovery as `_walk_browse`, but also returns the table's own byte extent
    (`start` of its first length field, `end` just past its last string) -- needed to
    exclude this region from the club/comp candidate scan. See `_name_table_bounds`."""
    for start in range(200, 3000):
        ln = _u32(mm, start)
        if 2 <= ln <= 40:
            raw = mm[start + 4:start + 4 + ln]
            try:
                s = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if s and s[0].isalpha() and all(ord(c) >= 0x20 for c in s):
                out = []
                o = start
                while o + 4 < len(mm):
                    L = _u32(mm, o)
                    if not (1 <= L <= 40):
                        break
                    raw = mm[o + 4:o + 4 + L]
                    try:
                        t = raw.decode("utf-8")
                    except UnicodeDecodeError:
                        break
                    if any(c < 0x20 for c in raw):
                        break
                    out.append(t)
                    o = o + 4 + L
                if len(out) > 1000:
                    return start, o, out
    return None, None, []


def _walk_browse(mm):
    """The flat [len u32][utf-8] name table near the file start -> list of strings."""
    return _walk_browse_bounds(mm)[2]


def _discover_id_tables(mm, browse_len, probe=8192):
    """Find the two dense id->ordinal tables. A record is 16 bytes with the id at +4 and
    the browse ordinal at +0; ids run 0,1,2,… . Anchor on a mid-range id (present in both
    tables), verify the dense run, walk back to base. Returns [(base, count), …] largest
    first."""
    pat = struct.pack("<I", probe)
    bases = {}
    pos = 0
    while True:
        i = mm.find(pat, pos)
        if i == -1:
            break
        pos = i + 1
        o = i - 4                       # i is the +4 id field -> record start
        if o < 0:
            continue
        if (_u32(mm, o + 20) == probe + 1 and _u32(mm, o + 36) == probe + 2
                and _u32(mm, o) < browse_len and _u32(mm, o + 16) < browse_len):
            base = o - probe * 16
            if base >= 0 and _u32(mm, base + 4) == 0 and _u32(mm, base + 20) == 1:
                n = probe
                while _u32(mm, base + n * 16 + 4) == n:
                    n += 1
                bases[base] = n
    return sorted(bases.items(), key=lambda x: -x[1])


_NAME_TABLES = {}   # id(mm) -> (browse_list, base_first, base_surname)


def build_name_resolver(mm, validate=None):
    """Discover the name tables for `mm` and cache them. `validate` is an optional list of
    (first_name_id, last_name_id, expected_full_name) — normally the managed squad, whose
    names we already have from the snapshot — used to orient which id-table is first names
    vs surnames (falls back to size: the larger table is surnames)."""
    browse = _walk_browse(mm)
    tabs = _discover_id_tables(mm, len(browse))
    if len(tabs) < 2:
        _NAME_TABLES[id(mm)] = (browse, None, None)
        return False
    big, small = tabs[0][0], tabs[1][0]
    base_sur, base_first = big, small           # heuristic: more surnames than first names
    if validate:
        def score(bf, bs):
            ok = 0
            for fid, lid, exp in validate:
                try:
                    if f"{browse[_u32(mm, bf + fid * 16)]} {browse[_u32(mm, bs + lid * 16)]}" == exp:
                        ok += 1
                except IndexError:
                    pass
            return ok
        if score(big, small) > score(small, big):
            base_first, base_sur = big, small   # swap only if that orientation fits better
    _NAME_TABLES[id(mm)] = (browse, base_first, base_sur)
    return True


def resolve_name(mm, first_name_id, last_name_id):
    """Full 'First Last' for any player from their info-field name ids, or None. Call
    build_name_resolver(mm) once first (cached per mmap)."""
    t = _NAME_TABLES.get(id(mm))
    if not t or t[1] is None:
        return None
    browse, base_first, base_sur = t
    try:
        return f"{browse[_u32(mm, base_first + first_name_id * 16)]} " \
               f"{browse[_u32(mm, base_sur + last_name_id * 16)]}"
    except IndexError:
        return None
