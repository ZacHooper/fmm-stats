# Warehouse build — raw → stg → int → mart

> **Status (2026-10-01): planned, not started.**
>
> **Goal:** build the semantic model in [`docs/data-model/`](../data-model/README.md) as layered,
> declared models: **raw → stg → int → mart**. Built alongside the existing code; the marts the
> site reads move onto it one at a time, with the site's own JSON as the regression test.

## Why

`fmstats/mart.py` is 3,600 lines and ~87 views in one file, each reading the landed parser
output directly. So every view re-applies the same clean-up and rules (latest phase per season,
snapshot-scoped joins, `person_id` not `tid`, appearance arithmetic), and building blocks are
mixed in with site-shaped output. Layering puts each rule in one place, with a stated grain and
one test, so marts become thin and users and agents query tables whose meaning is documented.

## The layers

```
save ─▶ fmparser ─▶ raw ─▶ stg ─▶ int ─▶ mart ─▶ site, fmq, agents
```

| Layer | Schema | Holds | Rule |
|---|---|---|---|
| **raw** | `raw` (today's `staging`, renamed) | the parser's JSON as landed, one row set per snapshot; plus seeds (role weights, model coefficients, event types) | written only by `load_duckdb.py`; no logic |
| **stg** | `stg` | one model per raw table: rename, cast, decode codes, attach `person_id`, drop unused rows | 1:1 with its source; no joins across sources, no business rules |
| **int** | `int` | the logic: snapshot dedupe and latest-phase rules, spells, contract reconstruction, derived standings and outcomes, **model scoring** | joins and rules live here and only here |
| **mart** | `mart` | the `dim_*` / `fact_*` tables from `docs/data-model/`, plus consumer-shaped marts built on them | what users, agents and the site read |

All of it is T-layer code in `fmstats/` (one package, `fmstats/models/`, with a sub-module per
layer and per area), reading the store only, so `tests/test_boundary.py` covers it unchanged.

**Coexistence:** every new mart table is named `dim_*` / `fact_*`, and no existing mart view uses
those names. So the new tables live in `mart` next to the old views, which are retired one by one.

## The two models (attributes, transfer value)

| Piece | Layer |
|---|---|
| **Fitting** (`scripts/fit_attribute_model.py`, `scripts/fit_value_model.py`) | offline, outside the pipeline; produces frozen coefficients |
| **Coefficients** | **raw** seed tables (`attribute_model` already is one; the value coefficients move out of `fmstats/value_model.py` into a seed) |
| **Scoring** | **int**: `int_player_attributes` (exact where stored, estimated otherwise), `int_player_value` |
| **Result** | **mart**: one set of attributes and one value per player on `fact_player_snapshot`, each with a provenance flag |

Fitting reads observed rows only (`is_estimated = false`), so a fit never trains on its own
predictions.

## Principles

1. **Every model is declared**, not just written as SQL: name, layer, kind (dim / fact / view /
   int / stg), grain (key columns), foreign keys, upstream models, SQL. The build order, the
   tests and the docs all read the declaration, the way `Record` declarations drive both the
   parser and `audit_records.py`.
2. **Natural keys, no surrogates.** The store is always rebuilt from scratch, so the save's own
   ids are stable within a build: `person_id` (never `tid`, which is recycled), team `tid`,
   competition `cid`, match = (date, home, away).
3. **Materialisation:** stg are views; int and mart dims/facts are tables (the rules run once
   per build); derived marts (`standings`, `tie_results`, records) are views.
4. **One source per fact; everything else is a check.** Checks report mismatches and never alter
   the build.
5. **Everything is kept**, raw ability included. The immersion rule applies at the presentation
   layer (site export, user-facing marts).

## Build and test

- **Build:** `fmstats.models.build(con)` runs stg → int → mart in dependency order.
  `load_duckdb.py --refresh-only` calls it, so an existing store gets the new layers without a
  rebuild.
- **`tests/validate_models.py`**, generated from the declarations: grain uniqueness, foreign
  keys resolve, keys not null.
- **Checks** (same script, reported separately): goal events vs score, transfer ↔ contract both
  ways, the save's contracted flag vs `contract_status`, the "loaned out" code vs loan spells,
  rebuilt league tables vs `club_league_history`, outcomes vs the roll of honour.
- **Parity:** where an existing mart view answers the same question, the new table must match it
  or the difference is explained.

## Phases

One PR each, merged green. Earlier phases unblock later ones.

| # | Phase | Builds | Gate |
|---|---|---|---|
| 0 | **Rename `staging` → `raw`** | loader, `mart.py`, `fmq`, scout, export and publish scripts, CLAUDE.md, `site/AGENTS.md`, `remote-duckdb-access.md`, the published store | `git diff site/api` empty; `validate_mart.py` and `run_tests.py` pass; R2 copy republished |
| 1 | **Foundations** | `fmstats/models/` package, the declaration, `build()`, `validate_models.py`, hook into `--refresh-only` | an empty build validates on the published store |
| 2 | **stg for everything** | one stg model per raw table | each stg row count equals its raw source |
| 3 | **Reference, nation, club** | int: club ↔ team, snapshot dedupe. mart: `dim_position`, `dim_role`, `dim_city`, `dim_stadium`, `dim_nation`, `fact_nation_snapshot`, `dim_club`, `dim_team`, `fact_club_snapshot`, `fact_team_snapshot` | vs `mart.clubs`, `mart.our_clubs` |
| 4 | **Competition & match** | int: match identity across snapshots, stages, outcomes. mart: `dim_competition`, `dim_stage`, `dim_round`, `dim_match`, `fact_team_match`, `fact_player_match`, `fact_match_event`, `fact_participation`, `fact_competition_outcome`; views `standings`, `tie_results` | vs `mart.club_matches`, `mart.match_stages`, `mart.league_tables`, `mart.match_player_facts`; events-vs-score check |
| 5 | **Person & models** | int: person identity, `int_player_attributes`, `int_player_value`, seasons unioned across snapshots. mart: `dim_person`, `fact_player_snapshot`, `fact_staff_snapshot`, `fact_injury_spell`, `fact_player_season`, `dim_award`, `fact_player_award` | vs `mart.player_snapshots`, `mart.player_value_est`, `mart.injury_spells`, `mart.player_seasons`, `mart.player_career_seasons` |
| 6 | **Contracts & transfers** | int: contract reconstruction, spells. mart: `fact_contract`, `fact_transfer`, `fact_loan_spell`, `fact_staff_spell`, squad-membership view | vs `mart.player_spells`, `mart.at_club_spells`, `mart.transfers`, `mart.loan_out_spells`, `mart.squad_current` / `squad_on`; transfer ↔ contract check |
| 7 | **Move the site's marts** | each existing mart view rewritten over `dim_*` / `fact_*`, one per commit; recreate or drop, view by view | **`git diff site/api` empty** after `export_data.py`; `validate_mart.py` passes |
| 8 | **Retire and publish** | old views dropped; `fmq sql` and agent docs pointed at the new tables; published store and mart object rebuilt | site diffs clean; publish verify passes; size within the R2 budget |

## Known blockers and unknowns

| Item | Blocks | Note |
|---|---|---|
| Person identity (TODO #14) | phase 5 | `dim_person` has to be right before anything keys on it |
| History lost to pool reclamation (TODO #15) | phase 5 | `fact_player_season` unions history across snapshots |
| Extra-time minutes (TODO #16) | phase 4 | `fact_player_match.minutes` needs the extra-time flag |
| Two-legged ties: one round or two? | phase 4 | decides how `tie_results` groups |
| Reputation per team or per club | phase 3 | modelled per team; moves if the save says otherwise |
| Contract signed dates (unread dates on the training row) | phase 6 | exact end dates instead of snapshot bounds, if they decode |
| Referee link, call-ups | phases 4, 3 | modelled; empty until located in the save |

## Relation to TODO #12 (extract dumps tables, the mart does the joins)

stg and int are where those joins land. New models read the raw per-table data where it exists,
not the pre-joined `players` row, and no new pre-joins go into `extract.py`. The loader's
remaining transforms (the attribute decode view, `rebuild_persons`, the rating views) move into
stg/int as part of phases 2 and 5.

## Out of scope

- New parsing: gaps the model names (referee link, call-ups, contract dates) stay TODO items.
- Analytics beyond the two models (role weights, ratings, home-grown rules): they move to read
  the new marts in phase 7 but are not redesigned here.
- Site changes beyond what moving the marts requires.
