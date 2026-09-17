#!/usr/bin/env python3
"""
The 25-byte MATCH-SLOT table: a fixed-size table, ~73% of whose slots carry real data and
~7-15% of THOSE carry a resolvable club pair (a "fixture").

WHAT IS PROVEN, and what is not. The table's SHAPE, EXTENT and the fixture field group are
established from the bytes and hold across five Frem saves and two Bucaspor ones. What the
table is FOR is not established -- the other 18 bytes are carried, not named. Do not describe
this as "the fixture list": it holds 275 matches on the reference save, drawn from many
leagues at once, which is nothing like a competition's full programme. Do not describe it as
"~7% populated" either -- see POPULATION below; that figure only counts slots with a club pair,
and undercounts what's actually stored by a factor of ten.

LOCATION -- self-locating, never a constant. Every window in regions.py drifts per save and
per career, and this one drifts hard: 37.78M on frem-2023-07-02, 40.59M on frem-2025-06-29,
40.04M on frem-2026-06-11. So `locate()` finds it by the table's own invariant instead --
the 4-byte constant `87 01 ff ff` at +20, which repeats on exactly ONE residue class mod 25
and in exactly ONE contiguous run. On the reference save 4,354 of the file's 19,663
occurrences of that constant sit on the winning residue; the runners-up score ~650, which is
the ~787 you would expect if residues were random. That margin is the identification.

EXTENT -- bounded by the table's own structure, not by a tuned constant:

    save                    start        end     slots
    frem-2023-07-02      37.7794M   37.8787M     3,975
    frem-2025-06-29      40.5857M   40.6851M     3,975
    frem-2026-03-22      39.7082M   39.8076M     3,975
    frem-2026-06-11      40.0422M   40.1416M     3,975
    frem-2026-06-29      40.3934M   40.4927M     3,975
    bucaspor-2022-05-25  39.9654M   40.0640M     3,943
    bucaspor-2022-06-01  40.8197M   40.9183M     3,943

The slot count is CONSTANT within a career across four seasons and DIFFERS between careers,
which is the signature of a table preallocated when the career is created. That is the
invariant to bound the walk with; it is also why `locate()` returns the run and the caller
does not get to pass a length.

STRIDE -- 25, measured two independent ways. Autocorrelation over 40.050-40.120M puts 25 at
70.35% with 50 and 75 as its multiples (the next non-multiple, 23, scores 31.89%); and the
trailer's residue class mod 25 is unique. Neighbouring bands are DIFFERENT tables -- 16/48 at
40.0-40.7M, 9/27 at 41.1-41.5M -- so a sweep must respect the extent above.

VALIDATION of the fixture group, on frem-2026-06-11's 3,975 slots:
  * 275 slots carry a club pair and 100% of them resolve to a real club (chance is ~8%);
  * +4/+5 max 6-6, mean 1.37/1.67, and NO row exceeds 12 -- football-shaped;
  * +6 is a valid day-of-year on 100% of those rows;
  * two are screenshot-verified: Tottenham 5-0 Bournemouth and West Brom 0-2 Liverpool, both
    day 143 = 2026-05-24, the final round. A third, Southampton 3-6 Newcastle day 135, is
    independently confirmed by the Club History screen's "Highest scoring match, 16/5/2026".

The record is AWAY-FIRST. That is why it went unfound for so long: every probe that assumed
the home club comes first, or that searched for an oriented home->away pair, excluded it by
construction.

POPULATION -- checking `day != 0` independently of the club-pair filter, across four saves
spanning 2023-2026:

    save                   fixture  clubless-but-dated  inert(day=0)  populated total
    frem-2023-07-02            138                2,736         1,101            2,874
    frem-2024-06-30            157                2,717         1,101            2,874
    frem-2026-06-11            275                2,598         1,102            2,873
    frem-2026-07-02            100                2,773         1,102            2,873

The populated total is essentially CONSTANT (2,873-2,874) while fixture count ranges 100-275 --
slots don't get added or removed, matches flip from "dated, no club yet" to "fixture" as they're
played, inside a fixed ~2,874-slot band (slot index 1..2,874 populated, 2,875..3,974 inert, same
boundary on saves years apart). Reads as a preallocated calendar that fills in progressively,
not a sparse table. **The ~2,600 clubless-but-dated slots are the majority of the table's real
content and are not examined by `scrape()` or anything downstream.**

WORLD CUP -- checked `frem-2023-01-06` (after the real Qatar 2022 final) and `frem-2026-07-02`
(during the real 2026 tournament window, in which fixture count correctly drops to 100 as
domestic leagues break for it). Zero fixture rows resolve to a nation in either save. Nations do
exist as their own club-style records (86 found, e.g. Qatar tid 1,632,698,368) but their tids
exceed the 16-bit `away_tid`/`home_tid` fields (max 65,535) by 4+ orders of magnitude -- a
national team cannot be addressed by this record's club-pair fields at all, regardless of when
the save was taken.

COMPETITION TYPE -- no `cid` field is stored; every league grouping quoted anywhere for this
table (e.g. "349 clubs across 48 league_cids" on frem-2026-06-11) is each club's own DEFAULT
league membership looked up separately via `reference.club_record`, not anything read from the
row. Of 275 fixtures, 242 pair two clubs from the same inferred league; the other 33 can't be
ordinary league matches by construction. Four were checked against real in-game fixture screens
and all four decoded EXACTLY on DATE while turning out to be four DIFFERENT kinds of
non-league fixture -- "cross-league" means "not a plain league game", not "cup tie". Only two
of the four also had the SCORE read correctly on the first pass (see ORIENTATION below for
why -- corrected here):
    Forest 3-0 Maidstone       day 13  -> 2026-01-14   FA Cup Third Round REPLAY       (score OK)
    Burnley 1-2 Arsenal        day 199 -> 2025-07-19   pre-season FRIENDLY             (score OK)
    Sevilla 1-3 Gladbach       day 146 -> 2026-05-27   continental cup FINAL, neutral  (score was
                                                        misread as Gladbach 1-3 Sevilla)
    Nurnberg 2-3 Dusseldorf    day 140 -> 2026-05-21   promotion PLAYOFF, 1st leg,     (score was
                                                        Dusseldorf won AWAY, misread as
                                                        Nurnberg 3-2 at home)
A fifth (Logrones 0-3 A.Madrid, day 201) could not be found in-game; tid 989 is a real,
well-formed club record, so this isn't a bad resolve. Day 201 sits in the sparse 180-300 band
(1-2 rows/day vs. dozens/day in the 100-180 core) -- the likeliest place for a STALE slot, so
the year-inference rule (day>=181 -> season-1) may have the wrong YEAR here. Unresolved.

ORIENTATION IS NOT RELIABLE ON A REPEATED CLUB PAIR. Three (away_tid, home_tid) pairs recur in
the table with a different day AND a different score each time -- initially read as possible
reschedules, but ground truth says all three are perfectly ordinary fixtures where the real
venue genuinely differed (two are legs of a two-legged playoff tie with real alternating
venues; Merthyr/Bradford per Zac directly). The table gets it wrong for exactly ONE of the two
rows, every time (3/3):
    Palace/Stoke      day 138 correct (Stoke home 3-0), day 142 has the TIDS swapped
    Truidense/Beersch. day 121 correct (Truidense home 4-0), day 128 has the TIDS swapped
    Merthyr/Bradford   day 359 correct (Merthyr home 2-0), day 114 has the TIDS swapped
And it is not even ONE consistent bug: on Nurnberg/Dusseldorf above, the TIDS are right
(Dusseldorf really was away) but the GOALS are swapped between the two clubs instead. So a
repeated pair can fail by mislabelling WHO played where, or by mislabelling WHO SCORED WHAT
while the venue is right -- two distinct failure modes, both invisible from the bytes alone.
**Every single-occurrence row checked against a screenshot has been exactly right** (the three
originals plus Forest/Maidstone and Burnley/Arsenal above) -- the unreliability is specific to
a club pair that shows up more than once, not a general flaw in the away-first convention.

RULED OUT as a competition-type flag, on the four confirmed rows plus the three known league
fixtures: `+8` (reads 5 on 226/242 same-league rows AND 17/20 cross-league rows) and
`trailer_a` (the cup replay and a same-day plain-league game are both 5; another plain-league
game is 391). Neither separates cup/friendly/playoff from league play.

LEAD on A/B/k: the Sevilla-Gladbach final is stored TWICE, 500 bytes (20 slots) apart, same
tid/score/day, different `trailer_a` -- the same multi-copy pattern as `clubrecords.py`. On the
Newcastle/Southampton duplicate pair, `k` (= (+9) - (+13), == (+11) - (+15) per the
four-numbers-hold-three identity above) is IDENTICAL across both copies (26 both times) even
though (+9)/(+11) themselves differ (33/19 vs 101/60) -- so `k` looks MATCH-level (shared by
every copy of one fixture) while (+9)/(+11) are COPY-specific. Neither is named yet.
"""
from . import regions as RG        # noqa: F401  (kept so callers see the region vocabulary)

