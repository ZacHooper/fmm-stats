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
from .save import cache_key as _cache_key

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


# `type_id` (the byte immediately after the 3 name strings) is the REAL field; it is carried
# raw on every competition record and is what code should branch on -- `lightresults.py`
# already does (`type_id in (0, 1)` for a round-robin league).
#
# COMP_TYPES is a DISPLAY label for the handful of type_ids anchored against named, verified
# competitions, nothing more. It is not a closed enum and the parser does not validate
# against it: at minimum 3, 4, 5, 7, 10, 11, 12, 13, 14, 15, 21, 22, 23, 26, 28, 29, 30, 36,
# 37, 38, 39 are all real (Carabao Cup, FA Trophy, European Championship, Copa América,
# African Cup of Nations, national Super Cups, youth leagues, All-Star exhibitions), and
# every unlabelled value falls through to `type_N` rather than getting a guessed name.
# Naming a type_id requires the same sourcing as any other field -- an upstream definition
# or repeated ground truth -- not an inference from one competition that happened to carry
# it, which is why 21 ("continental_cup", read off a single chat observation) is NOT here.
# Calibrated on Turkey: top-flight league(0), league(228)/play-off(227)=1, cup(117)=2,
# reserve league(1370)=8, friendly(65)=9. 0 and 1 are BOTH round-robin leagues (0 = a
# nation's top flight, e.g. 3F Superliga / Bundesliga / Serie A; 1 = the divisions below it).
COMP_TYPES = {0: "league", 1: "league", 2: "cup", 8: "reserve_league", 9: "friendly"}
# Long-name sanity bound, used ONLY to validate record 0 when locating the table anchor --
# never to accept or reject a record, since `_walk_comp_table` reads every declared slot by
# arithmetic. 60 matches the club long-name cap (`_eval_club_candidate`'s [2,60]); real
# competition names reach 52 ("Chinese National Amateur Division North East Group").
_COMP_NAME_CAP = 60


