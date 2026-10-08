#!/usr/bin/env python3
"""
Fit the player transfer-value model and write its coefficients to `seeds/value_model.csv`.

WHAT THE SAVE STATES. A transfer value is stored only on a Scrapbook Profile -- a copy of a
player's profile screen as it was on its date (`fmparser/tables/player_lists.py`). Our own
squad has one per player (the Manager's Best Eleven lists), and the World Best XI and All-Time
pools hold one for every player who made them: the world's best, at every elite club. Nothing
else in the save holds a value (`docs/agent-context/player-value-estimation.md`), so every
other player's price is this model's estimate.

THE TRAINING ROWS are `int.player_value_labels`: each stated value paired with the player's
model inputs on the snapshot nearest its date (within `value_label_max_gap_days`), so a label
is never asked to predict a player as he was a year later. The terms are built once, in
`int.player_value_inputs`, which `int.player_value` also scores: the fit and the scorer cannot
drift apart. The term list is `value_terms` in `fmstats/dbt_project.yml`.

VALIDATION is 5-fold cross-validation GROUPED BY PLAYER -- a player appears in many entries and
snapshots, and an ungrouped split leaks him into his own test set -- averaged over five splits.
Error is the median factor between estimate and stated value (2.0x = half or double), reported
by ESTIMATED value, since the estimate is all a user of the model sees; that table is what
`value_trusted_band` is read from.

USAGE
    uv run python scripts/fit_value_model.py                  # refit and report
    uv run python scripts/fit_value_model.py --write          # ... and write seeds/value_model.csv
    uv run python load_duckdb.py --refresh-only --db fm-frem.duckdb    # then reseed and rescore

READ THE LIMITS IN `docs/agent-context/player-value-estimation.md` BEFORE TRUSTING A NUMBER. An
asking price is not a value (the one pair measured ran 31x: Røssner, £95k value, £3M ask).
"""
import argparse
import csv
import os
import sys

import numpy as np
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dbopen import open_readonly  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED = os.path.join(REPO, "seeds", "value_model.csv")
BANDS = [0, 2e4, 1e5, 5e5, 1e6, 2e6, 5e6, 1e7, 3e7, 1e8, float("inf")]


def project_vars():
    with open(os.path.join(REPO, "fmstats", "dbt_project.yml")) as fh:
        return yaml.safe_load(fh)["vars"]


def design(rows, terms):
    return np.column_stack([np.ones(len(rows))] + [rows[t].to_numpy(float) for t in terms])


def grouped_cv(rows, terms, seed, folds=5):
    rng = np.random.default_rng(seed)
    pred = np.zeros(len(rows))
    for fold in np.array_split(rng.permutation(rows.person_id.unique()), folds):
        test = rows.person_id.isin(fold).to_numpy()
        beta = np.linalg.lstsq(design(rows[~test], terms), rows.y[~test], rcond=None)[0]
        pred[test] = design(rows[test], terms) @ beta
    return pred


def report(label, pred, rows):
    err = np.exp(np.abs(rows.y.to_numpy() - pred))
    r2 = 1 - ((rows.y - pred) ** 2).sum() / ((rows.y - rows.y.mean()) ** 2).sum()
    ours = rows.is_our_club.to_numpy()
    print(f"{label}: R2 {r2:.3f}, median error {np.median(err):.2f}x "
          f"(our squad {np.median(err[ours]):.2f}x, n={ours.sum()}; "
          f"the world's {np.median(err[~ours]):.2f}x, n={(~ours).sum()})")
    est = np.exp(pred)
    print(f"  {'estimated value':>24s}  {'n':>5s}  median  70% within")
    for lo, hi in zip(BANDS, BANDS[1:]):
        m = (est >= lo) & (est < hi)
        if m.any():
            top = "      " if hi == float("inf") else f"£{hi / 1e6:7.2f}M"
            print(f"  £{lo / 1e6:7.2f}M - {top}  {m.sum():5d}  {np.median(err[m]):5.2f}x  "
                  f"{np.quantile(err[m], 0.7):5.2f}x")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="fm-frem.duckdb", help="store to fit against")
    ap.add_argument("--write", action="store_true", help="write seeds/value_model.csv")
    args = ap.parse_args()

    terms = project_vars()["value_terms"]
    con, _ = open_readonly(args.db, tag="fit_value_model")
    rows = con.execute(f"""
        SELECT person_id, entry_date, stated_value, is_our_club, {', '.join(terms)}
        FROM int.player_value_labels
        WHERE {' AND '.join(f'{t} IS NOT NULL' for t in terms)}""").df()
    rows["y"] = np.log(rows.stated_value.astype(float))
    print(f"{len(rows)} labelled values, {rows.person_id.nunique()} players "
          f"({rows.is_our_club.sum()} from our squad), "
          f"£{rows.stated_value.min():,.0f} - £{rows.stated_value.max():,.0f}\n")

    seeded = dict(con.execute("SELECT term, coefficient FROM stg.value_model").fetchall())
    if set(terms) <= set(seeded):
        beta = np.array([seeded["intercept"]] + [seeded[t] for t in terms])
        report("seeded coefficients, as they are", design(rows, terms) @ beta, rows)
        print()

    pred = np.mean([grouped_cv(rows, terms, seed) for seed in range(5)], axis=0)
    report("refit, grouped 5-fold CV by player (mean of 5 splits)", pred, rows)

    beta = np.linalg.lstsq(design(rows, terms), rows.y, rcond=None)[0]
    coefficients = [("intercept", float(beta[0]))] + [(t, float(b)) for t, b in zip(terms, beta[1:])]
    print("\nterm,coefficient")
    for term, value in coefficients:
        print(f"{term},{value!r}")
    if args.write:
        with open(SEED, "w", newline="") as fh:
            out = csv.writer(fh, lineterminator="\n")
            out.writerow(["term", "coefficient"])
            out.writerows([(t, repr(v)) for t, v in coefficients])
        print(f"\nwrote {SEED}; run: uv run python load_duckdb.py --refresh-only --db {args.db}")


if __name__ == "__main__":
    main()
