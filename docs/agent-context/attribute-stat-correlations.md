# What attributes actually make a player DO things

**Computed 2026-09-11 on the `frem-2026-03-22` store.** Four cuts, because a single one has twice
produced a claim that did not survive contact with a second:

| cut | what it is | n (player-seasons) |
|---|---|---|
| **US all divisions** | our players, ≥450 mins, every competition pooled | 104 |
| **US Superliga** | our players, ≥360 mins, top flight only | 41 |
| **US lower divs** | our players, ≥360 mins, 2./3. Division + NordicBet | 44 |
| **OPPONENTS** | players we have faced, ≥180 mins | 287 |

```bash
uv run python scripts/attribute_stat_correlations.py --competition '%Superliga%' --min-minutes 360
uv run python scripts/attribute_stat_correlations.py --who opponents --min-minutes 180
```

Method and traps: the [`attribute-profiles`](../../.claude/skills/attribute-profiles/SKILL.md)
skill. One row per (player, season) with **that season's** attributes; correlations computed
**inside a positional unit**; the figures below are unit-demeaned pools.

## Why the OPPONENTS cut is the important one

Every "us" figure is our players under **our** instructions — the single biggest caveat on this
whole exercise. The opponents cut is the same analysis on players from **57 different clubs under
57 managers**, so an effect that appears there is a property of the game rather than of
`frem_attacking_ss`. It is the out-of-sample check.

**Its coefficients are systematically smaller and that is expected, not a weaker result.** We only
see an opponent in the 2-4 games he plays us, so each observation is a few matches of noise, which
attenuates every correlation toward zero. **Compare signs and rank order with the "us" cuts, never
magnitudes.**

## What replicates in all four cuts — trust these

| Effect | US all | US SL | US low | OPP |
|---|---|---|---|---|
| **Aerial → headers won** | **.70** | **.64** | **.79** | **.52** |
| Strength → headers won | .55 | .64 | .44 | .29 |
| **Aerial → header win %** | .66 | .67 | .64 | .32 |
| **Shooting → shots on target** | **.61** | **.81** | .41 | **.32** |
| **Shooting → goals** | .45 | .60 | .32 | .33 |
| Aerial → dribbles | −.59 | −.57 | −.54 | −.24 |
| Pace / Dribbling / Movement → dribbles | +.49/.38/.31 | +.49/.47/.44 | +.46/.41/.49 | +.17/.21/.21 |
| **Positioning → interceptions** | .36 | .22 | .45 | .20 |
| **Tackling → interceptions** | .30 | .47 | .19 | .14 |
| Strength → key passes | −.38 | −.39 | −.35 | −.03 |

**Two solid negatives, confirmed on an independent sample:**

- **Nothing predicts tackle success %.** The largest coefficient anywhere is Passing −.41 in the
  Superliga (n=41) and it is ~0 in the other three cuts.
- **Nothing predicts cross completion %.** Same story.

Do not build a selection argument on either ratio.

## What does NOT replicate — do not act on these

| | US all | US SL | US low | OPP |
|---|---|---|---|---|
| **Aggression → interceptions** | +.09 | **−.32** | **+.34** | −.01 |
| Aggression → SOT % | .22 | .55 | .07 | .05 |
| Passing → key passes | .27 | .65 | .16 | .07 |

**Aggression on interceptions swings from −.32 to +.34 depending on the cut.** An earlier version
of this file reported it as "+0.45 in the lower divisions, −0.06 in the Superliga" and drew a story
about bullying the ball off lower-league midfields. The direction of the division contrast held
when the position bucketing was corrected, but the coefficients moved by 0.3 and the pooled figure
went from +.27 to +.09. **The honest read is that Aggression has no reliable effect on
interceptions.** Positioning and Tackling do, in all four cuts. That is the finding.

## Practical conclusions

1. **Shooting is the attribute to recruit for.** The only one that runs the whole chain — shots,
   shots on target, goals — in every cut including out-of-sample.
2. **Aerial is the most reliably measurable attribute in the game**, and it is a *role label* as
   much as a skill: strongly positive for headers, strongly negative for dribbles, crosses and
   assists. Read a big Aerial coefficient as "this is a centre-back or a target man" first.
3. **Interceptions are Positioning + Tackling, and forwards cannot supply them** — 0.5–1.4 per 90
   against 6–7 for centre-backs. Press intensity is a team instruction, not a selection.
4. **`SOT %` is nearly attribute-free while `shots on target` is attribute-dominated.** *Who shoots*
   is a player property; *how well the team shoots* is `Work Into Box`. See
   [`scoring-and-shot-quality`](scoring-and-shot-quality.md).

## Our XI's attributes do NOT predict what we concede

Match-level test (n=166 with a resolvable starting XI, 54 in the Superliga): mean attributes of our
starting outfield ten against opponent shots, shots on target and goals.

- **Pooled across divisions, every attribute correlates POSITIVELY with shots conceded** (.14 to
  .33). That is not a finding — it is the division confound. Our squad's attributes rose as we
  climbed, and so did the quality of who we faced.
- **Within the Superliga alone it collapses**: the largest |r| is .29 (Stamina) and nothing else
  clears .21. Tackling (−.19 on SOT conceded, −.18 on goals) and Positioning (−.13 on goals) point
  the sensible way but are far too small at n=54 to act on.

**What we concede is about the opponent and our instructions, not about which of our players
start.** Consistent with everything else here: the defensive dials are team settings.

## Two failure modes this file has already hit

**Restriction of range — a zero can mean "we have never had one".** Shooting drives midfielders'
shots (.72) and shots on target (.76) but not their goals (.06). Every midfielder we have fielded
sits between Shooting 8 and 12, so there is no variance to detect an effect in. The cost is
visible directly: Garly (Shooting 9) has **37 Superliga shots and 0 goals in 4,089 minutes**, and
Chukwuani (9) converts 12% of his shots against Ementa's 21% and Jakobsen's (17) 26%. Check the
spread within the unit before reading a near-zero as "does not matter".

**Position bucketing moves coefficients at low n.** Switching from `match_player_facts.unit` (which
records where a player lined up in one arbitrarily-chosen match) to primary position from
`mart.player_position_levels` moved the Superliga Positioning-on-interceptions figure from .65 to
.22. The current script uses `player_position_levels`, which is stable and covers every club. Treat
any single-cut coefficient at n≈40 as indicative only.

## Re-run once a season

The sample grows ~20 player-seasons a year (ours) and ~90 (opponents). Re-run after each season-end
import, keep the dated tables, and expect large coefficients on small n to shrink toward the middle.
A finding that survives three seasons *and* the opponents cut is worth building a recruitment rule on.