_REFDATA_INDEX_CACHE = {}   # _cache_key -> ({tid: club_record}, {cid: comp_record})
_NATION_BOUNDS_CACHE = {}   # _cache_key -> (lo, hi) of the real nation-name table, padded


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
    COMPETITION records share this exact shape [with nation records]", so the candidate
    prefilter proposes every nation's name/nationality/code triplet as a club candidate too.
    It is the CLUB scan this protects now: competitions stopped using the candidate scan
    entirely on 2026-09-18 (`_walk_comp_table`), and the collision that originally motivated
    this -- "British Virgin Is." (real nation_id 206) resolving as comp cid 63981, an id read
    from the wrong byte offset for that record type, actually the tail of the previous
    nation's own ranking-history array -- can no longer happen on the comp side at all.

    It very much still happens on the club side, and this is measured, not assumed: removing
    this exclusion and `_name_table_bounds` admits 191 EXTRA "clubs" on frem-2026-06-11 --
    'Angola', 'Botswana', 'Burkina Faso', 'Egypt', 'Ghana', 'Sint Maarten', 'Réunion' and so
    on, each under a nonsense tid like 393218 or 1376257 -- while costing zero real ones. So
    the exclusions are pure gain here. They are also a standing argument for doing to the
    club table what was done to the competition table (docs/TODO.md): a scan that needs whole
    regions fenced off to stop inventing records is a scan that has not found the table's own
    structure yet. Excluding a known region structurally is at least the fix CLAUDE.md's
    region-first method calls for -- an incidental gate (a reputation ceiling, a name-length
    shape) only catches the collisions that happen to look wrong, not the ones that don't.
    """
    key = _cache_key(mm)
    cached = _NATION_BOUNDS_CACHE.get(key)
    if cached is not None:
        return cached
    offsets = [rec["offset"] for rec in LK.scrape_nations(mm).values()]
    bounds = (min(offsets) - 200, max(offsets) + 200) if offsets else None
    _NATION_BOUNDS_CACHE[key] = bounds
    return bounds


_NAME_TABLE_BOUNDS_CACHE = {}   # _cache_key -> (start, end) of the browse name table, exact


def _name_table_bounds(mm):
    """The real NAME table's (the ~46k-entry flat [len][utf-8] first-name/surname "browse"
    table `_walk_browse` reads for player-name resolution) byte extent -- same collision
    class as `_nation_table_bounds`, one door down: this table sits at the very start of
    the file (`scripts/map_regions.py` independently maps it as `name_table`, entry0@299=
    'Rajagobal'), made of nothing but back-to-back length-prefixed strings, which is
    EXACTLY the shape the club candidate prefilter looks for.

    Originally added for the comp scan -- `cid=24931` named 'World' resolved from file offset
    897, squarely inside this table and nowhere near any real competition -- which no longer
    applies, since `_walk_comp_table` never reads outside the table's own declared extent. It
    stays for clubs, where it is still doing work: without it, tid 4294967295 resolves to
    'Rajagobal', this table's own first entry. See `_nation_table_bounds` for the measured
    cost/benefit of both exclusions together.

    No padding needed, unlike the nation table: `_walk_browse` already finds this table's own
    precise start/end by the same walk that reads its contents, not a separate candidate scan
    with its own continuity margin.
    """
    key = _cache_key(mm)
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
    key = _cache_key(mm)
    cached = _COMP_TABLE_ANCHOR_CACHE.get(key)
    if cached is not None:
        return cached
    buf = np.frombuffer(mm, dtype=np.uint8)
    is_ff = buf == 0xFF
    # Pad the mask with a False at each end before diffing, so a run touching byte 0 or the
    # last byte still produces both a rising and a falling edge. Without the padding,
    # np.diff sees no rising edge for a run that starts at offset 0, `run_starts` comes back
    # one element short of `run_ends`, and `zip` then pairs EVERY start with the wrong end --
    # a whole-file misalignment from a single leading 0xFF. No save in the archive starts
    # with one (they open "11/6..."), which is exactly why this would have gone unnoticed.
    d = np.diff(np.concatenate(([0], is_ff.view(np.int8), [0])))
    run_starts = np.flatnonzero(d == 1)
    run_ends = np.flatnonzero(d == -1)
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
    `25 + 8*n_refs` trailer extension apply identically whether or not the names are
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
    typ = trailer[0]
    # nation is a u16, not a byte. Both readers of this trailer used to take `trailer[3]`
    # alone and test it against 255, which gives the right answer today only by luck: the
    # real sentinel is 0xFFFF and every nation id in the save happens to fit in a byte
    # (227 nations, ids 1-249, so six spare values). `scripts/audit_records.py` has always
    # DECLARED this field as (3, 2) -- the parser was the half that disagreed, and reading
    # the declared width is what makes the layout the schema rather than a second opinion.
    # Verified byte-for-byte on frem-2026-06-11: +4 is 0x00 for all 1,212 nation-bound
    # competitions and 0xFF for exactly the 60 that carry the sentinel, so the u16 read is
    # behaviour-identical here and correct if a nation id ever crosses 255.
    nation = int.from_bytes(trailer[3:5], "little")
    rep = int.from_bytes(trailer[9:11], "little")
    level = trailer[11]
    parent = int.from_bytes(trailer[12:14], "little")
    # The record does NOT end at the trailer. What follows is a counted REFERENCE LIST --
    # `[n_refs]` then that many 8-byte entries -- and then a fixed 21-byte tail, so
    # `25 + 8 * n_refs`, which is the whole reason this function can report `next_p`.
    # Non-zero on 24 of this save's 1,272 named competitions (up to 134 across the archive)
    # and 914 records overall, so the `8 *` term is load-bearing, not speculative.
    #
    # The ORDER was measured, not assumed: the entries come BEFORE the 21-byte tail,
    # established on the 914 records that have a list by where the tail's three-u16 season
    # triple reads as a plausible year (686 hits at record_end-9, zero at +16 from here).
    # A contiguous-25-byte-head reading gives the identical record length, which is why it
    # went unnoticed -- 1,348 of 1,372 records have an empty list, so the two coincide there.
    #
    # The count is read as a u32 here because that is safe -- bytes +1..+3 are zero on all
    # 46,641 slots in the archive -- but it is DECLARED as a u8 plus three unknowns in
    # `scripts/audit_records.py`, because with a maximum count of 134 the two widths are
    # indistinguishable and the layout must not assert what was not measured. The entry's
    # own fields are decoded (`comp_ref_entry`) and readable via `comp_refs`, but are not
    # put in `rec`: only 24 of 1,272 competitions have any, and what the list MEANS varies
    # between them, so there is nothing yet worth a column. See `comp_refs`.
    list_p = pp + 14
    n_refs = int.from_bytes(mm[list_p:list_p + 4], "little")
    next_p = list_p + 25 + 8 * n_refs
    if ln == 0:
        return None, next_p
    rec = {"cid": cid, "uid": uid, "name": long, "short": short, "code": code,
           "type": COMP_TYPES.get(typ, f"type_{typ}"), "type_id": typ,
           "nation_id": None if nation == 0xFFFF else nation, "reputation": rep,
           "level": level, "parent_cid": None if parent == 0xFFFF else parent}
    return rec, next_p


class CompTableError(Exception):
    """The competition table could not be located or could not be walked.

    RAISED, not swallowed, and there is deliberately no fallback behind it. The scan this
    replaced (a candidate sweep gated on type/continent/nation/reputation/name-shape) was
    kept for one day as a "same-save-family fallback" and then deleted, because it was
    measured dead: `_comp_table_anchor` resolves and `_walk_comp_table` reads every declared
    slot exactly on all 32 saves in the archive, across BOTH careers -- Frem 1372 declared =
    1272 named + 100 blank, Bucaspor 1371 = 1271 + 100, `cid == i` for every slot in every
    one. A fallback that never runs is not insurance; it is a second, untested definition of
    what a competition record is, and the gate cascade's whole history was of that second
    definition quietly costing real records.

    So if this raises, the right response is to go and read the bytes -- the table's own
    declared count and start disagree with its contents, which means the format changed or
    the anchor locked onto the wrong 0xFF run. Guessing records back out of a plausibility
    sweep is what put "British Virgin Is." and "World" in the competition list.
    """


def _walk_comp_table(mm):
    """Pure structural walk of the ENTIRE competition table -> (comps, n_blank), where
    `comps` is {cid: rec} for named records and `n_blank` counts genuinely empty slots.
    No candidate scan, no plausibility gate, nothing tuned: `_comp_table_anchor` gives the
    table's start and its OWN declared record count, and every one of those records is then
    read by `_read_comp_slot`'s arithmetic alone.

    `cid == i` against the walk's own loop index is the ONE structural assertion (a real
    invariant, not a tuned constant, per CLAUDE.md's region-first method). Anything that
    stops the walk -- a missing anchor, a misaligned slot, a name that is not UTF-8, a read
    past the end of the buffer -- raises `CompTableError` with the slot and offset, because
    a table whose own count and start are known has no legitimate reason to drift and
    silently returning a short answer is how a scraper loses records without anyone noticing.
    """
    anchor = _comp_table_anchor(mm)
    if anchor is None:
        raise CompTableError(
            "competition table anchor not found: no 0xFF run followed by a plausible u16 "
            "record count whose record 0 reads cid=0 and whose record 1 reads cid=1")
    start, count = anchor
    comps = {}
    n_blank = 0
    p = start
    for i in range(count):
        cid = int.from_bytes(mm[p:p + 2], "little")
        if cid != i:
            raise CompTableError(f"competition table walk misaligned at slot {i} of {count}: "
                                 f"read cid={cid}, offset={p}, table start={start}")
        try:
            rec, p = _read_comp_slot(mm, p)
        except (IndexError, UnicodeDecodeError, ValueError) as exc:
            raise CompTableError(f"competition slot {i} of {count} at offset {p} is "
                                 f"unreadable: {type(exc).__name__}: {exc}") from exc
        if rec is None:
            n_blank += 1
        else:
            comps[cid] = rec
    return comps, n_blank

def comp_refs(mm, cid):
    """[{ref, season, ordinal}] -- the competition's counted reference list, in file order.
    Empty for a blank slot, a competition with none, or a cid past the table.

    `ref` resolves as a club **UID** for club competitions, and that part is solid: MLS's
    entries come back as its 28 member clubs (D.C. United, LA Galaxy, Atlanta United,
    Charlotte FC, Chicago Fire, CF Montréal), Copa Libertadores' as Bolivian and Ecuadorian
    clubs in the right competition. `0xFFFFFFFF` is the empty-slot sentinel.

    **Resolve by UID, never by tid.** 1,095 of these values also match some club's tid and
    the tid reading is wrong every time -- uid 1913 is D.C. United (right for MLS), tid 1913
    is York United. Build the index from `_build_refdata_index(mm)[0]`; there is no uid-keyed
    resolver in this module because nothing else needs one.

    **THE SIGN IS THE DISCRIMINATOR: `ref > 0` is a CLUB, `ref < 0` is a NATIONAL TEAM, and
    `-ref` is that nation's `uid` from `lookups.scrape_nations`.** Exact on 62/62 negative
    refs, with no exceptions and no fudge -- Copa América's ten resolve to Argentina,
    Bolivia, Brazil, Chile, Colombia, Ecuador, Paraguay, Peru, Uruguay and Venezuela, i.e.
    CONMEBOL's ten members and nothing else, and the European International League divisions
    to Scotland/Serbia/Slovakia/Slovenia/Spain/Sweden/Switzerland/Turkey/Ukraine/Wales. They
    are ten and sixteen CONSECUTIVE negative ids because the nation table is alphabetical and
    the negation reverses it, which is why they looked like a suspiciously dense id space
    before the mapping was found. `0xFFFFFFFF` (-1) is NOT a national team, it is the
    empty-slot sentinel; no nation has uid 1.

    A national team is stored as a CLUB-SHAPED record -- Argentina at offset 6,866,484 on
    frem-2026-06-11 reads `[tid 961][uid 0xFFFFF98F][9]'Argentina'[00][9]'Argentina'[00]
    [3]'ARG'[trailer]`, the exact long/short/code layout `_eval_club_candidate` looks for.
    It is nonetheless invisible to the club scan, because a uid of 4,294,965,647 fails both
    admission bands (`<= 400,000,000`, or the 1.9-2.1bn fill band). 202 of the save's 227
    nations have such a record. Not chased here -- see docs/TODO.md; it belongs with the
    club table's own structural rewrite, not with the competition record.

    WHAT THE LIST MEANS IS NOT DECIDED, and the name here is deliberately structural. It was
    briefly called `comp_qualifiers` after fmm-editor's `Qualifiers` table (`n × 8 bytes`,
    which this may well be) and Zac was right to push back on the inconsistency: only 24 of
    1,272 competitions populate it, and they do not share one meaning --

      * Copa Libertadores   47 entries × 2 seasons, each with a domestic placing. A
                            qualification list, exactly.
      * Major League Soccer its 28 member clubs, Charlotte FC stamped season 2022 (its real
                            expansion year). Membership, not qualification.
      * Canadian Champ'ship 3 entries: Forge FC, Toronto FC, CF Montréal -- the Canadian
                            clubs playing in FOREIGN leagues that still enter this cup.
      * Copa América        10 national-team refs (negative), no clubs at all.
      * Scottish Cup        13 entries, every one 0xFFFFFFFF. Reserved and empty.
      * Italian Cup         4 entries (3 Serie C clubs + a sentinel) against a ~78-team field.

    And the asymmetry that kills any single label: European Champions Cup has ZERO while the
    Libertadores / Asian / African Champions Leagues have 94 / 47 / 54, and 3F Superliga has
    zero while MLS has 28. The story that fits is "an explicit entrant list, stored only
    where the field cannot be derived from the league structure the game simulates" --
    promotion/relegation pyramids and UEFA coefficients being derivable, a closed franchise
    league and CONMEBOL's entrants not. A story is not a decode, so the fields are named and
    the list is not. See `scripts/audit_records.py`'s `comp_ref_entry`.
    """
    anchor = _comp_table_anchor(mm)
    if anchor is None:
        raise CompTableError("competition table anchor not found")
    start, count = anchor
    if not 0 <= cid < count:
        return []
    p = start
    for _i in range(cid):
        _rec, p = _read_comp_slot(mm, p)
    # re-derive the list's offset exactly as _read_comp_slot does, so the two cannot drift:
    # past the 3 names (one terminator after each of the first two), then the 14-byte trailer
    q = p + 6
    ln = int.from_bytes(mm[q:q + 4], "little")
    pp = q + 4 + ln + 1
    sl = int.from_bytes(mm[pp:pp + 4], "little")
    pp = pp + 4 + sl + 1
    cl = int.from_bytes(mm[pp:pp + 4], "little")
    pp = pp + 4 + cl
    list_p = pp + 14
    n = int.from_bytes(mm[list_p:list_p + 4], "little")
    out = []
    for k in range(n):
        e = list_p + 4 + 8 * k
        out.append({"ref": int.from_bytes(mm[e:e + 4], "little"),
                    "season": int.from_bytes(mm[e + 4:e + 6], "little"),
                    # u8, not u16: the byte above is 0 on 5,220 of 5,237 entries and 1 on
                    # the other 17, so the two widths are not separable here
                    "ordinal": mm[e + 6]})
    return out


def comp_table_spans(mm):
    """[(record_start, record_end)] -- one span per slot the competition table declares, in
    file order, plus the 2-byte count header in front of record 0.

    This is the competition table's EXTENT, reported per record rather than claimed as a
    window, which is what `scripts/audit_coverage.py`'s MEASURED tier requires. It reuses
    `_read_comp_slot` for the arithmetic, so the audit cannot drift from the parser: if the
    walk's idea of where a record ends is wrong, both are wrong together and the coverage
    map shows it as a gap.
    """
    anchor = _comp_table_anchor(mm)
    if anchor is None:
        raise CompTableError("competition table anchor not found")
    start, count = anchor
    spans = [(start - 2, start)]      # the u16 declared-count header
    p = start
    for _i in range(count):
        _rec, nxt = _read_comp_slot(mm, p)
        spans.append((p, nxt))
        p = nxt
    return spans


# ---- named reject reasons (CLUBS ONLY) ----------------------------------------------
# Both _build_refdata_index and diagnose_refdata_scan (below) call the SAME
# _eval_club_candidate -- there is exactly one implementation of "is this a valid club
# record", so the real scan and its audit cannot silently drift apart the way a hand-copied
# second walk could.
#
# COMPETITIONS have no reject reasons, because they have no gates: `_walk_comp_table` reads
# the table's own declared slots by arithmetic. The comp half of this cascade (a dozen
# COMP_REJECT_* reasons, `_eval_comp_candidate`, `CompCandidate`, a two-tier reputation
# arbitration and the `_MIN_COMP_REP` floor) was DELETED 2026-09-18 once the walk was
# measured exact on all 32 archived saves across both careers. Clubs are next: docs/TODO.md
# has the item, and the walk is the model to copy.
CLUB_REJECT_UID_RANGE = "uid_outside_admission_bands"
CLUB_REJECT_LONG_LEN = "long_name_length_out_of_range"
CLUB_REJECT_LONG_INVALID = "long_name_undecodable"
CLUB_REJECT_SHORT_INVALID = "short_name_undecodable"
CLUB_REJECT_FILL_NO_MARKER = "fill_tier_missing_trailer_marker"



class ClubCandidate(NamedTuple):
    accepted: bool
    reason: object          # None if accepted
    tid: int
    tier: object            # 0 or 1, only if accepted
    rec: object              # dict, only if accepted


def _candidate_positions(mm):
    """(lo, hi, cand) for the CLUB reference-data scan: the window bounds and the
    numpy-derived array of absolute offsets whose u32 reads as a plausible name-length field
    (2..60), with room to look back 8 bytes for a club header. Both `_build_refdata_index`
    and `diagnose_refdata_scan` call this so the candidate set used for real extraction and
    the candidate set used for diagnosis are the SAME array.

    Competitions no longer come from here at all (`_walk_comp_table` does that), which is why
    the file length is no longer returned: it existed only so the retired comp gates could
    bounds-check a trailer read."""
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
    # nation string resolves as a fake CLUB under a bogus id read from neighbouring bytes
    # that were never meant to be an id at all (191 such on frem-2026-06-11, measured).
    nation_bounds = _nation_table_bounds(mm)
    if nation_bounds is not None:
        nlo, nhi = nation_bounds
        cand = cand[(cand + lo < nlo) | (cand + lo > nhi)]
    # Exclude the real NAME (browse) table -- see _name_table_bounds' docstring. Same
    # collision class as the nation table: a flat run of length-prefixed strings at the
    # very start of the file can coincidentally satisfy every club gate.
    name_bounds = _name_table_bounds(mm)
    if name_bounds is not None:
        nmlo, nmhi = name_bounds
        cand = cand[(cand + lo < nmlo) | (cand + lo > nmhi)]
    return lo, hi, cand


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


def _build_refdata_index(mm):
    """({tid: club_record}, {cid: comp_record}) for the whole save, built once per mmap.

    The two halves are resolved DIFFERENTLY and on purpose. Competitions come from
    `_walk_comp_table`, a pure structural walk of the table's own declared slots -- no
    candidate scan reaches them at all. Clubs still come from the candidate-scan-plus-gates
    cascade (`_eval_club_candidate`), which is the next thing to convert; see docs/TODO.md.
    """
    key = _cache_key(mm)
    cached = _REFDATA_INDEX_CACHE.get(key)
    if cached is not None:
        return cached

    comps, _n_blank = _walk_comp_table(mm)

    lo, hi, cand = _candidate_positions(mm)
    clubs = {}
    tiers = {}                  # tid -> which gate admitted the stored record (0 beats 1)
    for off in cand.tolist():
        q = off + lo             # absolute offset of the length field
        cc = _eval_club_candidate(mm, q)
        if cc.accepted:
            existing = clubs.get(cc.tid)
            if _club_wins(tiers.get(cc.tid), existing, cc.tier, cc.rec):
                clubs[cc.tid] = cc.rec
                tiers[cc.tid] = cc.tier

    result = (clubs, comps)
    _REFDATA_INDEX_CACHE[key] = result
    return result


class RefdataDiagnosis(NamedTuple):
    """Candidate-level disposition for the CLUB scan. There is no comp half: competitions
    are resolved by `_walk_comp_table`, which has no candidates and no rejections to tally.
    The comp fields (`comp_accepted_tier0/1`, `comp_superseded`, `comp_already_resolved`,
    the four `comp_reject_*` Counters and `comp_rejections`) were removed 2026-09-18 with
    the gate cascade they described -- they had become numbers about a code path that could
    not execute, which `scripts/audit_declared_scans.py` was still printing as though they
    were the real resolution."""
    n_window_bytes: int
    n_candidates: int
    club_accepted_tier0: int         # tids WON at tier 0 (winners only, not every hit)
    club_accepted_tier1: int         # tids WON at tier 1
    club_superseded: int             # structurally valid, but an earlier/better candidate
                                       # for the same tid already won
    club_reject_candidates: object   # Counter: reason -> candidate occurrences
    club_reject_ids: object          # Counter: reason -> DISTINCT tids ever rejected for it
    club_rejections: list            # [(offset, tid, reason), ...]


def diagnose_refdata_scan(mm):
    """Per-candidate disposition for every position the CLUB scan in
    `_build_refdata_index` considers: accepted (with tier), rejected (a named reason), or
    superseded (structurally valid, but a better/earlier candidate already won that tid).
    Calls `_eval_club_candidate` -- the SAME function `_build_refdata_index` uses -- so this
    cannot drift from what the real scan actually does.

    COMPETITIONS ARE NOT DIAGNOSED HERE, and that is the point. They come from
    `_walk_comp_table`, which reads the table's own declared slots by arithmetic: there is
    no candidate to have a disposition, no gate to attribute a loss to, and the only two
    numbers worth checking (`named + blank == declared count`, `cid == slot index`) are
    assertions inside the walk itself rather than statistics after the fact. Until
    2026-09-18 this function still ran the retired comp cascade and reported its tiers and
    reject tallies, while `_build_refdata_index` ignored all of it -- so the docstring's
    no-drift guarantee, the entire reason this function is shaped the way it is, was true
    for clubs and false for comps. Deleting the comp half was the fix; do not add a
    "diagnosis" for the walk to replace it.

    Deliberately bypasses `_REFDATA_INDEX_CACHE`: this is for a human (or a script) running
    an audit, not the extract.py hot path, and re-derives the candidate array fresh.

    IMPORTANT: this covers 1.76% of the window on a real save (351,682 of 20,000,000
    bytes) -- one candidate per ~57 bytes. It answers "of the positions that LOOK like a
    name-length field, what happened to each one", not "what is every byte in this
    window". A record whose length field falls outside [2,60], or that has no length
    prefix at all, never becomes a candidate and is invisible here by construction -- see
    _candidate_positions' note.

    A reject count is not proof of a real gap, and the comp cascade got caught on that twice
    before it was deleted. Both cautions transfer directly to the club gates, which is why
    they are kept here:
      1. A candidate counted against EVERY gate it fails overstates each one. The comp
         reputation floor showed 9,410 candidates / 1,031 distinct cids that way, but only
         47 cids failed it ALONE -- the other 984 also failed type/continent/nation and
         could never have resolved however the floor was set. Count solo failures for "how
         many records would this fix recover"; count all failures only for "how much noise
         touches this gate".
      2. Even a solo count is not proof of NEED. The comp empty-CODE bug hit 164 cids solo,
         of which only ~30 were real competitions; the rest were coincidental non-records
         sharing a failure shape. Cross-reference rejected ids against ids something else in
         the save actually REFERENCES (a match's comp_id/home_tid/away_tid, a player's
         club_tid) before calling a reject count a gap -- see
         scripts/audit_declared_scans.py.
    """
    lo, hi, cand = _candidate_positions(mm)
    club_reject_candidates = collections.Counter()
    club_reject_id_sets = collections.defaultdict(set)
    club_rejections = []
    club_accepted_tier0 = club_accepted_tier1 = club_superseded = 0
    clubs_seen, tiers_seen = {}, {}

    for off in cand.tolist():
        q = off + lo

        cc = _eval_club_candidate(mm, q)
        if cc.accepted:
            existing = clubs_seen.get(cc.tid)
            prior_tier = tiers_seen.get(cc.tid)
            if _club_wins(prior_tier, existing, cc.tier, cc.rec):
                # A tid can win TWICE across this scan -- first at tier 1, later upgraded by
                # a tier-0 candidate. Counting both wins as separate accepts double-counts
                # that one tid; undo the earlier tier's count on an upgrade so each tid is
                # counted exactly once, in its FINAL tier.
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

    club_reject_ids = collections.Counter({r: len(ids) for r, ids in club_reject_id_sets.items()})

    return RefdataDiagnosis(hi - lo, len(cand), club_accepted_tier0, club_accepted_tier1,
                             club_superseded, club_reject_candidates, club_reject_ids,
                             club_rejections)


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
    """The competition record for `cid` -> full detail dict, or None if that slot is blank.

    Straight lookup into `_walk_comp_table`'s output -- there is no searching and no
    validation involved, because the table is walked in full by arithmetic from its own
    declared start and count. `cid` IS the slot index.

    It used to be a search, and the docstring here used to describe the gates that search
    needed: a `[type][0x02][0x00][nation]` "trailer signature", a type-byte whitelist, a
    `_MIN_COMP_REP` reputation floor, "first record passing all of that in file order wins".
    Every one of those is gone (2026-09-18), along with the bugs they caused -- cid 2
    resolving to 'Belfort' instead of '3F Superliga' when a uid rule skipped every top
    flight, 'Ivory Coast' and 'World' arriving as competitions from neighbouring tables,
    ~100 real leagues dropped by a length cap and a Europe-only continent test. A record is
    now whatever the table says is in slot `cid`, and nothing else can end up here.
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
    key = (_cache_key(mm), cid, want)
    if key not in _COMP_CACHE:
        _COMP_CACHE[key] = resolve_comp(mm, cid, want)
    return _COMP_CACHE[key]


