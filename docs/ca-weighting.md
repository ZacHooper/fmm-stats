# How the save gives us each attribute — and what CA is made of

**2026-09-17.** Two results that came out of the same investigation, both measured on the Frem
store (6 snapshots, 2021–2026). Companion to
[`attribute-model.md`](attribute-model.md), which covers the decoder itself.

Regenerate everything here with:

```bash
uv run python archive/attribute_taxonomy.py fm-frem.duckdb   # the taxonomy table
uv run python archive/ca_weight_set.py      fm-frem.duckdb   # the weight tables
uv run python archive/truth_ceiling.py      fm-frem.duckdb   # the label-noise ceiling
uv run python archive/ca_versatility.py     fm-frem.duckdb   # the familiarity trade-off
```

## Part 1 — the 23 displayed attributes, by how we get them

Three kinds, and the kind is what decides whether CA is involved. **It is the byte's kind that
matters, not the attribute's identity** — this is the same line that separates the composites.

| attribute | kind | source byte(s) | byte only | + CA shift |
|---|---|---|---|---|
| Technique | **direct** | `technique_src` | 99.5% | — |
| Aggression | **direct** | `aggression_src` | 98.9% | — |
| Agility | **direct** | `agility_src` | 100.0% | — |
| Pace | **direct** | `pace_src` | 95.2% | — |
| Leadership | **direct** | `leadership_src` | 94.1% | — |
| Strength | **direct** | `strength_src` | 88.2% | — |
| Stamina | **direct** | `stamina_src` | 87.6% | — |
| Teamwork | **composite** | `unselfishness_src` + `work_rate` | 97.8% | +1.1% |
| Aerial | **composite** | `heading_src` + `jumping` | 98.4% | −3.2% |
| Creativity | modelled | `creativity_src` | 32.3% | **86.6%** |
| Crossing | modelled | `crossing_src` | 19.9% | **72.6%** |
| Shooting | modelled | `finishing_src` + `long_shot_src` | 24.2% | **61.8%** |
| Passing | modelled | `passing_src` | 20.4% | **58.6%** |
| Decisions | modelled | `decision_src` | 36.0% | **55.9%** |
| Tackling | modelled | `tackling_src` | 30.1% | **54.3%** |
| Movement | modelled | `movement_src` | 23.7% | **50.5%** |
| Positioning | modelled | `positioning_src` | 25.3% | **41.4%** |
| Dribbling | modelled | `dribbling_src` | 26.3% | **40.9%** |
| Throwing | modelled (GK) | `throwing_src` | 12.5% | 68.8% |
| Reflexes | modelled (GK) | `reflexes_src` | 18.8% | 68.8% |
| Handling | modelled (GK) | `handling_src` | 25.0% | 62.5% |
| Kicking | modelled (GK) | `kicking_src` | 12.5% | 62.5% |
| Communication | modelled (GK) | `communication_src` | 0.0% | 0.0% |

Exact-match accuracy, CV held out by player, rounding offset chosen inside the training fold.
186 outfield truth rows / 73 players; **the five GK attributes are scored on the 16 GK rows
only** and those numbers are indicative at best. Communication at 0.0% is not a decode failure
so much as a sample-size one — do not read it as a finding.

- **direct** — the byte *is* the displayed value. Nothing to model, nothing to fit, no CA.
- **composite** — a closed form over two plain 1-20 bytes. Teamwork is
  `floor((unselfishness + work_rate) / 2)`, and a grid search independently rediscovers it.
  Aerial is `floor(0.30 × heading + 0.70 × jumping + 1.0)`. **Adding CA makes Aerial worse**
  (−3.2), which is the cleanest single demonstration that CA belongs to byte kind and not to
  attribute identity.
- **modelled** — an entangled 0-255 byte. The byte alone gets 20–36%; the shared CA shift is
  what makes it usable. See [`attribute-model.md`](attribute-model.md) for why it is ONE
  shift and not fourteen.

### The label ceiling: 94.8%, not 100%

