---
name: import-fm-saves
description: Parse new FMM22 .fms save files and load them into the career's DuckDB store (fm-<career>.duckdb) so they appear in the store and, once published, the web app (site/). Use when the user drops new save files (e.g. in ~/Downloads) and wants them reflected in the store/site. Handles season/phase placement and clash detection.
---

# Import FMM saves into the store

End-to-end: `.fms` save → extract (JSON) → load into `fm-<career>.duckdb`
(raw schema) → verify. Run from the repo root (the directory containing `extract.py`
and `load_duckdb.py`). Saves are read from wherever the user drops them (commonly
`~/Downloads`); adjust the paths in the commands below to your machine.

## Key facts (don't relearn these)

- **Run everything under uv** — `uv run python extract.py …`, `uv run python load_duckdb.py …`.
  numpy (needed by `fmparser/tables/history.py`) is in the uv env, so nothing here depends on a system
  python any more.
- **The extract takes no career; the loader does** — `load_duckdb.py --career <key>` (`frem` is
  the active one; `bucaspor` is archived), or no flag at all to use the career the store
  already records. The loader refuses a career other than the store's, and refuses the save
  if its match table disagrees with the world fixture list for that career's two clubs --
  the sign of a save from another career, or of a misread table. All saves loaded into one
  store must be the same career.
- **Archive the save FIRST** — it's the only irreplaceable artefact, and it is named
  `<career>-<date>.fms` from the in-game date in its own header title, so you never rename later:
  `uv run python scripts/archive_save.py <save.fms> --career frem --upload`.
  That moves it to `$FM_SAVES_DIR`, gzips it, hash-verifies the round-trip, and pushes to R2.
  `extract.py` names its `output/` dir after the save, so save file, `output/` dir and DB
  label are one string with no `--label`. The header dates a 0-match save too.
- **Refresh the rebuild recipe after loading** — `uv run python scripts/export_manifest.py`, then
  commit `seeds/manifest.csv`. Without this the new snapshot can't be rebuilt on another machine.
- **The stores are NOT committed** (96 MiB, rewrites wholesale, near GitHub's file limit). They're
  derived: `uv run python scripts/rebuild.py --career frem` rebuilds from saves + manifest.
- **Season = end-year of the campaign** (22/23 → 2023, Aus-financial-year style).
- **`phase` is the save's in-game DATE** ('YYYY-MM-DD'), the header date `extract.py` writes into
  `summary.json` (`save_date`). **The loader derives both — pass NEITHER `--season` nor
  `--phase`.** `phase` is the header date; `season` follows the career's rollover day
  (`Career.rollover`, Frem 30 June), and a new career's first save (0 matches, dated before
  the rollover) belongs to the campaign about to start. A save whose header
  does not read is refused. `--season/--phase` only force a slice.
  (Legacy stores may still hold the words `start/mid/end`; those keep working and sort correctly
  alongside dates — the ordering treats words as epoch.)
- **Loading replaces the exact `(season, phase=date)` slice** (idempotent DELETE+INSERT). Because
  phase is the date, **two different in-season snapshots now COEXIST** (different dates) instead of
  colliding — re-importing the *same* date overwrites it (the "newer export replaces old" mechanism).
- **Every load runs `dbt build`** over the `fmstats/` project in-process (`load_duckdb.build_models`):
  it rebuilds `stg`/`int`/`mart`/`site` and runs every dbt data and unit test, and a failing test
  stops the models downstream of it and fails the load.

## Player history

`player_history` + `player_history_seasons` populate on every save now, ~21-23k players each. If
a slice loads with **0 history rows** that is a regression — check the
`WARNING: history table not parsed` line in the extract output. The history table refuses to emit
a pool that fails its forest check, so it fails loudly rather than writing garbage. The loader
prints how many of the pool's records sit on a player's chain.

Before touching `fmparser/tables/history.py`, read its docstring and shape B of
`docs/parser-architecture.md`. The three facts that matter: `+12` is a **next-record pointer**
(linked lists — record starts are the in-degree-0 records, `FFFFFFFF` ends a chain); **one record
is one season line** (`[stats][club, fee, next]`); and the player link is `history_head`
(`u32 @ P-38`) in the **attribute** record, not anything inside the history table
(`docs/IDS.md` § PLAYER → CAREER HISTORY). The parser emits the pool as stored; the chains are
read by `load_duckdb.load_history`. Verify any change with
`python3 scripts/history_v2.py <save> --player <tid>` — it prints the career TOTAL line, which is
what you diff against an in-game History screenshot.

## Reprocessing EVERYTHING after a parser change

Different job from importing a new save: re-extract and reload every snapshot already registered,
so old slices pick up the new decode. The store knows the full manifest —

```sql
SELECT label, season, phase, save_path FROM raw.extracts ORDER BY season, phase;
```

Then just run the rebuild script — it does exactly this from `seeds/manifest.csv`, and checks
each extract's season/phase against the manifest row so nothing lands on the wrong slice:

```bash
uv run python scripts/rebuild.py --career frem            # add --skip-existing to reuse output/
```

Budget ~1 min per snapshot (12 snapshots ≈ 12 min); run it in the background and monitor the log.
`--skip-existing` re-loads from existing `output/` dirs without re-extracting, which is much
faster when only the ETL changed.

