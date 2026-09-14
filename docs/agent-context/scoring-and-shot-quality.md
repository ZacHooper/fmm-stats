---
name: scoring-and-shot-quality
description: "What actually drives Frem's goals — shots ON TARGET, not shot volume; and playing a centre-forward. Includes the plausible-sounding hypotheses that were tested and failed, so they are not re-derived."
metadata:
  node_type: memory
  type: reference
---

Written after a season-long "why can't we score" investigation that produced two durable results and
killed four attractive-looking ones. The negative results are the more valuable half — each was
compelling enough to have been written into a briefing before it was tested.

Method: `staging.match_player_stats` aggregated per match. **Read trap 4 in
[[player-analysis-methods]] first** — one match is stored under up to five `anchor`s and the obvious
dedup is a no-op.

## 1. Shots ON TARGET is the whole story; shot VOLUME is not

Correlations with goals scored, n=427 matches:

| | vs goals | vs shots |
|---|---|---|
| **Shots on target** | **+0.72** | — |
| **SOT rate** | **+0.52** | — |
| Shots | +0.46 | — |
| Pass completion % | +0.27 | +0.33 |
| Crosses completed | +0.23 | **+0.50** |
| Key passes | +0.20 | +0.37 |
| Mistakes | −0.18 | — |
| Aerials won | **−0.23** | −0.11 |

Bucketing by SOT rate settles it — **volume is flat and goals triple**:

| SOT rate | Games | Shots | Goals |
|---|---|---|---|
| worst (16%) | 117 | 8.0 | 0.80 |
| 2nd (36%) | 98 | 8.4 | 1.43 |
| 3rd (48%) | 108 | 9.1 | 1.98 |
| best (65%) | 104 | 8.5 | **2.71** |

We take ~8 shots a game almost regardless of what we do. **Chasing more attempts is a dead end;
chance quality is the entire lever.** Crossing is the trap that makes this concrete — it correlates
+0.50 with shots and only +0.23 with goals, i.e. more shots, not better ones.

**The in-game lever is the team instruction `Work Into Box` (vs `Shoot On Sight`)**, not team
selection. With it set, our worst-accuracy shooters simply stopped shooting and the SOT rate went
from a 36.2% season average to 47–67% across three matches. Diagnosing this as "stop picking players
who shoot badly" wasted weeks.

## 2. Play a centre-forward — worth ~0.66 goals a game

Starting XIs since 2024-07, split on whether anyone started at `FC`:

| | Games | Goals | Shots | SOT% |
|---|---|---|---|---|
| **Strikerless** | 18 | **0.78** | **6.39** | **36.0%** |
| **With a centre-forward** | 169 | **1.44** | 3.83 | **42.5%** |

Monotonic in how many are fielded: **0 → 0.78, 1 → 1.21, 2 → 1.55** goals/game. Note the strikerless
row's shape — *more* shots, *worse* accuracy, *fewer* goals, which is finding 1 restated: without a
focal point we manufacture attempts from bad positions.

**It shows up in points, not just goals** — re-cut on the 2025+ squad only (62 stats-bearing
first-team matches), which is the personnel any current briefing is actually picking from:

| starting FCs | Games | Goals/g | Conceded/g | Points/g |
|---|---|---|---|---|
| 0 (strikerless) | 10 | 0.70 | 1.40 | **0.90** |
| 1 | 31 | 1.45 | 1.19 | 1.32 |
| 2 | 21 | 1.62 | 1.05 | **1.95** |

Two forwards is also the *better defensive* row, which kills the "but it leaves us open" objection.
The strikerless bucket is only 10 games here — the 0.90 ppg is soft — but it points the same way as
the 18-game goals cut above, and no cut of this save has ever had strikerless ahead.

## 3. Tested and FAILED — do not re-derive these

- **Aerial dominance does not produce goals.** Team aerial win rate vs goals: **r = +0.03** over 563
  matches, and goals/game are flat (1.69/1.72/1.65/1.75) across every quartile. Aerials *won*
  correlates **−0.23** with goals. It does predict shots (4.2 → 8.0 per game worst to best quartile)
  — volume again, not quality. A vivid four-game sequence (striker's aerial win rate 75/71/50/30 →
  goals 3/2/0/0) looked like a law and is coincidence.
- **"Crosses need a target in the box" is false.** Cross completion is **20.4% strikerless vs 21.6%
  with a striker** — no difference. A 45%-completion game exists but is an outlier, not a mechanism.
