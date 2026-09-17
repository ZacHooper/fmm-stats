# The "light results" region is the CLUB RECORDS tables

> **SOLVED 2026-09-17.** Everything below was written while investigating this region as a
> list of match RESULTS. It is not one. It is the **Club History** screens — Team Records
> (biggest win, biggest defeat, highest scoring match, longest streaks) and Player Records
> (most goals in a season, youngest player, highest transfer fee). Identified against in-game
> screenshots of Southampton's Club History and now parsed by
> [`fmparser/clubrecords.py`](../fmparser/clubrecords.py), guarded by
> `tests/test_club_records.py`.
>
> **Read that module's docstring first.** This file is kept because the audit that led there
> is the method, and because several of its measurements (region bounds, coverage, the cost
> of each tuned constant) still describe `lightresults.py` as it stands today.
>
> **What it means for the hunt:** the complete match results are NOT here and never were.
> A club has ~12 rows because there are ~12 record CATEGORIES. "Each fixture stored in ≥2
> copies" is the two-slot pattern — "Highest scoring match" and "Highest scoring LEAGUE
> match" are the same game; a record in both the Overall and per-season table appears 4×.
> Standings computed from these rows read 5–13 games played because they were computed from
> record-holding matches. And 9/28 ground-truth "recovery" was us finding a fixture only when
> it happened to be a club record.

# The audit that got there

**2026-09-17.** What we actually read from the light-results region, what we demonstrably do
not, and the structural evidence for each claim. Every number here is measured by
**`uv run python scripts/audit_light_results.py`** on `frem-2026-06-11.fms`, against
**`tests/fixtures/light_results_truth.json`** — 28 results read off in-game screenshots.

That fixture file is the only honest check available. Our own club's matches live in the rich
match region (`regions.MATCH_LO`), a different structure, so grading the light parser against
them would be the parser marking its own homework.

> **Headline: `sweep()` recovers 9 of 28 verified fixtures — 32%.** An earlier estimate of
> "71% coverage" counted distinct club *pairs*, which is wrong twice over: a pair recurs twice
> a season, and a pair can be present carrying the wrong score.
>
> **The record is mis-aligned by one full stride** (below). Correcting it yields **4.7× more
> fixtures** with coherent dates — but still 9/28 on ground truth, because the missing 19 are
> absent from the structure rather than mis-read inside it. Two independent faults.

---

## What is NOT true (claims this audit overturned)

**The rolling buffer does not delete old results.** `agent-context/light-results-rolling-buffer.md`
says the engine "physically overwrites the oldest fixtures" past ~13–15 games so old results
"physically cease to exist". **Three of six opening-day fixtures (16 Aug 2025) are present,
with correct scores, in a save dated 11 Jun 2026** — ten months later. Coverage is spread
across the whole season, not clustered at the recent end. Light results is a **partial decode,
not a partial dataset**. The original authors saw ~13 games per club, assumed a 13-game window,
and the arithmetic happened to fit.

**Coverage is not uniform by date**, which is why a single spot-check misleads:

| round | recovered |
|---|---|
| EPL 2026-05-24 (final round) | 5/9 |
| EPL 2025-08-16 (opening day) | 3/6 |
| EPL 2026-01-10 (mid-season) | **0/7** |
| Bundesliga 2026-04-04 | 1/6 |

---

## Structure, verified

**Per-club HOME blocks.** The region is a sequence of blocks, one per club, each holding that
club's home fixtures on a 21-byte grid. Measured: of 1,476 chains of ≥5 records, **1,315 (89%)
have a constant first tid**; 1,161 blocks hold 8+ fixtures. This confirms the claim in
[`standings-record.md`](standings-record.md) independently.

**The chains are SHORT BY CONSTRUCTION** — longest 17, clear mode at 10–17, which is one club's
home programme for a season. Any region-finding heuristic with a `min_run` above ~17 finds
nothing at all. This is why `audit_light_results.grid_regions` uses `min_run=5`.

## The alignment — SOLVED, and the record is 11 bytes earlier than we thought

Measured, not guessed: for each of the 28 verified fixtures, find every record whose tid pair
AND score are both correct, then ask at what offset the **correct day-of-year** appears.

