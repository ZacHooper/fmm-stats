# Extract dumps tables; the store does the joins

> **Goal:** `extract.py` becomes a list of `dump(TABLE.scrape(mm))` calls: every table as the
> save stores it, one file each, with no joins, no lookups and no derived columns. Every join
> and derivation moves into the store as SQL, behind the `staging` names consumers already
> read, so no mart view, `fmq` command, scout or exporter changes. This is TODO #12.

## The pattern

The scrapbook move (`staging.players` over `staging.players_raw` plus
`staging.squad_scrapbook`) is the template for every phase:

1. extract dumps the table(s) as stored; the loader writes each to its own `staging` table;
2. the join or derivation that extract used to do becomes a `staging` VIEW with the same
   name and columns as the table it replaces, so every reader is untouched;
3. the gate is row-for-row: the new store's view equals the old store's table on every save
   of both careers, every column, and each difference is either zero or explained.

The loader writes the views for now; moving them into `fmstats` is TODO #12's separate
"move the loader's remaining transforms" step, done once, after this plan.

## What extract pre-joins today

| output | built from | joins / derivations it does | replaced by |
|---|---|---|---|
| `players.json`, `staff.json` (`build_database`) | person table, player attribute records, staff attribute records + formation catalog, contract grid, training table's squad status, the three name tables + browse strings, club table | person ⋈ attributes on `sid`, ⋈ staff record on `id2`, ⋈ contract and status on tid; player/staff split on `sid == ffffffff`; display name (common, then legal); club label and "Free agent"; `has_attributes`, `is_gk` (GK rating 20), `loaned_out` (status 65 with a club), `wage_gbp` (units × 520, in `scrape_contracts`); formation names from the catalog; attributes masked to `EXACT_SINGLE` with `estimated` flags | phases 1-3 |
| `clubs.json` | club table | only the clubs some player, match or history chain names (`_history_clubs`) | phase 4: the whole table |
| `club_details.json` | club table | only clubs in `clubs.json` | phase 4: the whole table |
| `club_league.json`, `leagues.json` (`build_leagues`) | club table, competition table, nations | club → league; league name, nation name, member list and count | phase 4: views |
| `competitions.json` (`build_competitions`) | competition table, rule files, matches | only competitions our matches name; `num_teams` from the rule files; `matches_in_save` | phase 4: the whole table + a view |
| `player_match_stats.csv` (`flatten_matches`) | matches | one row per (match, player) | phase 5: the loader reads `matches.json` |
| `players.csv` | `players.json` | a convenience copy | phase 5: drop |

## Phases (one PR each)

### 0. A store diff tool
`scripts/audit/diff_stores.py OLD.duckdb NEW.duckdb --table staging.players --key
season,phase,tid`: per-column counts of rows that differ, rows only in one store, and
examples. Every later gate is then one command against a store built from `main`. The
comparison script written for the scrapbook PR is the starting point.

### 1. Contracts and squad status
- extract dumps `contracts.json` (every used slot of the grid, as stored: marker, wage units,
  dates) and adds `contracted` / `squad_status` to `training.json`'s rows;
- `wage_gbp` stops being computed in `scrape_contracts`; `WAGE_GBP_PER_UNIT` goes to the store;
- `staging.players_raw` takes the contract and status columns from those tables (a view
  over `players_raw`'s remaining table plus the two new ones).

Smallest phase, and it proves the view-over-view chain before the big one.

### 2. Names
- extract dumps the three name id-tables and the browse strings (`names.json`) and the
  person table's name ids;
- the display name (common name, then first + last) is a view (TODO #12's `person_names`);
- `clubs_comps.build_name_resolver` / `resolve_name` / `resolve_common_name` go.

### 3. Person, player and staff records
- extract dumps `persons.json` (the person table as stored), `player_attributes.json` (the
  attribute record, keyed by `sid`, all 34 attribute bytes, positions, CA/PA, the tail) and
  `staff_attributes.json` (keyed by `id2`, formation indices) plus the formation catalog;
- `staging.players_raw` and `staging.player_attributes_exact_raw` become views over them:
  the `sid` / `id2` joins, the player/staff split, `has_attributes`, `is_gk`, `loaned_out`,
  and the `EXACT_SINGLE` masking (the one piece of attribute-model knowledge in extract,
  and the reason it imports `fmparser.model`);
- `build_database` is deleted.

**Name clashes to settle first:** `staging.persons` (the identity bridge),
`staging.player_records` (club records) and `staging.player_attributes` (the decoded view)
are taken. Suffix the new tables `_table` or rename by what they are
(`staging.person_records`, `staging.attribute_records`, `staging.staff_records`).

### 4. Clubs and competitions, whole
- `clubs.json`, `club_details.json` and a `competitions.json` of the whole competition
  table (every club and competition, not the subset something names), plus the rule files'
  team counts;
- `staging.clubs`, `club_details`, `club_league`, `leagues` and `competitions` keep their
  names as views where they are now filtered or joined;
- `_history_clubs`, `build_leagues`, `build_competitions`, `league_label` and the
  `clubs_comps` lookups (`club_record`, `resolve_club`, `league_name`, `comp_detail`,
  `club_details`) go. Their remaining users are `discover_career.py` and a few tests and
  audits, which read the tables directly instead.

### 5. Cleanup
- the loader flattens `matches.json` into `staging.match_player_stats`; drop
  `player_match_stats.csv`, `players.csv` and `write_players_csv`;
- move `clubs_comps.info_offset` (used by `tables/player_attributes.py`) into
  `tables/person_info.py` and delete `clubs_comps.py`;
- the other TODO #12 items: delete `staging.standings` and its loader code, and
  `staging.player_history`'s constant `confidence` / `origin_club` columns.

## Gates, every phase
- `diff_stores.py` on the changed `staging` names: every save of both careers, zero
  differences or each one explained in the PR;
- `validate_mart.py` on a full rebuild, and a no-op `git diff site/api` after
  `export_data.py`;
- `assert_identical.py` re-recorded with a note naming the files that changed and why;
- `run_tests.py`, and `test_boundary.py` in particular: extract must still import neither
  duckdb nor fmstats.

## Risks
- **Query cost.** `staging.players` becomes a view over several joins and the mart reads it
  many times. If a rebuild or `fmq` slows noticeably, the loader materialises
  `players_raw` at load time (`CREATE TABLE AS` over the raw tables) and keeps the view
  definitions as the tested source of truth.
- **Published stores.** `publish_duckdb.py` compacts TABLES only and leaves views; a view
  over a compacted table's expansion view works (the scrapbook PR relies on it). Check
  the published copy with `fmq` after phase 3.
- **Old stores.** Each phase renames or drops a table a store already has; each needs a
  migration like `_raw_tables`, or a note that the phase needs a rebuild.

## Out of scope
- Moving the views from `load_duckdb.py` into `fmstats` (TODO #12's next bullet).
- Naming unknown bytes; the dumps carry `RAW` spans as they are today.
