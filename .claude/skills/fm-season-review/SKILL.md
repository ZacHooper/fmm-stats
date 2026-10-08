---
name: fm-season-review
description: End of season review for the active FM career — our season's story, tactical/unit breakdown and player awards (serious & silly), plus a national review (league, cup, home clubs in Europe, home transfer market) and a global review (continental finals and nation performances, coefficients, world transfer market, top scorers). Use when the user asks for an end-of-season review, season recap, player awards, or "how did the world/nation go this season".
---

# FM End of Season Review

Use this skill when the user asks for an end-of-season review, team review, player awards, or a
national/global round-up of a season for their Football Manager save parsed via `fm-parser`.

## Context
- Analytics run against the career's DuckDB store through the **`mart` and `site` schemas**
  (`fmstats/`, the dbt project). Locally that is `fm-frem.duckdb`, opened read-only under its own
  file name (the views carry the catalog name `fm-frem`); with no local store, attach the
  published full copy `AS "fm-frem"` (see [`query-fm-data`](../query-fm-data/SKILL.md)). Check
  the newest snapshot covers the end of the season you review.
- The user reads these on Discord, so output must be punchy, narrative-driven text with bullet
  points, NOT massive markdown tables.
- The review has four parts, in this order:
  1. **Our season** — record, league position, cups, the story of the season (form swings,
     key sales/signings, bogey teams), our European run.
  2. **Units + awards** — tactical/positional review (for the coaches) and player awards.
  3. **National review** — final table, cup winner, top scorers, the home nation's clubs in
     Europe, the home transfer market and our own transfer ledger.
  4. **Global review** — continental finals, last eight, nations that over/under-performed,
     coefficient ranking moves, world transfer market, big-league top scorers.
  Parts 1–2 come from the SQL template below; parts 3–4 from
  **`world_review.py`** in this directory (see "National + global review").

## Behavioral Guardrails

