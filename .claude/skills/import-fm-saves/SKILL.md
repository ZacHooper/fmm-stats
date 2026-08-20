---
name: import-fm-saves
description: Parse new FMM22 .fms save files and load them into the DuckDB store (fm.duckdb) so they appear in the Streamlit dashboard. Use when the user drops new save files (e.g. in ~/Downloads) and wants them reflected in the dashboard/ETL. Handles season/phase labelling, auto-label collisions, and clash detection.
---

# Import FMM saves into the dashboard

End-to-end: `.fms` save → extract (JSON/CSV) → light-results → load into `fm.duckdb`
(staging schema) → verify. Run from the repo root (the directory containing `extract.py`
and `load_duckdb.py`). Saves are read from wherever the user drops them (commonly
`~/Downloads`); adjust the paths in the commands below to your machine.

## Key facts (don't relearn these)

- **Run everything under uv** — `uv run python extract.py …`, `uv run python load_duckdb.py …`.
  numpy (needed by `fmparser/history.py`) is in the uv env, so nothing here depends on a system
  python any more.
- **The parser is career-aware** — pass `--career <key>` (`frem` is the active one; `bucaspor` is
  archived). Verify the extract's `clubs.json` contains that career's managed + reserve tids
  (frem: `"346"` and `"7296"`). If not, the extraction is garbage for that save; stop and tell
  the user. All saves loaded into one store must be the same career.
- **Archive the save FIRST, with its in-game date** — it's the only irreplaceable artefact, and
  `--phase` gives it the canonical name (`<career>-<date>.fms`) so you never have to rename later:
  `uv run python scripts/archive_save.py <save.fms> --career frem --phase 2023-08-15 --upload`.
  That moves it to `$FM_SAVES_DIR`, gzips it, hash-verifies the round-trip, and pushes to R2.
  **Use the same string as the `--label`** — save file, `output/` dir and DB label are one
  vocabulary now. Ask the user for the in-game date if you don't have it; it can't be derived
  from a 0-match save.
- **Refresh the rebuild recipe after loading** — `uv run python scripts/export_manifest.py`, then
  commit `seeds/manifest.csv`. Without this the new snapshot can't be rebuilt on another machine.
