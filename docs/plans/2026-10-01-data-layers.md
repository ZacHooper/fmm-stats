# Data layers: extract dumps tables, the store models them (2026-10-01)

> **Status (2026-10-01): in progress. Done: steps 1–8; the stg/int layers are a dbt project (`transform/`).**
>
> **Goal:** two halves of one job. `extract.py` becomes a flat list of `dump(TABLE.scrape(mm))`
> steps that hand over every table as the save stores it, with no joins, lookups, labels or
> derived columns. The store then models that data in layers, **raw → stg → int → mart**, ending
> in the `dim_*` / `fact_*` tables of the semantic model ([`docs/data-model/`](../data-model/README.md)),
> and the site's marts move onto them one at a time.
>
> This replaces `2026-09-30-extract-cleanup.md` and `2026-10-01-warehouse-build.md` (both in git
> history). It is TODO #12.

**How to read it.** Part 1 is the roadmap: read it to know what's next. Part 2 has one section per
step. Part 3 holds what every step shares. The appendix is the evidence behind the extract steps.

---

# Part 1 — Roadmap

## Why

- **Extract does work that isn't extraction.** `players.json` is a row pre-joined from about
  seven tables; club and league labels, wages in pounds, the display name and the attribute
  masking are all decided in `extract.py`. Extract also filters: `valid_clubs` silently drops
  **20–26% of world fixtures** on every save.
- **The mart does work that isn't presentation.** `fmstats/mart.py` is 3,600 lines and ~87 views
  in one file, each reading the landed data directly, so every view re-applies the same rules
  (latest phase per season, snapshot-scoped joins, `person_id` not `tid`, appearance
  arithmetic) and building blocks are mixed in with site-shaped output.

Both halves fix the same thing: each rule gets one home, a stated grain and a test, and users and
agents query tables whose meaning is documented.

## The layers

```
save ─▶ fmparser (E) ─▶ raw (L) ─▶ stg ─▶ int ─▶ mart ─▶ site, fmq, agents
```

