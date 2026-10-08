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

Built in the store and fitted by `scripts/fit_value_model.py` (refitted 2026-10-08). Seven
terms, each a rule a game designer could have written:

```
value ~ k x current_rep^2.92 x league_rep^2.18 x 1.030^PA x 1.015^CA
          x 1.10^(contract years left, up to 6)
          x 1.29^(years under 21) x 0.79^(years over 30)
```

| factor | effect |
|---|---|
| double the player's **current reputation** | **x7.4** |
| double his **league's reputation** | **x4.5** |
| +10 PA | x1.34 |
| +10 CA | x1.17 |
| +1 contract year left | x1.10 |
| each year **under 21** | x1.29 (an 18-year-old is ~2.1x a 21-year-old, all else equal) |
| ages 21-30 | no age effect |
| each year **over 30** | x0.79 (a 33-year-old is ~half a 30-year-old) |

Reputation -- the player's and his league's -- is most of a price; potential counts about twice
what ability does per point. In the store: `log(value) = intercept + SUM(term x coefficient)`
over `value_terms` (`fmstats/dbt_project.yml`), the terms built in `int.player_value_inputs`,
the coefficients in `seeds/value_model.csv`, scored by `int.player_value` into
`mart.fact_player_valuation` (`value_is_estimated`, `value_in_trusted_band`).

- **Labels** (`int.player_value_labels`): every stated value -- ours and the World Best XI's
  -- paired with the player's inputs on the snapshot nearest the entry's date, within 31 days,
  the same person by age. **1,576 labels from 572 players** (378 from our squad), against the
  old model's 1,044 rows from our squad alone, whose entries could be a year older than the
  snapshot they were paired with.
- **Validation**: 5-fold cross-validation **grouped by player** (a player appears in many
  entries; an ungrouped split leaks him into his own test set), mean of five splits.

| | CV R² | median error | £1-10M | over £10M | our squad |
|---|---|---|---|---|---|
| previous model (our squad only, age capped at 28), on these labels | 0.913 | 1.91x | 2.40x | 1.76x | 2.28x |
| a 17-term fit (wage, home/world reputation, interactions) | 0.949 | 1.34x | 1.4-1.5x | 1.2-1.3x | 2.22x |
| **shipped: the 7 terms above** | **0.939** | **1.36x** | **1.5-1.6x** | **1.2-1.3x** | **2.35x** |

Against our squad's stated values on 2028-05-09 (40 players) the shipped model is 2.16x off,
the 17-term fit 2.29x, the previous model 3.25x.

Error by **estimated** value -- the figure a user of the model sees, and what
`value_trusted_band` (**£1M and up**) is read from:

| estimated | n | median | 70% within |
|---|---|---|---|
| under £20k | 168 | 2.42x | 3.74x |
| £20k - £100k | 69 | 3.24x | 6.61x |
| £100k - £500k | 122 | 2.60x | 4.19x |
| £500k - £1M | 51 | 1.73x | 2.34x |
| £1M - £10M | 186 | 1.53-1.62x | 1.71-2.03x |
| £10M - £30M | 373 | 1.32x | 1.47x |
| £30M and up | 607 | 1.19-1.26x | 1.32-1.54x |

The elite labels fix the old model's blind spot (it had two training rows above reputation 7082
and put William Clem, true £17.5M, at £4.6M).

## 4. Limits -- read before quoting a number

* **Under £1M it ranks; it does not price.** 2-3x typical error, the band most of our own
  squad and the Danish lower leagues sit in. From £1M up it is within ~1.5x.
* **The top end extrapolates a little.** The highest label is £176M (Mbappé, 2023); the
  model's top estimate is his, £204M at 29 on 2028-05-09, above his own latest entry (£164M,
  2027).
* **Home and world reputation, wage and the reserve flag are not terms.** Current reputation
  carries the reputation signal; wage is set by the game from the same inputs, so it predicts
  value without explaining it (the 17-term fit with it is 0.02x better).
* Contract expiry exists for practically every player (25,590 of 25,662 on 2028-05-09); the
  rest get no estimate.

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
small place in the value model (x1.10 per year left, up to 6), nothing like the markups
below, so the ask is still unmodelled.

**The one lever left is logging in-game asking prices as labels.** Every quote the manager
sees is a labelled observation at a club we otherwise have no data for. ~20–30 across a
spread of clubs would make the markup estimable, and would also give the first non-Frem
anchors for the value model itself.

## 6. Also rejected

* **A 17-term fit** -- adds home and world reputation, wage, goalkeeper and reserve flags and four
  interactions with league reputation; 0.02x better overall and 0.13x on our squad in CV, but
  its coefficients only mean anything together (ability alone reads negative), and it is no
  better on our squad's current stated values.
* **A smooth age curve** (age, age², a hinge at 28) -- invented a dip at 23 and a bump at 28;
  the flat middle with two kinks fits as well or better.
* **A squared-ability term** -- put Mbappé at £300M.
* **A separate curve for low-reputation leagues** -- a small gain for twice the coefficients.
* **Training on our squad alone** -- 2.5x on our squad, worse than pooling with the world's
  best.