- **Opponent ball-winning barely suppresses us.** Opponent tackles-won + interceptions vs our shots:
  **r = −0.30**; vs our goals: **−0.04**, with non-monotonic buckets. Three consecutive opponents
  whose best defender racked up 11, 16 and 12 interceptions against us looked like a pattern; the
  52-match test does not support it.
- **Our own interceptions do not predict results.** This is the mirror of the bullet above and it
  died the same way. A scouting note called interceptions "the clearest in-match dial we have" off
  an 8-match per-opponent split (wins 43 and 38, losses averaging 32.3). Over **176** of our own
  stats-bearing matches, interceptions vs points is **r = +0.044** — wins 33.8, draws 34.1, losses
  32.7 — and league-wide (351 matches, every club) **r = +0.093**. The differential is marginally
  better (+0.17 league-wide) and still not something to steer a game plan by. It is not even a
  "we're chasing the ball" artifact: interceptions correlate *positively* with our own pass volume
  (+0.21 to +0.25). The counterexample that prompted the test: a 2-0 home win over FC København on
  ~31 interceptions — below that fixture's *loss* average — while FCK made 39 and lost.
- **"Cross a lot when the target man plays" is tempting and does not survive as a PLAN.** A 0-6 with
  31 crosses, 13 corners and four goals from a striker who won 8 of 14 duels made this look like a
  lever. Cut properly on 2025+ starts: with Ementa starting, games of 20+ crosses average **2.13
  goals** against 1.14 with fewer — but also **1.50 conceded** against 1.08, and **1.25 ppg against
  1.50**, over just 8 games. Without him the split vanishes entirely (1.50 vs 1.57). So heavy
  crossing marks an open game, not a won one, and the headline result is finding 1 restated: that
  match was **9 shots on target from 13** (a 69% SOT rate against a 38.5% season average, the 2nd
  highest SOT count in 176 matches). The actionable residue is a negative one, in
  [[scouting-attribute-reads]]: do not *rule out* the aerial route on two named opponent centre-backs
  — just don't sell crossing as the mechanism either.

  **Re-tested 2026-04, and the negative result is stronger than "not a plan" — cross volume is
  close to inert.** Over **166 competitive matches** (2026 store, `our_match_history`):
  `corr(crosses, goals) = +0.089`, against **+0.660 for shots on target** and +0.423 for shots.
  Goals per game by cross-volume quartile are **1.47 / 1.82 / 1.79 / 1.81** — everything above
  roughly ten crosses a game buys nothing at all. Two corrections follow:
  1. **A grading that reads "we crossed a lot and won" as vindication is reading co-occurrence as
     cause.** The 2026-04-04 home leg vs Lyngby was graded exactly that way — it overturned the
     briefing's anti-crossing call because "we crossed 19 times and won anyway, winning headers
     18-14". The win was finding 1 restated once again: 6 shots on target from 10, a 60% SOT rate.
     That overturn was itself wrong, and it propagated — it was carried into the away-leg briefing
     three weeks later as "the aerial route is ON", which this doc had already advised against.
  2. **Vs Lyngby specifically, the route has now failed three times identically.** 24 crosses at
     home (0-0), 24 away (0-0), 24 away again on 2026-04-25 (won 1-0, 3 completed from 24, header
     count lost 16-24, and the goal was an unassisted Schöne strike, not a cross). n=3 on its own
     would prove nothing; sitting on top of the league-wide +0.089 it is just the general result
     showing up in one fixture.
- **Pairing two specific midfielders is not special.** "Our two best MCs together" reads
  1.58 goals/game vs 0.96 with neither at MC — but decomposed, **the gain is from having *at least
  one* of them at MC (+0.4 to +0.5); the second adds ~0.1**, and "both vs every other configuration"
  is +0.29 at just **1.3 SE**. Consistent with the ~3× underpowering this save has for pairing
  analysis (see [[player-analysis-methods]]). The actionable residue is the dull version: **avoid
  shapes with no true MC**, which cost ~0.5 goals/game.

## The habit that caught all four

Each failed hypothesis came from 3–4 vivid matches and was tested against 50–560. **Before writing a
pattern into a briefing or a skill, run it against the full match history** — and prefer a
league-wide effect size over a per-opponent record. A per-opponent split of "3 wins from 3" implies
an effect several times larger than anything that survives testing.
