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
- **Every `mart` and `site` column points at a shared doc block** in `models/_docs/` (one file
  per family, a block named for the canonical column name):
  `description: '<one sentence for this model, if any> {{ doc("club_tid") }}'`. A new column
  reuses its concept's block or adds one; a name that drifts from its block goes on the block's
  `Synonyms:` line. `uv run python scripts/check_dbt_docs.py --empty-store` checks it (CI).
- **Column names** follow the convention below; `check_dbt_docs.py` enforces the parts a
  script can see.
- **Lint and format with sqlfluff** (`.sqlfluff`: lower-case keywords, trailing commas,
  explicit aliases, 80 columns): `uv run python scripts/lint_sql.py` (`--fix` to apply). It lints
  against an empty store it builds, so no data is needed.
- **Test big views on a sample** (`tests/`, `macros/sample.sql`): a test that reads all 16M
  ratings takes ~45 s; the sample takes ~0.6 s.
- **Real-data checks are singular tests in `tests/`**, named by theme (`matches_`, `spells_`,
  `tables_`, `ratings_`, `origins_`, `registration_`, `growth_`). Each returns the failing rows,
  with a `"check"` column where one file asserts several things. They are generic invariants:
  they hold for any career. `yml` tests cover grain and relationships; these cover what the
  data says.
- **Known answers are the user's, in `known_answers/`** (gitignored; a `test-paths` entry, so
  dbt runs them when the folder exists). A known answer is a fact about one save — a named
  player's attributes, a season's goal total, a deal's fee — read off the game's screens. Tag
  each `known_answers`, filter on `stg_career.career_key = '<key>'` so it returns nothing for
  another career, and write it against a full rebuild of that career's saves. They are the
  strongest regression test there is for your own career, so keep yours.

## Column naming convention
When two names compete, these decide it, in order:
1. **The game's own word wins.** If the game's screens name it, use that word: `appearances`,
   not `apps`, `matches_played` or `n_games`.
2. **Whole words, no abbreviations**: `opponent_tid`, not `opp_tid`. Established ids stay
   (`tid`, `cid`).
3. **One name per concept across the warehouse.** A role on a shared concept is a prefix:
   `<role>_<concept>` (`from_club_tid`, `home_team_tid`).
4. **Relative to the row's subject**: `goals_for` / `goals_against`, or `home_` / `away_`.
   Never `_a` / `_b`.

| kind | pattern | examples |
|---|---|---|
| team slot (club or side) | `*_tid`; `team_tid` for a side, `club_tid` for a club | `team_tid`, `from_club_tid` |
| competition | `*cid` | `cid`, `league_cid` |
| other entity | `*_id` | `person_id`, `nation_id`, `match_id` |
| flag | `is_*`, `has_*` | `is_current`, `has_attributes` |
| count of a football thing | the plural noun the game uses | `appearances`, `goals`, `assists` |
| count of rows (no game word) | `n_*` | `n_teams` |
| money | `*_gbp` | `fee_gbp`, `wage_gbp` |
| date / season | `*_date`; `season` is the campaign's end year | `match_date`, `snapshot_date` |
| percentile | `*_pctile` | `level` is the existing exception |
| rate | `*_per_90` | |
| a kind or category | `*_type` | `fee_type`, `transfer_type` |