**0. The season is the END-YEAR — and "latest" is usually the wrong default**
**[REQUEST]** "Do the end of season review for the 2026 season." (they meant 26/27)
**[BAD]** *Runs `SEASON = 2026` and reviews 25/26; or leaves `SEASON = None` and gets the
season that has only just started.*
**[GOOD]** *"26/27" = `season 2027`. Map what the user said to an end-year, and if they gave a
single year, say which campaign you took it as ("reviewing 2026/27 (season 2027)") in the first
line so a wrong guess is caught before the review, not after it.*
**[WHY]** Seasons are coded by end-year (22/23 → 2023). A user saying "the 2026 season" usually
means the one that STARTED in 2026. And the newest snapshot is often a pre-season save for the
NEXT campaign (e.g. `2027-08-08` is season 2028, with a few games), so "latest season with
matches" lands on a season barely begun. Check `SELECT season, snapshot_date FROM site.snapshots
ORDER BY snapshot_date DESC` and review the most recent season whose last snapshot is in June.

**1. Query `mart` and `site`, never `raw`**
**[REQUEST]** "Run the end of season review for Frem."
**[BAD]** *Aggregates `raw.match_player_stats` directly and hand-rolls the snapshot dedup.*
**[GOOD]** *Reads `site.matches` / `site.match_players` / `mart.fact_player_match`, which hold each
match once.*
**[WHY]** `raw.*` holds one full row set per SNAPSHOT, and the match table is re-read on every
import, so summing across snapshots double-counts, and joining on a bare `tid` multiplies every
stat row by the number of snapshots the player appears in. The dbt models apply those rules once
(`fmstats/CLAUDE.md`). If the models are missing, rebuild with `uv run python load_duckdb.py …`
rather than working around it.

**2. Appeared ≠ named in the squad**
**[REQUEST]** "Who had the best average rating?"
**[BAD]** *Averages `rating` over every `fact_player_match` row for the player.*
**[GOOD]** *Filters `appeared` (or uses `site.match_players`, which holds appearances only).*
**[WHY]** An unused substitute still gets a row, carrying a **flat rating of 6.00** — 110 such
rows in Frem's 2024. Averaging them in drags every figure toward 6 and lets a pure benchwarmer
clear a "minimum games" filter. Mikkel Bruhn reads 6.66 unfiltered against 7.25 for the 20 games
he actually played.

**3. The Starter Filtering Rule (positional analysis only)**
**[GOOD]** *For UNIT breakdowns, filter `started` and require ~10 starts.*
**[WHY]** Sub appearances distort average ratings and defensive/passing volume. Positional
analysis evaluates pure starters. This is narrower than rule 2 — awards use appearances, units use
starts.

**4. The DuckDB Lock Rule**
**[WHY]** A process loading the store holds the write lock and a read-only connect fails. Wait
for it, or copy the store to a scratch DIRECTORY under the same file name and read the copy.

**5. The Mobile Output Rule**
**[BAD]** *A 20-column markdown table of DataFrame output.*
**[GOOD]** *"🏆 **Golden Boot:** Adam Jakobsen (34 goals)"*
**[WHY]** Read on a phone via Discord. Wide tables break. Translate data into a tight narrative.

**6. Never surface raw CA/PA** — house rule. Reason with attributes, role ratings and
percentiles. Growth totals (the sum of the 23 attributes) are attribute-derived and fine.

**7. Rank across positions on the ADJUSTED rating**
**[BAD]** *Player of the Season = highest raw `avg_rating`.*
**[GOOD]** *Rank on `avg_rating_adj` (from `rating_adj` on `site.match_players` / `mart.fact_player_match`);
show the raw average beside it.*
**[WHY]** The game's rating is position-biased: a DM rates ~0.47 below a central midfielder and a
forward ~0.47 above one for the same performance, so a raw ranking is partly "who plays furthest
forward". `rating_adj` restates each start on one scale, in the game's units. Raw stays the right
number WITHIN a position. See `docs/plans/2026-09-23-match-rating-normalisation.md`.

**8. Tell the story, not just the totals**
**[BAD]** *"W15 D7 L10, 2nd."*
**[GOOD]** *Split the league record at the winter break and look at what happened in the gap:
"10-3-4 before Christmas, 5-4-6 after — we sold Wass (£12.75M) and Ementa (£9.5M) in January."*
**[WHY]** The final line hides the season's shape. `site.matches` lists every game (the
template's season-shape query does the split). Look for: the form split either side of the winter
window, one opponent we kept losing to, and the Golden Boot winner who left halfway through. Check
our own transfers from `world_review.py`'s OUR LEDGER section against the dates of the form swing.

**9. Career-history goals for a goalkeeper are goals CONCEDED**
**[WHY]** `mart.fact_player_season.goals` holds conceded goals on a keeper's row, so a
league-wide top-scorer list built from it is topped by goalkeepers (Grabara "76 goals").
Exclude goalkeepers (`fact_player_snapshot.is_goalkeeper`) — `world_review.py` does.

## SQL template (parts 1–2)
Set `season`, save it to a file and run it with the runner in
[`query-fm-data`](../query-fm-data/SKILL.md) (~1 min). For every game, for the story:
`SELECT match_date, competition, stage, venue, opponent, gf, ga, result, formation FROM
site.matches WHERE season = 2027 ORDER BY match_date`.
```sql
SET VARIABLE season = 2027;          -- END-YEAR (26/27 -> 2027) — see guardrail 0
SET VARIABLE us = (SELECT team_tid FROM site.our_teams WHERE is_managed);

-- 1. RESULTS BY COMPETITION (site.matches: the managed first team, one row per match)
SELECT competition, count(*) AS games,
       count(*) FILTER (WHERE result = 'W') AS w, count(*) FILTER (WHERE result = 'D') AS d,
       count(*) FILTER (WHERE result = 'L') AS l, sum(gf) AS gf, sum(ga) AS ga
FROM site.matches WHERE season = getvariable('season')
GROUP BY competition ORDER BY games DESC;

-- FORMATIONS (competitive games; stage_kind is NULL for a friendly)
SELECT formation, count(*) AS games, sum(gf) AS scored, sum(ga) AS conceded,
       round(avg(pts), 2) AS ppg
FROM site.matches WHERE season = getvariable('season') AND stage_kind IS NOT NULL
GROUP BY formation ORDER BY games DESC;

-- THE SHAPE OF THE SEASON: league form either side of the winter window (guardrail 8)
SELECT CASE WHEN month(match_date) >= 7 THEN '1 before winter' ELSE '2 after winter' END AS half,
       count(*) AS p, count(*) FILTER (WHERE result = 'W') AS w,
       count(*) FILTER (WHERE result = 'D') AS d, count(*) FILTER (WHERE result = 'L') AS l,
       sum(gf) AS gf, sum(ga) AS ga, sum(pts) AS pts
