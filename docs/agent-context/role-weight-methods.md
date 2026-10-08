---
name: role-weight-methods
description: "How role_weights weight-sets work, the two the store ships, and what the match data can and cannot say about a role's weights (measured 2026-10-08)"
metadata:
  node_type: memory
  type: reference
  originSessionId: e454ef70-998b-4f22-a5f3-5cc24a02618f
---

## The mechanics

`seeds/role_weights.csv` (`method, role, attribute, category, weight`) drives every rating.
`int.player_ratings` (and the web app, `site/js/data.js`, to the last decimal) computes
`rating = SUM(attribute x COALESCE(weight, 1))` per (method, role). **An attribute a role does not
list counts at weight 1**, not 0, so a block *elevates* attributes above a baseline that weights
everything: key 4 / important 3 / useful 2 (`category` is only the label). Nothing can score below
1, and a role with no rows is **flat** (all 18 outfield attributes at 1). Ten roles: GK, LB, RB, CB,
DM, CM, AMC, AML, AMR, ST (position -> role in `seeds`/`stg.position_roles`; DML/DMR fold into
LB/RB, ML/MR into AML/AMR).

A consequence that matters for specialist roles: with 18 attributes at 1, a block of three 4s is
still mostly an all-round total. "Shooting 4, everything else 1" ranks strikers far more by their
other 17 attributes than by shooting.

`load_duckdb.seed_role_weights` reseeds on every load: it deletes the methods the CSV names (and
`RETIRED_METHODS`) and re-inserts the CSV, so a user-defined method in a store survives.

## The two weight-sets

- **`frem_attacking_ss`** -- hand-built from the strikerless setup's player traits, a shadow
  striker at AMC and no recognised 9. The web app's display default (`app_config.default_method`),
  and the base the 4-2-3-1's blocks are best judged against: the 4-2-3-1 now plays a real 9 and a
  10 in place of the shadow striker, so its ST and AMC blocks are the ones SS does not describe.
- **`frem_minmax_4231`** -- the career's `rating_method`, what we play and what the skills rate
  with. DERIVED by `scripts/derive_weight_set.py` from per-90 match output, role by role, against
  briefs (`BRIEFS`: e.g. CB "win the air + win it back"), with flat shipped where nothing beat it,
  a stored set inherited where it beat the derivation (CM inherits SS's block), and two judgement
  holds in `HELD`.

## What the match data says about the weights (measured 2026-10-08)

On the 31-snapshot Frem store (2022-2028), our own players at the position they played (#159's
full-time positions), each match paired with the latest snapshot's attributes on or before it.
Analysis only; nothing below changed `seeds/role_weights.csv`.

### 1. The target decides what you find

| target | what it turned out to measure |
|---|---|
| per-90 counting stats (the derivation's briefs) | opportunity and team context as much as quality: our better centre-backs make FEWER interceptions/tackles/headers per 90 (flat -0.38, our CBs), because a dominant side defends less; DM's apparent signal (flat +0.20) vanishes once ability is removed (-0.07) |
| the player's own match rating (`rating_adj`) | the match more than the player: within position and season, even overall ability predicts it at only -0.04..+0.11 at every role |
| **team result per match** (points, goal difference, goals for/against; season, venue and opponent reputation controlled) | **the target that sees a player's quality**: ability vs points is +0.13 at AMC where it was +0.01 vs his own rating |

### 2. The sample is players, not matches

650 rated matches at a role come from 12-26 players whose attributes barely move within a season,
so the data can *veto or confirm* a block when the effect is large; it cannot *build* one attribute
by attribute. That is why the derivation's blocks flip between runs: re-derived on the current
store with the same script, DM and AMC go flat, CM inherits SS, and ST gains Tackling 3 and
Leadership 2 -- the score each block clears flat by is noise-sized (most roles beat flat in under
80% of splits, several under 50%).

### 3. Per role, against team results

Correlation of the block's rating with the team's per-match result, within season; resampled by
player; every figure held its sign with any single player removed (leave-one-player-out).

| role | players | points (shipped) | weighted vs raw ability | verdict |
|---|---|---|---|---|
| CM | 26 | +0.13 (gd +0.15, GA -0.09) | weighted beats ability (+0.13 vs +0.07) | block confirmed |
| AMC | 17 | +0.17 (GA -0.13) | about level (+0.17 vs +0.13) | an all-round 10; the effect is goals conceded, not scored |
| CB | 14 | +0.10 (gd +0.10) | **weighting carries it** (SS +0.11 vs ability +0.03) | block confirmed |
| AML/AMR | 24 | +0.05 (SS +0.08) | level | fine; SS slightly ahead |
| LB/RB | 22 | +0.05, n.s. | -- | not measurable with our data |
| DM | 12 | -0.04..-0.07, n.s. | -- | not measurable with our data |
| ST | 16 | -0.03, n.s.; goals-for NEGATIVE for every block and for ability | -- | not measurable: see below |

SS and the shipped set are within noise of each other at every role where the data can judge.

### 4. The 10 and the 9

- **The 10.** The game's four 10 roles as key-attribute blocks (key 3, rest 1) -- Attacking
  Midfielder (movement, passing, decisions), Advanced Playmaker (+ creativity), Shadow Striker
  (AP - passing + shooting, pace), Trequartista (AP + SS + strength, aerial) -- none separates
  from flat on our 17 AMCs, against rating or results. The playmaker-only profile does worst; the
  single-attribute leanings (stamina, aerial, strength up; passing, pace, decisions down, all
  inside noise) point at a physical all-rounder. Read: **all-round quality wins games at 10**, and
  no specialist profile adds to it.
- **The 9.** Within a season, the better striker on paper -- by any block, by ability, or by the
  target-man brief (aerial, shooting, strength key; movement, pace, aggression, dribbling
  secondary) -- goes with the team scoring LESS. Shooting looked like the one attribute that
  counted (+0.09 vs goals for) until Johan Nordberg (high movement/pace/decisions, shooting 11; the
  team scored 0.63 a game with him in 2028) was removed: then shooting is -0.03 and ability still
  points the wrong way (-0.12). Four strikers carry 219 of 264 starts (Ementa, Nordberg, Rothmann,
  Jakobsen), and whoever starts the bulk of a hard season absorbs its hard fixtures. **The data
  cannot judge strikers**; the 9's block is a judgement call. The league is not the confound:
  every comparison is within season, and the first team played one league per season.

### 5. Method rules

- Score a candidate block on **team results**, beside rating and per-90 stats -- never per-90 alone.
- **Resample by player**, not by match, and **check leave-one-player-out** before believing a
  result (the "finishing counts" read of the 9 was one player).
- Compare **within season**: it removes the division.
- **Start from a base, let data veto**: the hand-built SS set matched or beat the derivation
  wherever the data could tell (it beat flat in 100% of resamples at CB, CM, LB/RB on the per-90
  briefs, where the derived CM block managed 48%). A block derived from under ~30 players is a
  hypothesis.
- Opponents are 706 of the derivation's 890 player-seasons, seen over 2-4 games each, with
  attributes that are mostly decoder estimates carrying ability as a shared shift
  ([`attribute-model.md`](../attribute-model.md)); the derivation's partial correlations control
  for the flat attribute total, which absorbs some of that. Opponents' full-time positions are
  in `fact_player_match.position` too, so they can enter the per-match tests, with those
  estimated attributes.

See [[attribute-stat-correlations]] (what attributes make a player DO, per 90), [[fmm-tactic-options]].
