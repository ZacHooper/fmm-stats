# Player transfer value: what the save holds, and the model that fills the gap

*Written 2026-09-14, from the Frem career (`fm-frem`, 22 snapshots, latest 2026-03-22).*

## 1. The save stores a value ONLY for the club you manage

`fmparser/attributes.py:attr_record` reads it as a u32 at `M+4` of the own-squad snapshot
record, where `M` is the `[club_tid u16][ff ff]` marker. That record does not exist for any
other club. Three independent checks on `frem-2026-03-22.fms`:

1. **No squad record for other clubs.** The marker is generic, so the whole 63 MB file was
   searched for `[club_tid][ff ff]` under each target's own club id. Clem (Wolfsburg),
   Røssner (Brøndby Res), Mathisen (Brøndby), Donovan (Odense), Kaiser (FCK): **0 hits each**.
2. **Not on the global attribute record either.** Every player has one (`record_for`) — it is
   where estimated attributes and the career-history pointer come from. Taking the 51 own
   players whose true value is known and testing every offset from `P-300` to `P+300` for a
   u32 equal to that value: **zero matches at any offset**.
3. **Our own values appear exactly once in the file.** Ementa £2,045,965, Garly £1,574,253,
   Jakobsen £1,428,889, Secka £703,787, Tjørnelund £535,839 — one occurrence each, all inside
   the snapshot record. A general valuation table would contain our players too and produce a
   second hit.

A handful of *smaller* values do appear elsewhere, around 44–45.6M. That is a 16-byte-stride
table of sequential ids (`a4 2f 03 00`, `a5 2f 03 00`, `a6 2f 03 00` …) — Grosso's £208,804
happens to collide with one entry. Coincidence, not a value table.

**Conclusion: a target's price cannot be read out of the save. It has to be modelled.**

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

`fmparser/value_model.py` (frozen coefficients, same pattern as `model.py`), refit with
`scripts/fit_value_model.py`, surfaced as `mart.player_value_est`.

OLS on log(value), trained on the managed club's own squad across all snapshots — **734 rows,
80 players, 22 snapshots**, the only labelled data that exists.

```
log(value) = intercept + ca*CA + pa*PA + lrep*ln(player rep) + llrp*ln(league rep)
           + gk*is_gk + acap*A + acap2*A^2 + res*is_reserve,  A = min(age, 28)
```

Validated with **5-fold CV grouped by player** — ungrouped CV leaks badly, since one player
appears in up to 22 snapshots.

| Spec | CV R² | Median error |
|---|---|---|
| ca only | 0.612 | 2.75× |
| no league reputation | 0.686 | 2.49× |
| **shipped** | **0.717** | **2.27×** |

In the £20k–£5M band real targets live in: **median 2.15×, 70% within 3.6×**.

Effect sizes, holding everything else equal — age is the second-biggest term after reputation:

| Age | 17 | 19 | 21 | 23 | 25 | 27 | 29+ |
|---|---|---|---|---|---|---|---|
| × a 26-year-old | 6.4× | 3.6× | 2.2× | 1.5× | 1.1× | 0.9× | 0.86× |

## 4. Limits — read before quoting a number

* **It ranks; it does not price.** 2.3× typical error separates a £200k player from a £2M one
  and nothing finer. It cannot tell you whether a deal clears a budget.
* **Above ~£5M it is unevidenced.** Only 2 training rows sit above reputation 7082, and our
  most valuable player ever is £6.76M. William Clem (true £17.5M) predicts £4.6M — 4× low.
* **Reserve-side players are the weakest case.** A reserve team has no league reputation of
  its own and inherits its first team's, which overshoots: Røssner (true £95k) predicts £280k
  with the fallback, £126k without it. The `res` term absorbs only part of this.
* **In-sample fit on our own expensive players is visibly loose** — Garly £1,574,253 actual vs
  £186,803 estimated. The view exposes `value_actual` beside `value_est` precisely so this
  stays checkable rather than hidden.
* **`llrp` is only identifiable because Frem climbed divisions** (league rep 14,860 → 34,817
  across the training window). A career that never changed division has no variation to fit it
  from and the term will be meaningless there.

## 5. AN ASKING PRICE IS NOT A VALUE — and this is the big one

The markup is large, varies enormously, and is **not modelled at all**:

| | Value | Ask | Multiple |
|---|---|---|---|
| Røssner, 18, coveted, long contract | £95,000 | £3,000,000 | **31×** |
| Mathisen, 30 | ~£250k (est) | £600–875k | **~3×** |

This is what actually cost us in the 2026 summer window: Røssner looked affordable on value
and was not. **Never present an estimate as a fee.**

Contract length is the obvious candidate for modelling the markup and **does not predict
value**: full coverage (734/734 rows, median 1.84 years remaining), in-sample coefficient
+0.28 in the right direction, but it *lowers* grouped-CV R² in every spec (0.724 → 0.722, and
0.718 adding a final-year flag). The reading is that contract length drives the ask, not the
value — which is consistent with Røssner.

**The one lever left is logging in-game asking prices as labels.** Every quote the manager
sees is a labelled observation at a club we otherwise have no data for. ~20–30 across a
spread of clubs would make the markup estimable, and would also give the first non-Frem
anchors for the value model itself.

## 6. Also rejected

* **Raw age quadratic** — scores marginally better (0.724) but turns *upward* past 28,
  claiming a 33-year-old is worth 1.5× a 26-year-old. Composition, not ageing: the 29+ band is
  8 players in 100 rows including our two best veterans, while 26–28 is low-CA squad filler. A
  hinge spec reproduced the same upturn. Age is capped at 28 on purpose.
* **Potential headroom (PA − CA)** — an exact linear combination of `ca` and `pa`; added a
  rank deficiency and nothing else.
