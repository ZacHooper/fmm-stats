# fmstats — the mart and the query layer

Loaded when working under `fmstats/`. The module docstrings say what each file is
(`__init__.py` has the map); this file holds the rules for changing them.

## Where code goes
**Facts go in the mart, opinions stay in Python.** A rule that gives every consumer the same
answer (a table, a record, a primary position, who is in the squad) is a view in `mart.py`, so
the site, remote SQL over the R2 copy and `fmq` all share it. Parameters, fuzzy lookup,
modelling choices (best XI, flag thresholds) and presentation stay in `scout`/`stats`/`league`.
A field the web app needs goes into `mart.py` first: `scripts/export_data.py` reads only the
`mart` schema.

fmstats imports neither `fmparser/` nor `extract` (`tests/test_boundary.py` enforces it). It
reads a `.duckdb` file and nothing else; `contract.py` plus the `raw` tables is the whole
interface. Every function takes an open `store.Store` (or its connection): no module-level
connections.

## Changing a mart view
- **The SQL constants are `str.format` templates.** Write the raw schema as `{S}` (it is `raw`
  in a local store, and `store._alias_raw` maps a published copy's `staging` onto it), double
  any literal brace, and write `{{S}}` inside an f-string constant such as
  `PLAYER_ROLE_RATINGS`.
- **`ORDER` is build order.** `create_mart` runs it top to bottom, so a view goes after every
  view it reads.
- **A definition is not data.** An existing store keeps the old view until something re-runs
  it: `uv run python load_duckdb.py --refresh-only --db fm-frem.duckdb`, then
  `uv run python tests/validate_mart.py --db fm-frem.duckdb` (or `--r2` against the published
  copy, built in memory, nothing written).
- **`fmq` re-creates the mart on its cached R2 copy** whenever `store.MART_VERSION` (a hash of
  `MACROS` + `ORDER`) changes, so a new view works against an older published store. If the
  new view reads a raw table that older stores lack, add it to `store._MART_INPUTS`, so the
  sync says why it can't refresh instead of failing to bind.
- **Macros live in the main schema and do not resolve across an `ATTACH`.** A view that calls
  `phase_ord`/`season_of`/… fails for a remote agent who attaches the published copy without
  `USE m` first. That is why `mart.snapshot_squad` is a plain view and `mart.squad_on` stays
  the one table macro.
- **The rating formula has three copies that must agree:** the dbt model behind
  `v_player_ratings` (`transform/models/legacy/legacy_player_ratings.sql`),
  `mart.player_role_ratings`, and `site/js/data.js`'s `rating()` (verified equal over 36,920
  combinations). `publish_mart.py` leaves `player_role_ratings` and
  `player_position_fit` out of the published mart object on size.
- **Raw ability may be used inside a view, never exposed by one.** Computing Level %ile from
  `ca` is fine; a surfaced column named `ca`, `pa`, `aca`, `current_ability` or
  `potential_ability` is not. `publish_mart.py`'s `FORBIDDEN`, `export_data.py`'s
  `check_immersion()` and `validate_mart.py` §8 each check for it.
- **`compat.py` names are for old consumers only.** `raw.players`, `raw.persons` and
  `v_player_ratings` are views over the dbt models until their last consumer moves (data-layers
  step 17). New code reads `mart`.

## Checking a change
- `uv run python tests/validate_mart.py --db <store>`: spell invariants, ring-buffer dedup,
  loan-in ground truth, season totals, growth, the regression guards, site-facing grain, and
  immersion.
- `uv run python tests/run_tests.py --store`: adds `test_fmq` over the published copy.
- `git diff site/api` after `scripts/export_data.py`: the export is deterministic, so a change
  that should not move the site must leave it empty.
