# The transform layer — built on the semantic model

Loaded when working under `fmstats/` or `transform/`. **The semantic model in
[`docs/data-model/`](../docs/data-model/README.md) is the foundation of this layer:** every new
table is one of its `dim_*` / `fact_*` entities, at the grain the model gives it, and a question
the model answers is answered from those tables. Its overview and shared rules are imported
here; read the area doc (`person.md`, `club.md`, `match.md`, `competition.md`,
`contract-transfer.md`, `nation.md`, `reference.md`) before building or changing anything in
that area.

@../docs/data-model/README.md

## Where the refactor stands
The plan is [`docs/plans/2026-10-01-data-layers.md`](../docs/plans/2026-10-01-data-layers.md):
**raw → stg → int → mart**, ending in the model's tables.

| Layer | Lives in | Holds | Rule |
|---|---|---|---|
| raw | written by `load_duckdb.py` | each table as the save stores it, one row set per snapshot, plus seeds | no logic |
| stg | `transform/models/stg/` (views) | one model per raw table: rename, cast, decode codes, sentinels to NULL | 1:1 with its source: no joins, no dropped rows (`rows_match_source`) |
| int | `transform/models/int/` (views) | snapshot rules, joins across tables, spells, derived standings and outcomes | joins and business rules live here and only here |
| mart | `transform/models/mart/` (tables) | the model's `dim_*` / `fact_*`, plus thin consumer views (`standings`, `tie_results`) | the only layer users, agents and the site read |

- **Built (steps 13–14):** reference, nation, club and team, competition, stage, round, match,
  team-match, player-match, events, participation, outcomes.
- **Not built:** person (`dim_person`, `fact_player_snapshot`, `fact_player_season`, awards,
  injuries; step 15) and contracts, transfers and loans (step 16). Until then those questions
  are answered by the old views.
- **`fmstats/mart.py` is the old consumer mart**: ~87 views in one file, each re-applying the
  same rules to raw. Step 17 rewrites each one over the new tables, or deletes it when the site
  can read a new table directly. `fmstats/compat.py` and `transform/models/legacy/` keep the old
  shapes alive for it until then. **Nothing reads the new tables yet** except
  `tests/validate_mart.py`; `scout`, `stats`, `league`, `fmq` and the site export all read the
  old views.

## Building on the model
- **New data goes into the model, not into `mart.py`.** A fact or dimension the model names is
  built in `transform/`, in its layer. A new view in `mart.py` is only for a consumer that
  can't wait for its step, and then it reads the new tables where they exist.
- **Grain is declared, not described.** Each mart model states its key as a
  `unique_combination` test and its joins as `relationship_combination` tests in
  `models/mart/_mart.yml`; int rules get dbt unit tests (fixed rows in, required rows out).
- **Natural keys, never surrogates.** The store is rebuilt from scratch, so the save's ids are
  stable within a build. The model docs' `*_key` columns are conceptual; as built they are
  `nation_id`, `team_tid`, `cid`, `snapshot_date`, `match_id` (date and both teams packed into
  one BIGINT, `macros/match_id.sql`), and `person_id` = `<tid>-<dob>` (`macros/person_id.sql`).
  Never key a person on `tid`: the game hands a retired person's slot to a newgen.
- **Dimensions hold what never changes; snapshots hold what does.** A dimension's row is its
  id's latest snapshot (`macros/latest.sql`). A stadium's capacity, a nation's ranking and a
  team's reputation are on `fact_*_snapshot`, measured to change before being put there.
- **Things with a lifespan are spells**: contracts, loans, injuries, staff, call-ups.
- **One source per fact; everything else is a check.** Scores come from the world fixture list.
  Events, the save's record tables, the roll of honour and league history check what is
  derived; a check reports a mismatch and never changes the build.
- **Team facts roll up to the club; club facts never split down.** "Us" is a club owning
  both our teams.
- **Measure the save before modelling it.** Every rule in the area docs ("as built" sections)
  was measured on the gate stores first: extra time in the fixture list, a tie as one round
  played twice, reserve facilities as defaults. A new rule states its measurement in the
  doc beside the model.
- **The warehouse keeps everything, raw ability included.** The immersion rule binds at the
  presentation layer: the site export, user-facing views, `fmq` output.
- **Gate every step against the old view it replaces**, row for row:
  `scripts/audit/diff_stores.py OLD.duckdb NEW.duckdb --table <schema.table> --key <cols>`
  against a store built from `main`, plus `tests/validate_mart.py`. The plan's Part 3 lists the
  gate saves and the check per kind of change.

## Changing an old view in `fmstats/mart.py` (until step 17 retires it)
- **Facts go in the mart, opinions stay in Python.** A rule every consumer must share is a
  view; parameters, fuzzy lookup, modelling choices (best XI, flag thresholds) and presentation
  stay in `scout`/`stats`/`league`. The site export reads only `mart`.
- **The SQL constants are `str.format` templates**: write the raw schema as `{S}`, double
  literal braces, and write `{{S}}` inside an f-string constant (`PLAYER_ROLE_RATINGS`).
- **`ORDER` is build order**: `create_mart` runs it top to bottom.
- **A definition is not data**: re-run it with
  `uv run python load_duckdb.py --refresh-only --db fm-frem.duckdb`, then
  `uv run python tests/validate_mart.py --db fm-frem.duckdb` (`--r2` builds against the
  published copy in memory). `fmq` re-creates the views on its cached R2 copy whenever
  `store.MART_VERSION` changes; a view reading a raw table older stores lack goes in
  `store._MART_INPUTS`.
- **Macros don't resolve across an `ATTACH`**: a view calling `phase_ord`/`season_of` fails
  for a remote agent who hasn't run `USE m`.
- **The rating formula has three copies that must agree**:
  `transform/models/legacy/legacy_player_ratings.sql` (behind `v_player_ratings`),
  `mart.player_role_ratings`, and `site/js/data.js`'s `rating()`.
- **Raw ability may be used inside a view, never exposed by one** (`ca`, `pa`, `aca`,
  `current_ability`, `potential_ability`). `publish_mart.py`'s `FORBIDDEN`,
  `export_data.py`'s `check_immersion()` and `validate_mart.py` §8 each check it.

fmstats imports neither `fmparser/` nor `extract` (`tests/test_boundary.py`); it reads a
`.duckdb` file and nothing else. Every function takes an open `store.Store`.