STRIDE = 25
TRAILER = b"\x87\x01\xff\xff"      # constant at +20..+23
TRAILER_OFF = 20
NO_CLUB = 0xFFFF

UNKNOWN = "UNKNOWN"
U8, U16, I16 = "u8", "u16", "i16"

# One declarative layout IS the schema: the reader below reads FROM it and
# tests/test_match_slots.py checks AGAINST it, so the two cannot drift. Every byte in
# [0, STRIDE) appears exactly once. UNKNOWN rows are first-class -- a byte we have decided we
# cannot name yet, which is a different thing from a byte we stepped over.
LAYOUT = (
    (0,  2, "away_tid",   U16),   # 0xffff when the slot references no match
    (2,  2, "home_tid",   U16),
    (4,  1, "away_goals", U8),
    (5,  1, "home_goals", U8),
    (6,  2, "day",        U16),   # day-of-year, 0-based -- same encoding as the club record
    (8,  1, UNKNOWN,      U8),    # 5 on 93% of slots. NOT the cid: it reads 5 on rows whose
                                  # clubs are in leagues 2, 4 and 32. Not competition-type
                                  # either -- 5 on both same-league (226/242) and cross-league
                                  # (17/20) fixture rows. See COMPETITION TYPE above.
    (9,  2, UNKNOWN,      I16),   # call it A. 0..360 on fixture rows.
    (11, 2, UNKNOWN,      I16),   # B. r=+0.994 with A; B ~ 0.58 x A.
    (13, 2, UNKNOWN,      I16),   # == A - k
    (15, 2, UNKNOWN,      I16),   # == B - k, the SAME k. Verified 275/276 fixture rows:
                                  # (+9 - +11) == (+13 - +15) and (+9 - +13) == (+11 - +15).
                                  # k looks MATCH-level, not copy-level: on a fixture stored
                                  # twice (Southampton/Newcastle), k was identical (26) across
                                  # both copies while A and B themselves differed. See LEAD
                                  # on A/B/k above.
                                  # So the four hold only three independent numbers.
    (17, 2, UNKNOWN,      I16),
    (19, 1, UNKNOWN,      U8),    # 0 on 99.6%
    (20, 2, "trailer_a",  U16),   # constant 391 on 93%
    (22, 2, "trailer_b",  U16),   # constant 0xffff on 99%
    (24, 1, UNKNOWN,      U8),    # 3 on 93%
)


