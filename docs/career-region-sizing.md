# Career-half structures: which ones are fixed pools, and which just look that way

**2026-09-18/19, following on from PR #58 ("table-framing").** That PR proved the *reference*
database announces its own table sizes (`[8xFF][count]`). This asks the same question of the
*career* half instead — is anything back there a fixed-size allocation, and is anything else
just an ordinary growing structure? Tested against **five independent saves**: three spanning
the whole career (`frem-2023-07-02`, `frem-2024-06-30`, `frem-2026-06-11`) plus two more from
the *same* season (`frem-2022-08-27`, `frem-2023-06-26`) pulled specifically to separate
"grows once a season" from "grows continuously." A third save was pulled the first time
specifically to stop a two-save coincidence being reported as a proof, and it caught exactly
that once — a pattern repeated below.

**Headline: two real fixed pools found so far, two false ones ruled out.** The player-history
slab and the away-first match-slot table (`matchslots.py`, established separately) are genuine
fixed-size allocations. Club-records and the "our matches" rich per-match stat blocks both
*looked* like fixed pools at some point in this investigation and both turned out to be ordinary
append-and-shift structures once tested properly — real records get inserted, physically growing
that part of the file, and everything downstream shifts to make room. Matches also does
something club-records doesn't: it resets to empty at every season boundary.

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

## 4. Our matches — append-and-shift within a season, wiped at season start, then a real wall

This also resolves the `matches.find_match_region()` discrepancy flagged as an open thread
below in an earlier pass of this doc: **it isn't a locator bug.** `2023-07-02` and `2024-06-30`
return 0 valid match anchors because both saves are effectively at a season boundary — the
first is literally day one of a new season, and the region turns out to reset to empty there,
same as `2024-06-30` apparently being close enough to one. Confirmed by testing two saves from
inside the *same* season instead.

### The region genuinely grows with match count, not into reserved space

`2022-08-27` (early in season 2023) and `2023-06-26` (near the end of the same season) both
start their real matches on the exact same day (day 196, 2022 — season start), and the amount
of real match data between them scales with how many matches had actually been played:

| save | valid matches | offset span of real match data |
|---|---|---|
| 2022-08-27 | 9 | 41,275 bytes |
| 2023-06-26 | 43 | 216,358 bytes |

9 → 43 matches is 4.8×; the span grows 5.2×. Roughly proportional, and nowhere near equal — a
fixed container being filled in would show the same span in both saves regardless of match
count. It doesn't. **This is append-and-shift, the same signature as club-records**, just reset
to zero at every season change instead of accumulating across the whole career.

### The exact wall at the end — real, and reproduces on all three saves tested

Right after the *last* real match's own data (not the aggregate span above — the tail end of
whichever match happened to be added most recently), there is a run of `0xFF` padding whose
length does not depend on how many matches preceded it:

| save | matches | padding length | first bytes after |
|---|---|---|---|
| 2022-08-27 | 9 | **550** | `01 7b 04 5a 01 e5 07 ff ff …` |
| 2023-06-26 | 43 | **550** | `02 7b 04 5a 01 e5 07 ff ff …` |
| 2026-06-11 | 59 | **550** | `03 7b 04 5a 01 e5 07 ff ff …` |

Exactly 550 bytes, independent of match count, in all three saves. So the matches region really
does end at a hard, reproducible wall — it just isn't headroom reserved for more matches (see
next).

### What's actually on the other side: a different table entirely, not more match space

Extending the read past the wall shows a small, distinct, repeating record —
`[flag u8][value u16][tid u16][year u16]` — that has nothing to do with match count:

```
2026-06-11:
  56,314,027:  03 7b 04 5a 01 e5 07   flag=03  value=1147 (Danish 3rd Division, our league in 2021)  tid=346 (us)  year=2021
  56,314,092:  01 04 00 5a 01 e6 07   flag=01  value=4                                                tid=346      year=2022
  56,314,157:  01 03 00 5a 01 e7 07   flag=01  value=3                                                tid=346      year=2023
```

Consecutive entries sit **exactly 65 bytes apart** (confirmed twice: 2021→2022 and 2022→2023 in
the same save) — a stride not seen anywhere else in this codebase (21/22 club-records, 25
matchslots, 70 the trailing club-slot table, 16 history rows). It grows by one record per
**season**, tid 346 constant throughout: the 2023 save shows 2 entries (2021, 2022), the 2026
save shows at least 3 (2021, 2022, 2023). Not characterised beyond this — see Open threads.

