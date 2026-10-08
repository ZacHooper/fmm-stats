# Player transfer value: what the save holds, and the model that fills the gap

*Written 2026-09-14; the model refitted 2026-10-08 on the 31-snapshot Frem store (latest 2028-05-09).*

## 1. Where the save states a value: Scrapbook Profiles only

A transfer value is stored on a **Scrapbook Profile** -- a copy of a player's profile screen as
it was on its date (`fmparser/tables/player_lists.py`, `stg.scrapbook_entries.value`). Our own
squad has one per player (the Manager's Best Eleven lists, which is where `int.player_info.value`
comes from), and the World Best XI and All-Time pools hold one for every player who made them:
**611 of the world's best players, 2,435 entries, £500 to £176M** on the 2028-05-09 store. A
player in neither has no stated value anywhere, which the search below established for the
squad records and the global attribute record.

Three independent checks on `frem-2026-03-22.fms` that no general valuation table exists:

1. **No squad record for other clubs.** The marker is generic, so the whole 63 MB file was
   searched for `[club_tid][ff ff]` under each target's own club id. Clem (Wolfsburg),
   Røssner (Brøndby Res), Mathisen (Brøndby), Donovan (Odense), Kaiser (FCK): **0 hits each**.
2. **Not on the global attribute record either.** Every player has one (`record_for`) — it is
   where estimated attributes and the career-history pointer come from. Taking the 51 own
   players whose true value is known and testing every offset from `P-300` to `P+300` for a
   u32 equal to that value: **zero matches at any offset**.
3. **Our own values appear exactly once in the file.** Ementa £2,045,965, Garly £1,574,253,
   Jakobsen £1,428,889, Secka £703,787, Tjørnelund £535,839 — one occurrence each, all inside
   our squad's scrapbook profiles. A general valuation table would contain our players too and produce a
   second hit.

A handful of *smaller* values do appear elsewhere, around 44–45.6M. That is a 16-byte-stride
table of sequential ids (`a4 2f 03 00`, `a5 2f 03 00`, `a6 2f 03 00` …) — Grosso's £208,804
happens to collide with one entry. Coincidence, not a value table.

**Conclusion: a target outside the scrapbook pools has no price in the save. It has to be modelled.**

## 2. There is no "band" field either

Scanning every u8/u16 offset from `P-80` to `P+80` for rank correlation with log(value)
across the 51 labelled players returns only fields we already decode:

| Offset | Field | ρ with log(value) |
|---|---|---|
| P+21 | reputation | +0.848 |
| P+17 | ca | +0.839 |
| P+19 | pa | +0.794 |

Nothing else. The value is derived by the game, not stored in coarse form.

## 3. The model

Built in the store and fitted by `scripts/fit_value_model.py` (refitted 2026-10-08):

- **Terms** (`int.player_value_inputs`, list `value_terms` in `fmstats/dbt_project.yml`):
  ability and potential; the reputation trio (home, current, world) and the league's
  reputation, as logs; goalkeeper and reserve flags; age as a quadratic with a hinge past 28;
  log wage; contract years left (capped at 6); and four interactions -- ability x league
  reputation, reputation x league reputation, wage x league reputation, and the potential still
  to come for a player under 23. `log(value) = intercept + SUM(term x coefficient)`,
  coefficients in `seeds/value_model.csv`, scored by `int.player_value` into
  `mart.fact_player_valuation` (`value_is_estimated`, `value_in_trusted_band`).
- **Labels** (`int.player_value_labels`): every stated value -- ours and the World Best XI's
  -- paired with the player's inputs on the snapshot nearest the entry's date, within 31 days,
  the same person by age. **1,576 labels from 572 players** (378 from our squad), against the
  old model's 1,044 rows from our squad alone, whose entries could be a year older than the
  snapshot they were paired with.
- **Validation**: 5-fold cross-validation **grouped by player** (a player appears in many
  entries; an ungrouped split leaks him into his own test set), mean of five splits.

| | CV R² | median error | under £1M | £1-10M | over £10M | our squad |
|---|---|---|---|---|---|---|
| previous model (our squad, age capped), on these labels | 0.913 | 1.91x | 2.21x | 2.40x | 1.76x | 2.28x |
| **shipped**, refitted | **0.949** | **1.34x** | 2.4x | **1.4-1.5x** | **1.2-1.3x** | 2.22x |

Error by **estimated** value -- the figure a user of the model sees, and what
`value_trusted_band` (**£1M and up**) is read from:

| estimated | n | median | 70% within |
|---|---|---|---|
| under £20k | 170 | 2.23x | 3.77x |
| £20k - £100k | 77 | 3.38x | 5.34x |
| £100k - £500k | 114 | 2.71x | 4.13x |
| £500k - £1M | 43 | 2.15x | 2.41x |
| £1M - £2M | 47 | 1.51x | 1.93x |
| £2M - £10M | 140 | 1.39-1.40x | 1.54-1.66x |
| £10M - £30M | 352 | 1.33x | 1.51x |
| £30M and up | 633 | 1.19-1.20x | 1.30-1.32x |

The elite labels fix the old model's blind spot (it had two training rows above reputation 7082
and put William Clem, true £17.5M, at £4.6M) and also improve our own squad (2.22x against
2.28x; trained on our squad alone, time-aligned, it scores 2.5x): they pin down the slopes the
small sample could not.

## 4. Limits -- read before quoting a number

* **Under £1M it ranks; it does not price.** 2-3x typical error, the band most of our own
  squad and the Danish lower leagues sit in. Above £1M it is within ~1.5x.
* **The top end extrapolates a little.** The highest label is £176M (Mbappé, 2023); the
  model's top estimate is his, £214M at 29 on 2028-05-09, above his own latest entry (£164M,
  2027). The squared-ability term was dropped because it put him at £300M.
* **A single coefficient means nothing alone**: ability enters directly and through its
  interaction with league reputation (ca -0.04, ca x llrp +0.013), so read an effect only
  through the model as a whole.
* **Reserve-side players** take their first team's league reputation with the `res` term.
* Wage and contract expiry exist for practically every player (25,590 of 25,662 on
  2028-05-09); the 72 without them get no estimate.

## 5. AN ASKING PRICE IS NOT A VALUE — and this is the big one

The markup is large, varies enormously, and is **not modelled at all**:

| | Value | Ask | Multiple |
|---|---|---|---|
| Røssner, 18, coveted, long contract | £95,000 | £3,000,000 | **31×** |
| Mathisen, 30 | ~£250k (est) | £600–875k | **~3×** |

This is what actually cost us in the 2026 summer window: Røssner looked affordable on value
and was not. **Never present an estimate as a fee.**

Contract length is the obvious candidate for modelling the markup. On our squad alone it did
not predict value (it lowered grouped-CV R² in every spec); with the elite labels it earns a
small place in the value model (+0.09 per year left, up to 6), but nothing like the markups
below, so the ask is still unmodelled.

**The one lever left is logging in-game asking prices as labels.** Every quote the manager
sees is a labelled observation at a club we otherwise have no data for. ~20–30 across a
spread of clubs would make the markup estimable, and would also give the first non-Frem
anchors for the value model itself.

## 6. Also rejected

* **A squared-ability term** -- marginally better in CV but extrapolated the very top to
  £300M.
* **A separate curve for low-reputation leagues** -- 2.15x on our squad against 2.22x, for
  twice the coefficients and a league threshold; the single model's interactions get the same
  £1-10M error.
* **Training on our squad alone** -- 2.5x on our squad, worse than pooling with the world's
  best.