def _u16(mm, o):
    return int.from_bytes(mm[o:o + 2], "little")


def _i16(mm, o):
    v = _u16(mm, o)
    return v - 65536 if v >= 32768 else v


def locate(mm, bridge_slots=40, min_trailers=50):
    """(start, end, n_trailers) of the table, or None.

    Found by the trailer's residue class mod STRIDE, then the longest contiguous run on that
    class. `bridge_slots` spans the empty slots inside the table (7% carry no trailer); it
    bounds a GAP, not the table, so it cannot decide the row count -- widening it merges
    nothing because there is only one run to find.
    """
    buf = mm[:] if not isinstance(mm, (bytes, bytearray)) else mm
    offs, i = [], buf.find(TRAILER)
    while i != -1:
        offs.append(i)
        i = buf.find(TRAILER, i + 1)
    if not offs:
        return None
    best = None
    for res in range(STRIDE):
        on = [o for o in offs if o % STRIDE == res]
        if len(on) < min_trailers:
            continue
        runs, cur = [], [on[0]]
        for a, b in zip(on, on[1:]):
            if b - a <= bridge_slots * STRIDE:
                cur.append(b)
            else:
                runs.append(cur)
                cur = [b]
        runs.append(cur)
        run = max(runs, key=len)
        if best is None or len(run) > len(best):
            best = run
    if not best:
        return None
    return best[0] - TRAILER_OFF, best[-1] - TRAILER_OFF + STRIDE, len(best)


def read_slot(mm, o):
    """Decode one slot FROM the layout, so the parser cannot drift from the audit."""
    out = {"offset": o}
    for off, width, name, kind in LAYOUT:
        if name == UNKNOWN:
            continue
        b = o + off
        out[name] = mm[b] if kind == U8 else (_i16(mm, b) if kind == I16 else _u16(mm, b))
    return out


def scrape(mm, valid_clubs=None):
    """Every slot that references a match -> list of dicts, in file order.

    `valid_clubs` (a set of tids from the info spine or the club index) is the validator; with
    it, 100% of slots carrying a pair resolve on the reference save. Without it, only the
    0xffff sentinel is checked and the caller gets whatever the bytes say.
    """
    reg = locate(mm)
    if not reg:
        return []
    lo, hi, _ = reg
    out = []
    for o in range(lo, hi, STRIDE):
        a = _u16(mm, o)
        h = _u16(mm, o + 2)
        # 0 is a null id, the same class of sentinel as 0xffff -- not a tuned filter. It
        # matters at exactly one place: the table's FIRST slot straddles the 16-byte table
        # that ends immediately before it, and reads `10 27 10 27` (10000, 10000) there.
        # reference's club index has no tid range check (deliberately -- real club tids go
        # down to 51), so tid 0 resolves to an award record and the slot would otherwise
        # pass every other test.
        if a in (0, NO_CLUB) or h in (0, NO_CLUB) or a == h:
            continue
        if valid_clubs is not None and (a not in valid_clubs or h not in valid_clubs):
            continue
        out.append(read_slot(mm, o))
    return out
