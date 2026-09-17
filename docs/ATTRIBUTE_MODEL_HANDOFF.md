# Attribute model — handoff

**2026-09-17.** The estimation model moved out of the parser into the database, and was refit.
This is where it landed and what to do next. Read
[`docs/PARSER_EXPANSION_HANDOFF.md`](PARSER_EXPANSION_HANDOFF.md) first for how the raw bytes
got into the store in the first place.

## Where it stands

| | exact | within ±1 |
|---|---|---|
| frozen (`fmparser/model.py`, 2024, 28 Bucaspor players) | 52.6% | 87.8% |
| **refit** (`scripts/fit_attribute_model.py`) | **69.3%** | 89.5% |
| **the same coefficients on BUCASPOR, not refitted** | **68.1%** | 87.4% |

840 exact rows over 86 players (25 Frem snapshots), **held out by player**, 5 folds, nested
selection. 13 of 14 attributes beat the frozen model on Frem; **14 of 14 on Bucaspor.**

**The ceiling is 94.8% exact / 98.7% ±1**, not 100% — measured on the attributes read straight
from a plain byte, where a disagreement is the two sources disagreeing rather than a decode
error. See [`docs/ca-weighting.md`](ca-weighting.md). Quote accuracy against that, never 100.

### The cross-career hold-out is the important number

Everything is fitted on Frem, so the only evidence it generalises is a career it has never
seen. `scripts/holdout_score.py --fit fm-frem.duckdb --on fm-buca.duckdb` scores the Frem
coefficients on Bucaspor's 231 exact rows / 41 players **without refitting**: **68.1%**, against
69.3% on its own data. A drop of 1.2 points across Denmark → Turkey.

That is the failure mode the frozen model had and this one does not. The frozen coefficients
were fitted on 28 Bucaspor players and score 56.6% there and 52.6% on Frem — they did not
travel. These do.

The closed forms travel best of all: **Teamwork 99.6%, Aerial 87.4%** on Bucaspor (88.7% on
Frem), which is what you would hope for from two parameters over plain bytes.

## The exact-vs-±1 dial, and why "exact" is the right setting

The grid search optimises EXACT matches, so it is free to trade near-misses for hits — and it
does. Across the refit, exact gained **+16.7** points while ±1 gained only **+1.7**, and four
attributes went BACKWARDS at ±1: Dribbling 87.0 → 74.6, Tackling 92.6 → 86.3, Passing
89.2 → 83.2, Crossing 88.8 → 86.5. 10.3% of values are now off by 2 or more, asymmetrically
(−2 at 6.9% against +2 at 2.1%, so a bad miss is usually an UNDER-prediction).

That looks like it might be the wrong trade, because nothing surfaces a raw attribute — the app
surfaces role ratings, which are weighted means over 15–23 attributes, and a fatter tail could
propagate. **Measured (`archive/rating_error_propagation.py`, all 10 roles of
`frem_attacking_ss`, 840 snapshots), it does not:**

- mean role-rating error **0.21** on the 1–20 scale — **1.0% of full range**, max 1.3
- 7.5% of ordered player pairs come out in the wrong order, **but the median true gap in a
  swapped pair is 0.19 rating points**; 86% of swaps are between players within 0.5 of each
  other and 97.7% within 1.0

The inversions are near-ties between players who are genuinely interchangeable. Averaging over
15–23 attributes cancels the per-attribute error almost entirely, so the fat tail does not
reach the depth chart. **Keep the exact-match objective.** If a future use needs calibrated
per-attribute values rather than good rankings, the dial is one line — score `_grid_fit` on
`|err| <= 1` instead of equality.

Note this error only reaches players WITHOUT exact truth. Our own squad is COALESCEd to the
save's stated values, so it applies to opponents, recruitment targets and scouting — which is
where it matters most and where it cannot be checked directly.

## The three things that actually mattered

1. **The decoder, not the features.** Least squares minimises squared error; we score exact
   matches; `round()` sits between them with an offset nobody had tuned. Tuning that ONE
   parameter on the training fold is worth **+8.5 points** (58.3 → 66.8% on a fixed feature
   set) — as much as the entire feature-selection apparatus. Every fold of every attribute
   picks a NEGATIVE offset (−0.12 to −0.60), so the game's decoder is not round-half-up.
2. **Position, per attribute.** It lifts Dribbling 48→62%, Positioning 35→41%, Movement
   46→54% and COSTS Aerial 89→77%, Handling 94→82%, Kicking 82→71%. One global encoding has to
   eat one of those losses; per-attribute selection does not.