def comp_detail(mm, cid):
    """Full competition record: cid, uid, name, short, code, type, type_id, nation_id,
    reputation, level, parent_cid. `type_id` is the real field; `type` is a display label
    for the five sourced values only (see COMP_TYPES). Read by `_read_comp_slot`."""
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


_NAME_TABLES = {}   # _cache_key -> (browse_list, base_first, base_surname)


def build_name_resolver(mm, validate=None):
    """Discover the name tables for `mm` and cache them. `validate` is an optional list of
    (first_name_id, last_name_id, expected_full_name) — normally the managed squad, whose
    names we already have from the snapshot — used to orient which id-table is first names
    vs surnames (falls back to size: the larger table is surnames)."""
    browse = _walk_browse(mm)
    tabs = _discover_id_tables(mm, len(browse))
    if len(tabs) < 2:
        _NAME_TABLES[_cache_key(mm)] = (browse, None, None)
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
    _NAME_TABLES[_cache_key(mm)] = (browse, base_first, base_sur)
    return True


def resolve_name(mm, first_name_id, last_name_id):
    """Full 'First Last' for any player from their info-field name ids, or None. Call
    build_name_resolver(mm) once first (cached per mmap)."""
    t = _NAME_TABLES.get(_cache_key(mm))
    if not t or t[1] is None:
        return None
    browse, base_first, base_sur = t
    try:
        return f"{browse[_u32(mm, base_first + first_name_id * 16)]} " \
               f"{browse[_u32(mm, base_sur + last_name_id * 16)]}"
    except IndexError:
        return None
