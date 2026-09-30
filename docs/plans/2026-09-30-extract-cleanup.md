# extract.py clean-up plan (2026-09-30)

`extract.py` still carries code from before the save header gave us the exact in-game date,
and from before the club and competition tables were walked whole. This plan removes that
code in four PRs, then moves extract towards a one-pass read in file order.

It runs alongside the `squad.py` clean-up in another session, which is expected to retire
`build_database`'s exact/estimated attribute join (the join moves to the mart). PRs 1–3 touch
`build_database` only where noted. PR 4 waits for that session to merge.

## What was measured

Four saves from R2, both careers: `frem-2023-07-02` (0 matches), `frem-2027-08-08`,
`bucaspor-2022-05-25`, `bucaspor-2024-03-16`.

### Consumers of each extract output

| output / function | read by | verdict |
|---|---|---|
| `_period`, `auto_label`, `parse_label`, `_PHASES` | `load_duckdb.py:33` imports `parse_label` (old-style fallback in `resolve_season_phase`, the `--all` duplicate check at ~2223) | remove, loader in the same PR |
| `summary.label_auto` / `label_source` | `staging.extracts.label_auto` (written, never read) | remove |
| `summary.latest_match` / `date_range` | `mart.snapshots.latest_match` / `is_preseason` (shown only by `fmq labels`); loader's "replacing a newer snapshot" warning | remove; compare phase dates instead |
| `flatten_matches`, `player_match_stats.csv` | nothing (loader reads `matches.json`; `_crosscheck` compares only players/staff/matches) | remove |
| `players.csv` | nothing in the repo; `docs/agent-context/squad-comparison-bridge.md` describes an outside tool reading it | remove once that tool is confirmed dead |
| `_history_clubs` | decides which clubs enter `clubs.json` / `club_details.json` | replaced by dumping the whole club table |
| `build_leagues` → `leagues.json` | `staging.leagues` → `mart.club_leagues`, `mart.clubs`, `mart.leagues`, `mart.competitions`, `export_data.py` | output needed; derive in the mart from the whole tables |
| `leagues.json` `fixtures` | always 0 | dead |
| `leagues.json` `members` → `league_members source='members'` | nothing (mart filters `source='club_league'`) | dead |
| `club_league.json` `league_name` | never loaded | dead |
| `league_label` → `players.league` | nothing (mart names leagues from `staging.leagues`) | remove |
| `players.league_cid` | `v_player_rating_ranks` (`load_duckdb.py:825`) | take it from `mart.club_leagues` instead |
| `build_competitions` → `competitions.json` | `mart.competitions`, uid lookup at `mart.py:962` | output needed; dump the whole table |
| `competitions.matches_in_save` | nothing (`mart.competitions` counts `fx.games` itself) | remove |

### Whole tables vs what extract emits today (frem-2027-08-08)

| | today | whole table |
|---|---|---|
| clubs (`clubs.json`) | 4,593 | 11,331 (every slot named) |
| competitions (`competitions.json`) | 4 (those in our matches) | 1,272 named |
| league ids from club records | 292 | 332, all resolved in the competition table |
| world fixtures | 20,721 (after `valid_clubs`) | 28,154 |

`clubs_comps.club_record` / `comp_detail` / `league_name` are thin lookups over
`scrape_clubs` / `scrape_competitions`, so the data is already parsed; extract only filters.

**`valid_clubs` silently drops 20–26% of world fixtures** on all four saves (e.g. 28,154 →
20,721). The dropped rows involve 609 clubs with no attributed players: the Spanish and Belgian
reserve groups, and national teams in World Cup / European Championship / Nations League
qualifying. Against the whole club table the filter drops nothing.

The 40 extra leagues are mostly national-team competitions (`type_7`, `type_11`, `type_28`)
and deep regional leagues (Spanish Primera Andaluza, Italian Promozione, NPSL regions).

### Labels vs header dates

For **20 of 37 manifest rows** the file name's date is not the header date. The older names
came from the last match date (`frem-2023-07-01.fms` has header 2023-06-30,
`frem-2027-08-08.fms` has 2027-08-09, `fm_save1.fms` has no date). On every row
`save_file == label + ".fms"`, so the save file's name is already the label.

`HDR.campaign` returns `None` for a match-less save dated before the rollover (a new career's
first save). That is why `rebuild.py` passes `--season`/`--phase` explicitly.

### Table order in the save

Identical sequence on all four saves, both careers (Frem offsets shown):

| table | start (frem-2027-08-08) |
|---|---|
| browse names | ~0 |
| person info | 572,042 |
| player attributes | 3,977,039 |
| staff attributes | 6,044,441 |
| officials | 6,248,956 |
| rounds | 6,310,546 |
| clubs | 6,320,674 |
| competitions | 12,600,228 |
| nations | 12,749,322 |
| stadiums | 12,789,152 |
| cities | 13,464,805 |
| currencies | 13,958,548 |
| languages | 13,969,165 |
| rule files | 16,704,215 |
| contracts | 29,170,756 |
| match slots | 38,530,164 |
| surnames / first names / nicknames | 38,629,745 |
| history | 41,109,871 |
| club records | 45,356,645 |
| player progress | 46,848,304 |
| training | 51,974,540 |
| matches | 54,142,250 (empty on a 0-match save) |
| player lists | 59,271,525 |
| zstd archive (fixtures, competition rules) | tail |

Locators take 0.0–0.7 s each; history took 2.7 s on its first run. The case for the cursor is
simplicity and robustness, not speed.

Five modules already chain to their predecessor internally: clubs after rounds, competitions
after clubs, staff after player attributes, club records after history, training after player
progress. These are "starts right after" rules, which are stronger than a lower bound.

