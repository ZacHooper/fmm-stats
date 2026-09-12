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

Or explore it interactively in **[The Attribute Lab](https://claude.ai/code/artifact/bae40c5f-a50a-485b-b4be-3d2735e2a5f5)**,
which also carries a workbench for rebuilding a role's attribute weights from this evidence
(`scripts/export_attribute_lab.py` builds its data; `scripts/import_weight_set.py` brings a
weight-set back into the store).

**All 23 attributes are covered as of 2026-09-12**, and there is now a GK unit. Two rules make
that safe; figures below that predate the re-run do not reflect them.

### Blank cells are a feature: the sd floor

A predictor with almost no variance does not yield a reassuring zero — one stray value drives the
coefficient. Standard deviation within outfield units:

| | min | median | max |
|---|---|---|---|
| The 18 real attributes | 1.85 | 2.64 | 3.64 |
| The 5 keeper attributes | 0.56 | 0.72 | 1.14 |

No overlap: outfielders average 1.5–2.3 on Handling/Reflexes/Throwing against a real keeper's
10–12. So `attribute_stat_correlations.py` **blanks any cell whose predictor varies by less than
`MIN_SD = 1.5` in that unit**, blanks any cell whose *outcome* never varies (keepers score no
goals), and pools only over the units where the attribute does vary. Without the last rule a
keeper attribute pools outfielders' 1–2 jitter with keepers' real 10–12 and reports a coefficient
that is nothing but the gap between the two groups.

This is the **restriction-of-range** caveat below, finally enforced in code rather than left to
whoever is reading. If a future squad's midfielders all sit between Shooting 8 and 12, that cell
blanks itself.

### Unit averages hide opposite effects — read the position too

The three outfield units are coarse, and inside them attributes can point opposite ways. Pace
against match rating, league-wide:

| | unit says | positions inside it |
|---|---|---|
| **Attack** | +0.21 | ST **+0.49** · AML +0.32 · AMR −0.24 · AMC **−0.19** |
| **Defence** | +0.06 | DL +0.22 · DR +0.26 · **DC +0.04 (n=111)** |

The Defence row is the clearest: 111 of its ~199 player-seasons are centre-backs, so the column is
effectively "what pace does for a centre-back" — nothing — and the full-backs' real effect never
appears. Same trap on interceptions, where **DR reads +0.40 and the Defence unit reads +0.07**.

So the export now emits **per-position correlations alongside per-unit ones**, wherever the cut has
`MIN_N` players at that position. Availability is uneven and the export states it per cut:

| cut | positions with n ≥ 12 |
|---|---|
| League · all | DC 111 · GK 59 · MC 57 · DR 44 · DL 43 · ST 40 · AMC 32 · DMC 29 · AML 25 · AMR 19 |
| League · Superliga | DC 38 · GK 22 · DMC 15 · DR 14 · MC 14 |
| Us · all | DC 20 · MC 20 · DR 13 |
| Us · Superliga | none |

**A position view is the sharpest and the thinnest read at once.** Twenty to a hundred
player-seasons is a direction, not a measurement, and usually only one cut can see it at all — so
nothing corroborates it. Check it against the unit before acting.

### Pace: the worked example

Pace is where this matters most, because the unit view makes it look inert. By position, against
match rating, and again controlling for the game's own ability model (`level_league`, i.e. *among
players of the same Level %ile at that position*):

| position | n | raw | controlled for ability |
|---|---|---|---|
| **ST** | 39 | **+0.51** | **+0.44** |
| AML | 25 | +0.32 | +0.36 |
| DR | 43 | +0.30 | +0.33 |
| DL | 41 | +0.22 | +0.21 |
| MC | 58 | +0.18 | +0.16 |
| DC | 111 | +0.06 | +0.07 |
| GK | 59 | −0.01 | −0.01 |
| **AMC** | 31 | −0.19 | **−0.16** |

It survives the control, so it is not a proxy for "good player". And it is emphatically *not* good
everywhere — at AMC, who receives in front of the defence with no space to run into, it is
negative.

**Why the community says pace is king.** Against `level_league` within position, Pace averages
**−0.01** across positions while Technique averages +0.29, Passing +0.22 and Decisions +0.16. The
game's ability model barely charges CA for pace — so a pacy striker delivers performance the model
does not price. That also means **our own Level %ile scouting understates pacy strikers.**

**And it is the best evidence that off-the-ball work is real but invisible here.** Pace barely
touches the counting stats (goals +0.21 in attack, shots on target ~0, key passes −0.01) yet
predicts a striker's match rating at +0.51. That gap is the off-the-ball running: no stat records
it, and rating is the only measure that sees it.

### The GK unit, and what it cannot tell you

GK player-seasons: **league/all 59, league/Superliga 22, us/all 7, us/Superliga 2** — usable in
the league cuts, not in ours. But a keeper's match row holds `passA ≈ 21.7`, `intercept ≈ 0.47`
and essentially nothing else: **no saves, no clean sheets, no goals conceded**. So the unit
answers "does Kicking predict his distribution" and "what predicts his match rating", and
**nothing about shot-stopping**. One result worth having already: **Kicking → pass completion %
is −0.24 for keepers** — the better kickers get asked to hit longer passes, which complete less
often.

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

## The first weighting this changed: `frem_attacking_ss` / ST

The point of the file. Scored **within role** against what strikers actually produced (league
player-seasons, n=40, correlation of the weighted attribute total with goals):

| weight-set | r vs goals |
|---|---|
| the old ST weights | **0.351** |
| flat — every attribute 1 | 0.411 |
| the new ST weights | **0.484** |
| Shooting alone | 0.469 |

The old set was **worse than not weighting at all**, because it came from forum consensus rather
than measurement: Aggression 4, Stamina 4, Movement 4 and Shooting only 3. Shooting is the one
attribute that predicts shots, shots on target and goals in every cut. Nearly all of the gain is
Shooting — the rest of the set is tidy-up rather than discovery, which is worth remembering before
the next rewrite.

New set (`seeds/role_weights.csv`): shooting 4; aerial, decisions, pace, strength 3; agility,
movement, technique 2; **aggression, passing, stamina, teamwork dropped to baseline 1**.

Two caveats recorded deliberately:
- **Movement is held at 2 on the manager's judgement, not the data.** Measured it contributes
  nothing (sd 1.66, range 8-15 across our strikers; removing it costs 0.007). Off-the-ball work is
  the one thing the match stats cannot see, so this is a reasonable place to keep a thumb on the
  scale — but it is a belief, not a measurement, and should be labelled that way.
- **Pace at 3 is a position-specific call.** Pace correlates +0.51 with a striker's goals (+0.44
  controlled) but +0.06 for centre-backs and −0.19 at AMC, and it barely moves Level %ile (−0.01
  against Technique's +0.29) — so the game charges little CA for it and our Level-%ile scouting
  *understates* pacy strikers. Do not generalise the 3 to other roles without measuring them.

It re-ranked our strikers immediately. Our actual current squad at ST (`mart.squad_current`, not
a raw `club_tid` filter — which pollutes the list with departed loanees):

| | old | new |
|---|---|---|
| 1 | Nordberg 477.8 | **Ementa 409** |
| 2 | Ementa 476.0 | Olesen 403 |
| 3 | Olesen 459.0 | Nordberg 390 |

Ementa up one, Nordberg down two: Shooting 11 against Ementa's 15, and the Aggression 15 the old
set paid 4 for now counts once. His Pace 16 (now weighted 3, against Ementa's 12) wins some of it
back — it is not enough.

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
