# Warehouse build — the semantic model as real tables

> **Status (2026-10-01): planned, not started.**
>
> **Goal:** build the semantic model in [`docs/data-model/`](../data-model/README.md) as a formal
> layer of dimension and fact tables between `staging` and `mart`. It is built alongside the
> existing code and changes nothing until the marts are moved onto it, one at a time, with the
> site's own JSON as the regression test.

## Why

`fmstats/mart.py` is 3,600 lines and ~87 views in one file, each reading `staging` directly. So
every view re-applies the same rules (latest phase per season, snapshot-scoped joins,
`person_id` not `tid`, appearance arithmetic) and mixes building blocks with site-shaped
output. A warehouse layer applies those rules **once**, in tables with a stated grain, so:

- marts become thin: shaping and presentation over clean facts;
- users and agents query tables whose meaning is in the docs, not in the SQL;
- each rule has one home and one test.

## Where it sits

```
save ─▶ fmparser (E) ─▶ staging (L) ─▶ dw (T: the model) ─▶ mart (T: site/fmq shapes) ─▶ site, fmq, agents
```

- **Schema `dw`**, built by **`fmstats/warehouse/`**. It reads `staging` only and is part of the
  T layer, so the existing boundary rule (`tests/test_boundary.py`: fmstats imports no fmparser)
  covers it unchanged.
- `mart` keeps working on `staging` until each view is moved; the two coexist throughout.

## Principles

1. **One module per area**, mirroring the docs: `reference.py`, `nation.py`, `club.py`,
   `competition.py`, `match.py`, `person.py`, `contract.py`.
2. **Every table is declared**, not just written as SQL: name, kind (dim / fact / view), grain
   (the key columns), foreign keys, and its SQL. The build, the tests and the docs all read the
   declaration, the way `Record` declarations drive both the parser and `audit_records.py`. So
   a grain or a foreign key can't be stated in a doc and missed in the code.
3. **Natural keys, no surrogates.** The store is rebuilt from scratch, so the save's own ids are
   stable within a build: `person_id` (never `tid`, which is recycled), team `tid`, competition
   `cid`, match = (date, home, away). A surrogate key would add a lookup and buy nothing.
4. **Dims and facts are materialised tables; derived things are views** (`standings`,
   `tie_results`, records, per-club transfer in/out). The rules run once per build, not once per
   query.
5. **One source per fact; everything else is a check.** Checks live in their own suite and
   report mismatches; they never alter the build (scores from the fixture list, events checked
   against them).
6. **The warehouse keeps everything**, raw ability included. The immersion rule applies at the
   presentation layer (site export, user-facing marts).

## Build and test

- **Build:** `fmstats.warehouse.build(con)` creates `dw` in dependency order (read from the
  declarations). `load_duckdb.py --refresh-only` calls it before the mart, so an existing store
  gets the warehouse without a rebuild.
- **`tests/validate_warehouse.py`**, generated from the declarations:
  - **grain**: no duplicate key in any table;
  - **foreign keys**: every key resolves to its dimension;
  - **not-null** on keys.
- **Checks suite** (part of the same script, reported separately): goal events vs score,
  transfer ↔ contract both ways, the save's contracted flag vs `contract_status`, the "loaned
  out" code vs loan spells, rebuilt league tables vs `club_league_history`, outcomes vs the roll
  of honour.
- **Parity:** where a mart view already answers the same question, the `dw` version must match
  it, or the difference must be explained (and is usually a bug in one of them). Listed per
  phase below.

## Phases

Each phase is one PR, merged with its tests green. Earlier phases unblock later ones.