- **The stores are NOT committed** (96 MiB, rewrites wholesale, near GitHub's file limit). They're
  derived: `uv run python scripts/rebuild.py --career frem` rebuilds from saves + manifest.
- **Season = end-year of the campaign** (22/23 → 2023, Aus-financial-year style).
- **`phase` is the save's in-game DATE** ('YYYY-MM-DD'), written explicitly into `summary.json`
  (`season` + `phase`) by `extract.py`. **The loader auto-derives both — normally pass NEITHER
  `--season` nor `--phase`.** Match-less season-**start** saves (0 matches, no date) get a
  synthetic `<start-year>-07-01`. Only pass `--season/--phase` to force/override a slice.
  (Legacy stores may still hold the words `start/mid/end`; those keep working and sort correctly
  alongside dates — the ordering treats words as epoch.)
- **Loading replaces the exact `(season, phase=date)` slice** (idempotent DELETE+INSERT). Because
  phase is the date, **two different in-season snapshots now COEXIST** (different dates) instead of
  colliding — re-importing the *same* date overwrites it (the "newer export replaces old" mechanism).
  A superseded *different* label in the same slice is archived to `history.player_snapshots` first.
- After loading, tell the user to **restart Streamlit** (`pkill -f streamlit && uv run streamlit
  run dashboard/Home.py`); it auto-reconnects to the rebuilt DB on mtime change thereafter.

## Player history is live (since 2026-08-19)

`player_history` + `player_history_seasons` populate on every save now, ~21-23k players each. If
a slice loads with **0 history rows** that is a regression, not the old known gap — check the
`WARNING: history table not parsed` line in the extract output. `build()` refuses to emit from a
slab that fails its forest check, so it fails loudly rather than writing garbage.

Before touching `fmparser/history.py`, read `docs/agent-context/player-history-table.md`. The
three facts that matter: `+4` is a **next-row pointer** (linked lists — record starts are the
in-degree-0 rows, `FFFFFFFF` ends a chain); **season+stats come from row `k-1`, club+fee from row
`k`**; and the player link is `u32 @ P-38` in the **attribute** record, not anything inside the
history table (`docs/IDS.md` § PLAYER → CAREER HISTORY). Verify any change with
`python3 scripts/history_v2.py <save> --player <tid>` — it prints the career TOTAL line, which is
what you diff against an in-game History screenshot.

## Reprocessing EVERYTHING after a parser change

Different job from importing a new save: re-extract and reload every snapshot already registered,
so old slices pick up the new decode. The store knows the full manifest —

```sql
SELECT label, season, phase, save_path FROM staging.extracts ORDER BY season, phase;
```

Then just run the rebuild script — it does exactly this from `seeds/manifest.csv`, passing
season/phase explicitly so nothing lands on the wrong slice:

```bash
uv run python scripts/rebuild.py --career frem            # add --skip-existing to reuse output/
```

Budget ~1 min per snapshot (12 snapshots ≈ 12 min); run it in the background and monitor the log.
`--skip-existing` re-loads from existing `output/` dirs without re-extracting, which is much
faster when only the ETL changed.

Before starting: **`pkill -f streamlit`** (it holds the DuckDB write lock). No need to back the
store up any more — it's rebuildable from `seeds/manifest.csv` + the R2 archive, which is the
whole point. `scripts/rebuild.py` already passes season/phase from the manifest; don't let them
re-derive, or a save whose in-game date differs from its last match date lands on a different
phase and you get a duplicate slice instead of a replaced one. `--reset` is now safe for the things that used to be at risk: role_weights,
eligible_origin_clubs and app_config all seed from `seeds/` (all 7 tactic methods are in
`role_weights.csv`, and `config_bundle.json` carries the app settings), while the shortlist and
saved scouts have left the store entirely for `state/` + R2. A tactic inserted straight into the
DB and never exported to `seeds/role_weights.csv` would still be lost.

Afterwards, verify rather than assume: row counts per slice, plus a ground-truth anchor you can
check against a screenshot.

## Steps

1. **Locate the saves.** `ls -la ~/Downloads/*.fms` (or wherever the user says). If several
   exist, identify the *new* ones (recent mtime + descriptive names). Confirm the set with the
   user if ambiguous.

2. **Extract each save to a filename-based output dir** (so nothing is clobbered before you
   decide labels). For each save `<stem>.fms`:
   ```bash
   python3 extract.py "$HOME/Downloads/<stem>.fms" --label "<stem>" --out output
   python3 dump_lightresults.py "$HOME/Downloads/<stem>.fms" --label "<stem>" --out output
   ```
   These are slow (~1–2 min each, 65 MB mmap). Run all in one **background** bash block and
   wait for a `DONE` sentinel via Monitor.

3. **Inspect each `output/<stem>/summary.json`**: read `label_auto`, `latest_match`,
   `date_range`, `competitions`, `counts`. Also check `clubs.json` for the career's managed +
   reserve tids (frem: `346`/`7296`) as a career sanity check. Build a mapping table of **file → intended (season, phase)**, resolving:
   - filename intent (`-23-mid` → 2023/mid) over the date heuristic,
   - 0-match start saves → the season/phase the user names,
   - the Mar–Jul "end" collision (see above).

4. **Detect clashes** and surface them to the user *before* loading:
   - Does an intended `(season, phase)` already exist in `staging.extracts`? Loading will
     **replace** it. Confirm that's intended (usually yes — a cleaner/newer re-export). Compare
     player counts / date ranges to check it's the same career point vs a genuinely different one.
   - Do two new saves map to the same `(season, phase)`? One will overwrite the other — resolve
     the labels with the user.
   Present the mapping table + any clashes, then proceed (the user has usually pre-approved).

5. **Load each** (season + phase=date auto-derive from `summary.json` — no flags needed). Use the
   career's store `fm-<key>.duckdb`. Kill any running Streamlit first so the DB isn't locked. Run in
   **background**, wait for a `DONE` sentinel:
   ```bash
   pkill -f streamlit 2>/dev/null; sleep 1
   uv run python load_duckdb.py output/<stem> --db fm-<key>.duckdb
   # …repeat per save… ; echo LOADS_DONE
   ```
   (Only add `--season/--phase` to force a slice. The loader auto-migrates older stores — drops the
   legacy `phase IN (start,mid,end)` CHECK on first load so date-phases are accepted.)

6. **Verify**: query `staging.extracts` (all labels + row counts), squad sizes per label
   (`club_tid in (346,7296)` for frem), and run an `AppTest` smoke over the dashboard pages to
   confirm rendering — all 14 should pass, including against a read-only store. Report the final snapshot table.

## Gotchas seen before
- `output/` and `*.duckdb` are gitignored; extraction writes lots of JSON there — fine.
- DuckDB single-writer: a running Streamlit server holds the file; `pkill -f streamlit` before loading.
- `load_duckdb.py` collision pre-flight only triggers with `--all`; for explicit single loads you
  do the clash reasoning yourself (step 4).
