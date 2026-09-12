---
name: attribute-profiles
description: Measure how a player's ATTRIBUTES drive his on-pitch STATS — which attributes actually produce interceptions, key passes, headers won, shots on target, dribbles, mistakes or a high rating, computed per positional unit from the career's own match data. Use when the user asks what makes a player do X, which attribute to prioritise for a behaviour, whether an attribute is worth selecting on, what kind of player fits a role or instruction, or wants to sanity-check a football intuition ("does aggression win the ball back?"). Also the right tool before recommending personnel for a specific in-match effect.
---

# Attribute → stat profiles

*What does a player with this make-up actually DO on the pitch?* Ratings and role weights say how
good a player is; this says how he behaves. Use it when the question is about a **behaviour**
(win the ball high, create chances, hit the target, give it away) rather than about quality.

## There is a dashboard for this — offer it
[**The Attribute Lab**](https://claude.ai/code/artifact/bae40c5f-a50a-485b-b4be-3d2735e2a5f5) is
the explorable version: every statistic against every attribute, per unit, across the four
measurements — plus a workbench for rewriting a role's weights with the measured evidence beside
each slider, the squad re-ranking live underneath, and outcome presets ("build this role to win
it back / create / finish") that derive weights from the correlations instead of from taste.

Rebuild its data after an import, and re-verify the arithmetic, then republish the page:
```bash
uv run python scripts/export_attribute_lab.py                    # -> site-data/lab.json
uv run python scripts/check_rating_parity.py site-data/lab.json  # must PASS
```
`check_rating_parity.py` asserts the page computes `base_rating`/`eff` identically to
`mart.player_position_fit`. CLAUDE.md requires that equality and, until this was written, no
committed test enforced it. **A weight-set built in the Lab** comes back via
`scripts/import_weight_set.py` (writes `state/weights/<name>.json`, which syncs to R2; `--promote`
makes it a real method in `staging.role_weights`).

## Run the tool, don't hand-roll it
`scripts/attribute_stat_correlations.py` is the validated implementation. It already handles every
trap below.

```bash
# ALWAYS filter to the division you are playing in — see trap 5
uv run python scripts/attribute_stat_correlations.py --competition '%Superliga%' --min-minutes 360
uv run python scripts/attribute_stat_correlations.py --competition '%Superliga%' --stat intercept_90 --top 10
uv run python scripts/attribute_stat_correlations.py                      # pooled; prints a warning
uv run python scripts/attribute_stat_correlations.py --csv /tmp/attr.csv  # long-form for further cuts
```
Remote session with no local store: `rclone copy r2:fmm-stats/site-data/fm-frem.duckdb "$SCRATCH"`
then pass `--db "$SCRATCH/fm-frem.duckdb"`. Pull the **full** store, not `-mart` (no rating layer).

Stats available: `intercept_90 tackW_90 tackA_90 keyPass_90 assists_90 goals_90 shotA_90 shotO_90
passA_90 passC_90 headA_90 headW_90 crossA_90 crossC_90 dribbles_90 mistakes_90`, the ratios
`pass_pct sot_pct head_pct tack_pct cross_pct`, and `rating`.

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
Positioning stays positive in both (.45 / .22) and so does Tackling (.19 / .47). The tool warns when you pool; pass `--competition '%Superliga%'`. Lower `--min-minutes` to ~360 to keep the
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
  and 12 — the analysis cannot see what a 16 would do.
- **Re-run once a season** and keep the dated tables; the sample grows ~20 player-seasons a year
  and large coefficients on small n will shrink toward the middle.
- **Correlation, not causation, and no controls.** Attributes are correlated with each other
  (fast players are usually agile), so a single column cannot separate them. Report the shape of
  the answer, not a coefficient to two decimals.
- **A negative correlation is usually a role signal, not a defect.** Aerial correlates −0.58 with
  dribbles because aerial players are centre-backs and target men, not because heading stops you
  dribbling. Ask "who has this attribute?" before concluding "this attribute causes that".
- **Cross-check against `mart.role_weights`.** An attribute the role is not scored on is noise —
  see [`scouting-attribute-reads`](../../../docs/agent-context/scouting-attribute-reads.md) for the
  Movement/Positioning duel pair that this repeatedly gets wrong.
- **Say the sample size in the report**, every time, next to the number.

## What to hand back
A short table of the 5-8 attributes that matter for the stat asked about, with the per-unit columns
kept (they are often the interesting part — Tackling drives interceptions at +0.75 in midfield and
+0.35 in defence), the `n`, and one sentence on the mechanism. Then the practical call: which
players in the current squad have that profile
(`db.squad_frame(S, P, method, [db.MANAGED_CLUB_TID])` carries the 23 attributes), and whether a
team instruction would do the job instead.
