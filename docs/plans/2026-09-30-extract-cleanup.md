# Extract clean-up: extract dumps tables, the store does the joins (2026-09-30)

> **Goal:** `extract.py` becomes a flat list of `dump(TABLE.scrape(mm))` steps in the save's
> own table order: every table as the save stores it, one file each, with no joins, no
> lookups, no label rules and no derived columns. Every join and derivation moves into the
> store as SQL. This is TODO #12, plus the date and label code left over from before the
> save header gave us the exact in-game date.

Merged from two plans written the same day: the `extract.py` clean-up (labels, dead
outputs, whole reference tables, file-order cursor, with the measurements below) and the
`build_database` decoupling that followed the scrapbook PR (`squad.py` retired, our
squad's exact values picked in the store).

## The pattern

The scrapbook PR (`staging.players` a view over `staging.players_raw` plus
`staging.squad_scrapbook`) is the template for every phase that moves a join:

1. extract dumps the table(s) as stored; the loader writes each to its own `staging` table;
2. the join or derivation extract used to do becomes a `staging` VIEW with the same name and
   columns as the table it replaces, so the mart, `fmq`, the scout and the exporter are
   untouched. Where the output is a new analytical fact (leagues, club leagues), it is a
   `mart` view instead;
3. the gate is row-for-row: the new store equals a store built from `main` on every save of
   both careers, every column, each difference zero or explained in the PR.

The loader writes the `staging` views for now; moving them into `fmstats` is TODO #12's
separate "move the loader's remaining transforms" step, done once, after this plan.

## Decisions (Zac, 2026-09-30)

1. **`players.csv` is dead**: the outside squad-comparison tool no longer reads it. PR 2
   deletes it.
2. **Rename the saves to their header dates** before PR 1 drops the label rules, so every
   save's name, label and `phase` are the same string again.
3. **Write the whole club table** (11,331 clubs) and the whole competition table. Any
   filtering (the site's club list) is a view in the store, not a choice extract makes.
4. **Migrate older stores**: each phase that drops or renames a column or table ships a
   migration (like `load_duckdb._raw_tables`), not NULL columns and not "needs a rebuild".

## What was measured

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
| `build_database` → `players.json`, `staff.json` | `staging.players_raw`, `staging.player_attributes_exact_raw`, `staging.staff_attributes` | phases 5-7 |

### What `build_database` joins and derives

From the person table, the player and staff attribute records, the formation catalog, the
contract grid, the training table's squad status, the three name tables + browse strings
and the club table: person ⋈ attributes on `sid`, ⋈ staff record on `id2`, ⋈ contract and
status on tid; the player/staff split on `sid == ffffffff`; the display name (common, then
legal); the club label and "Free agent"; `has_attributes`, `is_gk` (GK rating 20),
`loaned_out` (status 65 with a club), `wage_gbp` (units × 520, inside `scrape_contracts`);
formation names from the catalog; the attributes masked to `EXACT_SINGLE` with `estimated`
flags (the one piece of attribute-model knowledge in extract, and why it imports
`fmparser.model`).

### Whole tables vs what extract emits today (frem-2027-08-08)

| | today | whole table |
|---|---|---|
| clubs (`clubs.json`) | 4,593 | 11,331 (every slot named) |
| competitions (`competitions.json`) | 4 (those in our matches) | 1,272 named |
| league ids from club records | 292 | 332, all resolved in the competition table |
| world fixtures | 20,721 (after `valid_clubs`) | 28,154 |

**`valid_clubs` silently drops 20–26% of world fixtures** on all four saves. The dropped rows
involve 609 clubs with no attributed players: the Spanish and Belgian reserve groups, and
national teams in World Cup / European Championship / Nations League qualifying. Against
the whole club table the filter drops nothing. The 40 extra leagues are mostly
national-team competitions (`type_7`, `type_11`, `type_28`) and deep regional leagues.

### Labels vs header dates

For **20 of 37 manifest rows** the file name's date is not the header date: the older names
came from the last match date (`frem-2023-07-01.fms` has header 2023-06-30,
`frem-2027-08-08.fms` 2027-08-09, `fm_save1.fms` no date). On every row
`save_file == label + ".fms"`. `HDR.campaign` returns `None` for a match-less save dated
before the rollover, which is why `rebuild.py` passes `--season`/`--phase` explicitly.

### Table order in the save

Identical on all four saves, both careers (offsets on frem-2027-08-08): browse names ~0,
person info 572,042, player attributes 3,977,039, staff attributes 6,044,441, officials
6,248,956, rounds 6,310,546, clubs 6,320,674, competitions 12,600,228, nations 12,749,322,
stadiums 12,789,152, cities 13,464,805, currencies 13,958,548, languages 13,969,165, rule
files 16,704,215, contracts 29,170,756, match slots 38,530,164, surnames / first names /
nicknames 38,629,745, history 41,109,871, club records 45,356,645, player progress
46,848,304, training 51,974,540, matches 54,142,250 (empty on a 0-match save), player lists
59,271,525, then the zstd archive (fixtures, competition rules) at the tail.

Locators take 0.0–0.7 s each; history 2.7 s on its first run. The case for a cursor is
simplicity and robustness, not speed. Five modules already chain to their predecessor
(clubs after rounds, competitions after clubs, staff after player attributes, club records
after history, training after player progress): "starts right after" rules, stronger than a
lower bound.

## PRs

### 0. The store diff tool
`scripts/audit/diff_stores.py OLD.duckdb NEW.duckdb --table staging.players --key
season,phase,tid`: per-column counts of differing rows, rows only in one store, examples.
Every later gate is one command against a store built from `main`. The comparison script
from the scrapbook PR is the starting point. Small; can ride with PR 2.

### 1. Header dates only: rename the saves, drop labels and match dates
**Saves (decision 2)**: rename the 20 saves whose name is not their header date, in every
place the name lives: the `.fms` and `.gz` in `$FM_SAVES_DIR`, the R2 objects, the manifest,
`staging.extracts.save_path` / `label` in the store, and the saved scouts' keys.
`scripts/canonicalise_names.py` (deleted; restore from git) did exactly this set once.
`fm_save1.fms` gets its header date or moves to `unfiled/`.

**extract.py**
- Delete `_period`, `auto_label`, `parse_label`, `_PHASES` and the `--label` default logic;
  the output folder is the save's name without `.fms`.
- `season_phase` uses the header date only; an unreadable header is a hard failure.
- `HDR.campaign`: a match-less save before the rollover belongs to the next campaign
  (`frem-2021-07-01` → 2022), so the summary always carries a season.
- The summary drops `label_auto`, `label_source`, `latest_match`, `date_range`.

**load_duckdb.py**
- Drop `from extract import parse_label` (the loader's only import from `extract`).
- `resolve_season_phase`: override, else summary, else fail loudly; the `--all` duplicate
  check keys on the summary's season/phase; the "replacing a newer snapshot" warning
  compares phase dates.
- Stop writing `label_auto`, `latest_match`, `date_from`, `date_to`; a migration drops them
  from older stores (decision 4).

**mart / fmq**: remove `latest_match` and `is_preseason` from `mart.snapshots` and
`fmq labels`; a "last match" date, if ever wanted, comes from `staging.matches`.

**scripts/rebuild.py**: stop passing `--label`, `--season`, `--phase`; after each extract,
compare the summary's season/phase with the manifest row and fail loudly on a mismatch
(`--trust-manifest` forces the manifest values).

**Docs**: the `import-fm-saves` skill (reads `label_auto`, `latest_match`, `date_range`),
`CLAUDE.md`, `README.md`, `docs/agent-context/etl-duckdb-dashboard.md`.

**Check**: `assert_identical --record --note` (summary.json changes); a full `rebuild.py
--career frem` with the manifest check passing on every row.

### 2. Delete dead outputs
`players.csv`, `player_match_stats.csv`, `flatten_matches`, `write_players_csv`,
`write_match_stats_csv`, `_STAT_FIELDS`, the `csv` import and the `player_match_lines`
count; fix the module docstring (it still lists `transfers.json` and the old label rule).
**Check**: re-record; exactly two fewer files, every other file byte-identical.

### 3. Whole reference tables (clubs, competitions, fixtures)
**extract.py**
- `clubs.json` = the whole club table, every slot, with `club_details.json` merged in.
- `competitions.json` = the whole competition table; the rule files' team counts get their
  own file (`competition_team_counts.json`, uid → teams).
- Delete `leagues.json`, `club_league.json`, `build_leagues`, `league_label`,
  `build_competitions`, `_history_clubs`, `build_database`'s `club_ids` / `club_names` /
  `club_leagues` loop and the league stamping on each player. Player `club` labels come
  from the whole table.
- `FIX.fixtures(mm)` without `valid_clubs` (drop the parameter).

**load_duckdb.py**: `staging.clubs` and `staging.club_details` both load from `clubs.json`;
`staging.competitions` loads the whole table (no `matches_in_save`); stop loading
`staging.leagues` and `staging.league_members` (migration drops them);
`v_player_rating_ranks` takes `league_cid` from `mart.club_leagues`.

**fmstats/mart.py**: `mart.club_leagues` takes the league id off the club table (same
as-at logic) and name, reputation, type from `staging.competitions`, nation via
`nation_id`; `mart.leagues` is the competitions some club plays in, `member_count`
counted; `mart.competitions` drops the `lg` merge; the site's club list keeps its current
scope through a view (decision 3).

**Risks**: `mart.clubs` grows from ~4.6k to ~11.3k rows per snapshot; 292 → 332 leagues can
shift the tier derivation and the league ladder (likely a filter to league types);
`world_fixtures` gains ~7k rows per save, so `mart.league_tables` and everything on fixtures
must still key on the right competitions.

**Check**: `diff_stores` on the existing rows of `mart.clubs`, `mart.leagues`,
`mart.club_leagues`, `mart.competitions`, `mart.league_tables`; `validate_mart.py`; a
reviewed `git diff site/api`; `assert_identical` re-record. Then delete the `clubs_comps`
lookups nothing uses (`club_record`, `resolve_club`, `league_name`, `comp_detail`,
`club_details`); `discover_career.py` and the tests and audits that used them read the
tables directly.

### 4. Contracts and squad status
- extract dumps `contracts.json` (every used slot of the grid as stored: marker, wage units,
  dates) and adds `contracted` / `squad_status` to `training.json`'s rows;
- `wage_gbp` stops being computed in `scrape_contracts`; `WAGE_GBP_PER_UNIT` goes to the
  store;
- `staging.players_raw` takes the contract and status columns from those tables.

The smallest of the `build_database` phases; it proves the view-over-view chain first.

### 5. Names
- extract dumps the three name id-tables and the browse strings (`names.json`) and the
  person table's name ids;
- the display name (common name, then first + last) is a view (TODO #12's `person_names`);
- `clubs_comps.build_name_resolver` / `resolve_name` / `resolve_common_name` go.

### 6. Person, player and staff records
- extract dumps `persons.json` (the person table as stored), `player_attributes.json` (the
  attribute record keyed by `sid`: all 34 attribute bytes, positions, CA/PA, the tail) and
  `staff_attributes.json` (keyed by `id2`, formation indices), plus the formation catalog;
- `staging.players_raw` and `staging.player_attributes_exact_raw` become views over them:
  the `sid` / `id2` joins, the player/staff split, `has_attributes`, `is_gk`, `loaned_out`
  and the `EXACT_SINGLE` masking;
- `build_database` is deleted.

**Name clashes to settle first**: `staging.persons` (the identity bridge),
`staging.player_records` (club records) and `staging.player_attributes` (the decoded view)
are taken; name the new tables by what they are (`staging.person_records`,
`staging.attribute_records`, `staging.staff_records`).

### 7. Cleanup
- move `clubs_comps.info_offset` (used by `tables/player_attributes.py`) into
  `tables/person_info.py` and delete `clubs_comps.py`;
- the other TODO #12 items: delete `staging.standings` and its loader code, and
  `staging.player_history`'s constant `confidence` / `origin_club` columns.

### 8. Save order + cursor
- `main()` becomes a flat list of steps `(name, scrape, dump)` in the file order above, the
  archive tables last.
- Each locator gains an optional `lo=0`; audit scripts keep calling it without one. Cursor =
  the end of the previous table's spans; an empty table (matches on a 0-match save) leaves
  it where it was. On a miss, raise an error naming the table, the cursor and the previous
  table; `--no-cursor` re-runs every locator from 0.
- Keep the five "starts right after" chains; the cursor is only a lower bound for the rest.
- Test: locator starts only go up on the test saves, both careers.

**Check**: `assert_identical` byte-identical (only the order of `dump()` calls changes).

## Gates, every PR
- `diff_stores.py` on every changed `staging` / `mart` name, every save of both careers;
- `validate_mart.py` on a full rebuild, and a reviewed `git diff site/api` (no-op unless the
  PR says why);
- `assert_identical.py` re-recorded with a note naming the files that changed and why;
- `run_tests.py`, and `test_boundary.py` in particular: extract imports neither duckdb nor
  fmstats.

## Risks across the plan
- **Query cost.** `staging.players` becomes a view over several joins and the mart reads it
  many times. If a rebuild or `fmq` slows noticeably, the loader materialises `players_raw`
  at load time (`CREATE TABLE AS` over the raw tables) and keeps the view definitions as
  the tested source of truth.
- **Published stores.** `publish_duckdb.py` compacts tables only; a view over a compacted
  table's expansion view works (the scrapbook PR relies on it). Check the published copy
  with `fmq` after PRs 3 and 6.

## Out of scope
- Moving the views from `load_duckdb.py` into `fmstats` (TODO #12's next bullet).
- Naming unknown bytes; the dumps carry `RAW` spans as they are today.
