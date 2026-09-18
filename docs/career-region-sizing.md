# Two career-half structures, and which one is a fixed pool

**2026-09-18/19, following on from PR #58 ("table-framing").** That PR proved the *reference*
database announces its own table sizes (`[8xFF][count]`). This asks the same question of the
*career* half instead — is anything back there a fixed-size allocation, and is anything else
just an ordinary growing structure? Tested against **three independent saves spanning the whole
career** (`frem-2023-07-02`, `frem-2024-06-30`, `frem-2026-06-11`) — a third save was pulled
specifically to stop a two-save coincidence being reported as a proof, and it caught exactly
that once.

**Headline: one real fixed pool, one false one.** The player-history slab is a fixed-size
allocation, proven with a parameter-free structural test, reproduced exactly on all three
saves. The club-records region right after it looked like a second fixed pool after two saves
agreed to the byte — the third save refuted it. It is an ordinary append-and-shift structure:
real records get inserted, physically growing that part of the file, and everything downstream
shifts to make room. The two structures sit back-to-back but behave oppositely, and that
contrast is the actual finding.

## 1. The history slab — genuinely a fixed pool, proven exactly

`fmparser/history.py`'s `locate()` finds this table by **sampling** 48 points and scoring
candidates by how many satisfy pointer continuity — fast, and correct in practice, but a
threshold, not a proof. Redone here with **zero sampling and zero thresholds**, so a candidate
either satisfies every check on **100% of its declared rows** or it is discarded outright:

1. Deterministic range+fits filter (same first stage `locate()` already uses: the header's high
   byte is 0, the declared count is in a sane range, the table fits in the file). This leaves
   millions of candidates.
2. Progressively longer **exact** prefix checks — every one of the first 16, then 256, then
   4,096, then 65,536 rows must satisfy `next == 0xFFFFFFFF or next < declared_count`. No
   candidate survives on a partial match; this is pure funnel-narrowing, not scoring.
3. On the handful of survivors, a **full check over every declared row**: build the pointer
   graph and require **max in-degree == 1** and **count(in-degree-0 rows) == count(terminator
   rows)** — a perfect forest. Exactly one candidate in the whole file clears this on every save
   tested.

| save | rows | start | end | heads = terminators |
|---|---|---|---|---|
| 2023-07-02 | **265,423** | 40,364,927 (`0x0267eb7f`) | 44,611,695 (`0x02a8b86f`) | 34,441 |
| 2024-06-30 | **265,423** | 40,479,437 (`0x0269aacd`) | 44,726,205 (`0x02aa77bd`) | 44,117 |
| 2026-06-11 | **265,423** | 42,630,105 (`0x028a7bd9`) | 46,876,873 (`0x02cb48c9`) | 25,622 |

