#!/usr/bin/env python3
"""Refit the entangled-attribute model AGAINST THE STORE, and optionally write it back.

Since the estimation moved into the database (2026-09-17) this needs no save file and no
re-extract: `staging.players` carries the raw record bytes and `player_attributes_exact`
carries the values the save states outright. Our own squad has all 23 exact, from the
managed-club snapshot -- those rows are the ground truth, and there is one per player PER
SNAPSHOT.

    uv run python scripts/fit_attribute_model.py --db fm-frem.duckdb            # report only
    uv run python scripts/fit_attribute_model.py --db fm-frem.duckdb --write    # then refresh

Two rules the 2024 fit could not follow with 28 players, and which this enforces:

  * HOLD OUT BY PLAYER, not by row. The same player appears in up to 25 snapshots; splitting
    rows at random leaks him into his own test set and inflates every number.
  * SCORE THE INCUMBENT ON THE SAME HELD-OUT ROWS. A new model that looks better only because
    the protocol changed is worse than useless, so the frozen coefficients are re-scored here
    rather than compared against the number in model.py's docstring.

`--write` replaces staging.attribute_model. Nothing takes effect until the views are rebuilt:
    uv run python load_duckdb.py --refresh-only --db fm-frem.duckdb
"""
import argparse
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser import model as MOD                                    # noqa: E402
from fmparser.attributes import (ATTR_ORDER, SRC_OFFSETS, PLAIN_OFFSETS,   # noqa: E402
                                 HIDDEN_OFFSETS)

COLS = {**SRC_OFFSETS, **PLAIN_OFFSETS, **HIDDEN_OFFSETS}
MEAN9 = ["heading_src", "unselfishness_src", "pace_src", "strength_src", "stamina_src",
         "technique_src", "aggression_src", "leadership_src", "agility_src"]
POS = ["GK", "SW", "DL", "DC", "DR", "DMC", "ML", "MC", "MR", "AML", "AMC", "AMR",
       "ST", "DML", "DMR"]
FWD_ATT, FWD_MID = ("ST", "AML", "AMR", "AMC"), ("ML", "MR", "MC", "DMC", "DML", "DMR")

# Feature sets to try per attribute; CV picks. "frozen" is whatever model.py already uses for
# that attribute, so the search always contains the incumbent's own shape.
SETS = {
    "frozen": None,
    "base":   ("own", "partner", "CA", "PA", "mean9", "own*CA", "fwd"),
    "pos":    ("own", "partner", "CA", "PA", "mean9", "own*CA", "fwd", "POS"),
}


def load(db):
    import duckdb
    con = duckdb.connect(db, read_only=True)
    byte_cols = sorted(set(COLS.values()))
    sql = f"""
        SELECT p.tid, p.ca, p.pa,
               {', '.join('p."' + c + '"' for c in byte_cols)},
               {', '.join('e."' + a + '"' for a in ATTR_ORDER)},
               {', '.join(f'''COALESCE((SELECT t.familiarity FROM staging.player_positions t
                    WHERE (t.season,t.phase,t.tid)=(p.season,p.phase,p.tid)
                      AND t.position = '{q}'), 0)''' for q in POS)}
        FROM staging.players p
        JOIN staging.player_attributes_exact e USING (season, phase, tid)
        WHERE p.ca IS NOT NULL AND p.passing_src IS NOT NULL
          AND e."Passing" IS NOT NULL          -- exact rows only: our own squad
    """
    rows = con.execute(sql).fetchall()
    bi = {c: 3 + i for i, c in enumerate(byte_cols)}
    ai = 3 + len(byte_cols)
    pi = ai + len(ATTR_ORDER)
    return rows, bi, ai, pi


def features(r, bi, pi, own, partner, names):
    g = lambda off: r[bi[COLS[off]]]
    o = MOD.uw(g(own))
    ca, pa = r[1], r[2]
    m9 = sum(r[bi[c]] for c in MEAN9) / 9.0
    fam = r[pi:pi + len(POS)]
    top = POS[int(np.argmax(fam))] if max(fam) else ""
    fwd = 1.0 if top in FWD_ATT else (0.5 if top in FWD_MID else 0.0)
    vals = {"own": o, "CA": ca, "PA": pa, "mean9": m9, "own*CA": o * ca / 100.0, "fwd": fwd,
            "partner": MOD.uw(g(partner)) if partner is not None else 0.0}
    f = []
    for n in names:
        f += list(fam) if n == "POS" else [vals[n]]
    return f + [1.0]


