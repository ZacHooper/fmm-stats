---
name: attribute-profiles
description: Measure how a player's ATTRIBUTES drive his on-pitch STATS — which attributes actually produce interceptions, key passes, headers won, shots on target, dribbles, mistakes or a high rating, computed per positional unit from the career's own match data. Use when the user asks what makes a player do X, which attribute to prioritise for a behaviour, whether an attribute is worth selecting on, what kind of player fits a role or instruction, or wants to sanity-check a football intuition ("does aggression win the ball back?"). Also the right tool before recommending personnel for a specific in-match effect.
---

# Attribute → stat profiles

*What does a player with this make-up actually DO on the pitch?* Ratings and role weights say how
good a player is; this says how he behaves. Use it when the question is about a **behaviour**
(win the ball high, create chances, hit the target, give it away) rather than about quality.

## Run the tool, don't hand-roll it
`scripts/attribute_stat_correlations.py` is the validated implementation. It already handles every
trap below.

```bash
uv run python scripts/attribute_stat_correlations.py                      # every stat
uv run python scripts/attribute_stat_correlations.py --stat intercept_90 --top 10
uv run python scripts/attribute_stat_correlations.py --min-minutes 600
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

## The four traps — all of them have already produced a wrong answer here

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

**4. This is description under OUR instructions, not physics.** Every row is our players playing
our tactic. A **team instruction moves a whole column at once and is invisible here** — `Work Into
Box` changed the squad's SOT rate from 36% to 47-67% without changing anybody's attributes. So
before recommending personnel for an effect, ask whether an instruction does it more cheaply.
That has been the right answer twice: shot quality (`Work Into Box`) and press intensity
(closing down). See [`scoring-and-shot-quality`](../../../docs/agent-context/scoring-and-shot-quality.md).

## Reading a result honestly
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
