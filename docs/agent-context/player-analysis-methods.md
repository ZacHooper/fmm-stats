---
name: player-analysis-methods
description: "Repeatable recipes for player/squad analytical questions (why did the attack collapse, is this prospect worth it, do these two combine) — the data traps that make a naive answer wrong, the methods that worked, and the ones that are underpowered and should not be re-run"
metadata:
  node_type: memory
  type: reference
  originSessionId: 8924d56f-face-5c26-83b3-703d209ceffd
---

Worked recipes for the analytical questions the save actually gets asked — "why did our attack fall
apart", "is this 16-year-old worth signing", "which pairings worked". Read the **Data traps** first:
three of them silently invert an answer, and two of them did invert answers during the session that
produced this doc.

## Data traps (read before querying)

**1. The published mart holds ONE snapshot.** `mart.player_snapshots` in
`site-data/fm-<career>-mart.duckdb` contains only the latest snapshot (~24k rows, one phase). A
player appearing once there is NOT evidence he is new — it is the table's shape. **Per-snapshot
attribute history lives in the FULL store**, `site-data/fm-<career>.duckdb` →
`staging.player_attributes` (~24k players × 20 snapshots ≈ 482k rows). `mart.player_attribute_growth`
also keeps history but is scoped to ~58 own-squad players. Joining the growth table to
`mart.player_snapshots` on `(person_id, snap_ix)` silently keeps only the latest snapshot's rows
(1,242 of 24,081) — join to the full store instead, or derive age from `dob` + `phase_date`.

**2. Only 8 attributes are real save-wide; 15 are model-estimated.** From
`fmparser/attributes.py::EXACT_SINGLE` (+ Teamwork, computed from two exact bytes):

| Exact for every player | Estimated for everyone outside our club |
|---|---|
| Pace, Strength, Stamina, Technique, Aggression, Leadership, Agility, Teamwork | Crossing, Dribbling, Tackling, Shooting, Aerial, Passing, Decisions, Creativity, Movement, Positioning + the 5 GK attrs |

Real values for the estimated 15 exist for ~72 players only (our own squad, historically) — filter
`NOT "<Attr>_est"`. **Scouting rule: on any player outside the club, trust the exact 8 and treat the
rest as a decode.** The estimates are not fabrications: per `fmparser/model.py`, each is a frozen
linear decode of the player's *own* raw byte plus ability terms, ~63% exact / ~93% within ±1. In
particular **Crossing = f(own byte, own×CA) — Technique is NOT an input**, so "does Technique predict
Crossing" is not circular on estimated data. Some others (Dribbling, Shooting, Decisions, Reflexes)
do take `mean9`, which is a mild cross-attribute channel; CA enters most of them, so partial out the
CA-derived **Level %ile** (never the raw number — see [[level-vs-fit-percentile]]) when the question
is "does attribute X matter beyond overall quality".

**3. `mart.squad_current` omits loan players whose spell data lapsed.** Both loanees and recent
signings can read `club_tid = ours` while being absent from `squad_current`, and the site export can
lag the live game. Cross-check against `site/api/core.json`'s `ours.squad_tids` and ask the user.
See [[loan-status-unreliable]].

## Methods that worked

**Phase-split a season around the event, then control with the same opponents.** Cutting 2025 at
Jakobsen's last game and again at the championship-group boundary separated three candidate causes.
The control that settled it: re-run the comparison *restricted to the five championship-group
opponents*, who were also played earlier in the season. Same teams, 1.86 → 1.67 → 0.70 goals/game —
so neither the sale nor "tougher opponents" explained the collapse.

**Age-adjusted percentile — the single most useful move for a young squad.** Raw Level %ile punishes
a 17-year-old for being 17. Rank him instead against players of his own age and position class:

```sql
-- percentile of `lvl` among wide players within a year of `age`
SELECT 100 * avg(CASE WHEN peer.lvl < :lvl THEN 1.0 ELSE 0 END)
FROM pop peer WHERE peer.age BETWEEN :age - 1 AND :age + 1;
```

This reversed two judgements: Bech (17, Level %ile 32.9) is **83rd percentile for his age**, while
Fugl (24, Level %ile 19.0) is **10th** — one is a prospect, the other is finished.

**Project a weak attribute from a strong one via the mature population.** For "he's 16, he'll grow
into it", don't guess — look up what players aged 21+ with his *exact* attribute actually have.
Wide players with Technique 11–13: **6.5 mean Crossing at 15–17, 9.8 at 18–20, 10.5 at 21+**. That
turns "will his Crossing 8 improve" into a number (~+4, landing 11–12). Caveats to state every time:
it is cross-sectional (different players at different ages, not tracked individuals) and the mature
pool has survivorship in it, so it overstates individual growth somewhat.