def score(pred, y):
    p = np.clip(np.rint(pred), 1, 20)
    return (p == y).mean(), (np.abs(p - y) <= 1).mean()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="fm-frem.duckdb")
    ap.add_argument("--write", action="store_true", help="replace staging.attribute_model")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--min-rows", type=int, default=400,
                    help="refuse to fit below this. One snapshot yields ~30 exact rows, which "
                         "cannot support even the incumbent's 5-parameter shape; lower it only "
                         "to smoke-test the pipeline, never to produce coefficients to keep.")
    a = ap.parse_args()
    if not os.path.exists(a.db):
        print(f"{a.db} not found")
        return 1
    rows, bi, ai, pi = load(a.db)
    tids = np.array([r[0] for r in rows])
    uniq = np.array(sorted(set(tids.tolist())))
    folds = min(a.folds, len(uniq))
    if len(rows) < a.min_rows or folds < 2:
        print(f"only {len(rows)} exact rows over {len(uniq)} players — not enough to fit "
              f"(need {a.min_rows}; --min-rows to override for a pipeline smoke test)")
        return 1
    rng = np.random.default_rng(0)
    fmap = {t: i % folds for i, t in enumerate(rng.permutation(uniq))}
    fold = np.array([fmap[t] for t in tids])
    print(f"{len(rows):,} exact rows over {len(uniq)} distinct players, "
          f"{folds} folds held out BY PLAYER\n")
    print(f"{'attribute':<15}{'frozen ex':>10}{'frozen ±1':>10}"
          f"{'new ex':>9}{'new ±1':>9}  features")
    out, tot = [], np.zeros(4)
    for attr, (own, partner, ffeats, fcoef) in MOD.FROZEN.items():
        y = np.array([r[ai + ATTR_ORDER.index(attr)] for r in rows], float)
        keep = ~np.isnan(y)
        # NESTED selection. Choosing the feature set by the same CV score you then report is
        # selection bias -- with three candidates and fifteen attributes it flatters the
        # result for free. So the set is chosen INSIDE each training fold, and the outer fold
        # scores whatever that choice produced, on players it has never seen.
        cand = {}
        for label, names in SETS.items():
            nm = ffeats if names is None else names
            if partner is None:
                nm = tuple(n for n in nm if n != "partner")
            cand[label] = (nm, np.array([features(r, bi, pi, own, partner, nm)
                                         for r in rows], float))
        pred = np.empty(len(rows))
        chosen = []
        for k in range(folds):
            te = fold == k
            tr = ~te & keep
            inner = np.array([fmap[t] for t in tids[tr]]) % (folds - 1)
            pick, pick_ex = None, -1.0
            for label, (nm, X) in cand.items():
                ip = np.empty(tr.sum())
                Xtr, ytr = X[tr], y[tr]
                for j in range(folds - 1):
                    ite = inner == j
                    if ite.all() or not ite.any():
                        continue
                    c, *_ = np.linalg.lstsq(Xtr[~ite], ytr[~ite], rcond=None)
                    ip[ite] = Xtr[ite] @ c
                e, _ = score(ip, ytr)
                if e > pick_ex:
                    pick, pick_ex = label, e
            chosen.append(pick)
            nm, X = cand[pick]
            c, *_ = np.linalg.lstsq(X[tr], y[tr], rcond=None)
            pred[te] = X[te] @ c
        ex, w1 = score(pred[keep], y[keep])
        label = max(set(chosen), key=chosen.count)          # the set the folds mostly agreed on
        names, X = cand[label]
        coef, *_ = np.linalg.lstsq(X[keep], y[keep], rcond=None)
        best = (ex, w1, label, names, coef)
        # the incumbent, scored on the same rows
        fz = np.array([MOD.predict(attr, _buf(r, bi), 60, r[1], r[2],
                                   sum(r[bi[c]] for c in MEAN9) / 9.0,
                                   _fwd(r, pi)) for r in rows], float)
        fex, f1 = score(fz[keep], y[keep])
        ex, w1, label, names, coef = best
        print(f"{attr:<15}{fex:>9.1%}{f1:>10.1%}{ex:>8.1%}{w1:>9.1%}  {label}")
        out.append((attr, own, partner, names, coef, ex, fex))
        tot += (fex, f1, ex, w1)
    n = len(MOD.FROZEN)
    print(f"\n{'MEAN':<15}{tot[0]/n:>9.1%}{tot[1]/n:>10.1%}{tot[2]/n:>8.1%}{tot[3]/n:>9.1%}")
    better = sum(1 for o in out if o[5] > o[6])
    print(f"\n{better} of {n} attributes improve on the frozen model.")
    if a.write:
        _write(a.db, out)
    else:
        print("report only — pass --write to replace staging.attribute_model")
    return 0


def _buf(r, bi):
    b = bytearray(120)
    for off, name in COLS.items():
        b[60 + off] = r[bi[name]]
    return b


def _fwd(r, pi):
    fam = r[pi:pi + len(POS)]
    top = POS[int(np.argmax(fam))] if max(fam) else ""
    return 1.0 if top in FWD_ATT else (0.5 if top in FWD_MID else 0.0)


def _write(db, out):
    import duckdb
    con = duckdb.connect(db)
    con.execute("DELETE FROM staging.attribute_model")
    rows = []
    for attr, own, partner, names, coef, *_ in out:
        flat = []
        for nm in names:
            flat += POS if nm == "POS" else [nm]
        for nm, c in list(zip(flat, coef)) + [("intercept", coef[-1])]:
            rows.append((attr, nm, float(c), own, partner, "refit-2026-09-17"))
    con.executemany("INSERT INTO staging.attribute_model VALUES (?,?,?,?,?,?)", rows)
    con.close()
    print(f"wrote {len(rows)} coefficients to staging.attribute_model in {db}")
    print("run:  uv run python load_duckdb.py --refresh-only --db " + db)


if __name__ == "__main__":
    raise SystemExit(main())
