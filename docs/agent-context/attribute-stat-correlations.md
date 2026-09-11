# What attributes actually make a player DO things

**Computed 2026-09-11 on the `frem-2026-03-22` snapshot: 104 player-seasons at ≥450 competitive
minutes (Defence 45, Midfield 37, Attack 22).** Regenerate rather than quote after any import:

```bash
uv run python scripts/attribute_stat_correlations.py --top 8
```

Method, and the four traps that have each produced a wrong answer here, are in the
[`attribute-profiles`](../../.claude/skills/attribute-profiles/SKILL.md) skill. The short version:
one row per (player, season) with **that season's** attributes; every correlation computed **inside
a positional unit**; POOLED is unit-demeaned. Ratings/role weights say how good a player is — this
says how he behaves.

## The headline table (POOLED, unit-demeaned)

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