## PR 1 — dates only: no labels, no match dates

**extract.py**
- Delete `_period`, `auto_label`, `parse_label`, `_PHASES` and the `--label` default logic.
- Output folder = the save file's name without `.fms` (see decision 2).
- `season_phase` uses the header date only; an unreadable header is a hard failure (no
  latest-match fallback).
- `HDR.campaign`: a match-less save before the rollover belongs to the next campaign
  (`frem-2021-07-01` → 2022) instead of `None`, so the summary always carries a season.
- Summary drops `label_auto`, `label_source`, `latest_match`, `date_range`.
- `scrape_matches` no longer has to run before the output folder exists.

**load_duckdb.py**
- Drop `from extract import parse_label` (the loader's only import from `extract`).
- `resolve_season_phase`: override, else summary, else fail loudly.
- `--all` duplicate check keys on the summary's season/phase.
- "Replacing a newer snapshot" warning compares phase dates.
- Stop writing `label_auto`, `latest_match`, `date_from`, `date_to` in `staging.extracts`
  (see decision 4).

**mart / fmq**: remove `latest_match` and `is_preseason` from `mart.snapshots` and `fmq labels`.
If a "last match" date is ever wanted, derive it from `staging.matches`.

**scripts/rebuild.py**
- Stop passing `--label`, `--season`, `--phase`.
- After each extract, compare the summary's season/phase with the manifest row. Fail loudly on
  a mismatch; `--trust-manifest` forces the manifest values.

**Docs**: `.claude/skills/import-fm-saves/SKILL.md` (reads `label_auto`, `latest_match`,
`date_range`), `CLAUDE.md`, `README.md`, `docs/agent-context/etl-duckdb-dashboard.md`.

**Check**: `assert_identical.py --record --note` (summary.json changes); a full
`rebuild.py --career frem` in which the manifest check passes on every row.

## PR 2 — delete dead outputs

- Delete `players.csv`, `player_match_stats.csv`, `flatten_matches`, `write_players_csv`,
  `write_match_stats_csv`, `_STAT_FIELDS`, the `csv` import and the `player_match_lines` count.
- Fix the module docstring (it still lists `transfers.json` and the old label rule).

**Check**: re-record; exactly two fewer files, every other file byte-identical.

## PR 3 — whole reference tables (the clubs + competitions part of TODO #12)

**extract.py**
- `clubs.json` = the whole club table, every slot, with `club_details.json` merged in (one
  table, one file).
- `competitions.json` = the whole competition table (`scrape_competitions`).
- `rule_files.team_counts` gets its own file (`competition_team_counts.json`, uid → teams); the
  mart joins it on uid.
- Delete `leagues.json`, `club_league.json`, `build_leagues`, `league_label`,
  `build_competitions`, `_history_clubs`, the `club_ids` / `club_names` / `club_leagues` loop in
  `build_database`, and the league stamping on each player. Player `club` / `parent_club`
  labels read from the whole table.
- `FIX.fixtures(mm)` without `valid_clubs`; drop the parameter.

**load_duckdb.py**
- `staging.clubs` and `staging.club_details` both load from the one `clubs.json`.
- `staging.competitions` loads the whole table; drop `matches_in_save`.
- Stop loading `staging.leagues` and `staging.league_members`.
- `v_player_rating_ranks` takes `league_cid` from `mart.club_leagues`.

**fmstats/mart.py**
- `mart.club_leagues`: league id off the club table (same as-at logic); name, reputation, type
  from `staging.competitions`; nation via `nation_id`.
- `mart.leagues`: competitions that some club plays in; `member_count` counted.
- `mart.competitions`: drop the `lg` merge.

**Risks**
- `mart.clubs` grows from ~4.6k to ~11.3k rows per snapshot; the site's `clubs.json` grows with
  it (decision 3).
- 292 → 332 leagues can shift the tier derivation (`mart.py` ~2846) and the league ladder;
  likely needs a filter to league types.
- `world_fixtures` gains ~7k rows per save (reserve and national-team games);
  `mart.league_tables` and anything else built on fixtures must still key on the right
  competitions.

**Check**: row-for-row mart diff before/after on the existing rows (`mart.clubs`,
`mart.leagues`, `mart.club_leagues`, `mart.competitions`, `mart.league_tables`);
`tests/validate_mart.py`; a reviewed `git diff site/api`; `assert_identical` re-record.
Then delete the `clubs_comps` lookups nothing uses any more and shrink TODO #12.

## PR 4 — save order + cursor (after the `squad.py` session merges)

- `main()` becomes a flat list of steps `(name, scrape, dump)` in the file order above; the
  archive tables come last.
- Each locator gains an optional `lo=0`; audit scripts keep calling it without one.
- Cursor = end of the previous table's spans. An empty table (matches on a 0-match save) leaves
  the cursor where it was.
- On a miss, raise an error naming the table, the cursor and the previous table.
  `--no-cursor` re-runs every locator from 0, so a broken locator can be reported and still
  worked around.
- Keep the five existing "starts right after" chains; the cursor is only a lower bound for the
  rest.
- Add a test: locator starts only go up on the test saves, in both careers.

**Check**: `assert_identical` byte-identical (only the order of `dump()` calls changes).

## Decisions needed

1. Is the outside squad-comparison tool that read `players.csv` still in use? If not, PR 2
   goes ahead.
2. Output folders named after the save file (no churn), or first rename the 20 saves to their
   header dates (touches R2, the manifest, `staging.extracts` and saved scouts)?
3. Site `clubs.json`: every club (11.3k) or only clubs with a squad?
4. Older stores: leave the dropped `staging.extracts` columns NULL, or drop them in a migration?