```
offset  -7 : 18/26  (69%)      <- the real field
offset +14 :  4/26  (15%)      <- what the parser reads
offset -28 :  4/26              (= -7 - 21, the previous record's copy)
```

−7 and +14 differ by exactly **21 — one full stride**. The parser has been reading the *next*
record's date. The same test puts `cid` at **−11** (61%), again 21 away from the +10 it reads.

**Corrected layout, relative to record start `R` (= the tid pair minus 11):**

| offset | width | field |
|---|---|---|
| R+0 | 2 | `comp_cid` |
| R+4 | 2 | `day` — day-of-year, 0-based |
| R+11 | 2 | `home_tid` |
| R+13 | 2 | `away_tid` |
| R+15 | 1 | `score_home` |
| R+16 | 1 | `score_away` |

Verified against ground truth: `Tottenham 0-5 Bournemouth, cid 5, day 143` → 2026-05-24, and
`Southampton 4-0 Sheff Utd, cid 5, day 227` → 2025-08-16. Both exact.

**Effect: 26,297 fixtures against the current parser's 5,569 — 4.7×**, with cid and day now
self-consistent per row instead of sliding.

**`+12` is not a year.** Searching every offset for the fixture's true year (2025/2026) finds
it **nowhere**. The old `year` field was the misaligned neighbour's bytes. A block mixes
competitions and seasons — Bournemouth's holds cid 5 (Premier League) and cid 6 (Championship)
fixtures together — so the season has to come from context, not from the record.

## Blocks are slot-limited, which is the real coverage story

Southampton's home block holds **17 fixtures**, ordered by day-of-year (0, 1, 4, 9, 10, 24, 79,
80, 95, 101, 135, 227, 234, 266, 280, 308, 359) and mixing seasons and competitions. A club
plays ~19 home league games in ONE season; across five seasons that is ~95. So the block is a
**fixed-size, date-ordered slot array**, and a later season's game at a similar day-of-year
overwrites an earlier one.

That reconciles every observation: opening-day 2025 survives (its day-227 slot was not reused)
while `Southampton 3-0 Aston Villa`, day 143 of 2026, is simply **not in the block** — the
neighbouring slot holds day 135. It is a ring buffer, but **per club and keyed by date slot**,
not the global 13-game time window the old note described.

**The alignment fix does not change the ground-truth score: still 9/28.** The missing 19 are
genuinely absent from this structure, not mis-read within it. Those two faults are independent
and it would be easy to claim the alignment fixed something it did not.

## The original mis-reading (kept: it is how the bug presented)

Within a block, **every opponent appears twice in consecutive rows, and the cid/year/day
columns slide down one row relative to the opponent+score columns**:

```
vs Stoke City        2-5   cid=6    +12=2021  +14=291
vs Stoke City        2-5   cid=6    +12=2023  +14=145
vs Bristol City      5-0   cid=6    +12=2023  +14=145
vs Bristol City      5-0   cid=5    +12=2022  +14=259
vs Aston Villa       0-5   cid=5    +12=2022  +14=259
vs Aston Villa       0-5   cid=276  +12=2020  +14=264
```

opponent+score is constant on row pairs (0,1), (2,3), (4,5); cid+date is constant on pairs
(1,2), (3,4), (5,6). **Offset by exactly one row.** This is the COLUMN-OFFSET trap CLAUDE.md §5
records from the career-history table, where a row's stats belong to the season on the previous
row.

Three symptoms, one cause:
- duplicated opponents in consecutive rows
- cid / year / day sliding by one row
- **years reading 2020–2023 in a 2026 save** — `+12` is not a plain year, or is misaligned

Ground truth pins it. In Bournemouth's block:

```
vs Watford            5-0   +14=143
vs Tottenham Hotspur  0-5   +14=143     <- Tottenham 5-0 Bournemouth, 24 May 2026 = day 143
```

Day 143 is exactly right for the Tottenham fixture; the Watford row above has borrowed it.

**Consequence for the parser, and it is not small.** `lightresults.py`'s docstring states each
fixture is stored in "≥2 copies (empirically always an even count)", and `sweep()` acts on it
via `min_copies=2`. That may not be a storage fact at all — it may be **this misalignment
manufacturing each fixture twice**, once aligned and once straddling its neighbour. If so, the
`min_copies` filter and the mirror-dedup are discarding real distinct fixtures, which explains
the misses far better than the year gate does.