The direct attributes are read straight from a plain byte, so a disagreement with the
managed-club snapshot is **the two sources disagreeing, not a decode error**. They agree
**94.8% exact / 98.7% within ±1**, and the modelled attributes are scored against the same two
sources. So the decoder's 57.7% is against a ceiling of about 95, and its 88.1% within ±1
against a ceiling of about 99. Stamina and Strength are the noisiest (87.6%, 88.2%); Agility
and Technique are essentially clean. Suspect snapshot staleness
(`docs/agent-context/reserve-marker-stale-attrs.md`) before suspecting the decode.

## Part 2 — what CA is made of, by position

Regress CA on all 34 raw attribute slots, per top position, over **155,134 player-snapshots**.
Mirror positions are pooled (DL/DR, ML/MR, AML/AMR, DMC+DML/DMR). R² 0.60–0.74.

This says what the game rewards in a given slot. It is a **scouting** asset — it is *not* a
lever for the decoder, because CA's contribution there is uniform across attributes.

| attribute | GK | DC | DL/DR | DMC | MC | ML/MR | AMC | AML/AMR | ST |
|---|---|---|---|---|---|---|---|---|---|
| stamina | 7 | 5 | 8 | 10 | 9 | 8 | 13 | 11 | 9 |
| pace | 8 | 4 | 7 | 5 | 5 | 7 | 9 | 12 | 7 |
| decisions | – | 12 | 11 | 7 | 8 | 7 | 4 | 4 | 6 |
| unselfishness | 12 | 2 | 4 | 4 | 4 | 5 | 5 | 6 | 2 |
| strength | 10 | 6 | 5 | 8 | 5 | 5 | 8 | 5 | 8 |
| dribbling | – | 5 | 5 | 6 | 8 | 10 | 4 | 5 | 7 |
| agility | 9 | 3 | 5 | 4 | 5 | 6 | 9 | 8 | 4 |
| positioning | – | 9 | 7 | 6 | 6 | 4 | – | 1 | 2 |
| technique | 9 | 6 | 6 | 6 | 5 | 2 | 8 | 6 | 6 |
| tackling | – | 7 | 6 | 6 | 8 | 7 | 2 | 4 | 2 |
| finishing | – | 2 | 3 | 1 | 4 | 6 | 4 | 8 | 8 |
| creativity | – | 6 | 4 | 4 | 7 | 5 | 3 | 3 | 6 |
| heading | – | 7 | 3 | – | – | – | – | – | 5 |
| passing | – | 7 | 4 | 4 | 6 | 2 | 3 | 2 | 5 |
| set pieces | 2 | – | – | 3 | 3 | 3 | 7 | 5 | 3 |
| movement | – | 4 | 5 | 3 | 5 | 6 | 3 | 2 | 6 |
| crossing | – | 4 | 6 | 3 | 3 | 4 | 2 | 3 | 4 |
| jumping | 5 | 3 | 1 | 3 | 1 | 1 | 2 | 2 | 3 |
| reflexes | 5 | – | – | – | – | – | – | – | – |
| penalty | 2 | 2 | 3 | 3 | 1 | 3 | 4 | 4 | 1 |
| versatility | 3 | 1 | 1 | 2 | 2 | 4 | 3 | 2 | 2 |
| flair | 1 | 2 | 2 | 4 | 1 | 3 | 2 | 2 | 2 |
| kicking | 4 | – | – | – | – | – | – | – | – |
| work rate | 4 | 1 | 1 | 3 | 1 | 1 | 2 | 1 | 1 |
| throwing | 4 | – | – | – | – | – | – | – | – |
| handling | 4 | – | – | – | – | – | – | – | – |
| leadership | 3 | – | – | – | – | 1 | – | – | – |
| consistency | 3 | 1 | – | 1 | 1 | – | – | 1 | – |
| big match | 2 | – | – | – | 1 | 1 | – | 1 | – |
| aggression | 1 | – | 1 | – | – | – | 2 | – | 1 |
| **n** | 16,785 | 26,106 | 21,655 | 12,246 | 21,165 | 5,131 | 10,549 | 18,525 | 22,972 |
| **R²** | 0.60 | 0.74 | 0.72 | 0.67 | 0.73 | 0.70 | 0.67 | 0.72 | 0.70 |