3. **GK/outfield as separate fits** measured +2.6 (65.6 → 68.2%) in scratch analysis. **NOT in
   the tool** — it needs a `group` column on `staging.attribute_model` and a CASE in the
   generated view, and it rests on 16 GK rows. Worth doing on the full store, not before.

## CA is ONE shared shift, not fourteen separate effects

**This is the structural finding, and it should shape the model rather than be bolted onto it.**

Fit each entangled attribute from its own byte alone and keep the residuals. If CA entered each
attribute separately, those residuals would be unrelated across attributes. They are not:

- mean pairwise residual correlation across the 9 outfield entangled attributes: **+0.66**
  (min +0.55, max +0.79)
- a single per-row shift explains **69.3%** of the residual variance
- that shift correlates **+0.93 with CA**, and is **linear** in it — `shift ≈ 0.049 × CA − 3.96`,
  R² 0.896, and a quadratic term adds exactly nothing (0.896)
- every attribute loads on it at about 1.0 (0.86–1.35)

So the record's shape is

```
displayed_a = round( beta_a * unwrap(byte_a) + alpha_a + g(CA) )      g(CA) = 0.049*CA - 3.96
```

**one** CA term for the whole player — roughly one display point per 20 CA — not one per
attribute. Scored like for like (186 outfield truth rows, same folds, same offset rule):

| model | free params | exact | ±1 |
|---|---|---|---|
| byte only | 18 | 28.0% | 69.0% |
| **shared CA shift** | **20** | **57.7%** | 88.1% |
| shared shift + per-attribute loading | 29 | 55.1% | 88.5% |
| per-attribute CA/PA/own×CA (the current shape) | 45 | 57.5% | 89.5% |

The shared shift **matches the per-attribute fit on 2.25× fewer parameters**, and letting the
loading vary per attribute makes it *worse* — which is the direct test that the CA effect does
not differ by attribute. With only 202 truth rows that parsimony is the whole argument for it
generalising to another career.

