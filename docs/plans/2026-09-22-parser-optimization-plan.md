# Parser Performance Optimization Plan

> **Goal:** Optimize the top bottlenecks in `extract.py` identified during profiling (`person_info`, `lightresults`, `clubrecords`, and `history`), reducing per-snapshot extraction from ~19.3s to <4.0s and full career rebuild to <2.5 minutes, while maintaining 100% byte-identical baseline outputs.

**Worktree Requirement:** All implementation work will be carried out in an isolated git worktree (`../fm-parser-perf` on branch `perf-parse-optimizations`) to prevent interference with concurrent agents working on the repository.

---

## Architectural Breakthrough: `person_info` is Fully Sequential

We confirmed the true binary layout of `person_info` on both Frem (Denmark) and Bucaspor (Turkey):
- The table header frame `[8x 0xFF][u32 count]` at ~572 KB (`locate_person_info`) defines the exact table bounds.
- Slot 0 is a template/null record, followed immediately by record 1 (`tid=1`), record 2 (`tid=2`), through record `count - 1`.
- **Each record's length is 100% deterministic and self-contained:**
  - 68-byte fixed `PERSON_INFO` head (`tid`, `uid`, names, `dob`, etc.)
  - 16 bytes of padding (`4 x int32 = -1`)
  - 1 byte `Unknown7`
  - 1 byte `LanguageCount (L)`
  - `L * 3` bytes (each language is `language_id u16` + `proficiency u8`)
  - 1 byte `RelationshipCount (R)`
  - `R * 8` bytes (each relationship is `[Level u8][Type u8][Unk u8][Uid u32][Reason u8]`)
  - 1 byte `Unknown21`
  - Total stride per record: `88 + L * 3 + R * 8` bytes.
- **Empirical validation:**
  - Frem: Walked all **32,965 records in 0.191s** (recovering 276 valid records previously missed by the sentinel scan).
  - Bucaspor: Walked all **34,311 records in 0.204s**.
- **No scanning whatsoever.** Zero pattern matching, zero birth-year sweeps across 60 MB. We locate the table header once, and walk every record sequentially.

---

## Measured Realities Across Careers (Empirical Baseline)

Inspected saves across both careers and dates:
- Frem: `frem-2021-07-01.fms` (day 1), `frem-2024-05-25.fms` (mid), `frem-2026-07-02.fms` (season 5)
- Bucaspor: `bucaspor-2022-05-25.fms` (season 1), `bucaspor-2024-03-16.fms` (season 3)

### Discovered Invariants:
1. **`history` slab bounds (`h_start`, `h_end`):**
   - File size: 59.1 MB to 65.2 MB.
   - `h_start` always sits between **39,561,805 and 43,219,460** (consistently at 66.8%–67.0% of file size).
   - `h_end` always sits at **73.3%–74.0%** of file size.
   - Currently, `history.locate()` evaluates candidates across the **entire 65 MB file** from offset 0.
2. **`clubrecords` location relative to `h_end`:**
   - On every save with records (both careers, 2022–2026), team records start at **EXACTLY `h_end + 209` bytes**.
   - Player records start between **`h_end + 461` and `h_end + 3,471` bytes**.
   - All team and player records terminate before **`h_end + 1,286,114` bytes** (a 1.29 MB total span).
   - Currently, `clubrecords.py` runs a 1-byte incremental loop `while r < len(mm): r += 1` across 60 MB, executing **11.2 million row validations** in Python bytecode.
3. **`lightresults` redundancy:**
   - `lightresults.sweep()` runs 18.1M `_u16` reads searching for simulated match results.
   - Its results are already discarded in `extract.py` (club->league comes from club records directly; only 31 competition metadata entries were pulled from it, all available via `R.comp_detail` / `clubs_comps.py`).

---

## Implementation Tasks

### Task 1: Migrate `person_info` to Pure Table Walk & Purge Scanners
- **Files:** `fmparser/tables/person_info.py`
- **Approach:**
  - Define composite segment / record walk from `locate_person_info` start.
  - Advance slot 0, then read records 1 to `count - 1` using the `88 + L * 3 + R * 8` stride.
  - Completely **delete `_scrape_nicknamed` and `_nickname_sentinel_candidates`**.
  - All nicknames and un-nicknamed records are decoded directly in order.
- **Expected Speedup:** 4.59s -> **0.20s** (**~23x speedup**, saving ~4.4s).
- **Verification:** Unit test asserting complete sequential walk on Frem and Bucaspor saves.

---

### Task 2: Bound & Streamline `clubrecords`
- **Files:** `fmparser/clubrecords.py`, `extract.py`
- **Approach:**
  - Update `scrape_team_records(mm, valid_clubs, lo, hi)` and `scrape_player_records(mm, valid_players, lo, hi)` to accept explicit search bounds.
  - In `build()`, obtain `h_start, h_end = H.slab_bounds(mm)`.
  - Default search window: `lo = h_end + 150`, `hi = h_end + 1_500_000` (covering the verified 1.29 MB span with safety margin).
  - Fallback: if `h_end` is unavailable, default to file boundaries.
- **Expected Speedup:** 2.44s -> **0.58s** (**4.2x speedup**, saving ~1.9s).
- **Verification:** Assert identical team records and player records on all test saves.

---

### Task 3: Bound `history.locate()` Candidate Evaluation
- **Files:** `fmparser/history.py`
- **Approach:**
  - The history header `u32 @ (start - 12)` strictly appears in the upper third of the save file.
  - Constrain candidate offset scanning in `locate(mm)` to `lo = 35_000_000`, `hi = min(len(buf) - 3, 48_000_000)` (or relative file window `0.55 * len(buf)` to `0.80 * len(buf)`).
  - Keep full `Table.sanity()` validation and rank ordering intact.
- **Expected Speedup:** 3.85s -> **0.85s** (**4.5x speedup**, saving ~3.0s).
- **Verification:** Verify `slab_bounds(mm)` returns identical `(rows, start)` on all archives.

---

### Task 4: Retire `lightresults` Sweep & Decouple League Reference
- **Files:** `extract.py`, `fmparser/lightresults.py`
- **Approach:**
  - In `extract.py:build_leagues()`, eliminate calls to `L.build()` and `L.sweep()`.
  - Build `leagues` reference directly from:
    1. `club_leagues.values()` (the actual competition CID of every club in the save).
    2. Any match competition CIDs from `season`.
    3. Resolve names, nations, reputations, and levels via `R.comp_detail(mm, cid)` and `R.league_name(mm, cid)`.
  - Keep `lightresults.py` helper constants/signatures as shims if needed, but remove the expensive sweep from the extraction pipeline.
- **Expected Speedup:** 2.11s -> **<0.05s** (**saving ~2.0s**).
- **Verification:** `leagues.json` and `club_league.json` remain identical.

---

### Task 5: End-to-End Regression Verification & Re-Benchmark
- **Files:** Full test suite
- **Steps:**
  1. `uv run python scripts/run_tests.py -u` (all unit test suites pass).
  2. `uv run python scripts/run_tests.py` (all 22+ suites pass).
  3. `uv run python scripts/assert_identical.py` (verify baseline files byte-identical).
  4. Run full `extract.py` timing benchmark to confirm target parse speed (<4.0s per snapshot).
  5. Run `scripts/validate_mart.py --db fm-frem.duckdb` to assert all 62 mart objects and ground truth invariants remain green.
