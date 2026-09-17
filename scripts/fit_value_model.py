#!/usr/bin/env python3
"""
Fit the player transfer-value model and print coefficients for `fmparser/value_model.py`.

WHY THIS EXISTS. The save stores a transfer value ONLY for the club you manage — it lives
at `M+4` in the own-squad snapshot record (`fmparser/attributes.py:attr_record`), and that
record does not exist for any other club. Verified three ways on frem-2026-03-22:

  1. Searching the whole 63 MB file for `[club_tid u16][ff ff]` under each of five
     opponents' own club ids returns ZERO records.
  2. Taking our 51 players whose true value is known and testing every byte offset from
     P-300 to P+300 of the GLOBAL attribute record (the one every player has) for a u32
     matching that value returns ZERO matches at any offset.
  3. Our own values appear EXACTLY ONCE each in the entire file. If a general valuation
     table existed, our players would be in it too and there would be a second hit.

So a target's price cannot be read; it has to be estimated. The managed club's own
squad is the only labelled data there is, which is what this fits on.

USAGE
    uv run python scripts/fit_value_model.py                     # refit, print coefficients
    uv run python scripts/fit_value_model.py --db fm-frem.duckdb
    uv run python scripts/fit_value_model.py --compare           # also score rival specs

Paste the printed COEF block into `fmparser/value_model.py` and re-run
`load_duckdb.py --refresh-only` so `mart.player_value_est` picks it up.

READ THE LIMITS IN `docs/agent-context/player-value-estimation.md` BEFORE TRUSTING A NUMBER.
Short version: median error ~2.2x, so it ranks targets and gets the order of magnitude
right; it does not tell you whether a specific deal clears a budget. And an ASKING PRICE
is not a value — the one pair we have measured ran 31x (Røssner: £95k value, £3M ask).
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dashboard"))

# Features, in the order value_model.COEF stores them.
FEATURES = ["ca", "pa", "crep", "llrp", "gk", "acap", "acap2", "res"]

TRAIN_SQL = """
WITH c AS (
    SELECT season, phase, club_tid, name, league_reputation FROM mart.clubs
), par AS (
    SELECT season, phase, name, MAX(league_reputation) lr FROM c GROUP BY 1, 2, 3
), lr AS (
    SELECT c.season, c.phase, c.club_tid,
           COALESCE(c.league_reputation, p.lr)        AS lrp,
           (c.league_reputation IS NULL)::INT         AS is_res
    FROM c LEFT JOIN par p
      ON p.season = c.season AND p.phase = c.phase
     AND p.name = regexp_replace(c.name, ' Reserves$', '')
)
SELECT p.season, p.phase, p.tid, p.name, s.club,
       p.ca, p.pa, p.reputation, s.current_reputation, s.world_reputation,
       p.is_gk, s.age,
       lr.lrp, lr.is_res, p.player_value AS val
