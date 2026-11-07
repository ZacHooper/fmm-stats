# The match-slot table, and where the fixture list is not

The ~47 MB region once read as "light results" is the Club History record tables, documented
in [`docs/parser/club_records.md`](parser/club_records.md). This file keeps the search for a
complete fixture list (it is the archive's `fix_man`, [`save-archive.md`](save-archive.md))
and the 25-byte match-slot table.

## The 2026-09-17 sweep: what the fixture list is NOT

The hunt for a complete results list was re-run from scratch against all 28 screenshot-verified
fixtures (`tests/fixtures/light_results_truth.json`) on `frem-2026-06-11.fms`. Each item below
is a MEASUREMENT, not an impression, and each kills a hypothesis that looked reasonable:

| hypothesis | test | result |
|---|---|---|
| home tid + away tid near each other with both scores | every oriented template `(sep, hg_off, ag_off)`, sep 1..128, offsets ±64, scored by DISTINCT FIXTURES explained | best template explains **9/28** — noise. The separation histogram is symmetric and all multiples of 16, i.e. per-club lookup tables |
| clubs referenced by club UID, not tid | same probe on the uid (a genuinely separate id space: Southampton is tid 504, uid 713) | best **5/27** |
| clubs referenced by a slot index within the competition | scan every stride/phase for a column where each index appears ~19 times over ~380 rows | **no round-robin column exists**; every hit is a byte counter (24 values × exactly 256) |
| the scores stored bare, order implied by the generated schedule | every run of ≥120 bytes all ≤ 11 with a football-shaped distribution | **0 survive** |
| the datadict holds fixtures (`fxds`, `ofxd`, `nfxd`, `mtdy`) | decoded all 996 + 60 + 59 + 106 records | **scheduling RULES** — day-of-week, kickoff 1800, template years 2000/2001. No scoreline anywhere. This is why an earlier session found "a schedule table but no link to a scoreline": there is no link to find |
| a second result list at ~49.36 MB (claimed by `lightresults.py`) | read the bytes | **does not exist** — an UNSET table, every field `0xff` on a 70-byte stride with clubrecords' `e4 07` (2020) empty-slot sentinel |
| an append diff between 2026-03-22 and 2026-06-11 would expose a filling table | per-section diff (the file grew 517 KB, so absolute offsets shift) | section 2 is only 61% identical; newly-filled bytes are smeared across 34–40 MB with no append signature |

Two dismissals from the earlier pass were themselves wrong and are withdrawn: the 40.05 MB
structure was ruled out because "`L.sweep()` recovers 0 records there", but `sweep()` reads the
21-byte CLUB RECORD and could never have found anything there — that argument proves nothing.

## The 25-byte MATCH-SLOT table — EXTENT and COVERAGE settled

> **MERGED into `fmparser/tables/match_slots.py` 2026-09-17.** The module's docstring is now the
> canonical, current source for this table — it carries everything below plus what's been
> found since (the table is 73% populated not 7%, competition-type findings, the orientation
> bug on repeated club pairs, and the `k`/`B` formulas this section left as leads). Read it
> first; this section is kept for the measurements and dead ends, not as the live reference.

Parsed by **`fmparser/tables/match_slots.py`**, guarded by **`tests/test_match_slots.py`**. The record
is **AWAY-FIRST**, which is the whole reason it went unfound: every probe above searched for an
oriented home→away pair and excluded it by construction.

### Location — self-locating, never a constant

It drifts hard (37.78 M on a 2023 save, 40.59 M on a 2025 one), so `locate()` uses the table's
own invariant: the 4-byte constant `87 01 ff ff` at **+20**, which occupies exactly ONE residue
class mod 25 and forms exactly ONE contiguous run. On frem-2026-06-11, 4,354 of the file's
19,663 occurrences sit on the winning residue against ~670 for the runner-up, where random
residues would give ~787. That margin *is* the identification.

### EXTENT — the slot count is preallocated, and that is the invariant

| save | start | end | slots |
|---|---|---|---|
| frem-2023-07-02 | 37.7794 M | 37.8787 M | 3,975 |
| frem-2025-06-29 | 40.5857 M | 40.6851 M | 3,975 |
| frem-2026-03-22 | 39.7082 M | 39.8076 M | 3,975 |
| frem-2026-06-11 | 40.0422 M | 40.1416 M | 3,975 |
| frem-2026-06-29 | 40.3934 M | 40.4927 M | 3,975 |
| bucaspor-2022-05-25 | 39.9654 M | 40.0640 M | **3,943** |
| bucaspor-2022-06-01 | 40.8197 M | 40.9183 M | **3,943** |

Constant within a career across four seasons, different between careers — the signature of a
table allocated when the career is created. A walk returning any other count is wrong, and the
test asserts it, so the row count can never become a function of a tuned constant.

### STRIDE — 25, measured two independent ways

Autocorrelation over 40.050–40.120 M puts stride 25 at 70.35% with 50 and 75 as its multiples;
the best non-multiple (23) scores 31.89%. Independently, the trailer's residue class is unique.
**Neighbouring bands are different tables** — 16/48 at 40.0–40.7 M, 9/27 at 41.1–41.5 M — so any
sweep must respect the extent above rather than the neighbourhood.

*Method note, worth keeping:* the first extent attempt measured periodicity over raw bytes and
returned a 157 KB region at 34.12 M as the strongest 25-byte table in the file. It was wrong —
inside a run of `00` or `ff` a byte equals its neighbour at EVERY stride, so a padding desert
scores ~1.0 on any period. That region is on an **83**-byte period and turned out to be a
per-person table of two dates (`[id u32]…[day 233][year 2025][day 174][year 2026]`, nulls
reading `00 00 b3 07` = day 0 year 1971) — a contract/registration table, now named rather than
mistaken for this one. Score periodicity over CONTENT only, and control against stride 24 and 26.

### COVERAGE — all 25 bytes, 12 named and 13 declared UNKNOWN

```
+0  away_tid   u16    0xffff (or 0) when the slot references no match
+2  home_tid   u16
+4  away_goals u8
+5  home_goals u8
+6  day        u16    day-of-year, 0-based
+8  UNKNOWN    u8     5 on 93%. NOT the cid — reads 5 on rows whose clubs are in leagues 2/4/32
+9  UNKNOWN    i16    call it A; 0..360 on fixture rows
+11 UNKNOWN    i16    B; r = +0.994 with A, B ~ 0.58 x A
+13 UNKNOWN    i16    == A - k
+15 UNKNOWN    i16    == B - k, the SAME k
+17 UNKNOWN    i16
+19 UNKNOWN    u8     0 on 99.6%
+20 trailer_a  u16    constant 391 on 93%
+22 trailer_b  u16    constant 0xffff on 99%
+24 UNKNOWN    u8     3 on 93%
```

`(+9 − +11) == (+13 − +15)` and `(+9 − +13) == (+11 − +15)` hold on **275/275** fixture rows, so
those four fields carry only **three** independent numbers. They are carried, not named.

### Validation of the fixture group

* **275 slots carry a club pair and 100% resolve to a real club** — chance is ~8%.
* `+4`/`+5` max 6-6, mean 1.37/1.67, **no row above 12**.
* `+6` is a valid day-of-year on **100%** of those rows.
* Three decode against the game: Tottenham 5-0 Bournemouth and West Brom 0-2 Liverpool (day
  143 = 2026-05-24, final round) from the screenshots, and Southampton 3-6 Newcastle (day 135)
  independently confirmed by the Club History screen's "Highest scoring match, 16/5/2026".

One row needed excluding and it is worth saying why, because it is not a fudge: the table's
FIRST slot straddles the 16-byte table ending immediately before it and reads `10 27 10 27`
(10000, 10000). It resolved only because reference's club index has no tid range check, so tid
0 maps to an award record. Rejecting a **null id** is structural; with it gone the internal
identity goes from 275/276 to **275/275**, which is the confirmation that it was noise.

### What the 275 matches actually are (frem-2026-06-11)

Every slot carries a **real result**, not a fixture: 3.05 goals/game, 121 home wins / 71 draws
/ 83 away wins, most common scorelines 1-0 (31), 1-1 (26), 2-2 (19), 0-0 (17). That is a
football distribution, and it is the strongest evidence the field group is read correctly.

**Our own club never appears.** 0 of 275 slots involve Frem (346) or the reserves (7296) —
our games live in the rich match region (`regions.MATCH_LO`) instead. The table is about
everyone else.

**30 leagues at once**, so it is not grouped per competition. By nation of the club's league:
Spain 222, England 131, Denmark 66, Germany 34, Belgium 6 — which tracks how many divisions
each nation has loaded, i.e. a scatter across the loaded world rather than a selection.
349 distinct clubs appear, 218 of them exactly once.

**Dates cluster into weekly rounds and thin out going back.** Days 121/128/135/142/150 are
exactly 7 apart and hold 25/24/27/24/25 matches each; before that it is 1–6 per day back to
day 9, and a thin tail runs into the PREVIOUS calendar year. That last part is confirmed
arithmetically, not assumed — see the `k` identity below, where those rows come out at
exactly −365.

All 14 English Premier Division slots on the reference save:

```
2026-03-14 Liverpool   3-2 Man City      2026-05-16 Brentford   1-1 Leeds
2026-04-04 Watford     3-1 Southampton   2026-05-16 Chelsea     1-0 Everton
2026-04-12 Leicester   2-4 Southampton   2026-05-16 West Brom   1-0 Watford
2026-04-26 Man UFC     0-4 Leeds         2026-05-16 Southampton 3-6 Newcastle
2026-05-02 Derby       0-3 Man City      2026-05-16 Newcastle   6-3 Southampton   <- mirror
2026-05-08 Bournemouth 1-0 Derby         2026-05-24 Tottenham   5-0 Bournemouth   <- verified
2026-05-09 Man City    2-1 Leeds         2026-05-24 West Brom   0-2 Liverpool     <- verified
```

A round is never complete: 2026-05-24 is a 10-match EPL round and only 2 of it are here.
11 fixtures are stored more than once and 10 also appear with home/away swapped, so the
275 slots are fewer than 275 distinct matches.

### The four unknown numbers carry ONE independent value

Naming them is still open, but their structure is now measured, and it collapses the record:

* **`k` is constant within a match-day** — 26 for every match on day 135, 19 for every match on
  day 142 — and `k == (save day-of-year) − (match day)` on 87% of slots. The exceptions are
  almost all exactly **−365**: matches from the previous calendar year, which is what
  establishes that a day above the save's own day-of-year belongs to the year before.
  So `C` and `D` are `A` and `B` re-referenced from the save date to the match date.
* **`B == floor(3A/5)`** on 81% of slots (100% of the day-135 block), so `B` is *derived*, not
  independent.

Four i16 fields, therefore, hold one number plus the match date. `A` ranges 6..354. What it
counts is unknown; `save_date − A` lands 1–100 days before the save with no pattern yet found.

One wrinkle worth recording rather than smoothing over: on `frem-2026-03-22` the offset is
**−6**, not 0, on 581/619 slots — the reference date is six days before the save's in-game
date. Consistent with the table being refreshed periodically rather than continuously; not
explained.

### How full the table gets

| save | in-game date | match slots filled (of 3,975) |
|---|---|---|
| frem-2026-03-22 | mid-season | **619** |
| frem-2026-06-11 | season just ended | **275** |
| frem-2026-06-29 | off-season | **125** |

The fill tracks how much football has recently been played. A fixed-size table holding a
decaying sample of recent results is exactly the shape the old
`light-results-rolling-buffer.md` note described — so that idea may have been right about a
STRUCTURE while being attached to the wrong bytes (it was written about the club-records
region, where nothing is deleted). Stated as a lead, not a finding: we have three saves, not a
controlled test.

### Ruled out as the selection rule

* **Club-record matches.** Southampton 3-6 Newcastle is in both this table and the Club History
  screen, which looked promising. It is coincidence: only 31/275 slots (11.3%) are also a
  club-record match, and only 36/3,262 club-record matches have a slot.
* **Our shortlist.** 0 of the 9 shortlisted players' clubs appear.

### What this table is NOT

It is **not the fixture list**. 275 matches, drawn from many leagues at once (Danish 2/3/4,
Spanish 32, English 5/6/7/8/70, reserve leagues), clustered on recent days — nothing like a
competition's full programme, and it recovers only 2 of the 28 screenshot fixtures. The other
3,700 slots carry a trailer, a day and the four numbers but no match. **What the table is FOR
is not established** — only its shape, its extent, and the fixture field group. Do not let the
module name suggest otherwise.

## Borders, and the search for a second match table (2026-09-17)

### Where the 275 sit inside the 3,975 slots

Every slot is written — **0 are untouched** — so the table is fully initialised and the empty
ones are blank-by-value, not blank-by-absence.

```
slot census (3,975)              match slots by decile
  3,699  trailer, day, numbers     0- 397 |##                            4
         but +0..+5 ALL 0xff       397- 795 |###################################  70
    275  a resolvable club pair    795-1192 |#####################################  83
      1  boundary artifact        1192-1590 |############################  56
                                  1590-1987 |###############  30
first match at slot 280           1987-2385 |##########  21
last  match at slot 2608          2385-2782 |#####  11
                                  2782-3975 |  0
```

The last **30% of the table is entirely matchless**, and the filled part decays from a peak
around slots 800–1200. Slot index is **neither** a club ordering (50% monotonic in either club
tid — chance) **nor** a time ordering (r = −0.16 against match date), so what orders the table
is unknown.

### The byte borders

* **Immediately before** (ends at 40042185): a **16-byte**-stride table, rows like
  `xx xx 5c a1 00 05 | 10 27 | 10 27 | yy yy`, where `10 27` is 10000 — a default/initial
  value repeated. This is what bleeds into the 25-byte table's first slot.
* **Immediately after** (from 40141560): unstructured records, with the ASCII string
  `Manager` at 40141735.
* The final slots read `ff ff ff ff ff ff 00 00 ... 00 ff 00 00 87 01 ff ff 03` — trailer
  present, everything else zeroed.

### You cannot expand beyond the 275 *within* this table

3,699 of the 3,700 non-fixture slots have **`+0..+5` all `0xff`** — both club fields *and* both
goal bytes explicitly unset. The match is not stored elsewhere in the record; it is simply
absent. What those slots DO carry: a valid day-of-year on 2,598 of them, a nonzero `+9` on
2,600, and the `+8` type byte (5 on 2,442, 0 on 1,105, then 4/2/3/1).

So the table is better understood as **~3,975 dated entries of which 275 additionally
reference a match**, not as a match table that is mostly empty.

### There is no second match table

The match signature — `[club u16][club u16][goals<=12][goals<=12][day 1..366]` with both clubs
in the **same league** — was swept at **every byte offset** in the file: 1,185 hits. Raw counts
are useless here, because any region with dense small bytes fires it. The control that works is
**alignment**: a real table's hits share a stride, noise does not.

| cluster | hits | best stride | on-grid | verdict |
|---|---|---|---|---|
| 40.049–40.107 M | 242 | **25** | **100%** | the known table |
| 36.395–36.398 M | 15 | 143 | 100% | **false** — see below |
| 14.4–14.9 M | ~120 | 2–3 | 45–72% | **false** — only ever Stoke/Sunderland/Swansea and Genoa/Inter/Lazio/Zebre, at irregular gaps, in a dense small-byte region |
| 6.127–6.205 M | 91 | 3 | 67% | **false** — fails alignment (this is the "497-record chained region" TODO flagged as never swept; it is now swept) |

Inside the known table the plausible/implausible ratio is **121**; outside it is **1.46**.
**No other gridded match signature exists in the save.**

The 36.395 M cluster is worth spelling out, because it is the most instructive false
positive and an earlier draft of this table described it wrongly. The 15 hits are NOT the same
fixture repeated: the opponent varies (Brøndby x8, FC Roskilde x6, FC København x5, FC
Midtjylland x2). What is CONSTANT is bytes `+4..+7` = `01 00 00 01`, which the signature reads
as "0-1" and "day 256" (`0x0100`). A constant scoreline and a constant date across four
different opponents is the tell — the opposite way round from how it first looked.

The containing structure is a **143-byte record, 4,099 of them at 36.3556–36.9418 M**, carrying
a sequential `u32` counter at +8 (6,411 -> 10,509, step 1) and a second at +12 that is always
exactly 4,723 higher. Its `+0`/`+2` fields vary freely (710 distinct values at +0) and only
coincidentally land on club tids — `+2` looked like a constant "Frem" only because a 15-row
window was sampled from a 4,099-row table. Unidentified, and not a match table.

Method note: the first null model required *implausible* goal bytes (13–250) and reported the
14 MB band as `inf` ratio, i.e. perfect. That was wrong — implausible bytes are rare in ANY
small-byte region, so the null measured nothing. Control on alignment, not on value ranges.

## A UI observation worth keeping

The game renders a single match-day as **two sections under the same date header**, with nothing
clickable to tell them apart (visible in all four screenshots: EPL 4+2, 5+2, Bundesliga 5+1).
Zac spotted it. Of the verified fixtures, **group 1 scores 9/23 and group 2 scores 0/5** — n is
too small to be conclusive on its own, but it is consistent with one match-day being stored in
more than one place, and it costs nothing to keep recording. The `ui_group` field in the truth
fixture exists for this.


## Match-slot findings beyond the shape (moved from TODO, 2026-09-29)

The world fixture list in the archive (`fix_man.dat`, [`save-archive.md`](save-archive.md)) is now the source of results, so the match-slot table (`fmparser/tables/match_slots.py`) is secondary. What was measured on it:

**The 25-byte AWAY-FIRST record is now DECODED as far as its shape goes** —
`fmparser/tables/match_slots.py`, guarded by `tests/test_match_slots.py`. Stride 25 (two independent
measurements), self-locating by a constant at +20, **3,975 slots on every Frem save across four
seasons and 3,943 on Bucaspor** (a preallocated table, which is the invariant that bounds the
walk), all 25 bytes named or declared UNKNOWN, and three fixtures verified against the game.

**It is NOT the fixture list, and it is not ~7% populated either** — that figure only counts
slots with a resolvable CLUB PAIR (a "fixture"; 275 on `frem-2026-06-11`). Checking the `day`
field independently of the club filter shows the table is **72-74% populated**, and the total
stays essentially constant while the mix shifts: fixture-count + clubless-but-dated count is
**2,874** on `frem-2023-07-02` and `frem-2024-06-30`, **2,873** on `frem-2026-06-11` and
`frem-2026-07-02` — four saves spanning 2023-2026, fixture count anywhere from 100 to 275, same
populated total every time. The remaining ~1,101-1,102 slots are genuinely inert (day=0, every
carried field zero). Reads as a fixed-size calendar of ~2,874 slots that fill in progressively
as matches are played, not a fixture list that's mostly empty — **the ~2,600 clubless-but-dated
slots are the majority of the table's real content and have never been examined.**

**Checked for a World Cup** (`frem-2023-01-06`, days after the real Qatar final, and
`frem-2026-07-02`, taken DURING the real 2026 tournament window): zero fixture rows resolve to
a nation in either save (100 fixture rows in the WC-window save, correctly down from 275 three
weeks earlier as domestic leagues broke for it). National teams do exist as their own club-style
records (86 found, e.g. Qatar tid 1,632,698,368) but their tids are 4+ orders of magnitude
bigger than this record's 16-bit `away_tid`/`home_tid` fields can hold (max 65,535) — a national
team is structurally unable to appear here, independent of the calendar.

**No `cid`/competition field is stored in the record — reconfirmed 2026-09-17 with the right
test, after the reputation-floor/empty-CODE fix raised the obvious question of whether one of
the 8 UNKNOWN bytes was secretly a now-more-resolvable cid.** "Does this byte resolve to *some*
valid competition" says yes almost everywhere — worthless, since 678 real cids packed densely
into 0..1400 make that near-guaranteed by chance. The test that actually settles it: on the
242/275 fixtures where both clubs share a league (so the correct cid is known independently of
the row), does any of the 25 bytes, read as u8 or u16, EQUAL that known cid? Every offset hits
0-2%, not the ~100% a real field would show (`tests/test_match_slots.py`'s new "NO CID FIELD"
check pins this). So the fix changed which already-inferred leagues resolve (`frem-2026-06-11`'s
275 fixtures span 349 distinct clubs across 47 `league_cid`s via each club's own DEFAULT
league membership looked up separately, ALL 47 of which now resolve, 20 only because of the
fix), not whether a hidden cid exists — it doesn't, and this table structurally cannot answer
the question for the other 33 fixtures. 242/275 pair two clubs from the same inferred league;
the other 33 can't be ordinary league fixtures by construction, and their real competition (cup
/ friendly / playoff) is unrecoverable from this record, full stop — not blocked by any decode
bug, so no future fix to `reference.py` can unlock it. Four were checked against Zac's own
in-game fixture screens and all four decoded
EXACTLY on **date**, but only two of the four also had the score read correctly the first time
— the other two were corrected after further checking (below), so treat any score quoted for a
cross-league row as unverified until it's been checked twice, not once:

| row | day → date | screenshot says |
|---|---|---|
| Forest 3-0 Maidstone | 13 → 2026-01-14 | FA Cup Third Round **Replay** (score OK) |
| Burnley 1-2 Arsenal | 199 → 2025-07-19 | pre-season **Friendly** (score OK) |
| Sevilla 1-3 Gladbach | 146 → 2026-05-27 | continental cup **Final**, neutral (was misread the other way round) |
| Nürnberg 2-3 Düsseldorf | 140 → 2026-05-21 | promotion **Playoff**, 1st leg, Düsseldorf won away (was misread as Nürnberg winning at home) |

A fifth cross-league row (Logroñés 0-3 A. Madrid, day 201) couldn't be found in-game — **now
solved** by the `k` formula below: its `k` is `naive + 4×365`, i.e. this really is a match, just
roughly four seasons stale in a slot that was never overwritten. It won't be on Atlético's
current fixture screen because it isn't from the current season at all — not a wrong
year-guess, as the old day≥181 heuristic made it look.

**Orientation is NOT reliable on a repeated club pair.** Three `(away_tid, home_tid)` pairs
recur with a different day and score each time — first read as possible reschedules, but
ground truth says all three are ordinary fixtures where the real venue genuinely differed (two
are legs of a two-legged playoff with real alternating venues; Merthyr/Bradford confirmed
directly). The table gets it wrong for exactly **one of the two rows, every time (3/3)**:
Palace/Stoke (day 142 wrong, day 138 right), Sint-Truidense/Beerschot (day 128 wrong, day 121
right), Merthyr/Bradford (day 114 wrong, day 359 right). It isn't even one consistent bug: on
Palace/Stoke the club **identities** are swapped between the away/home slots; on
Nürnberg/Düsseldorf above, the identities are correct but the **goals** are swapped between the
two clubs instead. Two distinct failure modes, both invisible from the bytes alone. **Every
single-occurrence row checked against a screenshot has been exactly right** — this is specific
to a club pair appearing more than once, not a flaw in away-first generally.

