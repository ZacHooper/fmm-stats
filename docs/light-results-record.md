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

## A UI observation worth keeping

The game renders a single match-day as **two sections under the same date header**, with nothing
clickable to tell them apart (visible in all four screenshots: EPL 4+2, 5+2, Bundesliga 5+1).
Zac spotted it. Of the verified fixtures, **group 1 scores 9/23 and group 2 scores 0/5** — n is
too small to be conclusive on its own, but it is consistent with one match-day being stored in
more than one place, and it costs nothing to keep recording. The `ui_group` field in the truth
fixture exists for this.