Before starting, make sure nothing else holds the store open for writing (DuckDB is
single-writer; another loader or a read-write session blocks it). No need to back the store up —
it's rebuildable from `seeds/manifest.csv` + the R2 archive, which is the whole point. `scripts/rebuild.py` fails a snapshot whose save dates itself differently from
its manifest row (`--trust-manifest` loads the manifest's values anyway). `--reset` loses nothing
that isn't rebuilt: role_weights, eligible_origin_clubs and app_config all seed from `seeds/` (both
shipped weight-sets are in `role_weights.csv`, and `config_bundle.json` carries the app settings),
and the shortlist and saved scouts live in `state/` + R2, not the store. A weight-set inserted
straight into the DB and never exported to `seeds/role_weights.csv` would be lost.

Afterwards, verify rather than assume: row counts per slice, plus a ground-truth anchor you can
check against a screenshot.

## Steps

1. **Locate the saves.** `ls -la ~/Downloads/*.fms` (or wherever the user says). If several
   exist, identify the *new* ones (recent mtime + descriptive names). Confirm the set with the
   user if ambiguous.

2. **Archive, then extract each save** ("Archive the save FIRST" above names it
   `<career>-<date>.fms`). For each archived save:
   ```bash
   uv run python extract.py "$FM_SAVES_DIR/<career>/<career>-<date>.fms"
   ```
   The output lands in `output/<career>-<date>/`.
   These are slow (~1–2 min each, 65 MB mmap). Run all in one **background** bash block and
   wait for a `DONE` sentinel via Monitor.

3. **Inspect each `output/<label>/summary.json`**: read `save_date` (the phase), `save_title`
   (its "(Nickname)" names the career's club), `competitions`, `counts`. Build a table of
   **file → save date** from the summaries; the loader places each in its season.

4. **Detect clashes** and surface them to the user *before* loading:
   - Does an intended `(season, phase)` already exist in `raw.extracts`? Loading will
     **replace** it. Confirm that's intended (usually yes — a cleaner/newer re-export). Compare
     player and match counts to check it's the same career point vs a genuinely different one.
   - Do two new saves map to the same `(season, phase)`? One will overwrite the other — resolve
     the labels with the user.
   Present the mapping table + any clashes, then proceed (the user has usually pre-approved).

5. **Load each** (season + phase=date are derived from `summary.json` and the store's career — no
   flags needed; a NEW store needs `--career <key>`). Use the career's store `fm-<key>.duckdb`;
   nothing else may hold it open for writing. Run in **background**, wait for a `DONE` sentinel:
   ```bash
   uv run python load_duckdb.py output/<stem> --db fm-<key>.duckdb
   # …repeat per save… ; echo LOADS_DONE
   ```
   (Only add `--season/--phase` to force a slice. The loader auto-migrates older stores — drops the
   legacy `phase IN (start,mid,end)` CHECK on first load so date-phases are accepted.)

6. **Verify**: the load's dbt summary must show no failing test. Then query `raw.extracts` (all
   labels + row counts) and our squad size per snapshot from the squad arrays, and report the
   final snapshot table:
   ```sql
   SELECT snapshot_date, team_tid, count(*) AS players
   FROM mart.squad_membership WHERE is_managed_club
   GROUP BY ALL ORDER BY snapshot_date DESC, team_tid LIMIT 6;
   ```
   Preview the web app after the export in step 7 (`uv run python -m http.server -d site 8000`).

7. **Refresh the remote artefacts** — not automatic, easy to forget since the store itself is
   already correct without it. Three things read stale data otherwise: the deployed web app, a
   remote agent's `ATTACH` (see `docs/agent-context/remote-duckdb-access.md`), and
   `seeds/manifest.csv` (the rebuild recipe — without it another machine can't reproduce this
   snapshot). Full detail in `docs/DEPLOY.md`'s "Refreshing after an import":
   ```bash
   uv run python scripts/export_manifest.py                          # refresh the rebuild recipe
   uv run python scripts/export_data.py --upload-all                 # -> site/api/*.json + R2 all.json
   uv run python scripts/publish_duckdb.py --career frem --upload    # -> R2 full copy (~34 MB)
   uv run python scripts/publish_mart.py   --career frem --upload    # -> R2 analysis copy (~24 MB)
   # BOTH R2 copies are needed: publish_duckdb ships `raw` (+ the `mart` schema) for
   # re-derivation, publish_mart ships the mart alone for analysis. They are SEPARATE
   # objects — running one does not refresh the other, and neither is written by
   # load_duckdb.py, so an import leaves both stale until these run.
   git add site docs seeds && git commit -m "site: <snapshot>" && git push   # Pages deploys on push
   ```
   `site/api/*.json` is git-tracked and the export is deterministic, so the diff should be
   snapshot data and nothing else. A large reordering with no numbers changed means something
   lost its `ORDER BY` — worth chasing rather than committing.

8. **Sanity-check the models** — the `dbt build` each load runs is the check (grain,
   relationships, `rows_match_source`, the unit tests). After editing `fmstats/` models, rerun it
   without loading anything: `uv run python load_duckdb.py --refresh-only --db fm-frem.duckdb`.
   It is structural: also eyeball one ground-truth number (a squad size, a score) against the
   in-game screen.

## Gotchas seen before
- `output/` and `*.duckdb` are gitignored; extraction writes lots of JSON there — fine.
- DuckDB single-writer: any process with the store open for writing blocks a load; a read-only
  reader blocks it too while connected.
- `load_duckdb.py` collision pre-flight only triggers with `--all`; for explicit single loads you
  do the clash reasoning yourself (step 4).
