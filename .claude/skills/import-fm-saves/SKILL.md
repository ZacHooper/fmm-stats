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

- **Extractors are pure-stdlib**: run with `python3 extract.py …` (NOT uv). The **loader is
  `uv run python load_duckdb.py …`** (duckdb lives only in the uv env).
- **Parser is hardcoded to the Bucaspor career** (`MANAGED_CLUB_TID=6567`, reserves `11320`).
  Every save MUST be the same career — verify `clubs.json` has `"6567"` and `"11320"`.
  If not, the extraction is garbage for that save; stop and tell the user.
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

Then per row: `python3 extract.py <save_path> --career <key> --label <label>` followed by
`uv run python load_duckdb.py output/<label> --db fm-<key>.duckdb --season <season> --phase <phase>`.
Budget ~1 min per snapshot (18 snapshots ≈ 25 min); run it in the background and monitor the log.

Before starting: **`pkill -f streamlit`** (it holds the DuckDB write lock) and copy both stores to
`backups/`. Pass the season/phase explicitly from the manifest rather than letting them re-derive,
or a save whose in-game date differs from its last match date will land on a different phase and
you will end up with a duplicate slice instead of a replaced one. Do **not** use `--reset` unless
you have checked that everything hand-maintained is reproducible from `seeds/` (role_weights and
eligible_origin_clubs are; a user-added tactic inserted straight into the DB would not be).

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
   `date_range`, `competitions`, `counts`. Also check `clubs.json` for `6567`/`11320`
   (career sanity). Build a mapping table of **file → intended (season, phase)**, resolving:
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
   (`club_tid in (6567,11320)`), and run a quick `AppTest` smoke over the dashboard pages on a
   new label (e.g. the newest season) to confirm rendering. Report the final snapshot table.

## Gotchas seen before
- `output/` and `*.duckdb` are gitignored; extraction writes lots of JSON there — fine.
- DuckDB single-writer: a running Streamlit server holds the file; `pkill -f streamlit` before loading.
- `load_duckdb.py` collision pre-flight only triggers with `--all`; for explicit single loads you
  do the clash reasoning yourself (step 4).
