# Attribute decoding — findings, formulas, and where it's wrong

Status of the effort to read **every league player's attributes** (not just our own
squad). This is the deep-dive companion to `BUGS.md` #8/#9. Paused here as a
"good-enough + documented" checkpoint.

## TL;DR

- Every player (opponents included) has a **fixed 78-byte record** in the ~3.8–6.6 MB
  region, located via their **SID** (from the info-field). `league_attrs.py` reads it.
- **Exactly decoded for any player:** 15 position ratings, both feet, CA, PA,
  reputation, and **8 attributes** (7 raw + Teamwork via a formula).
- **Estimated to ±1 (92%)** for the other ~14 attributes (technical/mental/GK) via a
  regression (`regress.py`), because those are stored **entangled with CA** and exact
  inversion needs FM's position-weight tables we don't have for mobile.
- Two attribute mechanisms fully understood: **Teamwork = floor(avg of 2 sub-stats)**
  and **Communication = raw + Leadership boost**.

---

## 1. The record (all offsets relative to positions-block start `P`)

`P` is found as `SID_hit + 42`, and every record sits on a **78-byte grid** with
`P % 78 == 57` (used as a validity filter). Record spans `P-55 … P+22`.

| Offset | Field | Status |
| --- | --- | --- |
| `P-50 … P-43` | **Personality** (8 vals: Adaptability, Ambition, Determination, Loyalty, Pressure Handling, Professionalism, Sportsmanship, Temperament) | lead — b-50 Adaptability=16 for both "Adaptable" players; bytes interleaved, decode TODO |
| `P-42 … P-39` | **SID** (the record key) | confirmed |
| `P-34 … P-1` | **34 attribute slots**, exact rough-guide Step-6 order (`slot = guide# ; offset = guide#-35`) | see §2 |
| `P-0 … P+14` | 15 **position** ratings (GK,SW,DL,DC,DR,DMC,ML,MC,MR,AML,AMC,AMR,ST,DML,DMR; 20=natural) | confirmed |
| `P+15 / P+16` | left / right **foot** (0-20) | confirmed |
| `P+17` (u16) | **CA** | confirmed (CA≤PA holds all 28) |
| `P+19` (u16) | **PA** | confirmed |
| `P+21` (u16) | **reputation** | confirmed |

The 5 MB record's CA/PA is the **authoritative/current** value; the 62 MB Bucaspor
snapshot is a slightly stale cache (see §5).

---

## 2. The attribute slots (b-34 … b-1) and how each decodes