Read down a column for a position's priorities; across a row for where an attribute earns its
keep. Decisions is the single biggest term for a defender or a fullback and nearly irrelevant to
a wide forward. Crossing earns weight at DL/DR and ST and almost none at DC. Finishing is joint-top
at ST and 2% at DC. Tackling matters at DC/MC/DL and not in the front three.

| attribute | GK | DC | DL/DR | DMC | MC | ML/MR | AMC | AML/AMR | ST |
|---|---|---|---|---|---|---|---|---|---|
| decisions | – | +5.0 | +4.6 | +3.2 | +4.7 | +4.0 | +1.6 | +1.8 | +3.3 |
| dribbling | – | +1.6 | +1.8 | +1.8 | +2.8 | +3.7 | +1.1 | +1.4 | +2.3 |
| pace | +1.8 | +1.3 | +2.2 | +1.5 | +1.7 | +2.4 | +2.2 | +3.3 | +2.0 |
| positioning | – | +3.1 | +2.6 | +1.9 | +2.3 | +1.6 | -0.1 | +0.3 | +0.6 |
| tackling | – | +2.8 | +3.1 | +2.1 | +3.1 | +2.7 | +0.5 | +1.4 | +1.3 |
| creativity | – | +2.2 | +1.9 | +1.4 | +3.1 | +2.2 | +0.8 | +1.1 | +2.2 |
| finishing | – | +1.5 | +1.7 | +0.4 | +2.3 | +2.8 | +1.4 | +2.5 | +2.9 |
| passing | – | +2.1 | +1.6 | +1.5 | +2.6 | +1.0 | +0.9 | +0.7 | +1.5 |
| stamina | +1.0 | +1.2 | +2.0 | +2.2 | +2.4 | +1.9 | +2.4 | +2.1 | +2.2 |
| heading | -2.5 | +2.2 | +0.9 | -0.4 | -0.5 | -0.6 | -0.6 | -0.4 | +1.2 |
| agility | +1.7 | +0.9 | +1.4 | +1.2 | +1.7 | +1.6 | +2.2 | +2.0 | +1.0 |
| movement | – | +1.8 | +1.7 | +0.9 | +1.8 | +2.1 | +0.9 | +0.7 | +1.8 |
| crossing | – | +1.5 | +2.1 | +0.9 | +1.3 | +1.7 | +0.6 | +0.9 | +1.4 |
| unselfishness | +2.1 | +0.3 | +1.0 | +0.8 | +1.0 | +1.3 | +1.0 | +1.3 | +0.4 |
| technique | +1.4 | +1.3 | +1.7 | +1.5 | +1.7 | +0.6 | +1.8 | +1.4 | +1.6 |
| strength | +1.7 | +1.4 | +1.2 | +1.6 | +1.4 | +1.2 | +1.5 | +1.0 | +1.6 |
| reflexes | +1.3 | – | – | – | – | – | – | – | – |
| set pieces | +0.6 | -0.3 | +0.1 | +0.6 | +0.7 | +0.8 | +1.1 | +1.1 | +0.7 |
| versatility | +0.5 | +0.3 | +0.2 | +0.6 | +0.6 | +1.1 | +0.6 | +0.4 | +0.4 |
| flair | +0.2 | +0.7 | +0.5 | +1.0 | +0.3 | +0.8 | +0.4 | +0.4 | +0.5 |
| jumping | +1.0 | +0.9 | +0.3 | +0.6 | +0.4 | +0.2 | +0.4 | +0.4 | +0.8 |
| kicking | +0.9 | – | – | – | – | – | – | – | – |
| handling | +0.9 | – | – | – | – | – | – | – | – |
| throwing | +0.8 | – | – | – | – | – | – | – | – |
| penalty | +0.7 | +0.4 | +0.6 | +0.6 | +0.3 | +0.6 | +0.6 | +0.6 | +0.1 |
| work rate | +0.6 | +0.2 | +0.2 | +0.7 | +0.3 | +0.2 | +0.4 | +0.3 | +0.2 |
| leadership | +0.5 | +0.1 | +0.0 | -0.1 | +0.1 | +0.1 | -0.2 | +0.0 | -0.1 |
| consistency | +0.5 | +0.3 | +0.1 | +0.3 | +0.2 | -0.1 | -0.1 | +0.2 | -0.1 |
| **n** | 16,785 | 26,106 | 21,655 | 12,246 | 21,165 | 5,131 | 10,549 | 18,525 | 22,972 |
| **R²** | 0.60 | 0.74 | 0.72 | 0.67 | 0.73 | 0.70 | 0.67 | 0.72 | 0.70 |

