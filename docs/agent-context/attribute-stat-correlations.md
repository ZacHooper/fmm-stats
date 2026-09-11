# What attributes actually make a player DO things

**Computed 2026-09-11 on the `frem-2026-03-22` snapshot.** Two reads, because *the division
changes the answer* (see below): **all competitions pooled** = 104 player-seasons at ≥450 minutes
(Defence 45, Midfield 37, Attack 22); **3F Superliga only** = 41 player-seasons at ≥360 minutes
(Defence 18, Midfield 15, Attack 8). Regenerate rather than quote after any import:

```bash
uv run python scripts/attribute_stat_correlations.py --competition '%Superliga%' --min-minutes 360
uv run python scripts/attribute_stat_correlations.py --top 8      # pooled, warns about mixing
```

## ⚠️ Standard changes what an attribute buys — filter by division

Frem has climbed 3. Division → 2. Division → NordicBet Liga → 3F Superliga, so an unfiltered run
mixes four standards. On interceptions the two eras disagree sharply:

| pooled, interceptions/90 | **3F Superliga** (n=41) | lower divisions (n=44) | both (n=104) |
|---|---|---|---|
| **Positioning** | **.65** | **.51** | **.51** |
| Tackling | **.74** | .25 | .49 |
| **Aggression** | **−.06** | **+.45** | +.27 |
| Strength | .15 | .40 | — |
| Decisions | .31 | −.01 | .28 |
| Movement | −.69 | −.19 | −.43 |

**Positioning is the only stable one.** Aggression and Strength win the ball in the lower leagues
and stop working in the top flight; Tackling triples in importance going the other way. The
plausible reading is that you can bully the ball off a 3. Division midfield and cannot bully it off
a Superliga one. **The pooled +0.27 for Aggression is an artefact of mixing divisions** — it is
entirely a lower-league effect, and quoting it at a Superliga squad is wrong.

**So: always pass `--competition` for the division you are actually playing in.** The tool prints a
warning when you don't.

Method, and the four traps that have each produced a wrong answer here, are in the
[`attribute-profiles`](../../.claude/skills/attribute-profiles/SKILL.md) skill. The short version:
one row per (player, season) with **that season's** attributes; every correlation computed **inside
a positional unit**; POOLED is unit-demeaned. Ratings/role weights say how good a player is — this
says how he behaves.

## The headline table — ALL COMPETITIONS POOLED (unit-demeaned)

*For a Superliga-only
read of the rows that shift most, see the division table above and re-run with `--competition`.*

| Stat | drives it ▲ | suppresses it ▼ | note |
|---|---|---|---|
| **Interceptions** | **Positioning .51**, Tackling .49, Decisions .28, Aggression .27 | Movement −.43, Dribbling −.37 | Tackling is far stronger in midfield (**.75**) than defence (.35) |
| **Tackles attempted** | Agility .35, Passing .25, Pace .23, Stamina .23 | Strength −.27 | in midfield it's Stamina .49 / Passing .40 — volume is a legs stat |
| **Tackle success %** | *nothing above .10* | Passing −.17, Shooting −.17 | **no attribute predicts winning the tackles you attempt** |
| **Headers won** | **Aerial .67**, Strength .55, Shooting .34, Decisions .31 | Agility −.32, Dribbling −.31 | the cleanest, most consistent effect in the file |
| **Header win %** | **Aerial .62**, Tackling .38, Strength .32 | Dribbling −.35, Movement −.34, Pace −.31 | holds at .63/.68/.64 across all three units |
| **Passes attempted** | Passing .28, Teamwork .27, Positioning .24, Aggression .24 | Dribbling −.27 | positional, mostly: who the ball goes through |
| **Pass completion %** | **Aggression .39**, Positioning .28, Teamwork .26 | **Pace −.42**, Dribbling −.28, Movement −.26 | fast, direct players give it away; see caveat below |
| **Key passes** | **Agility .39**, Passing .33, Technique .29 | Strength −.35, Aerial −.25 | small, nimble creators — not strong ones |
| **Dribbles** | **Pace .50**, Dribbling .47, Movement .43 | **Aerial −.58**, Strength −.40, Tackling −.39 | |
| **Crosses attempted** | Pace .52, Dribbling .46, Movement .37 | **Aerial −.53**, Positioning −.35 | a wide-player signature, not a skill |
| **Cross completion %** | *nothing above .20* | — | **no attribute predicts a cross finding a man** |
| **Shots attempted** | **Shooting .56**, Strength .25, Aerial .22 | Tackling −.15 | in Attack alone: Shooting **.75** |
| **Shots on target** | **Shooting .62**, Strength .32, Aerial .27 | Agility −.17 | Attack: Shooting **.82** — the strongest single number here |
| **SOT %** | Aggression .20, Shooting .17, Teamwork .13 | — | **weak — accuracy is an instruction, not a player** |
| **Goals** | **Shooting .43**, Strength .32, Aerial .30 | Agility −.26 | Attack: Shooting .70, Strength .72, Aerial .63 |
| **Assists** | Pace .27, Technique .18 | **Aerial −.39**, Strength −.24 | |
| **Mistakes** | Agility .36, Pace .36, Passing .23 | **Aerial −.37**, Strength −.32 | reads as "small quick players carry the ball more" |
| **Match rating** | Shooting .32, Movement .23, Dribbling .19 | Tackling −.12 | attacking output is what the game rewards |