Two storage classes (this is the key structural finding, and matches the FMM rule that
**physical attributes don't contribute to CA**):

- **Class A — raw 1-20** (physical + CA-excluded). `display = byte`, exact.
- **Class B — entangled 0-255** (CA-contributing: technical/mental/GK). The byte
  **wraps** (`unwrapped = byte+256 if byte<128 else byte`; strong attrs have *low*
  bytes) and must be rescaled using CA/position. Estimated, not exact.

| Offset | Guide attribute | Class | Decode |
| --- | --- | --- | --- |
| b-34 | Crossing | B | regression |
| b-33 | Dribbling | B | regression |
| b-32 | Tackling | B | regression |
| b-31 / b-30 | **Shooting** = Finishing + Long Shots | B (both) | regression (2 inputs) |
| b-29 / b-28 | **Aerial** = Heading + Jumping | A-ish | `≈ round((b-29+b-28)/2)`, but see §4 |
| b-27 | Passing | B | regression |
| b-26 | Decisions | B | regression |
| b-25 | **Teamwork**.Unselfishness | A | part of Teamwork formula |
| b-24 | **Pace** | A | `display = b-24` (28/28) |
| b-23 | **Strength** | A | `display = b-23` |
| b-22 | **Stamina** | A | `display = b-22` |
| b-21 | **Technique** | A | `display = b-21` (28/28) |
| b-20 | Consistency | hidden | — |
| b-19 | **Aggression** | A | `display = b-19` (28/28) |
| b-18 | Big Matches | hidden | — |
| b-17 | Injury Proneness | hidden | — |
| b-16 | **Leadership** | A | `display = b-16` |
| b-15 | Versatility | hidden | — |
| b-14 | Set Pieces | hidden | — |
| b-13 | Penalties | hidden | — |
| b-12 | Creativity | B | regression |
| b-11 | Movement | B | regression |
| b-10 | Positioning | B | regression |
| b-9 | **Teamwork**.Work Rate | A | part of Teamwork formula |
| b-8 | Flair | hidden | — |
| b-7 | Handling | B (GK) | regression |
| b-6 | Kicking | B (GK) | regression |
| b-5 | **Agility** | A | `display = b-5` (27/28) |
| b-4 | Aerial GK | B (GK) | (feeds keeper Aerial) |
| b-3 | Reflexes | B (GK) | regression |
| b-2 | Communication | B (GK) | `raw + Leadership` (see §3) |
| b-1 | Throwing | B (GK) | regression |

---

## 3. EXACT formulas (fully understood)

**Class-A attributes** — the stored byte *is* the displayed 1-20 value:
```
Pace       = byte[P-24]      Technique  = byte[P-21]
Strength   = byte[P-23]      Aggression = byte[P-19]
Stamina    = byte[P-22]      Leadership = byte[P-16]
Agility    = byte[P-5]
```

**Teamwork** (verified 28/28):
```
Teamwork = floor( (byte[P-25] + byte[P-9]) / 2 )
         = floor( (Unselfishness + Work Rate) / 2 )
```

**Communication** (mechanism confirmed; exact fit on the 4 keepers, but 4 points ≈
overfit so treat as strong-not-proven):
```
Communication_display = raw + f(Leadership)
```
This is why Communication was our worst regression miss (±5): the regressor targeted a
value that carries a leadership modifier it wasn't given. Add Leadership as an input.

---

## 4. The ESTIMATION model (Class-B) — the formulas I'm actually using

Each Class-B attribute is predicted by a linear model over a grid-searched subset of
features (`regress.py`). Inputs:
- `own`  = **unwrapped** byte at the attribute's offset (`b+256 if b<128`)
- `partner` = unwrapped byte of the 2nd sub-stat (Shooting/Aerial only)
- `CA`, `PA` = the record's CA/PA
- `own*CA` = `own * CA / 100` (multiplicative term — captures the CA entanglement)
- `mean9`  = mean of the 8 exact attributes (proxy for overall level)
- `fwd`    = position class (1.0 attacker / 0.5 midfield / 0.0 def-GK)

`display = round( Σ coef·feature + intercept )`, clamped 1-20. **Fitted coefficients**
(28 Bucaspor players; ±1 = within-one hit rate):

| Attribute | ±1 | Formula (coef·feature … + intercept) |
| --- | --- | --- |
| Tackling | 28/28 | `+0.106·own +0.067·CA -0.005·PA -0.731·fwd -22.32` |
| Shooting | 28/28 | `-0.121·CA -0.013·PA -0.090·mean9 +0.097·own*CA -0.686·fwd +0.025·partner -4.88` |
| Decisions | 28/28 | `+0.083·own +0.069·CA -0.031·PA +0.300·mean9 -0.146·fwd -16.40` |
| Kicking | 28/28 | `+0.159·own +0.172·CA -0.061·own*CA -32.01` |
| Reflexes | 28/28 | `+0.070·own -0.311·mean9 +0.028·own*CA -12.39` |
| Crossing | 27/28 | `+0.090·own +0.026·own*CA -18.86` |
| Creativity | 27/28 | `+0.081·own +0.025·own*CA -16.86` |
| Handling | 27/28 | `-0.250·CA +0.035·PA +0.126·own*CA +0.09` |
| Throwing | 27/28 | `+0.087·own +0.060·CA -18.83` |
| Aerial | 26/28 | `+0.128·own +0.847·partner -249.21` |
| Passing | 25/28 | `+0.166·own +0.206·CA +0.001·PA -0.071·own*CA -35.05` |
| Dribbling | 24/28 | `+0.115·own +0.076·CA -0.020·PA -0.104·mean9 -23.33` |
| Positioning | 24/28 | `+0.127·own +0.044·PA +0.642·fwd -26.97` |
| Movement | 23/28 | `+0.114·own -19.37` |
| Communication | 22/28 | `+0.060·own +0.039·PA -0.422·fwd -12.81` (should include Leadership) |

Overall on the 28 training players: **63% exact, 93% within ±1**
(`estimate_dump.py` → `attr_estimates.csv`). Coefficient table exported to
`model_weights.csv` (rows=attribute, cols=feature coefficient + intercept).

**Held-out validation (opponents NOT in training):**
- **Pazarlı** (24Erzincanspor CB, TID 21365): **15/17 exact, 17/17 within ±1** — the
  outfield decoder genuinely generalises (Crossing 4, Dribbling 4, Shooting 4,
  Tackling 12, Aggression 17 all exact).
- **Akyüz** (24Erzincanspor GK, TID 21124): **11/17 exact, 15/17 within ±1** — misses
  are Communication −5 (the un-applied Leadership modifier, §3) and Creativity +2.

> These coefficients are **not the game's formula** — they're a least-squares
> approximation of a position×attribute **weight table** (see §6). Treat them as a
> practical estimator, refit if the calibration set changes.

---

## 5. Where it's WRONG / uncertain

1. **Not bit-exact** for Class-B (±1 on ~8%, ±2+ on a few). Fine for scouting, not for
   claiming a player's exact Finishing.
2. **GK attributes are weak** (Communication ±5; Handling/Kicking/Reflexes/Throwing fit
   on only **4 keepers** → high overfit risk, coefficients not trustworthy).
3. **CA-dependence may be partly spurious** — CA correlates with all attributes, so
   `own*CA`/`CA` terms may be absorbing "overall level" rather than a true CA scaling.
4. **Communication** target carries a Leadership modifier not in the model (§3).
5. **CA/PA drift**: the 5 MB record and the 62 MB snapshot disagree on CA for ~6/28
   players (young ↑, old ↓). The 5 MB value is treated as authoritative/current.
6. **Aerial for keepers** doesn't fit `avg(Heading,Jumping)` — likely needs the GK
   Aerial component `b-4` (0-255 scale). Outfielder Aerial ≈ `round(avg(b-29,b-28))`.
7. **SID collisions**: SID is only 2 meaningful bytes. The `P%78==57` grid filter +
   position/foot/CA sanity make false hits rare, but not impossible for opponents we
   can't cross-check.

---

## 6. If/when we dig deeper — TODO & pointers

**Goal:** turn the ±1 estimate into an exact decode of the Class-B (CA-weighted) attrs.

- **Use the FM CA weight table** (saved from FM Scout; per-position attribute weights).
  The model is `CA = (weighted attribute avg / 20) * 200 * modifiers`. Our byte is
  effectively an attribute's **CA-contribution** (`attr × position_weight`), so
  `display ≈ (unwrapped_byte − offset) / position_weight`. With real per-position
  weights, the ±1 scatter should collapse.
  - **FMM rule (user): PHYSICAL attributes do NOT count toward CA in mobile.** So zero
    the physical rows (Acceleration, Agility, Balance, Jumping Reach, Natural Fitness,
    Pace, Stamina, Strength) when applying the table. This also *explains* why physical
    attrs are stored raw/Class-A. Aggression/Determination/Flair are CA-excluded too.
  - Weights are **not published as a formula** — they live in the FM pre-game editor.
    FMM likely uses a **simplified subset**, so desktop weights may need calibration.
  - **LEAD (user): the weight table may be embedded in the save/OBB itself** — the game
    must know the weights to compute CA, and the rough guide notes the save carries a
    decoded copy of `comps.dbc` (competition rules), so a `.dbc`-style attribute/CA
    weight table could be mirrored in-file. Hard to locate blind, but if we pin ONE
    exact per-position weight (e.g. from the FM editor or by solving one attribute from
    same-position players), we could grep the save/OBB for that value/sequence.
- **Get more calibration ground truth spanning positions** — our squad is heavy on
  CB/MC/wingers and has only 4 GKs. Opponent attribute screenshots for a full-back, a
  pure winger, a target man, and 2-3 more keepers would let `regress.py` isolate the
  per-position weights (and fix the GK attrs). Ground truth we already have: Pazarlı
  (24Erzincanspor CB, TID 21365), Akyüz (24Erzincanspor GK, TID 21124).
- **Verify the wrap threshold** (currently `<128`) against a player with a mid-range
  Class-B attribute near the wrap boundary.
- **Personality block** (`P-50…P-43`): decode the 8 values (b-50 Adaptability=16 for
  both "Adaptable" players is the confirmed anchor; the bytes look interleaved, so
  check for a u16/stride issue).
- **Re-derive coefficients** whenever `bucaspor_players.json` / calibration changes.

## Files

| File | Role |
| --- | --- |
| `league_attrs.py` | Locate any player's record via SID; read positions/feet/CA/PA/rep + exact attrs. |
| `export_calibration.py` → `calibration.csv` | Displayed values + all 78 raw bytes (guide-labeled) for the 28 Bucaspor players. |
| `regress.py` | Grid-search regression to decode Class-B attrs; reports exact/±1/R²/features. |
| `estimate_dump.py` → `attr_estimates.csv` | Per-player actual-vs-estimated for every attribute. |
