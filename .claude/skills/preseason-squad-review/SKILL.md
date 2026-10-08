---
name: preseason-squad-review
description: Data-driven pre-season squad review for the active FM career — best XI + bench for the current formation, loan candidates, fast-growing youth, and validation that the rating weighting matches actual match output. Use each pre-season (after importing the new season-start save) or when the user asks to analyse the team / pick a starting XI / decide loans.
---

# Pre-season squad review

Reads the active career's store, `fm-<key>.duckdb` (build/refresh via the `import-fm-saves` skill
first; open it read-only, keeping its file name — the views carry the catalog name `fm-frem`).
Combine **attribute-weighted ratings** (talent/profile) with **actual match output**
(performance) — neither alone is enough. Immersion rule: reason with ratings + match stats,
**never surface CA/PA**. Multi-statement recipes run with the runner in
[`query-fm-data`](../query-fm-data/SKILL.md).

## Inputs to establish first
- **Formation & roles** — ask the user. Map their roles → rating roles (WB→LB/RB, CD→CB, RP→DM,
  B2B→CM, IF→AML/AMR, AF→ST). The rating role of each position is `site.position_roles`, the slots
  of each formation `site.formation_slots`.
- **Which weight-set (method)** — read it, don't assume:
  `SELECT value FROM site.config WHERE key = 'career_rating_method'` (Frem → `frem_minmax_4231`,
  the 4-2-3-1 we play; `default_method` is the web app's display default, not our tactic).
- **Snapshot** — `SELECT snapshot_date, season FROM site.snapshots WHERE is_latest`. Phases are
  in-game DATES; a season-start save is the first snapshot of its `season`.
- **Squad** — `mart.squad_membership WHERE is_current AND is_managed_club` (the squad arrays).
  Never a `club_tid` filter: a lapsed loan can leave a departed player's record on our club for a
  year or more.
- **First team vs reserves** — `team_tid` on the same rows (`site.our_teams`: 346 first team, 7296
  reserves). Match stats always split on it.

## Core query patterns

**Fit per player × role** (familiarity-adjusted: `eff = base × (floor + (1 − floor) × fam/20)`,
curve `linear_floor`, floor 0.5, per `site.config`). `base` is the role-weighted rating
(`int.player_ratings` — attributes × `site.role_weights`, an unlisted attribute at weight 1), the
same formula the web app computes in `site/js/data.js`. One row per player per role, at his best
position for it (two positions can map to one role):
```sql
-- best Fit per player per role, our whole squad (first team and reserves)
WITH fit AS (
    SELECT sm.person_id, sm.team_tid, d.name, f.age, pr.role, p.position, p.familiarity,
           r.rating AS base, round(r.rating * (0.5 + 0.5 * p.familiarity / 20.0)) AS eff
    FROM mart.squad_membership sm
    JOIN mart.fact_player_snapshot f USING (person_id, snapshot_date)
    CROSS JOIN unnest(f.positions) AS u(p)
    JOIN site.position_roles pr ON pr.position = p.position
    JOIN int.player_ratings r
      ON r.snapshot_date = f.snapshot_date AND r.tid = f.tid
     AND r.method = 'frem_minmax_4231' AND r.role = pr.role
    JOIN mart.dim_person d USING (person_id)
    WHERE sm.is_current AND sm.is_managed_club
)
SELECT * FROM fit
QUALIFY row_number() OVER (PARTITION BY person_id, role ORDER BY eff DESC) = 1
ORDER BY role, eff DESC;
```

**Match output — split first team and reserves by `team_tid`.** One row per player per team; the
campaign is the date window from the rollover day (Frem 30 June):
```sql
-- match output this season, first team and reserves apart
SELECT f.person_id, p.name, f.team_tid,
       count(*) FILTER (WHERE f.appeared) AS apps, count(*) FILTER (WHERE f.started) AS starts,
       sum(f.minutes) AS mins,
       round(avg(f.rating) FILTER (WHERE f.appeared), 2) AS mr,
       round(avg(f.rating_adj) FILTER (WHERE f.started), 2) AS mr_adj,
       sum(f.goals) AS g, sum(f.assists) AS a, sum(f.key_passes) AS kp
FROM mart.fact_player_match f
JOIN mart.dim_match m USING (match_id)
JOIN mart.dim_person p USING (person_id)
WHERE f.team_tid IN (SELECT team_tid FROM site.our_teams)
  AND m.match_date BETWEEN DATE '2027-06-30' AND DATE '2028-06-29'
  AND m.cid <> 65                                              -- 65 = Friendly
GROUP BY ALL
ORDER BY f.team_tid, mins DESC;
```
> **`mr` is the game's rating, `mr_adj` the position-adjusted one.** Compare players in the same
> slot on either; compare across positions (a DM against a winger, or where a versatile
> midfielder is best) only on `mr_adj` — the game rates a DM ~0.47 below a central midfielder for
> the same game. Per-position splits: `scout-opponent`'s position-split query.
>
> Filter `appeared` for apps and ratings: an unused sub still gets a row carrying a flat **6.00**
> rating — average it in and every figure sags toward 6. Reserve matches carry goals, assists,
> minutes and rating but few of the other stats.

**Development** — attribute growth across the season just finished: the 23-attribute total at the
season's first and last snapshot, for players in our squad at both and read exactly at both (a new
signing's estimate→exact switch is not growth):
```sql
-- attribute growth across one season: the 23-attribute total at the season's first and last
-- snapshot, for players in our squad at both, read exactly (not estimated) at both ends
WITH ends AS (
    SELECT min(snapshot_date) AS d0, max(snapshot_date) AS d1 FROM site.snapshots WHERE season = 2027
),
tot AS (
    SELECT f.person_id, f.snapshot_date, f.age, f.attributes_are_estimated,
           Aerial + Crossing + Dribbling + Shooting + Passing + Tackling + Technique
           + Aggression + Creativity + Decisions + Leadership + Movement + Positioning
           + Teamwork + Pace + Stamina + Strength + Agility + Handling + Kicking + Reflexes
           + Communication + Throwing AS total
    FROM mart.fact_player_snapshot f, ends
    WHERE f.snapshot_date IN (ends.d0, ends.d1)
      AND (f.person_id, f.snapshot_date) IN (
          SELECT (person_id, snapshot_date) FROM mart.squad_membership WHERE is_managed_club)
),
mins AS (
    SELECT person_id, sum(minutes) AS minutes FROM site.match_players
    WHERE season = 2027 GROUP BY 1
)
SELECT p.name, b.age, a.total AS start_total, b.total AS end_total, b.total - a.total AS growth,
       coalesce(mins.minutes, 0) AS minutes
FROM tot a
JOIN tot b ON b.person_id = a.person_id AND b.snapshot_date > a.snapshot_date
JOIN mart.dim_person p ON p.person_id = a.person_id
LEFT JOIN mins ON mins.person_id = a.person_id
WHERE NOT a.attributes_are_estimated AND NOT b.attributes_are_estimated
ORDER BY growth DESC LIMIT 8;
```
A season alone badly understates a long server — for growth since joining, see the tenure query
in [`fm-season-review`](../fm-season-review/SKILL.md). Focus U24.

## Deliverables (the review)

1. **Best XI** for the formation: per role, rank squad by effective rating, then **cross-check
   with match output** (minutes, goals, avg match rating). Pick the top per slot, no duplicates.
   Where rating and output disagree, **trust output** — especially at **ST** (see gotcha).
2. **Bench of 7** covering GK / DEF / MID / ATT; prize versatile utility players.
3. **Loan candidates**: U24, low **first-team** minutes, blocked behind better players at a
   stacked position. Distinguish reserve minutes (a reserve regular ≠ first-team ready). Flag the
   truly starved (≈0 minutes anywhere) as top priority.
4. **Reserve standouts**: high reserve output (goals/assists, avg rating) = promotion or
   start-somewhere-senior loan candidates (e.g. a reserve top scorer with no first-team minutes).
5. **Fast growers**: biggest rating deltas, especially U24 — the trajectory players to protect.
6. **Weighting validation**: does rating rank track match output? Confirm the agreements; flag
   the outliers. Where a role's weighting is clearly off for this league/match-engine, propose the
   change as evidence for `scripts/derive_weight_set.py` (a judgement call goes in its `HELD` list
   with its argument) — never a hand edit of `seeds/role_weights.csv`.
7. **Succession note**: call out aging positions with no young cover (read `age` off the Fit
   query, per role) and say whether the answer is the academy, retraining, a tactical adaptation
   or a signing.

## Gotchas (learned the hard way)
- **Reserve vs first-team split is essential** — always split by `team_tid`; combining them
  overstates fringe players' first-team roles.
- **Striker rating is the least reliable** — attribute weighting predicts ST goals poorly here
  (a poacher can overperform a "better" profile; a great-profile winger can under-return). For
  strikers, **select on goals/90**; use rating only to scout. Restrict a role's comparison to
  players who actually play it (don't rank a winger as an ST).
- **Familiarity matters**: use `eff` (× familiarity), not `base`, for selection.
- `minutes` includes extra time (0–120).
- DuckDB is single-writer: open read-only for analysis; a store mid-load refuses the connect —
  wait for the loader or read a copy under the same file name.