FROM staging.players p
JOIN mart.player_snapshots s USING (season, phase, tid)
JOIN lr ON lr.season = p.season AND lr.phase = p.phase AND lr.club_tid = s.club_tid
WHERE p.ca IS NOT NULL AND s.age IS NOT NULL AND lr.lrp IS NOT NULL
"""


def prep(df):
    """Feature matrix columns. Age is CAPPED AT 28 on purpose — see the docstring note."""
    df = df.copy()
    for col in ("age", "ca", "pa"):
        df[col] = df[col].astype(float)
    # CURRENT reputation, not home (P+21) — PR #51 parsed two more reputation fields off the
    # same record tail, and current_reputation beats home reputation on grouped-CV (0.704 vs
    # 0.694 R2, 30-seed average) with LOWER seed-to-seed variance, for the same reason it's
    # named "current": home reputation is a slower-moving figure, current tracks the player's
    # actual present standing. world_reputation was tried too (alone, alongside home, alongside
    # current, all three together) and never beat current-alone in any combination — see
    # docs/agent-context/player-value-estimation.md for the full comparison table.
    df["crep"] = np.log(df.current_reputation.astype(float))
    df["lrep"] = np.log(df.reputation.astype(float))       # kept for --compare only
    df["wrep"] = np.log(df.world_reputation.astype(float))  # kept for --compare only
    df["llrp"] = np.log(df.lrp.astype(float))           # league reputation
    df["gk"] = df.is_gk.astype(float)
    # The raw age quadratic turns UPWARD past ~28, claiming a 33-year-old is worth more
    # than a 26-year-old. That is not ageing, it is composition: the 29+ band is 8 players
    # in 100 rows and two of them are our best veterans, while the 26-28 band is low-CA
    # squad filler. A hinge spec reproduced the same upturn, so it is the data and not the
    # functional form. Capping at 28 costs ~0.004 CV R2 and stops the model saying
    # something absurd about a 33-year-old.
    df["acap"] = df.age.clip(upper=28)
    df["acap2"] = df.acap ** 2
    df["res"] = df.is_res.astype(float)                 # reserve side (no league rep of its own)
    return df


def design(df):
    return np.column_stack([np.ones(len(df))] + [df[f].values for f in FEATURES])


def r2(y, pred):
    return 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()


def grouped_cv(df, feats, seed=0, folds=5):
    """5-fold CV GROUPED BY PLAYER. Ungrouped CV leaks badly here: the same player appears
    in up to 22 snapshots, so a random split puts him in train and test at once."""
    X = np.column_stack([np.ones(len(df))] + [df[f].values for f in feats])
    y = df.y.values
    rng = np.random.default_rng(seed)
    pred = np.zeros(len(df))
    for fold in np.array_split(rng.permutation(df.tid.unique()), folds):
        te = df.tid.isin(fold).values
        beta = np.linalg.lstsq(X[~te], y[~te], rcond=None)[0]
        pred[te] = X[te] @ beta
    return r2(y, pred), pred


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", help="store to fit against (default: the career's)")
    ap.add_argument("--compare", action="store_true", help="score alternative specs too")
    args = ap.parse_args()
    if args.db:
        os.environ["FM_DUCKDB"] = args.db
    os.environ.setdefault("FM_DUCKDB_READONLY", "1")
    import db  # noqa: E402  (needs the env vars above)

    d = prep(db.q(TRAIN_SQL + " AND p.player_value > 0"))
    d["y"] = np.log(d.val.astype(float))
    print(f"{len(d)} labelled rows, {d.tid.nunique()} players, {d.phase.nunique()} snapshots")
    print(f"value range £{d.val.min():,.0f} - £{d.val.max():,.0f}\n")

    if args.compare:
        core = ["ca", "pa", "crep", "llrp", "gk"]
        specs = {
            "ca only": ["ca"],
            "no league rep": ["ca", "pa", "crep", "gk", "acap", "acap2", "res"],
            "raw age quadratic": core + ["age", "age2"],
            "home rep instead of current": ["ca", "pa", "lrep", "llrp", "gk", "acap", "acap2", "res"],
            "+world rep alongside current": ["ca", "pa", "crep", "wrep", "llrp", "gk", "acap", "acap2", "res"],
            "world rep only (no home/current)": ["ca", "pa", "wrep", "llrp", "gk", "acap", "acap2", "res"],
            "SHIPPED (current rep, age capped, +res)": FEATURES,
        }
        d["age2"] = d.age ** 2
        for name, feats in specs.items():
            score, pred = grouped_cv(d, feats)
            err = np.median(np.exp(np.abs(d.y.values - pred)))
            print(f"  {name:28s} CV R2={score:.3f}  median err={err:.2f}x")
        print()

    score, pred = grouped_cv(d, FEATURES)
    err = np.exp(np.abs(d.y.values - pred))
    band = d[(d.val >= 20_000) & (d.val <= 5_000_000)]
    berr = err[(d.val >= 20_000) & (d.val <= 5_000_000)]
    print(f"grouped-CV R2      {score:.3f}")
    print(f"median error       {np.median(err):.2f}x  (all {len(d)} rows)")
    print(f"  shopping range   {np.median(berr):.2f}x  (£20k-£5M, n={len(band)})")
    print(f"  70% within       {np.quantile(berr, 0.7):.2f}x")

    beta = np.linalg.lstsq(design(d), d.y.values, rcond=None)[0]
    print("\n# --- paste into fmparser/value_model.py ---")
    print(f"N_TRAIN, CV_R2, MEDIAN_ERR = {len(d)}, {score:.3f}, {np.median(err):.2f}")
    print("COEF = {")
    print(f'    "intercept": {float(beta[0])!r},')
    for name, value in zip(FEATURES, beta[1:]):
        print(f'    "{name}": {float(value)!r},')
    print("}")


if __name__ == "__main__":
    main()
