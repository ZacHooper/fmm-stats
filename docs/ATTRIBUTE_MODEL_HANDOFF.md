# Attribute model — handoff

**2026-09-17.** The estimation model moved out of the parser into the database, and was refit.
This is where it landed and what to do next. Read
[`docs/PARSER_EXPANSION_HANDOFF.md`](PARSER_EXPANSION_HANDOFF.md) first for how the raw bytes
got into the store in the first place.

## Where it stands

| | exact | within ±1 |
|---|---|---|
| frozen (`fmparser/model.py`, 2024, 28 Bucaspor players) | 54.8% | 88.4% |
| refit (`scripts/fit_attribute_model.py`) | **68.4%** | 92.1% |

Measured on the same rows, **held out by player**, 202 exact rows over 80 distinct players
(one Frem snapshot per year, 2021–2026). Nothing is written to any store yet — the fit tool is
report-only until `--write`.

`model.py`'s docstring claims ~63%/93%, but that was measured on the 28 players it was fitted
from. On Frem it delivers 54.8%. **Always re-score the incumbent on the same rows** rather than
quoting that number.

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

## The next step: grid-search WEIGHTS on exact matches

The decoder result says the objective is what's binding. The same logic applies to the
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
