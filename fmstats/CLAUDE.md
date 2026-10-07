# fmstats — the dbt warehouse project (stg, int, mart, site)

The semantic model in [`docs/data-model/`](../docs/data-model/README.md) is the blueprint:
the entities, their grain, and the bus matrix. This directory (`fmstats/`) is the **dbt**
project that builds it inside DuckDB.

## The layers
The raw tables (written by the loader) are the extract. `fmstats/` turns them into the dimensional warehouse:

| Layer | Where | What | The one invariant |
|---|---|---|---|
| raw | written by `load_duckdb.py` | each table as the save stores it, one row set per snapshot, plus seeds | no logic |
| stg | `fmstats/models/stg/` (views) | one model per raw table: rename, cast, decode codes, sentinels to NULL | 1:1 with its source: no joins, no dropped rows (`rows_match_source`) |
| int | `fmstats/models/int/` (views) | snapshot rules, joins across tables, spells, derived standings and outcomes | joins and business rules live here and only here |
| mart | `fmstats/models/mart/` (tables) | the model's `dim_*` / `fact_*`, plus consumer views (`mart_standings`, `fact_player_snapshot`) | the dimensional layer users, agents and the site read |
| site | `fmstats/models/site/` (views) | the web app's presentation marts: one view per thing a page shows | read by `scripts/export_data.py` directly |

## dbt conventions here
- **Build**: the loader runs `dbt build` in-process (`load_duckdb.build_models`), so every load
  builds and tests the whole project. Run it by hand:
  `cd fmstats && FM_DUCKDB=<store> uv run dbt build --profiles-dir .`.
  `load_duckdb._drop_unbuilt` drops a `dim_`/`fact_` table the project no longer defines.
- **Naming**: a model file is `<layer>_<name>.sql` and its relation `<layer>.<name>`, except in
  `models/mart/`, where the file is named for the relation itself (`dim_city.sql` -> `mart.dim_city`).
- **The catalog name is baked into every view.** dbt writes the store's file name
  (`fm-<career>`) into each view, so a copy of the store binds only when attached under that
  name: `ATTACH 'copy.duckdb' AS "fm-frem"` (`select sql from duckdb_views()` shows it).
  Tables are unaffected.
- **Generated SQL comes from the `vars`** in `dbt_project.yml` (attribute order, exact
  attributes, record offsets), which `tests/test_boundary.py` checks directly against `fmparser`.
  Keep generated columns as SQL in the loop with plain `{% %}` tags and a
  literal `{% if not loop.last %},{% endif %}`, not SQL built in Jinja strings.
- **Lint and format with sqlfluff** (`.sqlfluff`: lower-case keywords, trailing commas,
  explicit aliases, 80 columns): `uv run python scripts/lint_sql.py` (`--fix` to apply). It lints
  against an empty store it builds, so no data is needed.
- **Test big views on a sample** (`tests/`, `macros/sample.sql`): a test that reads all 16M
  ratings takes ~45 s; the sample takes ~0.6 s.
