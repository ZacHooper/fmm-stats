---
name: wide-footedness
description: "Foot against flank for wide players (AML/AMR/ML/MR), ours and opponents', measured on our first-team matches: inside forwards out-shoot same-foot wingers, but for opponents only at Level %ile 70+. Recipe to re-measure."
metadata:
  node_type: memory
  type: reference
---

Measured 2026-10-08 on the published Frem store (matches 2021-07 to 2028-05), from the team-head
positions in `mart.fact_player_match.position` ([[match-position-encoding]]), which carry both
sides' eleven. Read by `scout-opponent` step 9.

**Definitions.** Starters only, minutes > 0, our FIRST-TEAM matches only. A player is
*two-footed* when his weaker foot is 15+ (`dim_person.foot_left` / `foot_right`, 1–20); otherwise
*same foot* when his stronger foot matches his flank (a left-footer at AML/ML) and *cuts inside*
when it is the opposite. Level %ile is `level_league` at the position he played, from his latest
snapshot on or before the match (ASOF join).

## Results

Wide AMs (AML/AMR), per 90:

| | Starts | Players | Level | Goals | Shots on target | Shots | Crosses | Dribbles | Rating |
|---|---|---|---|---|---|---|---|---|---|
| Opp, cuts inside | 194 | 108 | 68 | 0.18 | 0.50 | 1.30 | 3.56 | 0.63 | 7.02 |
| Opp, same foot | 147 | 87 | 67 | 0.17 | 0.39 | 1.05 | 3.81 | 0.83 | 7.04 |
| Frem, cuts inside | 184 | 14 | 49 | 0.27 | 0.54 | 1.42 | 1.37 | 0.64 | 7.42 |
| Frem, same foot | 244 | 17 | 41 | 0.13 | 0.25 | 0.80 | 2.42 | 1.00 | 7.20 |

By Level band (wide AMs; goals per 90 / shots on target per 90):

| | Cuts inside | Same foot |
|---|---|---|
| Opp 70+ | 0.23 / 0.64 (102 starts) | 0.16 / 0.42 (78) |
| Opp 40–70 | 0.10 / 0.31 (58) | 0.21 / 0.32 (44) |
| Opp <40 | 0.18 / 0.40 (33) | 0.17 / 0.39 (25) |
| Frem 70+ | 0.28 / 0.61 (57) | 0.10 / 0.19 (53) |
| Frem 40–70 | 0.16 / 0.51 (39) | 0.15 / 0.28 (34) |
| Frem <40 | 0.31 / 0.56 (81) | 0.13 / 0.28 (155) |

Opposition by flank and foot (AM + M, two-footed excluded): right-footer on their left 151 starts
/ 24 goals / 59 on target; right-footer on their right 126 / 19 / 40; left-footer on their right
83 / 11 / 34; left-footer on their left 65 / 6 / 17.

## Reading

- Opponent groups are level-matched (68 v 67), so their comparison is clean: footedness matters
  only for good players. Our own split is NOT level-matched overall (49 v 41) but holds inside
  each band, so it is not just better players happening to play inverted.
- Same-foot wingers cross and dribble more, and shoot less. Crosses barely predict our goals
  ([[scoring-and-shot-quality]]), which is why a same-foot winger is the least dangerous wide
  profile against us.
- Wide midfielders (ML/MR) show the same direction, on samples too small to quote (33–99 starts).
- Small cells: 6–24 goals each. Shots on target is the steadier signal.

## Trap found on the way

`mart.fact_player_match` holds our reserves' matches too (98 of 400), and opponent shot counts
there are incomplete (goals exceed shots on target). Over all matches, opponent goals per shot on
target read 0.8–1.0; in first-team matches the player rows add up exactly to
`mart.fact_team_match` (shots 2051 = 2051). Filter to first-team matches for any opponent per-90.

## Recipe

```sql
CREATE TEMP TABLE w AS
SELECT f.*, d.match_date,
  CASE WHEN f.position LIKE 'AM%' THEN 'AM' ELSE 'M' END band,
  CASE WHEN least(p.foot_left, p.foot_right) >= 15 THEN 'two-footed'
       WHEN (p.foot_left > p.foot_right) = (f.position LIKE '%L') THEN 'same'
       ELSE 'inverted' END kind,
  f.team_tid = 346 AS ours
FROM mart.fact_player_match f
JOIN mart.dim_match d USING (match_id)
JOIN mart.dim_person p USING (person_id)
WHERE f.started AND f.minutes > 0 AND f.position IN ('AML', 'AMR', 'ML', 'MR')
  AND f.match_id IN (SELECT match_id FROM mart.fact_player_match WHERE team_tid = 346);

CREATE TEMP TABLE w2 AS
SELECT w.*, lv.lvl FROM w LEFT JOIN (
    SELECT w.match_id, w.person_id, u.p.level_league AS lvl
    FROM w ASOF JOIN mart.fact_player_snapshot s
         ON s.person_id = w.person_id AND s.snapshot_date <= w.match_date
    CROSS JOIN unnest(s.positions) AS u(p)
    WHERE u.p.position = w.position) lv USING (match_id, person_id);

SELECT ours, band, kind,
       CASE WHEN lvl < 40 THEN '<40' WHEN lvl < 70 THEN '40-70' ELSE '70+' END AS level_band,
       count(*) AS starts, sum(goals) AS goals, sum(shots_on_target) AS on_target,
       round(90 * sum(goals) / sum(minutes), 2) AS g90,
       round(90 * sum(shots_on_target) / sum(minutes), 2) AS sot90,
       round(90 * sum(crosses) / sum(minutes), 2) AS cr90
FROM w2 WHERE kind <> 'two-footed' AND lvl IS NOT NULL
GROUP BY ALL ORDER BY ALL;
```