**Ruled out as a competition-type flag**, tested against the four confirmed rows plus the three
known league fixtures: `+8` (5 on 226/242 same-league rows AND 17/20 cross-league rows) and
`trailer_a` (the cup replay and a same-day plain-league game are both 5; another plain-league
game is 391). Neither separates cup/friendly/playoff from league. (Unaffected by the
orientation bug above — these are raw per-offset byte values, not which club they're read as.)

**`k` is SOLVED** — this was sitting unmerged in `light-results-record.md` from before
`matchslots.py` existed, so it's now folded into the module docstring rather than re-treated as
open. **`k = (save's own day-of-year) − (match day)`, wrapping `+365` for a previous-year
match** — exact or +365-exact on 251/275 rows (91%) on `frem-2026-06-11` (save day-of-year
161). This is the real date rule; prefer it over guessing a year from `day` alone. The ~9% that
miss are mostly off by a few days (a refresh-lag artifact, not a broken formula) except for a
handful that are further whole multiples of ~365 off — stale slots, as with the Madrid row
above. `B` isn't independent either: **`B == floor(3A/5)` on 223/275 (81%)** — of the four i16
fields, only ONE number is truly free.

The Sevilla-Gladbach final is also stored TWICE, 500 bytes (20 slots) apart, identical
tid/score/day, different `trailer_a` — the same multi-copy pattern as `clubrecords.py`.

**No ID field exists.** Checked every `UNKNOWN` byte for uniqueness across the 275 fixture rows
(262 genuinely distinct matches): the best candidate, `+9` (A), has only 94 distinct values —
reused ~3× on average. A is a date-derived number (via `k`), not a key; there's no sequential
match id to find here.

**Immediately before the table, no gap**: content density stays ~0.6 for at least 80KB back.
A DIFFERENT 16-byte-stride table runs for 9,692 records (~155KB) right up to this table's
start — `00 05 [u16 ~10000] [u16 ~10000] [i16 -1500..1087] ff ff ff 00 00 [u8] [2-byte trailer,
usually 5c-a1]`. The two ~10000 fields read as a percentage ×100 (100.00% default, real values
cluster 8500-9700). Not identified beyond that. "Manager" (ASCII) appears ~190 bytes after this
table's END, not before.

The 497-record chained region at 6.127-6.260 MB has now been swept: 91 signature hits but
only 67% share a stride, so it fails the alignment control and is not a match table. A
whole-file sweep at every byte offset found **no second gridded match signature anywhere** —
the 25-byte table is the only one (654 stray hits of the same trailer constant at 46.88-48.35M
were checked and decode as non-football garbage, not a second table).