Confounds checked and rejected: it is not per-save decode drift (the per-save means just track
each save's mean CA, and CA still correlates +0.77 with the shift *within* a save); not age
(+0.28); not CA/PA (+0.56). Reputation comes close (+0.87) but is itself CA-driven.

### What this means for "which attributes need CA"

The natural guess is that CA matters most for the attributes CA is most built from — that
shooting needs it and teamwork doesn't. **The first half is wrong and the second is right for
the wrong reason.** CA's contribution is uniform across the entangled attributes; Teamwork is
untouched by it because Teamwork is built from PLAIN bytes, which are already the displayed
value and need no rendering step at all. The dividing line is byte KIND, not attribute identity
— the same line that separates the three composites above.

Two consequences:

- **Do not add per-attribute CA terms.** Fit `g(CA)` once, jointly, by alternating least squares
  (`archive/ca_shared_shift.py` is the reference implementation and re-runs the
  table above against any store), then per-attribute slope and
  intercept on top.
- Apparent per-attribute variation in "how much CA helps" is an artifact of the floor. Handling,
  Reflexes and Communication look like they need no CA (+2.0, −4.5, −0.5 points) only because an
  outfielder's value is pinned at 1 — **Communication is 1 for 100% of outfield truth rows,
  Handling and Reflexes for 62%**. Score the GK attributes on GKs or not at all.

## A by-product: FM's positional CA weighting, recovered

Regressing CA on all 34 raw attribute slots recovers what the game weights at each position
(R² 0.60–0.74 over 155k player-snapshots). That, the full per-position weight tables, the
three-way taxonomy of how the save hands us each of the 23 displayed attributes, and the
**94.8% label ceiling** every accuracy number here is measured against, all live in
**[`docs/ca-weighting.md`](ca-weighting.md)**. Read it before quoting any accuracy figure — the
decoder's 57.7% is against a ceiling of ~95, not 100.

It is a scouting asset, **not** a lever for the decoder: CA's contribution to the entangled
attributes is uniform, per the section above.

## The next step: grid-search WEIGHTS on exact matches

The decoder result says the objective is what's binding, and the shared-shift result says the model has far fewer real parameters than we have been fitting. The same logic applies to the
coefficients, and there is direct evidence:

**Aerial.** `floor(0.30 × heading_src + 0.70 × jumping + 1.0)` scores **70.8% CV** against the
tool's current 58.9% for that attribute. Two parameters beating eight. Four of five folds chose
`w=0.30, offset=+1.0` exactly.

**Teamwork validates the method.** Grid-searching the same shape recovers `w=0.50, offset=0` in
all five folds at **99.5% exact** — i.e. it independently rediscovers
`floor((unselfishness + work_rate) / 2)`, the formula we already knew. A method that recovers a
known answer on a known case is worth trusting on the unknown ones.

So: for each attribute, grid-search the weights against exact-match accuracy instead of taking
the least-squares solution. Start with the composites, then the single-byte attributes
(`w × own + offset` is only two parameters there too).

### But composites are NOT all alike — this is the trap

There are exactly three composite attributes, and they split by the KIND of byte they blend:

| attribute | bytes | kind | closed form |
|---|---|---|---|
| Teamwork | `unselfishness_src` + `work_rate` | both PLAIN 1-20 | **99.5%** |
| Aerial | `heading_src` + `jumping` | both PLAIN 1-20 | **70.8%** |
| Shooting | `finishing_src` + `long_shot_src` | both ENTANGLED 0-255 | **28.2%** — WORSE than the frozen model's 40.6% |

Blending plain bytes works because a plain byte IS the attribute. Blending entangled bytes does
not, because an entangled byte needs CA to decode at all. **Do not assume "has a partner"
implies "has a closed form".** Shooting has a partner and does not.

## Can we INVERT the CA weights to recover an attribute? No — measured.

The idea: CA is a weighted sum of attributes, we know CA exactly and we know 11 of the 23
attributes exactly, so `sum(unknown w_a * attr_a) = CA - sum(known)` is an exact linear
constraint on the 14 we estimate. One equation in 14 unknowns is not invertible, but combined
with a byte-based estimate of each it becomes a constrained projection — and our decode errors
are correlated at +0.66, so their weighted sum is large and systematic, exactly what a
constraint should fix.

**It cannot work, because the constraint is looser than the estimate it would constrain**
(`archive/ca_constraint_test.py`, 840 truth rows where all 23 attributes are exact, CV by
player):

| | sd, CA points |
|---|---|
| the constraint's own residual — how tightly `CA = sum(w*attr)` holds | **16.8** |
| our decode's implied-CA error — what it would correct | **6.1** |

The constraint is **2.7x noisier than the error it would fix**, so projecting onto it adds
noise. Even with perfectly estimated weights it does not close: the 155k-row byte regression
reaches R² 0.70–0.77, which is a residual of about 10.7 CA points against our 6.1. CA is not a
pure linear function of the 23 displayed attributes — hidden attributes and position weighting
are in there too — so it is an inherently noisy measurement of the attribute vector.

**The usable part of CA is already extracted**, as the one shared per-player shift. That is the
robust form of this idea and it is in the model.

### Use the BYTE, not the displayed attribute — and then the whole idea still fails

The constraint above was written over the DISPLAYED attributes, which are a rounded, clipped
view of the internal values; the entangled bytes carry ~255 levels and CA is presumably
computed from those. Redone over the raw bytes (`archive/ca_surprise_test.py`, 118,876
snapshots, 34 bytes, CV by player):

| | R² | CA residual sd |
|---|---|---|
| outfield | 0.713 | **15.0** |
| GK | 0.683 | **15.7** |

Still 15.1 against our decode's implied-CA error of 6.1. The quantisation was not what made it
loose — **CA genuinely is not a linear function of the 34 bytes**, and ~29% of its variance
lives somewhere we cannot see.

That last fact kills a tempting follow-up. If CA *were* determined by the bytes it would be
redundant, and the only useful part would be the SURPRISE, `CA - sum(w*byte)` — CA with
everything we already know subtracted off. Tested as the decoder's CA term in place of raw CA:

| | mean exact |
|---|---|
| raw CA | **66.1%** |
| surprise | 44.8% |

**−21.2 points.** The reasoning behind it was wrong, and instructively so: the decoder is not
trying to learn something NEW about the player, it is trying to calibrate the byte→display map,
and what does that is CA's plain ability-level signal — which correlates with every attribute
at once. Subtracting the byte-predicted part removes exactly that common signal and leaves
noise (sd 18.2 against raw CA's 20.9, but decorrelated from the attributes). **The predictable
part of CA is the useful part, not the redundant part.**

Handling +8.9, Reflexes +5.4 and Communication +2.9 are the only gains, and they are the three
attributes floored at 1 for outfielders — i.e. the surprise is working as a crude keeper flag
there, the same thing `blend_w` turned out to be.

### Two traps that make a naive version of this look like it works

- **Circularity.** `staging.player_attributes`' entangled values are model output that USED CA
  as an input. Regress CA on them and you recover CA from itself: R² 0.945, sd 6.6 — better
  than the truth. Fit on CA-independent inputs only.
- **COALESCE.** The same view returns the EXACT value wherever one exists, i.e. on every truth
  row, so the decode error read off it is identically **zero**. Use `load_duckdb._model_expr`,
  which is the model branch with no COALESCE. Both of these bit during this investigation.

## `blend_w` earns +0.7, and mostly as a goalkeeper flag

The other half of Stage 3 — familiarity-weighted CA weights as a feature — is a DIFFERENT
mechanism from the constraint (redistribution at fixed CA, not a constraint on a sum) and it
does help, but barely (`archive/blend_weight_test.py`): **69.3% → 69.9%**. Ten of fourteen
attributes are unchanged to the decimal; the gain is Handling +4.6, Reflexes +3.8, Creativity
+2.0, and Shooting **−1.3**. That distribution says it is acting as a better goalkeeper
indicator than the raw GK familiarity already in the `gk` set, not as the positional
redistribution it was motivated by. Part of the +0.7 is also just fighting the pool penalty,
since testing it means offering 4 candidates instead of 2.

**Not built.** It needs `staging.ca_weights` + a migration + a mart view + a new SQL feature
expression + test changes, and 0.7 points that have never been checked on a second career is
not worth a schema change. Revisit only after the Bucaspor hold-out says the current
coefficients generalise at all.

## Everything already ruled out — do not re-test without more data

All at n=80 players, so all conditional on sample size; several may flip on the full store.

- **All 16 source bytes together** — loses to own + CA (Crossing 64→54%). The bytes are not a
  linear mixture of each other, so "entangled" is a misnomer.
- **The nine hidden attributes** as features — 63.2 → 62.7%. Residual correlations show none of
  the football-obvious pairings exist: `set_pieces`→Crossing, `penalty`→Shooting and
  `work_rate`→Movement are all absent, and with 360 correlations tested the noise floor is
  ≈0.25.
- **Feet, height/weight, the three reputations, age, the eight personality values** — every
  block loses (68.2% lean vs 66.1–66.5% with each). Two hints worth re-testing on more data:
  feet for Dribbling (48→54%) and height/weight for Shooting (63→66%).
- **`fwd`** — removed entirely. It collapsed a whole positional profile to 1.0/0.5/0.0 off the
  top position, it is not a quantity the save plausibly holds (15 familiarities are stored, not
  an attacking-ness score), and against a fair alternative it earned its place for one
  attribute of fifteen. Cost of removal: 0.2 points.
- **Quantile calibration instead of rounding** — +2.6 overall but only by capturing the bimodal
  GK distribution; it LOSES on outfield attributes. A substitute for the `gk` feature, not an
  addition.
- **The CA effect is ADDITIVE, not multiplicative.** The slope of displayed-on-byte is flat
  across CA bands (0.107–0.134) and dividing by CA makes the correlation worse (0.923 → 0.720).

## How to run it

```bash
uv run python scripts/fit_attribute_model.py --db fm-frem.duckdb            # report
uv run python scripts/fit_attribute_model.py --db fm-frem.duckdb --write    # store coefficients
uv run python load_duckdb.py --refresh-only --db fm-frem.duckdb             # take effect
uv run python tests/test_attribute_model.py --db fm-frem.duckdb             # guard the pair
```

The fit refuses below 400 exact rows (`--min-rows` overrides, for pipeline smoke tests only —
never to produce coefficients to keep). No save file and no re-extract is needed: the raw bytes
are in `staging.players` and the exact values our own squad carries are in
`staging.player_attributes_exact`.

## Two things worth doing before trusting any of this further

- **The full store.** Everything above is six snapshots. 25 gives ~4× the rows and ~2.2× the
  players, and several rejected features may flip.
- **Bucaspor as a held-out CAREER.** Every number here is fitted and validated on Frem squads.
  The frozen model scoring 63% on its own data and 54.8% on ours is exactly the failure a
  single-career validation cannot see.

## A diagnostic worth keeping

Model error is **U-shaped in ability**, not linear: frozen MAE by ability quintile runs
0.80 / 0.43 / 0.58 / 0.52 / 0.76. It is worst at both extremes because it regresses toward the
typical profile, so it is least reliable for unusual players. Johan Nordberg (28th percentile
globally, but decent technical attributes) gets MAE 1.00 from the frozen model against team-mate
Anosike Ementa's 0.53; the refit takes him to 0.47. The refit also flattens the whole curve, to
0.53 / 0.35 / 0.47 / 0.41 / 0.46.
