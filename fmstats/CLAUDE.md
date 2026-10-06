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
| mart | `transform/models/mart/` (tables) | the model's `dim_*` / `fact_*`, plus thin consumer views (`mart_standings`, `mart_tie_results`, `mart_squad_membership`) | the only layer users, agents and the site read |

- **Built:** reference, nation, club and team, competition, stage, round, match,
  team-match, player-match, events, participation, outcomes; person, player and staff
  snapshots, seasons, awards, injuries; contracts, transfers, loans, staff spells and squad
  membership (`mart_squad_membership`: who a squad array lists, never a record's club).
- **The dbt mart layer**: `transform/models/mart/` and `transform/models/site/` hold all dimensional
  and consumer marts. `fmq`, `scout`, `stats`, `league`, `tests/validate_mart.py`, and the site export
  all read directly from `site.*` and `mart.*`.

## The site schema
`transform/models/site/` holds the web app's marts: one view per thing a page shows
(`site.players`, `site.squad`, `site.matches`, `site.loan_outlook`, ...), each a thin select
over the model. `scripts/export_data.py` reads only `site.*`.
- **No rules in the exporter.** Squad status, the B-list, origin, Level %iles and the loan
  ranks are SQL; the exporter shapes rows and rounds for display. Ability may order rows
  inside a site view (the levels, the loan ranks) and never leaves it.
- **Check a change** by exporting both ways into scratch directories and diffing them:
  `export_data.py --out OLD`, `export_site.py --out NEW`, `scripts/diff_exports.py OLD NEW`.
  [`docs/plans/2026-10-03-site-marts.md`](../docs/plans/2026-10-03-site-marts.md) lists every
  intended difference; a new one goes there with its reason.

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

## Working with marts
- **Facts go in the mart, opinions stay in Python.** A rule every consumer must share is a
  view or model; parameters, fuzzy lookup, modelling choices (best XI, flag thresholds) and presentation
  stay in `scout`/`stats`/`league`. The site export reads only `site.*`.
- **The rating formula has copies that must agree**:
  `mart.player_role_ratings`, and `site/js/data.js`'s `rating()`.
- **Raw ability is kept in the warehouse, never exposed by the presentation layer.**
  `fact_player_snapshot` carries `ca`/`pa` so percentiles can be computed, while `site.*`,
  `export_data.py`'s `check_immersion()` and `validate_mart.py` §8 enforce that no raw ability column
  ever reaches the presentation or export layer.

fmstats imports neither `fmparser/` nor `extract` (`tests/test_boundary.py`); it reads a
`.duckdb` file and nothing else. Every function takes an open `store.Store`.
