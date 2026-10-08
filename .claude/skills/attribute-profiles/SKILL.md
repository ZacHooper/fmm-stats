---
name: attribute-profiles
description: Measure how a player's ATTRIBUTES drive his on-pitch STATS — which attributes actually produce interceptions, key passes, headers won, shots on target, dribbles, mistakes or a high rating, computed per positional unit from the career's own match data. Use when the user asks what makes a player do X, which attribute to prioritise for a behaviour, whether an attribute is worth selecting on, what kind of player fits a role or instruction, or wants to sanity-check a football intuition ("does aggression win the ball back?"). Also the right tool before recommending personnel for a specific in-match effect.
---

# Attribute → stat profiles

*What does a player with this make-up actually DO on the pitch?* Ratings and role weights say how
good a player is; this says how he behaves. Use it when the question is about a **behaviour**
(win the ball high, create chances, hit the target, give it away) rather than about quality.

## Run the tool, or the recipe
`scripts/attribute_stat_correlations.py` is the full implementation — every stat, both
`--who us` and `--who opponents`, the `MIN_SD` floor, the CSV export:
```bash
# ALWAYS filter to the division you are playing in — see trap 5
uv run python scripts/attribute_stat_correlations.py --competition '%Superliga%' --min-minutes 360
uv run python scripts/attribute_stat_correlations.py --competition '%Superliga%' --stat intercept_90 --top 10
uv run python scripts/attribute_stat_correlations.py --competition '%Superliga%' --who opponents
uv run python scripts/attribute_stat_correlations.py                      # pooled; prints a warning
uv run python scripts/attribute_stat_correlations.py --csv /tmp/attr.csv  # long-form for further cuts
```
Flags: `--db` (the store; default the career's), `--career`, `--stat` (repeatable), `--who
us|opponents`, `--competition` (an ILIKE pattern), `--min-minutes` (default 450), `--top`
(attributes per stat, default 7), `--positions played|familiar`, `--csv`. Each player-season sits
at the position he **started** most that season, both sides (`fact_player_match.position`), else
his most familiar; `--positions familiar` is the old grouping, kept for comparison. In the Superliga it moves
15% of our player-seasons and 30% of opponents' (wing-backs and holding players out of defence,
a forward who plays the 10 out of attack). Stats: `intercept_90 tackW_90 tackA_90 keyPass_90
assists_90 goals_90 shotA_90 shotO_90 passA_90 passC_90 headA_90 headW_90 crossA_90 crossC_90
dribbles_90 mistakes_90`, the ratios `pass_pct sot_pct head_pct tack_pct cross_pct`, and `rating`.
Remote session with no local store: `rclone copy r2:fmm-stats/site-data/fm-frem.duckdb
"$SCRATCH/db/"` (keep the file name — the views carry the catalog name `fm-frem`) and pass `--db
"$SCRATCH/db/fm-frem.duckdb"`. Pull the **full** store, not `-mart` (no `site` layer).

**The same measurement in SQL**, for one stat or a cut the tool doesn't offer (a position, a
stat it doesn't list). It builds player-seasons from `site.match_players` (our first team's
appearances, `season` our campaign) against the attributes on that season's last snapshot, and
correlates inside each unit, blanking an attribute whose spread in the unit is under 1.5. Swap
`interceptions_90` for another column of `ps` (`key_passes_90`, `headers_won_90`,
`shots_on_target_90`, `dribbles_90`, `mistakes_90`, `rating`), or group by `position` instead of
`unit`. Run it with the runner in [`query-fm-data`](../query-fm-data/SKILL.md):
```sql
-- one row per player-season: our competitive matches in one division, and the attributes he
-- had THAT season (its last snapshot) — never career totals against today's attributes
CREATE OR REPLACE TEMP TABLE ps AS
WITH seasons AS (SELECT season, max(snapshot_date) AS d FROM site.snapshots GROUP BY season),
out AS (
    SELECT person_id, season, mode(position) AS position, sum(minutes) AS mins,
           90.0 * sum(interceptions) / sum(minutes) AS interceptions_90,
           90.0 * sum(key_passes) / sum(minutes) AS key_passes_90,
           90.0 * sum(headers_won) / sum(minutes) AS headers_won_90,
           90.0 * sum(shots_on_target) / sum(minutes) AS shots_on_target_90,
           90.0 * sum(dribbles) / sum(minutes) AS dribbles_90,
           90.0 * sum(mistakes) / sum(minutes) AS mistakes_90,
           avg(rating) AS rating
    FROM site.match_players
    WHERE competition ILIKE '%Superliga%'
    GROUP BY person_id, season HAVING sum(minutes) >= 360
)
SELECT out.*, dp.unit, f.* EXCLUDE (person_id, snapshot_date, tid, team_tid, club_tid, age, ca, pa, positions)
FROM out
JOIN seasons USING (season)
JOIN mart.fact_player_snapshot f ON f.person_id = out.person_id AND f.snapshot_date = seasons.d
JOIN mart.dim_position dp ON dp.position = out.position;
-- each attribute against one stat, inside each unit (never across the squad)
WITH long AS (
    UNPIVOT (SELECT unit, interceptions_90, Aerial, Crossing, Dribbling, Shooting, Passing,
                    Tackling, Technique, Aggression, Creativity, Decisions, Leadership,
                    Movement, Positioning, Teamwork, Pace, Stamina, Strength, Agility FROM ps)
    ON COLUMNS(* EXCLUDE (unit, interceptions_90)) INTO NAME attribute VALUE value
)
SELECT attribute, unit, count(*) AS n, round(stddev_samp(value), 1) AS sd,
       CASE WHEN stddev_samp(value) >= 1.5 THEN round(corr(value, interceptions_90), 2) END AS r
FROM long WHERE unit <> 'goalkeeper'
GROUP BY attribute, unit
ORDER BY unit, r DESC NULLS LAST;
```

Current baseline findings, with the dates and samples they were computed on:
[`attribute-stat-correlations`](../../../docs/agent-context/attribute-stat-correlations.md).
**Re-run rather than quoting that file** if a snapshot has been imported since its date.

## The five traps — all of them have already produced a wrong answer here

**1. Position confounds everything. Never correlate across the whole squad.** Centre-backs have
high Tackling *and* high interceptions because they are centre-backs. A whole-squad correlation
"discovers" that Movement *prevents* interceptions (r = −0.54), which is just "attackers have
Movement and don't intercept". Every figure the tool prints is computed inside a unit, and the
POOLED column is unit-demeaned. If you write your own query, do the same or don't report it.

**2. Use player-SEASONS with contemporaneous attributes, not players with today's attributes.**
Attributes change every year. Joining career totals to the latest snapshot compares a 22-year-old's
numbers to the attributes he has at 25. This is not a technicality: on interceptions, the
career-totals-plus-latest-snapshot version of this analysis (n=26) returned **Aggression −0.31**,
and the player-season version (n=104) returns **+0.27**. Opposite sign, and the briefing built on
the first one told the manager to ignore Aggression. The tool builds player-seasons.

**3. Check `n` before believing a unit column.** Forwards are the thinnest group in any squad
(6 player-seasons before the Attack bucket merges in attacking midfielders). A single unit column
at n < 15 is a hint, not a result — say so. Trust the POOLED column and cross-unit agreement:
an effect that holds in all three units with the same sign is real; one that appears in a single
column is probably a player.

**5. Filter to the division. Standard changes what an attribute buys.** Frem has climbed from
3. Division to the Superliga, so an unfiltered run pools four standards. Interceptions, pooled:
Aggression runs **+0.34 in the lower divisions and −0.32 in the Superliga**; Strength **+.40 → +.02**.
Positioning stays positive in both (.45 / .22) and so does Tackling (.19 / .47). The tool warns when you pool; pass `--competition '%Superliga%'` (the recipe filters `competition`). Lower `--min-minutes` to ~360 to keep the
sample usable when you narrow it, and say the n.

**4. This is description under OUR instructions, not physics — so check it against `--who
opponents`.** Every "us" row is our players playing our tactic. A **team instruction moves a whole
column at once and is invisible here** — `Work Into Box` changed the squad's SOT rate from 36% to
47-67% without changing anybody's attributes. So before recommending personnel for an effect, ask
whether an instruction does it more cheaply; that has been the right answer twice, for shot quality
(`Work Into Box`) and press intensity (closing down). See
[`scoring-and-shot-quality`](../../../docs/agent-context/scoring-and-shot-quality.md).

  **`--who opponents` is the fix for this trap**, and should be run for any finding you intend to
  act on. It is the same analysis over the players we have faced — 287 player-seasons from 57 clubs
  under 57 managers — so an effect that survives there belongs to the game rather than to our
  tactic. Its coefficients attenuate (we only see an opponent in the 2-4 games he plays us, so each
  observation is a few matches of noise): **compare signs and rank order, never magnitudes**.
  Aerial→headers survives at .52 against our .64-.79; Aggression→interceptions does not survive at
  all, and neither does anything for tackle success % or cross completion %.

## Reading a result honestly
- **A near-zero coefficient may be restriction of range, not absence of effect.** Check the spread
  of the attribute within that unit before concluding it does not matter. Shooting looks irrelevant
  to midfield goals (r=.06) purely because every midfielder we have ever fielded sits between 8
  and 12 — the analysis cannot see what a 16 would do. **The tool now enforces the extreme case
  itself**: a cell whose predictor varies by less than `MIN_SD = 1.5` in that unit prints `·`
  rather than a number, as does one whose outcome never varies (the recipe applies the same
  floor and returns NULL). That is what keeps the five
  keeper attributes — sd ~0.7 among outfielders against a real attribute's ~2.6 — from
  manufacturing "Throwing +0.4 for strikers". It does not catch the milder cases, so keep
  checking.
- **Read the position, not just the unit — then check one against the other.** The three outfield
  units average away opposite effects: Pace against match rating is +0.21 for the whole Attack
  unit, +0.49 at ST and −0.19 at AMC, and the Defence unit's +0.06 is really "what pace does for a
  centre-back" because 111 of its ~199 rows are centre-backs. Per-position correlations are the
  sharpest read where the cut has the sample. They are the sharpest and the
  thinnest read at once — 20-110 player-seasons, usually visible in one cut only — so treat one as
  a direction and corroborate it against the unit. Group the recipe by `position` instead of
  `unit` for that cut.
- **Goalkeepers have their own unit, and a hard limit.** All 23 attributes are covered and the GK
  unit has 59 player-seasons league-wide, but a keeper's match row holds passes and little else —
  no saves, no clean sheets, no goals conceded. Measure his distribution and his rating; say
  plainly that shot-stopping is not in the data.
- **Re-run once a season** and keep the dated tables; the sample grows ~20 player-seasons a year
  and large coefficients on small n will shrink toward the middle.
- **Correlation, not causation, and no controls.** Attributes are correlated with each other
  (fast players are usually agile), so a single column cannot separate them. Report the shape of
  the answer, not a coefficient to two decimals.
- **A negative correlation is usually a role signal, not a defect.** Aerial correlates −0.58 with
  dribbles because aerial players are centre-backs and target men, not because heading stops you
  dribbling. Ask "who has this attribute?" before concluding "this attribute causes that".
- **Cross-check against `site.role_weights`** (lowercase attribute names). An attribute the role is not scored on is noise —
  see [`scouting-attribute-reads`](../../../docs/agent-context/scouting-attribute-reads.md) for the
  Movement/Positioning duel pair that this repeatedly gets wrong.
- **Say the sample size in the report**, every time, next to the number.

## What to hand back
A short table of the 5-8 attributes that matter for the stat asked about, with the per-unit columns
kept (they are often the interesting part — Tackling drives interceptions at +0.75 in midfield and
+0.35 in defence), the `n`, and one sentence on the mechanism. Then the practical call: which
players in the current squad have that profile, and whether a team instruction would do the job
instead:
```sql
SELECT d.name, sm.team_tid, f.age, f.Tackling, f.Positioning, f.Aggression, f.Decisions
FROM mart.squad_membership sm
JOIN mart.fact_player_snapshot f USING (person_id, snapshot_date)
JOIN mart.dim_person d USING (person_id)
WHERE sm.is_current AND sm.is_managed_club
ORDER BY f.Tackling + f.Positioning DESC LIMIT 10;
```
