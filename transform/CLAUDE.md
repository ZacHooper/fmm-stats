# transform — the dbt project (stg, int, and the model's mart tables)

The layer rules and the semantic model this project builds are shared with `fmstats/`:

@../fmstats/CLAUDE.md

## dbt conventions here
- **Build**: the loader runs `dbt build` in-process (`load_duckdb.build_models`), so every load
  and `--refresh-only` tests what it builds, and a failing test fails the load. By hand:
  `cd transform && FM_DUCKDB=<store> uv run dbt build --profiles-dir .`.
  `load_duckdb._drop_unbuilt` drops a `dim_`/`fact_` table the project no longer defines.
- **Naming**: a model file is `<layer>_<name>.sql` and its relation `<layer>.<name>`, except in
  `models/mart/`, where the file is named for the relation itself (`dim_city.sql` ->
  `mart.dim_city`).
- **The catalog name is baked into every view.** dbt writes the store's file name
  (`fm-<career>`) into each view, so a copy of the store binds only when attached under that
  name: `ATTACH 'copy.duckdb' AS "fm-frem"` (`select sql from duckdb_views()` shows it).
  Tables are unaffected.
- **Generated SQL comes from the `vars`** in `dbt_project.yml` (attribute order, exact
  attributes, record offsets), which `tests/test_boundary.py` checks directly against `fmparser`.
  literal `{% if not loop.last %},{% endif %}`, not SQL built in Jinja strings.
- **Lint and format with sqlfluff** (`.sqlfluff`: lower-case keywords, trailing commas,
  explicit aliases, 80 columns): `uv run python scripts/lint_sql.py` (`--fix` to apply). It lints
  against an empty store it builds, so no data is needed.
- **Test big views on a sample** (`tests/`, `macros/sample.sql`): a test that reads all 16M
  ratings takes ~45 s; the sample takes ~0.6 s.