## Tuned constants, and what each costs

All three faults are the same shape — a constant bounding a walk, the thing PR 51 existed to
remove.

**`YEARS = (0x07E4, 0x07E5, 0x07E6)`** — 2020/2021/2022, a Bucaspor-era literal
(`lightresults.py:61`). Measured rejection in the main region: it drops **69%** of candidates
that have two valid club tids. Widening to 2020–2037 recovers **+2,140 fixtures (+35%)** file-wide
— but still rejects 62%, so `+12` is simply **not a year for most records**. The gate is not
merely too narrow; it is the wrong test.

**`find_light_regions`** (`lightresults.py:70`) locates regions by searching for those same three
year-marker byte pairs, then gates on `min_hits=50`, `margin=30_000`, `merge_gap=200_000` —
**four** constants. It returns 5 regions on a 2023 save, 4 on `frem-2026-06-29`, **3** on
`frem-2026-06-11`: it goes blind as a career runs past 2022. A structural sweep finds a
**497-record chained region at 6.127–6.260 MB that it never sees**, in which the year gate
rejects **100%** of candidates.

## Coverage — every byte named, declared UNKNOWN, or padding

Main region, 46.877–48.342 MB:

```
inside decoded records    12.8%
0x00 / 0xff padding       65.1%
NON-PADDING, UNREAD      383,948 bytes  (26.2%)   <- content no parser looks at
```

Some of that is a **22-byte-stride per-season table** interleaved in the same region:
`[u32][IEEE-754 float][u32][u32][ff ff ff ff][year u16]`, floats running 22.0, 9.0, 5945.0,
12370.0, 79583.0, 536262.0 — the "likely club finances" lead in `standings-record.md`. Useful to
have identified: it is **not** missing fixtures.

## The 21-byte record as currently read

`uv run python scripts/audit_light_results.py --map` generates this, so it cannot go stale.

| offset | width | field |
|---|---|---|
| +0..1 | 2 | `home_tid` |
| +2..3 | 2 | `away_tid` |
| +4 | 1 | `score_home` |
| +5 | 1 | `score_away` |
| +6..7 | 2 | **UNKNOWN** |
| +8..9 | 2 | `flags` — 0x40xx/0xc0xx marker, NOT the competition |
| +10..11 | 2 | `comp_cid` |
| +12..13 | 2 | `year` — see the alignment problem above |
| +14..15 | 2 | `day` — day-of-year, 0-based |
| +16..17 | 2 | **UNKNOWN** |
| +18..19 | 2 | **UNKNOWN** — observed `ff ff` terminator |
| +20 | 1 | **UNKNOWN** — observed copy index |

**14 of 21 bytes decoded, 7 undecoded.** Do not treat the undecoded seven as padding; they are
declared UNKNOWN so that the audit counts them, per CLAUDE.md's coverage rule.

## Ruled out while looking

- **The 40.05 MB structure is not a light region.** `[A u16][B u16][sA][sB][day u16][cid u8]`,
  verified on two fixtures with the correct date and cid. No 21-byte stride, and `L.sweep()`
  recovers **0** records there against 5,830 from a real light region.
- **The ±16/±32/±48/±64 "variants"** the first variant pass surfaced are coincidence: they hinge
  on fixtures that finished 0–3, and the byte pair `(0,3)` is everywhere. Count distinct
  fixtures explained, not site-hits.
- **A packed per-round score array**: exactly one 8/9 window in the whole file, in a
  neighbourhood of `ff`-runs and u32s.
- **4-byte slot-index records** `[slot][slot][sh][sa]`: longest consecutive run 27; a 20-team
  season needs 380.

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

Parsed by **`fmparser/matchslots.py`**, guarded by **`tests/test_match_slots.py`**. The record
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

## A UI observation worth keeping

The game renders a single match-day as **two sections under the same date header**, with nothing
clickable to tell them apart (visible in all four screenshots: EPL 4+2, 5+2, Bundesliga 5+1).
Zac spotted it. Of the verified fixtures, **group 1 scores 9/23 and group 2 scores 0/5** — n is
too small to be conclusive on its own, but it is consistent with one match-day being stored in
more than one place, and it costs nothing to keep recording. The `ui_group` field in the truth
fixture exists for this.