| # | Area | Builds | Parity / gate |
|---|---|---|---|
| 0 | **Foundations** | `fmstats/warehouse/` package, the table declaration, `build()`, `validate_warehouse.py`, hook into `--refresh-only` | an empty `dw` builds and validates on the published store |
| 1 | **Reference, nation, club** | `dim_position`, `dim_role`, `dim_city`, `dim_stadium`, `dim_nation`, `fact_nation_snapshot`, `dim_club`, `dim_team`, `fact_club_snapshot`, `fact_team_snapshot` | `dim_club`/`dim_team` vs `mart.clubs`; first team ↔ reserves via `main_club_tid` matches `mart.our_clubs` |
| 2 | **Competition & match** | `dim_competition`, `dim_stage`, `dim_round`, `dim_match` (every match in the world, `has_detail`), `fact_team_match`, `fact_player_match`, `fact_match_event`, `fact_participation`, `fact_competition_outcome`; views `standings`, `tie_results` | vs `mart.club_matches`, `mart.match_stages`, `mart.league_tables`, `mart.match_player_facts`; events-vs-score check |
| 3 | **Person** | `dim_person`, `fact_player_snapshot` (incl. training, nationality, languages, `contract_status`), `fact_staff_snapshot`, `fact_injury_spell`, `fact_player_season`, `dim_award`, `fact_player_award` | vs `mart.player_snapshots`, `mart.injury_spells`, `mart.player_seasons`, `mart.player_career_seasons` |
| 4 | **Contracts & transfers** | `fact_contract`, `fact_transfer`, `fact_loan_spell`, `fact_staff_spell`; squad-membership view | vs `mart.player_spells`, `mart.at_club_spells`, `mart.transfers`, `mart.loan_out_spells`, `mart.squad_current` / `squad_on`; transfer ↔ contract check |
| 5 | **Move the marts** | each mart view rewritten to read `dw` instead of `staging`, one view per commit | **`git diff site/api` is empty** after `export_data.py` (the export is deterministic) and `validate_mart.py` passes |
| 6 | **Refactor and retire** | merge or drop marts that are now one-line selects over `dw`; agents and `fmq sql` pointed at `dw` | the site still diffs clean; CLAUDE.md, `site/AGENTS.md`, `remote-duckdb-access.md` updated |
| 7 | **Publish** | `dw` in the published store, and a `dw`-first object for remote agents | `publish_*` verify step passes; size checked against the R2 budget |

Phase 5 is where the choice between **recreating** a site-shaped mart and **refactoring** it is
made, view by view: if the site can read a `dw` table directly, the mart view goes; otherwise it
becomes a thin shape over `dw`.

## Known blockers and unknowns

| Item | Blocks | Note |
|---|---|---|
| Person identity (TODO #14: recycled tids keeping old names, `is_staff` flips emptying history) | phase 3 | `dim_person` has to be right before anything keys on it |
| History lost to pool reclamation (TODO #15) | phase 3 | `fact_player_season` should union history across snapshots |
| Extra-time minutes (TODO #16) | phase 2 | `fact_player_match.minutes` needs the extra-time flag |
| Two-legged ties: one round or two? | phase 2 | decides how `tie_results` groups |
| Reputation per team or per club | phase 1 | modelled per team; moves if the save says otherwise |
| Contract signed dates (unread dates on the training row) | phase 4 | exact end dates instead of snapshot bounds, if they decode |
| Referee link, call-ups | phases 2, 1 | modelled; tables stay empty until located in the save |

## Relation to TODO #12 (extract dumps tables, the mart does the joins)

The warehouse is where those joins land. Phases 1–4 should read the raw staging tables where they
already exist, not the pre-joined `staging.players`, and should not add new pre-joins to
`extract.py`. Moving extract's pre-joins out can then happen table by table under #12, with
`dw` already reading the right inputs.

## Out of scope

- New parsing. Gaps the model names (referee link, call-ups, contract dates) are TODO items, not
  part of this build.
- Analytics on top (role weights, ratings, the attribute and value models, home-grown rules):
  they stay in `mart`/`fmstats` and later read `dw` instead of `staging`.
- Site changes, beyond what moving the marts requires.
