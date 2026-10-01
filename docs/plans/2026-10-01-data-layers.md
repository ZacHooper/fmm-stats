# Data layers: extract dumps tables, the store models them (2026-10-01)

> **Status (2026-10-01): in progress. Done: steps 1 and 3.**
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

stg, int and mart are T-layer code in one package, `fmstats/models/`, with a sub-module per layer
and per area. It reads the store only, so `tests/test_boundary.py` covers it unchanged.

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
| 5 | Rename `staging` → `raw` | layers | `git diff site/api` empty; R2 copy republished |
| 6 | The models framework, and the loader's views moved into it | layers | every moved view equals its old self row-for-row |
| 7 | Contracts and squad status | both | `diff_stores` on the players compatibility view |
| 8 | Names | both | same |
| 9 | Person, player and staff records; `build_database` deleted | both | same |
| 10 | Extract cleanup | extract | `run_tests.py`; `assert_identical` re-recorded |
| 11 | Save order and the cursor | extract | `assert_identical` byte-identical |
| 12 | stg for every raw table | layers | each stg row count equals its source |
| 13 | Reference, nation, club | layers | vs `mart.clubs`, `mart.our_clubs` |
| 14 | Competition and match | layers | vs `mart.club_matches`, `match_stages`, `league_tables`, `match_player_facts` |
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
- `fmstats/store.py`'s view re-creation on cached copies must handle an older published store
  that still says `staging` (alias, or refuse with a message to refresh).

**Check**: `git diff site/api` empty; `validate_mart.py`, `run_tests.py` pass; the R2 copy and the
mart object republished, and `fmq` run against them.

## 6. The models framework, and the loader's views moved into it
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
- extract dumps `persons.json` (the person table as stored), `player_attributes.json` (the
  attribute record keyed by `sid`: all 34 attribute bytes, positions, CA/PA, the tail) and
  `staff_attributes.json` (keyed by `id2`, formation indices), plus the formation catalog;
- stg models over each; int does the `sid` / `id2` joins, the player/staff split,
  `has_attributes`, `is_gk`, `loaned_out` and the `EXACT_SINGLE` masking; the players and
  exact-attributes compatibility views read int;
- `build_database` is deleted, and with it extract's import of `fmparser.model`.

**Name clashes to settle first**: `persons` (the identity bridge), `player_records` (club records)
and `player_attributes` (the decoded view) are taken; name the new raw tables by what they are
(`raw.person_records`, `raw.attribute_records`, `raw.staff_records`).

**Checks for 7–9**: `diff_stores` on the players and exact-attributes compatibility views, every
save of both careers; `assert_identical` re-recorded with the new files named.

## 10. Extract cleanup
- move `clubs_comps.info_offset` (used by `tables/player_attributes.py`) into
  `tables/person_info.py` and delete `clubs_comps.py`;
- drop `raw.player_history`'s constant `confidence` / `origin_club` columns (migration).

## 11. Save order and the cursor
- `main()` becomes a flat list of steps `(name, scrape, dump)` in file order (appendix), the
  archive tables last.
- Each locator gains an optional `lo=0`; audit scripts keep calling it without one. Cursor = the
  end of the previous table's spans; an empty table (matches on a 0-match save) leaves it where it
  was. On a miss, raise an error naming the table, the cursor and the previous table;
  `--no-cursor` re-runs every locator from 0.
- Keep the five "starts right after" chains; the cursor is only a lower bound for the rest.
- Test: locator starts only go up on the test saves, both careers.

**Check**: `assert_identical` byte-identical (only the order of `dump()` calls changes).

## 12. stg for every raw table
One stg model per raw table still without one: rename to the model's vocabulary, cast, decode
codes to names where the code table is in the store, attach `person_id` where a `tid` appears,
drop unused slots (`tid = 0xffffffff` and the like). No joins across sources.

**Check**: each stg row count equals its raw source minus the documented drops.

## 13. Reference, nation, club
- **int**: club ↔ team via `main_club_tid` (national sides are club-shaped in the first slots,
  `club_type = national`); snapshot dedupe for slowly changing club data.
- **mart**: `dim_position`, `dim_role`, `dim_city`, `dim_stadium`, `dim_nation`,
  `fact_nation_snapshot`, `dim_club`, `dim_team`, `fact_club_snapshot` (facilities, academy,
  status, attendance, colours and kits, finances, affiliates), `fact_team_snapshot` (reputation,
  assumed per team).

**Check**: vs `mart.clubs`; first team ↔ reserves matches `mart.our_clubs`; `careers.py`'s
hardcoded `reserve_tid` can now be read from `dim_team`.

## 14. Competition and match
- **int**: match identity across snapshots (the latest-phase rule), stage and round labelling from
  the rules members, outcome derivation.
- **mart**: `dim_competition`, `dim_stage`, `dim_round`, `dim_match` (every match in the world,
  `has_detail` for ours), `fact_team_match` (score from the world fixture list),
  `fact_player_match`, `fact_match_event`, `fact_participation`, `fact_competition_outcome`;
  views `standings`, `tie_results`.

**Check**: vs `mart.club_matches`, `mart.match_stages`, `mart.match_player_facts`;
`mart.league_tables` for **Denmark only** (other countries are open analysis, TODO #13); checks:
events vs score, rebuilt tables vs `club_league_history`, outcomes vs the roll of honour.
**Blocked by** TODO #16 (extra-time minutes); settle how two-legged ties are stored first.

## 15. Person and the two models
- **int**: person identity (`person_id` = `<tid>-<dob>`, built across **every** snapshot so a
  retired player whose slot has gone to a newgen keeps his history), `int_player_attributes` (exact where stored, estimated otherwise,
  with the rule for when an old exact entry gives way to the estimate), `int_player_value`
  (coefficients moved from `fmstats/value_model.py` to a raw seed), seasons unioned across
  snapshots.
- **mart**: `dim_person`, `fact_player_snapshot` (attributes and positions, hidden attributes,
  CA/PA, value, reputation, team, training, nationality, languages, `contract_status`, provenance
  flags), `fact_staff_snapshot`, `fact_injury_spell`, `fact_player_season`, `dim_award`,
  `fact_player_award` (from `raw.player_scrapbook`, lists 0–30 and 62/64).

**Check**: vs `mart.player_snapshots`, `mart.player_value_est`, `mart.injury_spells`,
`mart.player_seasons`, `mart.player_career_seasons`. **Blocked by** TODO #14 (person identity) and
#15 (history reclamation).

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
- `diff_stores.py` on every changed table or view, every save of both careers;
- `validate_mart.py` (and `validate_models.py` from step 6) on a full rebuild;
- a reviewed `git diff site/api` (no-op unless the PR says why);
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
| #14 Person identity | step 15 | `dim_person` keys everything |
| #15 History lost to reclamation | step 15 | `fact_player_season` unions history across snapshots |
| #16 Extra-time minutes | step 14 | `fact_player_match.minutes` |
| Two-legged ties: one round or two? | step 14 | how `tie_results` groups |
| Reputation per team or per club | step 13 | modelled per team; moves if the save says otherwise |
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
  steps 4, 5, 9 and 18.
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
