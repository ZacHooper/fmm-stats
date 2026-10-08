---
name: query-fm-data
description: Answer a football question about the active FM career (top scorers, head-to-head, tables, transfers, squad, finances, injuries, development) from the published R2 mart via direct DuckDB SQL, without a local rebuild. Use for any quick data question or before writing ad-hoc SQL against the store — it lists the mart views, presentation models, and the ATTACH/club_tid traps.
---

# Answering a quick football question — don't default to a local rebuild
A question like "who was our top scorer last season" does NOT need
`scripts/rebuild.py` (~1 min/snapshot, dozens of minutes total) if a local `fm-<career>.duckdb`
isn't already sitting there. For arbitrary SQL, `ATTACH` the published R2 copy directly:
```sql
INSTALL httpfs; LOAD httpfs;
CREATE SECRET r2 (TYPE s3, KEY_ID '<R2_ACCESS_KEY>', SECRET '<R2_SECRET_ACCESS_KEY>',
                   ENDPOINT '<R2_ACCOUNT_ID>.r2.cloudflarestorage.com',
                   URL_STYLE 'path', REGION 'auto');
ATTACH 's3://fmm-stats/site-data/fm-frem-mart.duckdb' AS m (READ_ONLY);

-- "who was our top scorer in 23/24" — AGGREGATE FIRST, NAME SECOND:
--   * mart.fact_player_match is one row per player per match (unused subs included, so
--     filter `appeared`), with goals, assists, minutes, rating, rating_adj.
--   * a campaign runs from the career's rollover day (Frem: 30 June) — dim_match has the
--     date and the competition's own season label, not our campaign.
--   * 346 is Frem's first team (careers.py). dim_person resolves names.
WITH tot AS (
  SELECT f.person_id,
         SUM(f.goals) AS goals,
         COUNT(*) FILTER (WHERE f.appeared) AS apps,
         ROUND(AVG(f.rating) FILTER (WHERE f.appeared), 2) AS avg_rating,
         ROUND(AVG(f.rating_adj) FILTER (WHERE f.started), 2) AS avg_rating_adj
  FROM m.mart.fact_player_match f
  JOIN m.mart.dim_match d USING (match_id)
  WHERE d.match_date BETWEEN DATE '2023-06-30' AND DATE '2024-06-29'
    AND f.team_tid = 346
  GROUP BY f.person_id
)
SELECT p.name, tot.goals, tot.apps, tot.avg_rating, tot.avg_rating_adj
FROM tot
JOIN m.mart.dim_person p USING (person_id)
ORDER BY tot.goals DESC LIMIT 5;
```

### Which database object to attach?
* **`site-data/fm-<career>-mart.duckdb`** — the `mart` **tables** only, plus the
  `fact_player_snapshot` view. Attach it under any name (`AS m`). It holds:
  * **Dimensions**: `dim_person` (name, dob, `capital_eligible`, `origin_club_tid`),
    `dim_club`, `dim_team`, `dim_competition`, `dim_match`, `dim_stage`, `dim_round`,
    `dim_nation`, `dim_position` (position → unit), `dim_role`, `dim_award`.
  * **Facts**: `fact_player_match` (stats, `rating`, `rating_adj`, `role`, `position`),
    `fact_team_match` (each match once per side: score, result, formation, team stats),
    `fact_player_snapshot` (attributes + valuation + `positions` with Level %iles, per
    snapshot), `fact_player_season` (career-history lines, every club), `fact_transfer`,
    `fact_contract`, `fact_loan_spell`, `fact_injury_spell`, `fact_player_award`,
    `fact_staff_snapshot` (managers' formations and Style), `fact_staff_spell`,
    `fact_team_snapshot` (league, reputation), `fact_nation_snapshot`,
    `fact_competition_outcome`, `fact_participation`.
* **`site-data/fm-<career>.duckdb`** — the full store: `raw`, `stg`, `int`, `mart` (tables AND
  views) and `site`. Needed for the views — **`mart.squad_membership`**, `mart.standings`,
  `mart.tie_results`, every `site.*` model, `int.*`. dbt bakes the store's file name into each
  view as its catalog, so **attach it as `"fm-frem"`** or every view fails with
  `Catalog "fm-frem" does not exist`:
  ```sql
  ATTACH 's3://fmm-stats/site-data/fm-frem.duckdb' AS "fm-frem" (READ_ONLY);
  USE "fm-frem";
  SELECT count(*) FROM mart.squad_membership WHERE is_current AND is_managed_club;
  ```
  The same rule holds for a local copy of the store: keep the file name `fm-frem.duckdb`.

### Running a multi-statement recipe locally
The other skills' recipes (`scout-opponent`, `season-outlook`, ...) are several statements that
share `SET VARIABLE`s and temp tables, so run them in ONE connection. Save the recipe to a file in
the scratchpad and run it from the repo root against the store, read-only:
```bash
uv run python -c "
import duckdb, sys
con = duckdb.connect('fm-frem.duckdb', read_only=True)
con.execute('SET enable_progress_bar = false')
for stmt in open(sys.argv[1]).read().split(';\n'):
    if stmt.strip():
        rel = con.sql(stmt)
        if rel is not None:
            print(rel.df().to_string(index=False), end='\n\n')
" "$SCRATCH/recipe.sql"
```
A store another process is writing refuses a read-only connect; copy it to a scratch DIRECTORY
under the same file name (`$SCRATCH/db/fm-frem.duckdb`) and connect to the copy — a copy under any
other name loses every view.

### Critical Query Rules
1. **Never use a bare `club_tid = <our tid>` filter for "who is ours":**
   * A lapsed loan can leave a departed player's record pointing at our club indefinitely.
   * **Safe answer:** `SELECT person_id FROM mart.squad_membership WHERE is_current AND
     is_managed_club` (the squad arrays; `team_tid` splits first team 346 from reserves 7296),
     or `site.squad`. An opponent's squad: `WHERE is_current AND team_tid = <opp_tid>`. A past
     date: replace `is_current` with `snapshot_date = '<date>'` (one of `site.snapshots`).
2. **Comparing match ratings across positions:**
   * FM match ratings have position bias (DMs rate ~0.47 lower than CMs for identical output).
   * In `mart.fact_player_match` (and `site.match_players`), use **`rating_adj`**
     (the rating restated for the position played, set on positioned starts) for
     cross-position comparison. Use raw `rating` only when comparing players within the same
     role.
3. **Player Level Percentiles & Scouting:**
   * Level percentiles (`level_league`, `level_global`) are per position inside
     `fact_player_snapshot.positions` (and `site.players.positions`):
     `CROSS JOIN unnest(f.positions) AS u(p)` then `p.position`, `p.familiarity`,
     `p.level_league`.
   * `capital_eligible` (Capital region signing rule) is directly on **`mart.dim_person`**.
   * An opponent manager's preferred / attacking / defensive formation and Style:
     `mart.fact_staff_spell` (`role = 'manager' AND is_current AND team_tid = <opp>`) joined
     to `mart.fact_staff_snapshot` (`is_current`) on `person_id`.
4. **Our campaign vs the competition's season:** `site.matches` / `site.match_players` carry
   `season` (our campaign's end-year) for the managed first team's matches; elsewhere derive
   it from `match_date` and the rollover day.
5. **The Immersion Rule:**
   * Never surface or reconstruct raw CA/PA (`fact_player_snapshot.ca`/`pa`,
     `fact_staff_snapshot.ca`/`pa`). Work exclusively with attributes, percentiles
     (`level_league`), role ratings, and match stats.