**Row count is exactly 265,423 in all three** — a fixed, per-career allocation (already known to
differ between careers: Bucaspor's is 295,648, per `table-framing.md`), not something that grows
as the career plays out. **Absolute position drifts** (start moves ~2.3M bytes over the three
years, because everything upstream — contracts, transfer history, the name id-tables — grows),
so the slab must be *relocated* on every save; only its row count and internal shape are the
fixed things.

## 2. The 209-byte handoff — a real, exact constant

Immediately after the slab's proven end, the club-records table (`fmparser/clubrecords.py`)
begins **exactly 209 bytes later, in all three saves**:

| save | slab end | club-records start | gap |
|---|---|---|---|
| 2023-07-02 | 44,611,695 | 44,611,904 | **209** |
| 2024-06-30 | 44,726,205 | 44,726,414 | **209** |
| 2026-06-11 | 46,876,873 | 46,877,082 | **209** |

This is the one place in this investigation where "find the start structurally, then just add a
known number of bytes" is actually earned — three independent confirmations, zero tuning.
**The reverse is not true**: club-records' own *end* cannot be reached this way (see below).

## 3. Club-records — looked like a second fixed pool, is not

### The false positive

Two saves (2023, 2026) originally measured the same span from club-records' decoded end to a
genuine `0x00` filler wall: **4,558,055 bytes, to the byte.** That looked like a second fixed
pool, the same character as the slab. **A third save (2024) broke it**: properly re-measured
(tracking the actual stride-70 sentinel sequence, not just the raw last occurrence of the
2-byte pattern anywhere in the file — that raw approach hit unrelated high-entropy bytes 8+ MB
further into the file and produced garbage), the span comes out as 4,558,007 / 4,558,292 /
4,558,007 bytes for 2023/2024/2026 — close, but the middle save is 285 bytes off. Two saves
agreeing is not proof; it just means a third save hadn't been checked yet.

### What IS exact: the record's internal layout

One thing did reproduce perfectly. The genuine zero-fill wall always begins **exactly 48 bytes**
after the last `e4 07` (year-2020 empty-slot sentinel) hit belonging to the trailing table's
70-byte stride, in all three saves:

| save | last sentinel hit | wall | wall − hit |
|---|---|---|---|
| 2023-07-02 | 50,391,178 | 50,391,226 | **48** |
| 2024-06-30 | 50,529,856 | 50,529,904 | **48** |
| 2026-06-11 | 52,721,016 | 52,721,064 | **48** |

That pins the record's real internal layout: if the sentinel field sits at offset **+22** of a
70-byte record, the record's own end is `hit − 22 + 70 = hit + 48` — exactly the wall. So the
table's last record ends precisely where real padding starts; the sentinel is not at offset 0
as first assumed.

### The direct test that settled it: track one real club across all three saves

Southampton, tid 504, decoded identically every time via `clubrecords.scrape_team_records`:

| save | blocks (Overall + seasons) | footprint (bytes to the next club's block) |
|---|---|---|
| 2023-07-02 | 1 | 1,247 |
| 2024-06-30 | 1 | 1,247 |
| 2026-06-11 | **2** | **1,459** |

Gaining a second block (its 2025/26 season, on top of Overall) between 2024 and 2026 grew its
footprint by **exactly 212 bytes** — real bytes inserted, not space claimed out of a pre-existing
reservation. A whole-file sweep of every club's footprint (any tid, not just recognised ones)
shows the same 212-byte step across the board: clubs cluster into discrete size tiers exactly
212 bytes apart (1,247 / 1,459 / 1,671 / 1,883 / 2,282 / 2,494 / 3,317 / 3,529 / …), and a club
with 1 block and a club with 2 blocks are found at *overlapping* tiers depending on which other
categories happen to be populated — consistent with "costs 212 bytes per block, added on
demand," not "reserved N blocks' worth of space up front, most of it empty."

**Conclusion: club-records (and, by extension, the trailing empty-slot table right after it) is
an ordinary append-and-shift structure.** New blocks get inserted inline; everything physically
downstream — the trailing empty-slot pool, and the genuine `0x00` wall after it — shifts to make
room. That is exactly why the "second pool" size crept upward across the career
(club-records-start → wall: 5,779,322 / 5,803,490 / 5,843,982 bytes for 2023/2024/2026) rather
than staying fixed — it isn't one allocation being consumed, it's the whole downstream file
sliding as upstream content grows, the same drift `regions.py`'s own comments already warn
every hand-tuned window is subject to.

### Net effect

| structure | behaviour | proof standard |
|---|---|---|
| history slab | **fixed pool** — exact row count and forest shape, position recycled not grown | parameter-free, exact, 3/3 |
| club-records + trailing empty-slot table | **append-and-shift** — real growth, no reserved headroom | refuted a 2-save coincidence with a 3rd save |

## Method, reusable for the next region

This is the general recipe worth carrying into whatever gets checked next (see
[`docs/TODO.md`](TODO.md)):

1. **Never trust two saves.** A match between two data points can be coincidence — the whole
   4,558,055-byte "second pool" claim looked solid until a third save was pulled specifically to
   stress it, and it broke immediately.
2. **A sampled/thresholded test finds a candidate; only a 100%-of-rows check proves one.**
   `history.locate()`'s 48-sample score is fine for a first pass, but the claim "this is a fixed
   pool" needs the full pointer-forest check over every declared row, not a percentage.
3. **"Last occurrence of a byte pattern" is not the same as "extent of the structure it belongs
   to."** The raw last-hit approach silently wandered into unrelated high-entropy bytes; tracking
   the actual stride sequence (gaps that are exact multiples of the record size) is the fix.
4. **To tell "fixed pool" from "grows by insertion" apart, track one identified entity across
   saves**, not the aggregate region. Aggregate boundaries move for reasons that have nothing to
   do with whether any single structure inside them is fixed-size — Southampton's own footprint
   was the test that actually answered the question; the region-level byte-count never could.
5. **A structural boundary belongs to something with its own independent proof**, not to
   whatever happens to be adjacent. `matches.find_match_region()` (delimiter-cluster based) was
   tried as a possible far-side anchor and currently returns **0 valid anchors on the 2023 and
   2024 saves against 59 on 2026** — an open, unexplained discrepancy in its own right (see
   TODO), and a reminder not to lean on a locator that hasn't itself been proven stable.

## Reproducing this

No new script was shipped this pass (the working scripts were exploratory and removed); the
method above is written out in enough detail to reimplement directly against
`fmparser/history.py` (`locate()`, `STRIDE`) and `fmparser/clubrecords.py`
(`scrape_team_records`, `scrape_player_records`). A natural follow-up is turning the exact
(no-sampling) history-slab locator into a real function alongside `history.locate()`, the same
way `scripts/audit_table_headers.py --confirm` exists next to the reference-table locators — see
TODO.

## Open threads this surfaced

- **`fmparser/mapregions.py`'s `sub_regions()` calls `lightresults.find_light_region()`
  (singular) — the real function is `find_light_regions()` (plural, returns a list).** This is a
  live `AttributeError`, silently swallowed by a bare `except: pass`, so
  `scripts/map_regions.py`'s "content-located sub-regions" listing has never once printed a
  `light_results` line for any save. One-line fix; not yet applied.
- **`matches.find_match_region()` returns 0 valid anchors on `frem-2023-07-02` and
  `frem-2024-06-30`** (25 delimiter anchors found, none pass `_valid_match_header`) but 59/85 on
  `frem-2026-06-11`. Not investigated further here — could be a real gap in the matches locator
  for these specific saves, or something else entirely about their match data. Worth checking
  before relying on `find_match_region` as a boundary anchor for anything else.
- **The overall club-records + empty-slot span is not yet bounded by anything independently
  fixed on its far side.** We know it grows; we don't yet know what (if anything) sets a hard
  ceiling on it, or whether it's genuinely unbounded until it collides with whatever comes next
  in the file.