**So the full picture at this boundary is three-part**, not two: `[real matches, growing] →
[550 bytes of exact fixed padding] → [an independent, differently-shaped, differently-growing
per-season table]`. The 550-byte wall is a genuine, reproducible structural fact; it's a
separator between two unrelated structures, not slack space either one grows into.

### Net effect, updated

| structure | behaviour | proof standard |
|---|---|---|
| history slab | **fixed pool** — exact row count and forest shape, position recycled not grown | parameter-free, exact, 3/3 |
| club-records + trailing empty-slot table | **append-and-shift**, accumulates all career, no reserved headroom | refuted a 2-save coincidence with a 3rd save |
| our matches (rich per-match stat blocks) | **append-and-shift within a season**, wiped at season start, ends at an exact 550-byte wall | 3/3 on the wall; season-reset confirmed via same-season pair |
| the away-first match-slot table (`matchslots.py`, established separately) | **fixed pool** — exactly 3,975 slots on every Frem save across 4 seasons | already proven elsewhere; cited here for contrast |

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
   tried as a possible far-side anchor and initially returned **0 valid anchors on the 2023 and
   2024 saves against 59 on 2026** — resolved below (§4): both zero-anchor saves are effectively
   at a season boundary, and the region turns out to reset there. Still a reminder not to lean on
   a locator's output before checking *why* it disagrees across saves.
6. **A padding wall is not evidence that the thing before it owns the space behind it.** The
   550-byte gap after the last real match looked, before checking, like it might be slack the
   region could still grow into. Reading past it showed a completely different, independently
   growing table instead. Always read past a padding boundary before assuming what it's for.

## Reproducing this

No new script was shipped this pass (the working scripts were exploratory and removed); the
method above is written out in enough detail to reimplement directly against
`fmparser/history.py` (`locate()`, `STRIDE`), `fmparser/clubrecords.py`
(`scrape_team_records`, `scrape_player_records`), and `fmparser/matches.py`
(`match_anchors`, `parse_header`, `_valid_match_header`, `find_match_region`). A natural
follow-up is turning the exact (no-sampling) history-slab locator into a real function alongside
`history.locate()`, the same way `scripts/audit_table_headers.py --confirm` exists next to the
reference-table locators — see TODO.

## Open threads this surfaced

- **`fmparser/mapregions.py`'s `sub_regions()` calls `lightresults.find_light_region()`
  (singular) — the real function is `find_light_regions()` (plural, returns a list).** This is a
  live `AttributeError`, silently swallowed by a bare `except: pass`, so
  `scripts/map_regions.py`'s "content-located sub-regions" listing has never once printed a
  `light_results` line for any save. One-line fix; not yet applied.
- **RESOLVED: `matches.find_match_region()` returning 0 valid anchors on `frem-2023-07-02` and
  `frem-2024-06-30`** was not a locator bug — both saves are effectively at a season boundary and
  the matches region resets to empty there (§4). Not yet turned into an actual code fix or a
  documented invariant in `matches.py` itself — right now this knowledge only lives in this doc.
- **The stride-65 per-season table right after the matches wall is unnamed.** Shape is pinned
  (`[flag u8][value u16][tid u16][year u16]`, one record per season, tid constant at our own
  club), but the `value` field's meaning is not — 1147 for the 2021 entry (our league cid that
  season) versus small integers (4, 3) for 2022/2023 doesn't obviously generalise. Worth checking
  whether `value` is always "current league cid" for the season it belongs to, or something else
  entirely for seasons after the first.
- **Is this the same per-season series `table-framing.md` already flagged near 44.6 MB** ("a
  per-season series — `[f32][…][u16 year]`, 7.0 in 2021, 10.0 in 2022 — FF-padded, no count") —
  a second copy, a different table with a similar shape, or the same table this doc simply found
  a different route to? Not checked; the two were found independently and the offsets don't
  obviously match up.
- **The overall club-records + empty-slot span is not yet bounded by anything independently
  fixed on its far side.** We know it grows; we don't yet know what (if anything) sets a hard
  ceiling on it, or whether it's genuinely unbounded until it collides with whatever comes next
  in the file.
