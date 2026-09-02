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

**RETRACTED — do not use.** An earlier version of this section recommended looking up mature
(21+) players who share a *different* attribute (Technique) as a way to project a weak one
(Crossing) forward — "wide players with Technique 11–13 average 10.5 Crossing at 21+, so his
Crossing 8 should land around 11–12". That method is now known to overstate growth by roughly
3×, for the reason below, and is replaced by the "current value + age" lookup that follows.

**Forecast an attribute from ITS OWN current value + age — not from a different attribute.**
Tracking the SAME players longitudinally (25,635 players × 20 snapshots, 2021→2025) rather than
comparing different players cross-sectionally: current value alone predicts the future value
well (R²=0.85 for Crossing 4 years out, n=11,829). Holding current Crossing fixed, adding
Technique to the model gains **+0.000 R²** — a technical player is already ahead at 17 and stays
ahead; growth doesn't re-sort the field. So the retracted method's real driver was never
Technique, it was that high-Technique players already had higher Crossing at the start, and the
cross-sectional design let a mature high-Technique population's *survivorship* pass for growth.
Direct year-over-year tracking of a 17-year-old with Crossing 6–8 gives **~9.7 at 21** (wide
players only, exact starting value, n≈100–130 per cell) — about +1.5 to +2, not +4. This is now
shipped as `mart.attribute_forecast` (one row per attribute/age-now/value-now/horizon), exported
as `site/api/forecast.json` and surfaced on the site's Development tab and player profiles —
prefer reading it there over re-deriving this by hand.

**Empirical growth-by-age curve, and which attributes don't move at all.** Total attribute points
gained per year (year-over-year pairs, whole save): median 8 at 16, 7 at 18, 4 at 20, 3 at 22, 1
at 24, ~0 at 28. Growth is wildly uneven by attribute, and two are worth calling out explicitly:
**Agility never moves (0.00/yr at every age) and Technique is next to frozen (~0.02–0.04/yr)** —
confirmed on our squad's real attribute values, not just the decode. A third group only *looks*
frozen: the decode compresses Movement, Positioning and Aerial 8–24× relative to their real
growth (measured on our squad's real values vs the world's decoded ones), so treat those as
unmodelled rather than as further frozen attributes — `mart.attribute_forecast`'s `bucket` column
makes this split (`forecastable` / `fixed` / `unmodelled`) rather than leaving it to eyeballing.

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
(This correlation is real but describes the *level* relationship between Technique and Crossing,
not a growth-rate one — see the retraction above for why conflating the two overstated a forecast.)

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
