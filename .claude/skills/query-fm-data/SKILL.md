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

-- "who was our top scorer" — AGGREGATE FIRST, NAME SECOND:
--   * mart.fact_player_match is one row per appearance with goals, assists, minutes, rating, rating_adj.
--   * dim_person resolves player identity and names.
WITH tot AS (
  SELECT f.person_id,
         SUM(f.goals) AS goals,
         COUNT(*) AS apps,
         ROUND(AVG(f.rating), 2) AS avg_rating,
         ROUND(AVG(f.rating_adj), 2) AS avg_rating_adj
  FROM m.mart.fact_player_match f
  JOIN m.mart.dim_match match USING (match_id)
  WHERE match.season = 2024 AND f.team_tid IN (SELECT team_tid FROM m.mart.dim_team WHERE is_managed_club)
  GROUP BY f.person_id
)
SELECT p.name, tot.goals, tot.apps, tot.avg_rating, tot.avg_rating_adj
FROM tot
JOIN m.mart.dim_person p USING (person_id)
ORDER BY tot.goals DESC LIMIT 5;
```

### Which database object to attach?
* **Attach `site-data/fm-<career>-mart.duckdb` (~71 MB)** for all dimensional warehouse analysis (`mart.*`). It contains:
  * **Dimensions**: `dim_person` (includes `capital_eligible`, `origin_club_tid`), `dim_club`, `dim_competition`, `dim_match`, `dim_team`, `dim_position`, `dim_role`.
  * **Facts**: `fact_player_match` (includes `rating`, `rating_adj`, `role`, stats), `fact_player_snapshot` (view over SCD2 attributes + valuation + positions/level percentiles), `fact_player_season`, `fact_transfer`, `fact_contract`.
  * **Membership**: `mart_squad_membership` (`WHERE is_current AND is_managed_club` gives our current squad; `WHERE is_current AND club_tid = <opp_tid>` gives an opponent's squad).
* **Attach `site-data/fm-<career>.duckdb` (~107 MB)** only if you need full `raw.*` tables or `site.*` presentation views directly.

### Critical Query Rules
1. **Never use a bare `club_tid = <our tid>` filter for "who is ours":**
   * Departed players on lapsed loans can leave `club_tid` pointing at our club indefinitely in raw save records.
   * **Safe answer:** `SELECT person_id FROM m.mart.mart_squad_membership WHERE is_current AND is_managed_club` (or `site.site_squad`).
2. **Comparing match ratings across positions:**
   * FM match ratings have position bias (DMs rate ~0.47 lower than CMs for identical output).
   * In `mart.fact_player_match` (and `site.site_match_players`), use **`rating_adj`** (position-adjusted z-score normalized to the outfield pool) for cross-position comparison. Use raw `rating` only when comparing players within the identical role.
3. **Player Level Percentiles & Scouting:**
   * Level percentiles (`level_league`, `level_global`) are present inside `fact_player_snapshot.positions` (and `site.site_players.positions`).
   * `capital_eligible` (Capital region signing rule) is directly on **`mart.dim_person`**.
4. **The Immersion Rule:**
   * Never surface or reconstruct raw CA/PA. Work exclusively with attributes, percentiles (`level_league`), role ratings, and match stats.