FROM site.matches WHERE season = getvariable('season') AND stage_kind = 'League'
GROUP BY 1 ORDER BY 1;

-- FINAL TABLE (mart.standings; the league's own season label is the start year)
SELECT s.stage_index, s.position, t.name, s.played, s.won, s.drawn, s.lost,
       s.goals_for, s.goals_against, s.points
FROM mart.standings s JOIN mart.dim_team t USING (team_tid)
WHERE s.cid = (SELECT dm.cid FROM site.matches sm JOIN mart.dim_match dm USING (match_id)
               WHERE sm.season = getvariable('season') AND sm.stage_kind = 'League' LIMIT 1)
  AND s.competition_season = getvariable('season') - 1 AND s.is_latest
ORDER BY s.stage_index, s.position;

-- 2. POSITIONAL UNITS — pure starters only (rule 3), grouped by the role actually played
--    (fact_player_match.role, from the decoded position). 10+ starts.
SELECT f.role, p.name, count(*) AS starts, round(avg(f.rating), 2) AS avg_rating,
       round(avg(f.rating_adj), 2) AS avg_rating_adj, sum(f.goals) AS goals,
       sum(f.assists) AS assists, sum(f.key_passes) AS key_passes,
       sum(f.tackles_won + f.interceptions) AS def_actions, sum(f.mistakes) AS mistakes
FROM mart.fact_player_match f
JOIN site.matches m USING (match_id)
JOIN mart.dim_person p USING (person_id)
WHERE m.season = getvariable('season') AND m.stage_kind IS NOT NULL
  AND f.team_tid = getvariable('us') AND f.started
GROUP BY f.role, f.person_id, p.name HAVING count(*) >= 10
ORDER BY f.role, avg_rating_adj DESC;

-- 3. AWARDS — appeared-only (rule 2): site.match_players holds appearances only
CREATE OR REPLACE TEMP TABLE awards AS
SELECT mp.person_id, p.name,
       extract(year FROM age(make_date(getvariable('season'), 6, 30), p.dob)) AS age,
       count(*) AS games, count(*) FILTER (WHERE mp.started) AS starts,
       sum(mp.minutes) AS minutes, round(avg(mp.rating), 2) AS avg_rating,
       round(avg(mp.rating_adj) FILTER (WHERE mp.started), 2) AS avg_rating_adj,
       sum(mp.goals) AS goals, sum(mp.assists) AS assists, sum(mp.key_passes) AS key_passes,
       sum(mp.headers_won) AS headers_won, sum(mp.dribbles) AS dribbles,
       sum(mp.passes_completed) AS passes_completed, sum(mp.shots) AS shots,
       sum(mp.interceptions + mp.tackles_won) AS def_actions,
       sum(mp.mistakes) AS mistakes, sum(mp.yellows) AS yellows
FROM site.match_players mp
JOIN mart.dim_person p USING (person_id)
WHERE mp.season = getvariable('season') AND mp.competition <> 'Friendly'
GROUP BY mp.person_id, p.name, p.dob HAVING count(*) > 3;

-- Player of the Season / Young Player: POSITION-ADJUSTED rating (rule 7), 10+ starts;
-- the raw average beside it is the number the manager saw in-game
SELECT 'Player of the Season' AS award, name, avg_rating_adj, avg_rating, starts
FROM awards WHERE starts >= 10 QUALIFY row_number() OVER (ORDER BY avg_rating_adj DESC) = 1
UNION ALL
SELECT 'Young Player (U21)', name, avg_rating_adj, avg_rating, starts
FROM awards WHERE starts >= 10 AND age <= 21
QUALIFY row_number() OVER (ORDER BY avg_rating_adj DESC) = 1;

-- the counting awards: the leader in each column
SELECT award, arg_max(name, total) AS name, max(total) AS total
FROM (UNPIVOT (SELECT name, goals, assists, key_passes, headers_won, dribbles,
                      passes_completed, def_actions, mistakes, yellows FROM awards)
      ON goals, assists, key_passes, headers_won, dribbles, passes_completed, def_actions,
         mistakes, yellows
      INTO NAME award VALUE total)
GROUP BY award;

-- 4. MOST IMPROVED — the 23-attribute total at the season's first and last snapshot, for
--    players in our squad at both, read exactly (not estimated) at both: a new signing's
--    estimate->exact switch is not growth
WITH ends AS (
    SELECT min(snapshot_date) AS d0, max(snapshot_date) AS d1
    FROM site.snapshots WHERE season = getvariable('season')
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
)
SELECT p.name, b.age, a.total AS start_total, b.total AS end_total, b.total - a.total AS growth,
       coalesce(aw.minutes, 0) AS minutes
FROM tot a
JOIN tot b ON b.person_id = a.person_id AND b.snapshot_date > a.snapshot_date
JOIN mart.dim_person p ON p.person_id = a.person_id
LEFT JOIN awards aw ON aw.person_id = a.person_id
WHERE NOT a.attributes_are_estimated AND NOT b.attributes_are_estimated
ORDER BY growth DESC LIMIT 5;

-- GROWTH SINCE JOINING (top 5 of the current squad): first vs latest exact read while ours.
-- A season understates a long server (Garly: +11 in 2024, +36 since joining).
WITH ours AS (
    SELECT f.person_id, f.snapshot_date, f.age,
           Aerial + Crossing + Dribbling + Shooting + Passing + Tackling + Technique
           + Aggression + Creativity + Decisions + Leadership + Movement + Positioning
           + Teamwork + Pace + Stamina + Strength + Agility + Handling + Kicking + Reflexes
           + Communication + Throwing AS total
    FROM mart.squad_membership sm
    JOIN mart.fact_player_snapshot f USING (person_id, snapshot_date)
    WHERE sm.is_managed_club AND NOT f.attributes_are_estimated
)
SELECT p.name, arg_min(age, snapshot_date) AS age_first, arg_max(age, snapshot_date) AS age_now,
       arg_max(total, snapshot_date) - arg_min(total, snapshot_date) AS growth,
       round(date_diff('day', min(snapshot_date), max(snapshot_date)) / 365.0, 1) AS yrs
FROM ours JOIN mart.dim_person p USING (person_id)
WHERE person_id IN (SELECT person_id FROM mart.squad_membership
                    WHERE is_current AND is_managed_club)
GROUP BY person_id, p.name ORDER BY growth DESC LIMIT 5;

-- 5. THE STORMTROOPER — most shots without a goal in one match
SELECT p.name, mp.shots, mp.match_date, m.opponent
FROM site.match_players mp
JOIN mart.dim_person p USING (person_id)
JOIN site.matches m USING (match_id)
WHERE mp.season = getvariable('season') AND mp.goals = 0
ORDER BY mp.shots DESC LIMIT 1;
```

## National + global review — `world_review.py`

```bash
uv run python .claude/skills/fm-season-review/world_review.py --season 2027 [--db fm-frem.duckdb] [--nation Denmark]
```
It prints, in order: CONTINENTAL FINALS, LAST EIGHT AND BEYOND, a SANITY line, NATION RECORDS,
CLUBS THROUGH THE GROUPS, BIGGEST SCORELINES, <HOME NATION> IN EUROPE, UEFA NATION COEFFICIENTS,
<HOME NATION> CUP CANDIDATES, TOP SCORERS, and the transfer blocks (WORLD, BY WINDOW, TOP 10,
SPENDERS, SELLERS, BY LEAGUE NATION, HOME NATION deals + totals, OUR LEDGER — all read from
`mart.fact_transfer`). The home nation defaults to our club's. Its docstring has the full method.
What you need to read the output well:

**Continental cups are rebuilt, not looked up.** The fixture list carries stage keys, which
move every season, and no competition id. The script finds each final (a late-season
one-match cross-nation stage) and works back through the knockout rounds. A group belongs to
the competition that keeps two or more of its clubs. **Read the SANITY line first:** each
competition should show 8 groups and 32–40 clubs. If it doesn't, the reconstruction has gone
wrong and the per-nation tables can't be trusted.
- The tiers are **European Champions Cup** (cid 256), **EURO Cup** (258) and **EURO Cup II**
  (505, code EC2). These names come from the save's competition records and are fixed in
  `EURO_TIERS`, ranked by group-stage club reputation; a competition past the third tier (a
  nations' cup between first teams does not appear, but any other cross-nation knockout would)
  prints as `tier N cup`. The dormant `European Cup Winners Cup` (257) is never played.
- **Cross-check against the roll of honour.** The `comp_honours` grid in `comp_man.dat`
  records each finished competition's winner and runner-up. The parser reads it
  (`fmparser.tables.comp_honours`), but the store doesn't load it. For 25/26 it agrees with the
  reconstruction for all three competitions (Man City, Augsburg, Sevilla). It hadn't recorded
  26/27 by the 2027-08-08 save, so it can confirm an OLDER season but not the one just
  finished.
- Group third-placers drop a tier, so a club can appear in two competitions. The rebuild
  handles this. The storylines are worth using: in 26/27 RB Leipzig dropped out of the
  Champions Cup groups, knocked Frem out and won the EURO Cup. Lyon finished 3rd in Frem's
  group and went on to win EURO Cup II.
- **Unlicensed club names.** FMM renames unlicensed clubs, so name them for what they are:
  `Zebre` = Juventus, `Real Hispalis` = Real Betis, `A. Madrid` = Atlético Madrid,
  `Manchester UFC` = Manchester United, `VTSC` = Vitória SC. Say "Zebre (Juventus)".
- **A club with no nation** in `mart.dim_club` appears as `?<club>`; name it yourself.
- **The coefficient table is UEFA members only** (`site.nations.is_uefa`). `best_prev` is the
  best earlier season in the nation's history, so a `season_coef` above it is a best-ever season
  (Denmark 26/27: 11.10 against a previous best of 8.50). The 5-year rank move
  (`rank_5yr_before` → `rank_5yr_now`, the UEFA association ranking) is the headline for a
  nation.

**Transfers come from `mart.fact_transfer`**, one row per permanent move or academy graduation
(graduations are left out of the market).
- **What a move is:** a club change in a player's career history, or between two of his
  snapshots for a move the history has no line for yet.
- **Fee:** read from the selling club's career-history row, in £ (`fee_gbp`). `transfer_type`
  is `permanent` (a fee above 0) or `free` (0: a free, a Bosman, a contract that ran out);
  `fee_kind` says which.
- **`season`:** the campaign the player moves FOR. **A June signing belongs to the next
  season's market**, so the 26/27 market runs June 2026 to May 2027.
- **Window** is the move date's month (June–September summer), else the first snapshot that
  shows him at the new club; `undated` where neither is known.
- **Checked against our own deals** (Wass £12.75M, Ementa £9.5M, Kaiser £7.383M).
- **Two limits to caveat:**
  - It only covers clubs the save tracks in detail, so quote totals as a floor.
  - Loans are not transfers: they are `mart.fact_loan_spell`, and other clubs' loans barely
    appear there.

**Home cup winner.** CUP CANDIDATES lists the late-season all-domestic knockout stages. The
final is the single match that follows a two-leg semi-final stage. Other one-off stages (e.g. a
June European play-off) also appear, so pick the final using judgement.

**Top scorers** are all-competition totals from career history (`mart.fact_player_season`). Italy and France are
simulated in less detail: when a big league's leader has fewer than ~15 appearances, leave
that league out rather than report a partial table.

## Review Execution Steps
1. Pin the season (guardrail 0) and confirm the store's newest snapshot is past its end
   (`SELECT max(snapshot_date) FROM site.snapshots`).
2. Run the SQL template (parts 1–2), including the FINAL TABLE and every game for the story.
3. Run `world_review.py --season <S>` (parts 3–4) and check its SANITY line.
4. Sanity-check one number against a known figure before writing prose (e.g. the Golden Boot
   total against the site's Matches page, or one of our fees against the in-game screen).
5. Turn it into a Discord-friendly summary in four sections: Our season, Units + awards,
   National review, Global review. End with a short caveats list: fee coverage, any leagues
   left out.

## Reporting notes
- **Goals-for and player-attributed goals differ** and both are right: an opposition own goal
  counts to the team score without being attributed to any of our players. Frem 2024 = 73 team
  goals, 70 player goals, 3 own goals. Say which one you mean.
- **League position:** the template's FINAL TABLE (`mart.standings`). A league with a
  championship/relegation split shows the split as later `stage_index` tables, each counting the
  split's own matches. A foreign table is only as complete as the world fixture list's results
  for that league — check `played` before quoting one as fact.
- **Rank "most improved" on minutes too.** A 17-year-old gaining +33 in 190 minutes is a
  footnote. +31 in 1,530 minutes is the award.
