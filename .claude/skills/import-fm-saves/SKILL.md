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
- **Auto-labelling is unreliable and must be overridden:**
  - Season-**start** saves have **0 matches** → `label_auto = "unknown"` (no date to derive from).
  - `_period` maps **Mar–Jul → "end"**, so a late-March "mid" save and a May "end" save
    **both auto-label to `<year>-end`** and collide. **Trust the user's filename intent**
    (`…-23-mid`, `…-23-end`, `…-24-start`) and pass explicit `--season/--phase`.
- **Loading replaces the `(season, phase)` slice** (idempotent DELETE+INSERT). So re-importing
  a label overwrites it — that's the mechanism for "newer export with youth intake replaces old".
- After loading, tell the user to **restart Streamlit** (`pkill -f streamlit && uv run streamlit
  run dashboard/Home.py`); it auto-reconnects to the rebuilt DB on mtime change thereafter.

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

5. **Load each** with explicit season/phase (kill any running Streamlit first so the DB isn't
   locked). Run in **background**, wait for a `DONE` sentinel:
   ```bash
   pkill -f streamlit 2>/dev/null; sleep 1
   uv run python load_duckdb.py output/<stem> --db fm.duckdb --season <YYYY> --phase <start|mid|end>
   # …repeat per save… ; echo LOADS_DONE
   ```

6. **Verify**: query `staging.extracts` (all labels + row counts), squad sizes per label
   (`club_tid in (6567,11320)`), and run a quick `AppTest` smoke over the dashboard pages on a
   new label (e.g. the newest season) to confirm rendering. Report the final snapshot table.

## Gotchas seen before
- `output/` and `*.duckdb` are gitignored; extraction writes lots of JSON there — fine.
- DuckDB single-writer: a running Streamlit server holds the file; `pkill -f streamlit` before loading.
- `load_duckdb.py` collision pre-flight only triggers with `--all`; for explicit single loads you
  do the clash reasoning yourself (step 4).