| Layer | Schema | Holds | Rule |
|---|---|---|---|
| **raw** | `raw` (today's `staging`, renamed) | every table as the save stores it, one row set per snapshot; plus seeds (role weights, model coefficients, event types) | written only by `load_duckdb.py`; no logic |
| **stg** | `stg` | one model per raw table: rename, cast, decode codes, attach `person_id`, drop unused rows | 1:1 with its source; no joins across sources, no business rules |
| **int** | `int` | the logic: snapshot dedupe and latest-phase rules, joins across tables, spells, contract reconstruction, derived standings and outcomes, model scoring | joins and rules live here and only here |
| **mart** | `mart` | the `dim_*` / `fact_*` tables from `docs/data-model/`, plus consumer-shaped marts built on them | what users, agents and the site read |

stg, int and the `dim_*` / `fact_*` tables are a **dbt** project, `transform/` (decided after
step 8; it replaced the Python framework step 6 built, output identical). The old consumer
marts in `fmstats/mart.py` stay in Python and are not moved: the plan retires most of them. dbt
builds in schemas `stg`, `int` and (from step 16) `mart`, beside the old mart objects there.

## Decisions

From the extract plan (Zac, 2026-09-30):
1. **`players.csv` is dead**: the outside squad-comparison tool no longer reads it.
2. **Rename the saves to their header dates** before the label rules go, so every save's name,
   label and `phase` are the same string again.
3. **Write the whole club table** (11,331 clubs) and the whole competition table. Any filtering
   (the site's club list) is a view in the store, not a choice extract makes.
4. **Migrate older stores**: each step that drops or renames a column or table ships a migration
   (like `load_duckdb._raw_tables`), not NULL columns and not "needs a rebuild".

From the data-model work (Zac, 2026-10-01):
5. **Layers are raw → stg → int → mart**, and `staging` is renamed `raw`.
6. **Natural keys, no surrogates.** The store is always rebuilt from scratch, so the save's own
   ids are stable within a build: `person_id` = `<tid>-<dob>` (never `tid` alone: the game hands
   a retired person's slot to a newgen), team `tid`, competition `cid`, match = (date, home,
   away).
7. **New marts are named `dim_*` / `fact_*`** and live in `mart` next to the old views, which no
   existing name collides with; the old views are retired one by one.
8. **The two models** (attributes, transfer value) are fitted offline; their coefficients are raw
   seeds; scoring is int; the results are flagged columns on `fact_player_snapshot`. Fitting
   reads observed rows only.
9. **The store keeps everything**, raw ability included. The immersion rule applies at the
   presentation layer (site export, user-facing marts).

## Principles

1. **Every model is declared**, not just written as SQL: name, layer, kind, grain (key columns),
   foreign keys, upstream models, SQL. The build order, the tests and the docs all read the
   declaration, the way `Record` declarations drive both the parser and `audit_records.py`.
2. **Materialisation: only the mart is materialised.** stg and int are views; the build runs
   them once and writes the mart as tables, so no agent and no site ever reads upstream of the
   mart. An int model becomes a table only for a measured, serious performance reason, noted in
   its declaration.
3. **One source per fact; everything else is a check.** Checks report mismatches and never alter
   the build.
4. **Every step is gated row-for-row** against a store built from `main` (Part 3).

## The steps

One PR each, merged green, in this order.

| # | Step | Half | Gate |
|---|---|---|---|
| 1 | The store diff tool | extract | runs against two published stores |
| 2 | Header dates only: rename saves, drop labels and match dates | extract | full `rebuild.py`; manifest check passes on every row |
| 3 | Delete dead outputs | extract | exactly two fewer files; every other file byte-identical |
| 4 | Whole reference tables (clubs, competitions, fixtures) | extract | `diff_stores` on the existing mart rows; reviewed `git diff site/api` |
| 5 | Rename `staging` → `raw` | layers | migrated store equals its old self; site export unchanged |
| 6 | The models framework, and the loader's views moved into it | layers | every moved view equals its old self row-for-row |
| 7 | Contracts and squad status | both | `diff_stores` on the players compatibility view |
| 8 | Names | both | same |
| 9 | Person, player and staff records; `build_database` deleted | both | same |
| 10 | Extract cleanup | extract | `run_tests.py`; `assert_identical` re-recorded |
| 11 | Save order and the cursor; extract takes no career | both | `assert_identical` re-recorded; gate stores diffed |
| 12 | stg for every raw table | layers | `rows_match_source` on every stg model |
| 13 | Reference, nation, club | layers | vs `mart.clubs` row for row; `dim_team` = `mart.our_clubs` |
| 14 | Competition and match (14a, 14b) | both | vs `mart.club_matches`, `match_stages`; then `league_tables`, `match_player_facts` |
| 15 | Person and the two models | layers | vs `mart.player_snapshots`, `player_value_est`, `injury_spells`, `player_seasons` |
| 16 | Contracts and transfers | layers | vs `mart.player_spells`, `at_club_spells`, `transfers`, `loan_out_spells`, `squad_current` |
| 17 | Move the site's marts | layers | `git diff site/api` empty; `validate_mart.py` |
| 18 | Retire and publish | layers | site diffs clean; publish verify; size within the R2 budget |

**Why this order.** Steps 1–4 fix the inputs first: the whole club and competition tables and the
unfiltered fixture list are exactly what the dimensions need, and step 1's diff tool is the gate
everything later uses. The rename (5) comes before steps 7–9 so the new dumps land as `raw.*`
instead of adding more names to rename, and the framework (6) exists by the time those joins need
a home: they become stg/int models directly, never loader views. Steps 10–11 are independent and
can move. Steps 12–18 build the model on clean inputs.

---

# Part 2 — Step detail

## 1. The store diff tool
`scripts/audit/diff_stores.py OLD.duckdb NEW.duckdb --table <schema.table> --key season,phase,tid`:
per-column counts of differing rows, rows only in one store, examples. Every later gate is one
command against a store built from `main`. The comparison script from the scrapbook PR (#116) is
the starting point. Small; can ride with step 3.

## 2. Header dates only: rename the saves, drop labels and match dates
**Saves (decision 2)**: rename the 20 saves whose name is not their header date, in every place
the name lives: the `.fms` and `.gz` in `$FM_SAVES_DIR`, the R2 objects, the manifest,
`staging.extracts.save_path` / `label` in the store, and the saved scouts' keys.
`scripts/canonicalise_names.py` (deleted; restore from git) did exactly this set once.
`fm_save1.fms` gets its header date or moves to `unfiled/`.

**extract.py**
- Delete `_period`, `auto_label`, `parse_label`, `_PHASES` and the `--label` default logic; the
  output folder is the save's name without `.fms`.
- `season_phase` uses the header date only; an unreadable header is a hard failure.
- `HDR.campaign`: a match-less save before the rollover belongs to the next campaign
  (`frem-2021-07-01` → 2022), so the summary always carries a season.
- The summary drops `label_auto`, `label_source`, `latest_match`, `date_range`.

**load_duckdb.py**
- Drop `from extract import parse_label` (the loader's only import from `extract`).
- `resolve_season_phase`: override, else summary, else fail loudly; the `--all` duplicate check
  keys on the summary's season/phase; the "replacing a newer snapshot" warning compares phase
  dates.
- Stop writing `label_auto`, `latest_match`, `date_from`, `date_to`; a migration drops them from
  older stores (decision 4).

**mart / fmq**: remove `latest_match` and `is_preseason` from `mart.snapshots` and `fmq labels`; a
"last match" date, if ever wanted, comes from the matches table.

**scripts/rebuild.py**: stop passing `--label`, `--season`, `--phase`; after each extract, compare
the summary's season/phase with the manifest row and fail loudly on a mismatch
(`--trust-manifest` forces the manifest values).

**Docs**: the `import-fm-saves` skill (reads `label_auto`, `latest_match`, `date_range`),
`CLAUDE.md`, `README.md`, `docs/agent-context/etl-duckdb-dashboard.md`.

**Check**: `assert_identical --record --note` (summary.json changes); a full
`rebuild.py --career frem` with the manifest check passing on every row.

## 3. Delete dead outputs
`players.csv`, `player_match_stats.csv`, `flatten_matches`, `write_players_csv`,
`write_match_stats_csv`, `_STAT_FIELDS`, the `csv` import and the `player_match_lines` count; fix
the module docstring (it still lists `transfers.json` and the old label rule).

**Check**: re-record; exactly two fewer files, every other file byte-identical.

## 4. Whole reference tables (clubs, competitions, fixtures)
**extract.py**
- `clubs.json` = the whole club table, every slot, with `club_details.json` merged in.
- `competitions.json` = the whole competition table; the rule files' team counts get their own
  file (`competition_team_counts.json`, uid → teams).
- Delete `leagues.json`, `club_league.json`, `build_leagues`, `league_label`,
  `build_competitions`, `_history_clubs`, `build_database`'s `club_ids` / `club_names` /
  `club_leagues` loop and the league stamping on each player. Player `club` labels come from the
  whole table.
- `FIX.fixtures(mm)` without `valid_clubs` (drop the parameter). This is what lets `dim_match`
  (step 14) hold every match in the world.

**load_duckdb.py**: `staging.clubs` and `staging.club_details` both load from `clubs.json`;
`staging.competitions` loads the whole table (no `matches_in_save`); stop loading
`staging.leagues` and `staging.league_members` (migration drops them);
`v_player_rating_ranks` takes `league_cid` from `mart.club_leagues`.

**fmstats/mart.py**: `mart.club_leagues` takes the league id off the club table (same as-at logic)
and name, reputation, type from `staging.competitions`, nation via `nation_id`; `mart.leagues` is
the competitions some club plays in, `member_count` counted; `mart.competitions` drops the `lg`
merge; the site's club list keeps its current scope through a view (decision 3).

**Risks**: `mart.clubs` grows from ~4.6k to ~11.3k rows per snapshot; 292 → 332 leagues can shift
the tier derivation and the league ladder (likely a filter to league types); `world_fixtures`
gains ~7k rows per save, so `mart.league_tables` and everything on fixtures must still key on the
right competitions.

**Check**: `diff_stores` on the existing rows of `mart.clubs`, `mart.leagues`,
`mart.club_leagues`, `mart.competitions`, `mart.league_tables`; `validate_mart.py`; a reviewed
`git diff site/api`; `assert_identical` re-record. Then delete the `clubs_comps` lookups nothing
uses (`club_record`, `resolve_club`, `league_name`, `comp_detail`, `club_details`);
`discover_career.py` and the tests and audits that used them read the tables directly.

## 5. Rename `staging` → `raw`
Mechanical, but wide. Every `staging.` reference moves: `load_duckdb.py` (DDL, loaders,
migrations, the views it writes), `fmstats/mart.py`, `fmstats/*` (scout, stats, league, store),
`fmq.py`, `scripts/export_data.py`, `scripts/_export_db.py`, `scripts/publish_duckdb.py`,
`scripts/publish_mart.py`, tests, skills, CLAUDE.md, `site/AGENTS.md`,
`docs/agent-context/remote-duckdb-access.md`.

- A migration renames the schema in an existing store (decision 4).
- **Drop `staging.standings`** here rather than renaming a dead table: extract no longer writes
  it; remove the loader's `load_standings`, its group, and `export_data.py`'s note about it.
- The views the loader writes today (`squad_scrapbook`, `players` / `player_attributes_exact`
  over their `_raw` tables, the attribute decode view) move with the rename as a documented
  exception to "raw has no logic"; step 6 moves them out.
- Older published copies: `fmstats/store.py` exposes a cached copy's `staging` tables as `raw`
  views (Python in `fmstats` reads `raw.*` directly, not only through the mart), and reads a
  copy whose raw tables this checkout's mart cannot bind to "as published", using the mart
  materialised in it (step 4). The copies are republished at step 18.
- The migration copies each table into `raw` from its own DDL and drops `staging`: DuckDB
  cannot rename a schema or move a table. It refuses a published (compacted) copy.

**Check**: the migration run on a copy of the gate store, every table and view equal to its old
self; the site export from the migrated copy unchanged; `validate_mart.py`, `run_tests.py`; `fmq`
against the current R2 copy, read as published.

## 6. The models framework, and the loader's views moved into it
*(Done; the framework below was then replaced by the dbt project `transform/`, output identical,
and `validate_models.py` by `dbt test`.)*
- **`fmstats/models/`**: the declaration (name, layer, kind, grain, foreign keys, upstream, SQL),
  `build(con)` in dependency order, and `tests/validate_models.py` generated from the
  declarations: grain uniqueness, foreign keys resolve, keys not null. A separate checks report
  (Part 3) that never fails the build.
- **`load_duckdb.py --refresh-only` calls `build()`**, so an existing store gets the layers
  without a rebuild.
- **First real content, the loader's transforms** (TODO #12's "move the loader's remaining
  transforms"): the squad views, the attribute decode view (→ `int_player_attributes`, step 15
  extends it), `rebuild_persons` (the `(tid, dob) → person_id` bridge, → int) and
  `v_player_ratings` / `v_player_rating_ranks`. The old names stay as compatibility views over
  the models until their consumers move (step 17), so nothing downstream changes.
- After this, `load_duckdb.py` only writes JSON into `raw`.

**Check**: each moved view equals its old self row-for-row (`diff_stores`); a real `rebuild.py`,
not `--refresh-only`.

## 7. Contracts and squad status
- extract dumps `contracts.json` (every used slot of the grid as stored: marker, wage units,
  dates) and adds `contracted` / `squad_status` to `training.json`'s rows;
- `wage_gbp` stops being computed in `scrape_contracts`; `WAGE_GBP_PER_UNIT` goes to the store;
- `raw.contracts` → `stg_contracts`; the join to the person and the wage derivation are int; the
  players compatibility view takes the contract and status columns from there.

The smallest of the three record steps; it proves the raw → stg → int → compatibility chain first.

## 8. Names
- extract dumps the three name id-tables and the browse strings (`names.json`) and the person
  table's name ids;
- the display name (common name, then first + last) is an int model (`int_person_names`);
- `clubs_comps.build_name_resolver` / `resolve_name` / `resolve_common_name` go.

## 9. Person, player and staff records
*(Done: extract dumps `persons.json`, `attribute_records.json`, `staff_records.json` and
`formations.json` as stored, into `raw.person_records` / `attribute_records` / `staff_records` /
`formations` (`stg_persons`, `stg_player_attributes` with one column per position,
`stg_staff_attributes`, `stg_formations`). int splits a player into what he is and how he is
rated: `int_player_info` (person ⋈ attribute record on `sid`: identity, club, CA/PA,
reputation, value, contract, training, `has_attributes`, `is_goalkeeper`) and
`int_player_attributes` (the 23 displayed attributes, stated or decoded, with one
`is_estimated` flag, plus the hidden attributes, personality, positions and feet, all wide),
fed by `int_player_attributes_exact` and `int_player_attribute_estimates`;
`int_staff_snapshots` joins the staff record on `id2` (formation names, Style and reputation
tier banded in SQL). This is step 15's int half: step 15 keeps the mart, where
`fact_player_snapshot` joins `int_player_info` to `int_player_attributes`. The old shapes are
legacy models (`players`, `player_positions`, `staff_attributes`). `id2 = 0` is a real link
(tid 0's record); the old extract treated it as "none".)*
- extract dumps `persons.json` (the person table as stored), `player_attributes.json` (the
  attribute record keyed by `sid`: all 34 attribute bytes, positions, CA/PA, the tail) and
  `staff_attributes.json` (keyed by `id2`, formation indices), plus the formation catalog;
- stg models over each; int does the `sid` / `id2` joins, the player/staff split,
  `has_attributes`, `is_gk` and the `EXACT_SINGLE` masking (no `loaned_out`: loans are
  `fact_loan_spell`, step 16); the players and
  exact-attributes compatibility views read int;
- `build_database` is deleted, and with it extract's import of `fmparser.model`.

**Name clashes to settle first**: `persons` (the identity bridge), `player_records` (club records)
and `player_attributes` (the decoded view) are taken; name the new raw tables by what they are
(`raw.person_records`, `raw.attribute_records`, `raw.staff_records`).

**Checks for 7–9**: `diff_stores` on the players and exact-attributes compatibility views over
the four `assert_identical` saves (both careers); `assert_identical` re-recorded with the new
files named. A sample is enough because these views are per-snapshot: each snapshot's rows come
from its own extract alone, and the old mart reads only them.

## 10. Extract cleanup
- delete `clubs_comps.py`; its `info_offset` (a byte sweep gated on a DOB window) goes with
  it, and `tables/player_attributes.record_for` reads the player's `sid` off the walked person
  table instead;
- drop `raw.player_history`'s constant `confidence` / `origin_club` columns (migration).

## 11. Save order and the cursor
Done, with the career moved out of extract in the same PR, so every step reads one table and
nothing else:
- `extract.py` is a flat list of steps (`steps()`: table name, where it sits, its read), in
  file order (appendix), the archive last. Each table is one dump: names split into
  `browse_names.json` and `name_ids.json` (two tables, 38 MB apart); the club table is one
  reader (`clubs.scrape_clubs`, the whole record) instead of two merged in extract.
- History takes no input: a player's head row is his attribute record's own `history_head`
  (now in `attribute_records.json`), and the loader joins persons to it
  (`raw.attribute_records.history_head`), not a `heads` map in `history.json`.
- Extract takes no career. `careers.py` moved to the repo root, on the loader's side
  (`test_boundary` bans it from fmparser and extract); the loader takes `--career` (else the
  store's own), places each snapshot (`careers.campaign`, moved from `save_header`) and runs
  the match table vs fixture list check. `summary.json` loses `season`, `phase` and `career`.
- The cursor is a CHECK, not a search bound: each located table's first record must sit at
  or after the end of the table before it, else extract stops naming both;
  `--no-cursor` skips it. Locators do not take `lo`: a lower bound only changes a locator's
  answer when it would otherwise land before its predecessor, which is exactly what the
  check refuses, and on every measured save no locator does. Threading `lo` through ~20
  locators and their caches would change no output; add it to the one locator that ever
  needs it.
- `tests/test_extract_order.py`: the steps' first records only go up, both careers.

**Check**: `assert_identical` re-recorded (`attribute_records`, `history`, `summary` change;
`names.json` becomes `browse_names.json` + `name_ids.json`; every other file byte-identical);
the gate saves loaded with main's loader and with the branch's, every raw/stg/int/legacy/mart
relation diffed.

## 12. stg for every raw table
*(Started by the int redesign (#129), which gave every source the person and player models
read a stg model; finished here.)* Every raw table has one stg model (43), keyed by
`snapshot_date`: renamed to the model's vocabulary (`stadium_id`, `home_team_tid`,
`match_date`, `passes_completed`, ...), cast, and with each "none" sentinel read as NULL
(`no_id16` 0xFFFF, `no_id8` 0xFF; a free agent's history line has a NULL club). Coded seasons
become the project's season (`1971 + n`, a league history's start year + 1), and a career-history
fee code is decoded to `fee_kind` and `fee_gbp` (`fee_code_floor`, `fee_unit_gbp`,
`fee_contract_ended`). No stg model joins another source, and none drops a row. `person_id`
stays an int concern (`int_persons`), since attaching it would join the person table.
Unnamed fields (`unk*`, the records' and affiliates' day-of-year dates) are carried as stored.
`raw.results` was retired: extract no longer writes light results, so it was always empty.
`raw.nation_languages` has no key: Iceland lists English at 50, 70 and 95.

**Check**: `rows_match_source` on every stg model (each one's row count equals its raw source,
less the rows it documents dropping: none do), plus a grain test wherever the source has a
key; broken on purpose once (a `where` on `stg_stadiums` fails it).

## 13. Reference, nation, club
The first `dim_*` / `fact_*` tables, built by dbt in `models/mart/` as tables in the `mart`
schema beside the old views (`load_duckdb._drop_unbuilt` drops only the `dim_`/`fact_` tables
the project no longer defines).
- **The save stores every team as a whole club record**, so the team, not the club, is the
  unit it holds. `int_teams`: a team that names a parent in `main_club_tid` belongs to that
  club, else it is its club's first team. `team_type` is `first`, `reserve`, `b_team` (a
  first-team-typed record with a parent: a second side in the senior pyramid, Las Palmas C),
  `national` or `national_u21`. `int_team_squads` reads its team type and club from it.
- **Club vs team, measured, not assumed**: reputation and status are each team's (Frem 4691,
  its reserves 3530), on `fact_team_snapshot` with the training and youth facilities. A reserve
  side's record holds defaults for the facilities (training 10 and youth 0 on every reserve
  side, never changing), so it has its club's; a B team has its own. Ground, colours and kits
  are the first team's, on `fact_club_snapshot` (a reserve side stores no ground and empty
  kits); a team's ground is its own, else its club's. The record's attendance fields are not
  modelled (`mart.clubs` says why).
- **Dimensions hold what does not change between snapshots**; what changes is on a snapshot
  fact. A stadium's name and capacity change (Valby Stadion 4,400, 9,400, 15,000), so they are
  on `fact_stadium_snapshot`; a nation's languages, ranking and coefficients on
  `fact_nation_snapshot`. Measured on the gate stores, the nation, city, club-name and
  club/nation id fields never change.
- `based_id` is the nation whose league a club plays in (Cardiff City: England; home nation
  Wales): `league_nation_id`.
- **Codes named by seeds**: `seeds/roles.csv`, `training_attributes.csv` and `positions.csv`
  (the unit of each position) replace `fmstats/definitions.py`; the loader seeds them into raw
  (`seed_codes`) and `fmstats/mart.py` renders `mart.roles` / `mart.training_attributes` from
  the same files. A role carries no position: the save does not say where one is played.
- Mart models are named by their relation (`dim_city.sql` -> `mart.dim_city`), not
  `mart_<name>`. A dimension's row is its id's latest snapshot (`latest()`: the max
  `snapshot_date` the id appears in). Cities have no name in the save.

**Check**: `fact_team_snapshot` against `mart.clubs` on all 33,993 (Frem) and 12,278 (Bucaspor)
rows: name, reputation, last season's finish, staff size and status agree on every row, and
so do facilities and academy for every team but a reserve side (which now has its club's). The differences are all explained: the save's 0xFFFF reads
NULL; a reserve, U21 or B side with no ground gets its club's, and a reserve side its club's
facilities; and `mart.club_leagues` carries a
league forward from an earlier snapshot where the record names none (217 Frem rows), a
cross-snapshot rule that moves with the league tables in step 14. `dim_team`'s teams of the
managed club equal `mart.our_clubs` (a `validate_mart.py` check), and its reserve is
`careers.py`'s `reserve_tid` (7296, 11320).

## 14. Competition and match
Two PRs, both done. **14a**: the extra-time score, competitions, stages, rounds, matches and
the team-match fact. **14b**: player-match facts (minutes with extra time), events,
participation, outcomes, `standings` and `tie_results`.

What the save says, measured before modelling it:
- **Extra time is in the fixture list.** `fix_man`'s `+7`/`+12` bytes are the score after extra
  time (0xFF = none): equal to our match table's final score on all 5 extra-time matches among
  our 575, every save of both careers; the other 570 equal the 90-minute score. Extract now
  writes them (`home_extra_goals` / `away_extra_goals`; `stg`: `goals_aet`).
- **A two-legged tie is one round played twice**, home and away swapped, both fixtures
  carrying the round's `round_index`; the rules mark the round `legs = 2`. `int_matches`
  numbers the legs by date and gives the pairing a `tie_id`. A second leg's extra-time bytes
  are that match's own score, not the aggregate (Salzburg–Frem, 2027-07-28: 2-4 aet after a
  1-0 first leg; the aggregate would read 2-5). **No away-goals rule**: both two-legged ties of
  ours level on aggregate went to extra time though Frem led on away goals.
- **Rules change between seasons** (a round of 16 teams in 4 groups becomes 32 in 8; 32
  entries on the gate store), so stages and rounds are keyed by the **competition season**,
  the fixture's own season label (`season_year`: 2025 for a 2025/26 league and for a
  calendar-year 2025 one), with each season's rules from the earliest snapshot holding both
  one of its fixtures and its rules.
- **A fixture names its stage, not its competition**, and no decoded byte of the fixture, the
  `comp_man` stage record or the rules members holds the link (TODO #6). A stage is labelled
  from one of our matches in it (`our_match`), else by `mart.league_tables`' league rule
  (`league_structure`: a multi-matchday stage at index 0 is a league's regular stage, the
  season's other stages wholly inside its clubs are its split groups, named by the majority
  league with an 80% membership check). That rule is a heuristic, verified against the game's
  final positions for Denmark and the Premier League and failing for Spain (TODO #13); the
  rest (cups abroad) stay NULL. Competition reputation changes between snapshots
  (`fact_competition_snapshot`).

14a models: `int_world_matches` (one row per match, latest snapshot), `int_our_matches`,
`int_stage_competitions`, `int_competition_seasons`, `int_stages`, `int_rounds`, `int_matches`,
`int_team_matches`, `int_competitions`; mart `dim_competition`, `fact_competition_snapshot`,
`dim_stage`, `dim_round`, `dim_match` (every world match, `has_detail` for ours,
`competition_source`), `fact_team_match` (2 rows per match, the final score).

**Check (14a)**: `fact_team_match` equals `mart.club_matches` on every row of our matches
(goals, result, venue; Frem 114, Bucaspor 140), and `dim_match.cid` our match table's
competition on all of them. Against `mart.match_stages` (4,116 / 3,408 rows) the score differs
only on other clubs' extra-time matches (12 + 2 Frem, 20 + 2 Bucaspor), where the old view had
the 90-minute score. `dim_match` holds every row `mart.world_fixtures` does. Every match `mart.league_tables` counts
as a league game has the same league in `dim_match` (Frem 19,544 of 19,550, Bucaspor all
13,527; none differ). The 6 are one 4-club stage that fits two base stages; `dim_match` also
labels ~2,000 reserve-group matches `league_tables` drops at its 80% check (its
`club_leagues` carries a league forward, which inflates the league's size).

What 14b reads, measured first:
- **An event names its side.** Extract always gave each event's side (home/away, the player's
  team, own goals included); the loader now keeps it (`raw.match_events.side`), so an event's
  team is read, not joined through the player lines. Event minutes run past 90 in extra time
  (`120+2` for shoot-out kicks), and sub minutes do too (on at 105).
- **The match table calls the striker `FC`**; the positions list calls him `ST`.
  `stg_match_player_stats` maps it (var `match_position_codes`).
- **Reserve groups have no rules member**, so they have no `dim_stage` rows; a stage with no
  rules is a league stage when its competition's type is a league's or the league rule
  labelled it (`int_standings`).

14b models: `int_event_types`, `int_match_events`, `int_player_matches`, `int_ties`,
`int_standings`, `int_participations`, `int_competition_outcomes`; mart `dim_event_type`,
`dim_period`, `fact_player_match`, `fact_match_event`, `fact_participation`,
`fact_competition_outcome`, and the views `standings` and `tie_results`. Two fixes to 14a's
league rule, both to match `mart.league_tables`: the 80% check counts all the stage's clubs
with a league, whatever league (a snapshot after the last matchday has the promoted and
relegated clubs in their new leagues already, which left the 24-club English leagues at 75%),
and a stage key counts as multi-matchday when it is in any season (a league keeps its key
from season to season, so a season one matchday old is labelled).

**Check (14b)**, on the oracle stores plus one of three Frem saves holding our extra-time and
shoot-out matches (2023-06-29, 2027-06-29, 2027-08-09):
- `fact_player_match` equals `mart.match_player_facts` on every row (1,988 / 2,567 / 4,562):
  started, appeared, stats, position, person; minutes differ only on the 3 extra-time and
  shoot-out matches (109 rows), where the old view capped at 90 and a sub on at 105 read −15.
- Goal events per side equal the fixture-list score on all 255 matches with detail, extra time
  and shoot-outs included; each player's goals equal his goal events on all 4,562 lines.
- `standings` totals (played, points, goals) equal `mart.league_tables` on every row it has
  in Denmark (136 / 208) and elsewhere (1,449 / 957 / 1,769), except the Greek play-off
  group's first round (8 Bucaspor rows), which the old view leaves out.
- Against the game's final positions (`club_league_history`), complete single-stage tables
  agree for England (21/21) and Germany (9/9), and Danish split leagues with points carried
  over 8/8 on the extra-time store (the others are incomplete: a snapshot's fixture list
  holds only part of the season before). Spain agrees on 4 of 27 tables, and every miss is
  teams level on points: head to head decides all 41 such pairs it separates (TODO #13).
- Tie winners equal `mart.match_stages.went_through` on all 21 rows of our ties.
- Outcomes vs the roll of honour: not checked, since the roll of honour is not extracted
  (TODO 12a).

## 15. Person and the two models
*(int half largely done in steps 8–9: person identity (`int_person_snapshots`, `int_persons`),
`int_player_info`, `int_player_attributes` and `int_staff_snapshots`. What is left of the int
half is `int_player_value` and the seasons; the mart half is all to do.)*
- **int**: person identity (`person_id` = `<tid>-<dob>`, built across **every** snapshot so a
  retired player whose slot has gone to a newgen keeps his history), `int_player_attributes` (exact where stored, estimated otherwise,
  with the rule for when an old exact entry gives way to the estimate), `int_player_value`
  (coefficients moved from `fmstats/value_model.py` to a raw seed), seasons unioned across
  snapshots.
- **mart**: `dim_person`, `fact_player_snapshot` (attributes and positions, hidden attributes,
  CA/PA, value, reputation, team, training, nationality, languages, `contract_status`, provenance
  flags), `fact_staff_snapshot`, `fact_injury_spell`, `fact_player_season`, `dim_award`,
  `fact_player_award` (from `raw.player_scrapbook`, lists 0–30 and 62/64).

**Done.** As built:
- **Identity**: a person never turns back into a player once he loses his player record (2,520
  of 37,436 people across three Frem snapshots: 1,766 retire with no record, 633 become staff),
  so "is_staff flipping empties his history" (#14) is retirement, and the history union below
  is the fix. Old scrapbook entries can carry a tid since given to a newgen, so an award resolves
  to its `person_id`: the person with that tid whose dob gives the entry's age on its date.
- **History** (#15): the game keeps a player's newest lines and drops his oldest (and removes
  a loan year's 0-app parent line once the season is over), so `int_player_career_lines`
  takes the newest snapshot's lines plus what each older snapshot held that its successor
  dropped. 3,437 of 30,691 people had a richer history in an older snapshot; the union holds
  370,417 lines against the newest snapshots' 345,315.
- **Value**: coefficients in `seeds/value_model.csv` (`raw.value_model`), scored by
  `int_player_value`. The league reputation the store reads is the competition record's u16
  at +9 (58-136 in Denmark); the model was fitted on the u16 at +8 (256x that), so every
  estimate on main read £0-£300. The intercept is restated (+ llrp·ln 256), which also fixes
  `mart.player_value_est`. A reserve side takes its first team's league reputation, as fitted.
- **mart**: `dim_person`, `fact_player_snapshot`, `fact_staff_snapshot`, `fact_injury_spell`,
  `fact_player_season` (career history, every player), `fact_player_competition_season` (our
  matches, per competition), `dim_award`, `fact_player_award` (World Best XI pools: each
  season's list as its latest snapshot holds it, and the newest All-Time pool, list 62; the
  game's eleven are not stored, and 64 is the All-Time pool as of last season's end).
- Career-history rating: 0xFFFF, the save's "none" (7,380 pre-career lines), reads NULL like
  0. Not built: languages (no person-language table is read).

**Check** (Frem 2021-06-27 / 2023-07-02 / 2026-06-11):
- `fact_player_snapshot` = `mart.player_snapshots` on all 77,997 rows: person, age, every
  attribute, estimated flag, hidden and personality, stated value, wage, expiry, nationality,
  keeper, reputation, squad status, feet. Team differs on 1,597: free agents read NULL, not
  65535, and 4 loanees in carry their parent team (the record's), not ours.
- `int_player_value` = `mart.player_value_est` on every first-team and b-team row (one
  rounding difference); reserve rows differ by the league rule above, and 634 reserve players
  of Belgian clubs get no estimate (Belgian club records name no league, so their first-team
  players have none in either view).
- `int_player_value` median error against our stated values 1.7-2.3x per snapshot (the
  model's documented 2.27x).
- `fact_injury_spell` = `mart.injury_spells`, 106/106.
- `fact_player_competition_season` = `mart.player_seasons` (competitive) on all 562 rows, every
  stat.
- `fact_player_season`: each person's newest-snapshot lines in `mart.player_career_seasons`
  are exactly the union's newest lines (345,315/345,315); club 65535 reads NULL.
- Frem 2023-06-29 / 2027-06-29 / 2027-08-09: snapshots equal on all 78,609 rows (team: 1,052
  free agents, 1 loanee); injuries 126/126; competition seasons 1,379 rows, minutes higher on
  103, every one a season with an extra-time match (the old view caps at 90); awards 600
  season-pool and 100 All-Time entries, every entry resolved to a person_id (Lewandowski, whose tid is now a newgen's, to 1105-1988-08-21).
- Bucaspor 2023-04-01: snapshots equal on all 25,880 rows (171 free agents); injuries 60/60;
  competition seasons 1,041/1,041; 92 of 100 All-Time entries have a season (8 are from before
  the career).

## 16. Contracts and transfers
- **int**: contract reconstruction from snapshots (`last_seen` / `ended_by`), loan and staff
  spells.
- **mart**: `fact_contract`, `fact_transfer`, `fact_loan_spell`, `fact_staff_spell`, a
  squad-membership view.

**Check**: vs `mart.player_spells`, `mart.at_club_spells`, `mart.transfers`,
`mart.loan_out_spells`, `mart.squad_current` / `squad_on`; checks: transfer ↔ contract both ways,
contracted flag vs `contract_status`, "loaned out" code vs loan spells. Parsing the transfer band
first (TODO #3) gives real transfer dates instead of season-plus-snapshot bounds.

## 17. Move the site's marts
Each existing mart view rewritten over the `dim_*` / `fact_*` tables, one view per commit. Per
view: if the site can read a new table directly, the view goes; otherwise it becomes a thin shape
over the new tables. The compatibility views from steps 6–9 go as their last consumers move. The
one primary-position rule (TODO #21) lands here, since the depth chart and `data.js` switch to
the mart anyway.

**Check**: `git diff site/api` empty after `export_data.py`, every commit; `validate_mart.py`.

## 18. Retire and publish
Old views dropped; `fmq sql`, CLAUDE.md, `site/AGENTS.md` and `remote-duckdb-access.md` pointed at
the new tables, with the immersion rule scoped to the presentation layer; the published store and
the mart object rebuilt.

**Check**: site diffs clean; `publish_*` verify passes; size within the R2 budget.

---

# Part 3 — Shared

## Gates, every PR
The check fits what the step touches, and no step waits on a full rebuild:

| Step touches | Check | Time |
|---|---|---|
| extract only | `assert_identical.py` | ~35 s |
| mart / views only | copy the baseline store, `load_duckdb.py --refresh-only`, diff the changed views | ~1–2 min |
| extract + loader | re-extract the gate saves, load, diff the changed tables | ~3–4 min |

- **The gate saves**: `frem-2021-06-27` (day one, empty grids), `frem-2023-06-30` (season end),
  `frem-2023-07-02` (after the rollover, 0 matches), `frem-2026-03-28` (mid-season),
  `frem-2026-06-11` (the ground-truth save), `frem-2027-08-09` (newest); plus
  `bucaspor-2023-04-01` for the player-record steps (7–9). Both sides of a diff hold the same
  snapshots, because the views that read across snapshots depend on which exist.
- **The baseline is built once**: each step's branch store is the next step's old side.
- **Diffs are scoped and keyed**: `diff_stores.py` on the tables and views the step names, never
  a sweep of the whole store.
- **One full rebuild of both careers**, at step 18, run in the background; and the republish of
  the R2 copies happens there.
- `validate_mart.py` and `dbt test` on the gate store;
- a reviewed diff of `export_data.py` run against both gate stores (no-op unless the PR says
  why); `site/api` itself is committed only from a full store;
- `assert_identical.py` re-recorded with a note naming the files that changed and why;
- `run_tests.py`, and `test_boundary.py` in particular: extract imports neither duckdb nor
  fmstats, fmstats imports no fmparser.

## The checks report (from step 6)
Mismatches are reported, never fixed by the build:
- goal events vs the fixture-list score (the score is trusted);
- transfer ↔ contract, both ways;
- the save's contracted flag vs `contract_status`; the "loaned out" squad-status code vs loan
  spells;
- rebuilt league tables vs `club_league_history`; outcomes vs the roll of honour;
- the save's club and player record tables vs the derived records.

## Blockers
| TODO | Blocks | Why |
|---|---|---|
| Contract signed dates (unread training-row dates) | step 16 | exact end dates instead of snapshot bounds |

## Other TODOs this touches
| TODO | Relation |
|---|---|
| #3 transfer band | parse before step 16 for real transfer dates |
| #4 role names, training-row bytes | `dim_role` completeness; contract dates |
| #5 continent table | `dim_nation.continent` |
| #6, #8 competition rules | `dim_stage` progression and tie-breakers |
| #9 standings record | a check on derived outcomes |
| #11 season rollover | `dim_season` boundaries |
| #13 league tables outside Denmark | measured by step 14's check; stays open analysis |
| #17 views that hide their confidence | explicit int columns when those views move (steps 15–17) |
| #18 refit models on time-aligned rows | easier after step 15: fits read flagged, dated snapshots |
| #19 scripts failing at import | port straight onto the new marts after step 15 or 17 |
| #20 mart candidates left out on size | revisit after step 18 |
| #21 one primary-position rule | step 17 |
| #22 docs rewrite | coordinate with steps 5 and 18 |

## Risks
- **Query cost.** stg and int are views, and until step 17 the old mart reads the compatibility
  views many times. If a rebuild slows seriously, materialise that one int model and note why in
  its declaration; nothing downstream of the mart is affected either way.
- **Published stores.** `publish_duckdb.py` compacts tables only; a view over a compacted table's
  expansion view works (the scrapbook PR relies on it). Check the published copy with `fmq` after
  steps 4, 5 and 9 (read as published), and republish at 18.
- **Store size.** Whole tables (step 4) and the mart tables (13–16) grow the store; check against
  the R2 budget at step 18.

## Out of scope
- Naming unknown bytes; dumps carry `RAW` spans as they are today.
- New parsing: gaps the model names (referee link, call-ups, contract dates) stay TODO items.
- Analytics beyond the two models (role weights, ratings, home-grown rules): they move to read
  the new marts in step 17 but are not redesigned.
- Site changes beyond what moving the marts requires.

---

# Appendix — What was measured (extract steps)

Four saves from R2, both careers: `frem-2023-07-02` (0 matches), `frem-2027-08-08`,
`bucaspor-2022-05-25`, `bucaspor-2024-03-16`.

### Consumers of each extract output

| output / function | read by | verdict |
|---|---|---|
| `_period`, `auto_label`, `parse_label`, `_PHASES` | `load_duckdb.py` imports `parse_label` (old-style fallback in `resolve_season_phase`, the `--all` duplicate check) | remove, loader in the same PR |
| `summary.label_auto` / `label_source` | `staging.extracts.label_auto` (written, never read) | remove |
| `summary.latest_match` / `date_range` | `mart.snapshots.latest_match` / `is_preseason` (shown only by `fmq labels`); the loader's "replacing a newer snapshot" warning | remove; compare phase dates instead |
| `flatten_matches`, `player_match_stats.csv` | nothing (the loader reads `matches.json`) | remove |
| `players.csv` | nothing (decision 1) | remove |
| `_history_clubs` | decides which clubs enter `clubs.json` / `club_details.json` | replaced by the whole club table |
| `build_leagues` → `leagues.json` | `staging.leagues` → `mart.club_leagues`, `mart.clubs`, `mart.leagues`, `mart.competitions`, `export_data.py` | needed; derive in the mart from the whole tables |
| `leagues.json` `fixtures` | always 0 | dead |
| `leagues.json` `members` → `league_members source='members'` | nothing (the mart filters `source='club_league'`) | dead |
| `club_league.json` `league_name` | never loaded | dead |
| `league_label` → `players.league` | nothing (the mart names leagues from `staging.leagues`) | remove |
| `players.league_cid` | `v_player_rating_ranks` | take it from `mart.club_leagues` |
| `build_competitions` → `competitions.json` | `mart.competitions`, the uid lookup in `mart.py` | needed; dump the whole table |
| `competitions.matches_in_save` | nothing (`mart.competitions` counts games itself) | remove |
| `build_database` → `players.json`, `staff.json` | `staging.players_raw`, `staging.player_attributes_exact_raw`, `staging.staff_attributes` | steps 7–9 |

### What `build_database` joins and derives

From the person table, the player and staff attribute records, the formation catalog, the
contract grid, the training table's squad status, the three name tables + browse strings and the
club table: person ⋈ attributes on `sid`, ⋈ staff record on `id2`, ⋈ contract and status on tid;
the player/staff split on `sid == ffffffff`; the display name (common, then legal); the club
label and "Free agent"; `has_attributes`, `is_gk` (GK rating 20), `loaned_out` (status 65 with a
club), `wage_gbp` (units × 520, inside `scrape_contracts`); formation names from the catalog; the
attributes masked to `EXACT_SINGLE` with `estimated` flags (the one piece of attribute-model
knowledge in extract, and why it imports `fmparser.model`).

### Whole tables vs what extract emits today (frem-2027-08-08)

| | today | whole table |
|---|---|---|
| clubs (`clubs.json`) | 4,593 | 11,331 (every slot named) |
| competitions (`competitions.json`) | 4 (those in our matches) | 1,272 named |
| league ids from club records | 292 | 332, all resolved in the competition table |
| world fixtures | 20,721 (after `valid_clubs`) | 28,154 |

**`valid_clubs` silently drops 20–26% of world fixtures** on all four saves. The dropped rows
involve 609 clubs with no attributed players: the Spanish and Belgian reserve groups, and national
teams in World Cup / European Championship / Nations League qualifying. Against the whole club
table the filter drops nothing. The 40 extra leagues are mostly national-team competitions
(`type_7`, `type_11`, `type_28`) and deep regional leagues.

### Labels vs header dates

For **20 of 37 manifest rows** the file name's date is not the header date: the older names came
from the last match date (`frem-2023-07-01.fms` has header 2023-06-30, `frem-2027-08-08.fms`
2027-08-09, `fm_save1.fms` no date). On every row `save_file == label + ".fms"`. `HDR.campaign`
returns `None` for a match-less save dated before the rollover, which is why `rebuild.py` passes
`--season`/`--phase` explicitly.

### Table order in the save

Identical on all four saves, both careers (offsets on frem-2027-08-08): browse names ~0, person
info 572,042, player attributes 3,977,039, staff attributes 6,044,441, officials 6,248,956, rounds
6,310,546, clubs 6,320,674, competitions 12,600,228, nations 12,749,322, stadiums 12,789,152,
cities 13,464,805, currencies 13,958,548, languages 13,969,165, rule files 16,704,215, contracts
29,170,756, match slots 38,530,164, surnames / first names / nicknames 38,629,745, history
41,109,871, club records 45,356,645, player progress 46,848,304, training 51,974,540, matches
54,142,250 (empty on a 0-match save), player lists 59,271,525, then the zstd archive (fixtures,
competition rules) at the tail.

Locators take 0.0–0.7 s each; history 2.7 s on its first run. The case for a cursor is simplicity
and robustness, not speed. Five modules already chain to their predecessor (clubs after rounds,
competitions after clubs, staff after player attributes, club records after history, training
after player progress): "starts right after" rules, stronger than a lower bound.