## Re-run once a season

The sample grows by ~20 player-seasons a year and the Superliga read is currently n=41, so
coefficients will move. Re-run after each season-end import, keep the dated table, and treat a
finding that survives three seasons differently from one seen once. Expect the extremes to shrink
toward the middle as n grows — a correlation of .74 on 41 observations is not a .74 on 200.

## ⚠️ Restriction of range: a zero can mean "we have never had one"

In the Superliga read, Shooting drives midfielders' shots (.72) and shots on target (.76) but
**not their goals (.06)**, where the same attribute converts all the way through for defenders
(.61) and attackers (.66). That is not evidence that a shooting midfielder is worthless. **Our
midfielders' Shooting ranges from 8 to 12** — Tjørnelund at 12 is the highest we have ever fielded
— so there is no variance for the analysis to find. What the data actually shows is the cost of
that: Garly (Shooting 9) has taken **37 Superliga shots and scored 0** in 4,089 minutes, and
Chukwuani (Shooting 9) converts 12% of his shots against Ementa's 21% and Jakobsen's (Shooting 17)
26%.

**Before reading any near-zero coefficient as "this attribute doesn't matter here", check the
spread of that attribute within the unit.** A flat line across a range of 8-12 says nothing about
what a 16 would do.

## The five conclusions worth acting on

1. **Interceptions are a Positioning + Tackling stat, and forwards cannot supply them.**
   Per-90 interception rates by unit are roughly 6–7 (centre-backs), 4–6 (full-backs), 2.4 (central
   midfielders), **0.5–1.4 (forwards and wide attackers)**. Selecting forwards for ball-winning
   attributes buys ~1 interception; the count comes from the back five regardless. Press intensity
   is the lever, and it is a team instruction.

2. **Nothing predicts tackle success % or cross completion %.** Two of the most-quoted "quality"
   ratios in a match report are, on this data, noise with respect to attributes. Do not build a
   selection argument on either.

3. **Shooting is the one attribute that behaves like a superpower.** It drives shots (.56),
   shots on target (.62) and goals (.43) pooled, and .75/.82/.70 within Attack. Combined with the
   league-wide finding that SOT predicts goals at r=+0.72, the recruitment implication is blunt:
   for a forward, Shooting is the attribute.

4. **Aerial is the great divider.** Positive for headers (.67) and goals (.30); strongly negative
   for dribbles (−.58), crosses (−.53), assists (−.39) and mistakes (−.37). It is not causal —
   it is identifying centre-backs and target men. Treat every large Aerial coefficient as a role
   label first.

5. **`SOT %` is almost attribute-free (nothing above .20) while `shots on target` is
   attribute-dominated.** That is the whole shot-quality story in two rows: *who shoots* is a
   player property, *how well the team shoots* is `Work Into Box`. See
   [`scoring-and-shot-quality`](scoring-and-shot-quality.md).

## Caveats that matter for reading the table

- **Correlations are uncontrolled and attributes co-vary.** "Pass completion % ▲ Aggression .39 /
  ▼ Pace −.42" almost certainly means *slow deep midfielders keep it, fast wide players don't* —
  a position effect surviving inside the unit buckets, not evidence that aggression improves
  passing. Report the shape, never a mechanism you haven't argued for.
- **Attack n=22 is thin** and merges attacking midfielders with forwards (only 6 player-seasons are
  true forwards). Single-unit columns there are hints.
- **Everything is measured under our own instructions.** A whole column moves when an instruction
  changes and nothing here will show it.
- **A prior version of this analysis got Aggression-on-interceptions backwards** (−0.31 vs the
  correct +0.27) by using career totals joined to the latest snapshot with n=26. Player-seasons
  with contemporaneous attributes is not a refinement, it is the difference between the right and
  the wrong sign.