Shares are standardised betas rescaled to sum to 100 within a position; they are **invariant to
the byte→display scale** and are the ones to trust. The points-per-display-point table depends
on a per-attribute display slope measured from only 186 truth rows, so treat it as indicative.

### Three traps — a naive version of this table is wrong, not just imprecise

1. **Marginal correlation gets it backwards.** Pooled, `tackling_src` correlates **+0.04** with
   CA and `finishing_src` **+0.03** — apparently irrelevant. In the multiple regression tackling
   is among the largest terms at DC/MC/DL. The entangled bytes are ability-independent, so they
   only reveal themselves once the rest of the vector is controlled for. **Use the regression.**
2. **Exclude cross-group bytes.** On an outfielder the six GK bytes decode at or below the
   display floor (mean 1.5 in the bottom CA quintile, −1.3 in the top) and each correlates about
   **−0.61** with CA. Leave them in and the fit uses them as a negative CA proxy and hands them
   large negative weights — the strongest apparent signal in the whole table, and pure artifact.
   (They are six *independent* bytes, not one fill: all six are equal on only 3% of outfielders.
   None of them carries displayable information for an outfielder.) Dropping them costs about
   0.03 R², which is the artifact being removed.
3. **Convert entangled bytes per attribute.** One raw byte is 8.0 units per display point for
   Dribbling and 14.4 for Decisions. Converting them all at one rate mis-scales the
   unstandardised weights — Decisions by 1.65×.

## Part 3 — positional familiarity redistributes a fixed CA

**Hypothesis** (Zac's): CA is a familiarity-weighted blend of the per-position weight vectors,
so making a striker also a centre-back forces the game to raise his tackling and positioning and
pay for it out of his finishing. **Confirmed directionally, at full sample size.**

Every ST in the store (n=22,972), each attribute regressed on CA *and* DC familiarity, so CA is
held fixed. Per +10 DC familiarity:

| up | | down | |
|---|---|---|---|
| positioning | **+1.64** | dribbling | **−1.51** |
| tackling | **+1.61** | agility | −1.16 |
| strength | +1.46 | finishing | −1.10 |
| decisions | +0.46 | pace | −1.08 |
| heading | +0.29 | technique | −0.93 |
| | | movement | −0.90 |

Exactly the predicted trade: the defensive attributes rise, the forward ones pay for it, and CA
does not move.

The general form is only **partly** recovered. Building each player's blended weight vector
(familiarity-weighted average of the per-position weights above) and asking whether his
CA-residual is high where his blended weight is high gives **+0.23 pooled** over 138,349
outfielders — but it splits hard: strong for the role-defining attributes (positioning +0.69,
tackling +0.67, finishing +0.65, heading +0.54) and near zero for the generic ones (passing
−0.03, movement −0.06, dribbling −0.11, crossing −0.17).

So the **mechanism is real and it is not breadth per se** — a plain count of positions at
familiarity ≥15 gives a mixed, uninterpretable picture, because *which* position you add decides
which attributes rise. The exact formula (how familiarity enters, whether it is linear, what the
normalisation is) is **not** decoded. That is the open piece of work.