**Empirical growth-by-age and growth-by-attribute curves.** From `mart.player_attribute_growth` over
our own squad: total attribute points gained per year run ~9–11 at ages 16–20, ~6–8 at 21–22, ~3–5 at
23–24, ~1 at 25. Growth is wildly uneven by attribute — over ~3.3 tracked years the physicals move
most (Stamina +4.4, Strength +4.1, Pace +3.0) and **Technique is effectively frozen (+0.13)**. Use
this before promising that any technical weakness will train out.

## Methods that are underpowered — do not re-run without more seasons

**Pairing / with-or-without-you synergy does not work at this sample size.** Team output when two
players start, with a synergy term (actual − each player's individual effect) so two good players
don't score well merely for being good: across 143 matches and 197 pairs, **zero cleared 2 SE**; best
z was 1.24. Goals/game SD is 1.31, so the noise floor at a 10-game pair sample is ±0.83 while the
effects sought are ±0.3 — underpowered by ~3×. Detecting a +0.3 effect needs ~76 games *together*.

**Individual uplift (does A produce more when B plays) is confounded by squad churn**, not just
noisy. Shots/chances are ~5× more frequent than goals so the error bars close — 11 comparisons
cleared a 95% interval — but every one mapped onto *when* in the season a player featured, because
loans in/out meant different players occupied different phases. Chukwuani's "without Schjelderup"
sample contained **zero** phase-3 minutes and his "without Garly" sample was **85%** phase-3, and his
own creation collapsed in phase 3 — so six "findings" were one form slump wearing different hats.
Always tabulate the with/without split *by phase* before believing an uplift result.

**Small samples can invert a sign, not merely widen the interval.** The Technique↔Crossing
correlation on 41 real-data wide players read 0.568 for under-21s and 0.315 for mature players; on
11,229 estimated-Crossing wide players it reads **0.275 under-21 and 0.555 at 24–27** — the opposite
ordering. When a real-attribute sample is in the tens, prefer the decoded 24k population and say so.

## Reusable setup

Attach both objects — the mart for shaped tables, the full store for `staging` and history:

```python
con.execute("SET enable_progress_bar=false;")          # else progress bars flood tool output
con.execute("INSTALL httpfs; LOAD httpfs;")
con.execute(f"""CREATE SECRET r2 (TYPE s3, KEY_ID '{k}', SECRET '{s}',
    ENDPOINT '{acct}.r2.cloudflarestorage.com', URL_STYLE 'path', REGION 'auto');""")
con.execute("ATTACH 's3://fmm-stats/site-data/fm-frem.duckdb'      AS f (READ_ONLY);")
con.execute("ATTACH 's3://fmm-stats/site-data/fm-frem-mart.duckdb' AS m (READ_ONLY);")
```

`R2_ACCESS_KEY` / `R2_SECRET_ACCESS_KEY` / `R2_ACCOUNT_ID` are already in the environment on a Claude
Code web session (see [[remote-duckdb-access.md]]). `match_player_facts` has no `name` column —
resolve it in a scalar subquery against `at_club_spells` (one row per spell, so `any_value`, never a
join before aggregating).

## Findings from the first run (2025 season, 3F Superliga)

- The attack's collapse was **not** Jakobsen's sale (5 post-sale regular-season games: 1.40 goals,
  *more* shots at 10.0/gm) and **not** opponent quality (same five teams: 1.86 → 1.67 → 0.70). It
  was the supply line in the championship group — Chukwuani's creation 3.20 → 0.77 chances/90,
  Garly injured, Secka's loan ended. Both strikers' shot volume roughly halved.
- Jakobsen was a finisher, not the creator: 5 key passes and 0.56 chances/90 against Chukwuani's
  2.71. Never infer a creative role from goals.
- Schjelderup's 7.39 average rating hid a low-yield profile: 89 crosses at **18%** completion (squad
  high volume, near-worst accuracy) and 0.75 dribbles/90 despite Dribbling 16. Ratings reward
  involvement; check the completion rate and the per-90 of the player's *best* attribute.

See [[level-vs-fit-percentile]], [[loan-status-unreliable]], [[etl-duckdb-dashboard]],
[[remote-duckdb-access]], [[match-rating-position-bias]].
