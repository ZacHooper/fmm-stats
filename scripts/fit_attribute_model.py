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

# The nine attributes the player screen does not show. The frozen model could not use them --
# they were parsed and discarded until 2026-09-16 -- and there is obvious structure to exploit:
# set_pieces ought to predict Crossing, penalty Shooting, flair Creativity, work_rate Movement.
HIDDEN = [n for n in HIDDEN_OFFSETS.values()]

COLS = {**SRC_OFFSETS, **PLAIN_OFFSETS, **HIDDEN_OFFSETS}
MEAN9 = ["heading_src", "unselfishness_src", "pace_src", "strength_src", "stamina_src",
         "technique_src", "aggression_src", "leadership_src", "agility_src"]
POS = ["GK", "SW", "DL", "DC", "DR", "DMC", "ML", "MC", "MR", "AML", "AMC", "AMR",
       "ST", "DML", "DMR"]
FWD_ATT, FWD_MID = ("ST", "AML", "AMR", "AMC"), ("ML", "MR", "MC", "DMC", "DML", "DMR")

# Feature sets to try per attribute; CV picks. "frozen" is whatever model.py already uses for
# that attribute, so the search always contains the incumbent's own shape.
# `fwd` IS NOT A CANDIDATE FEATURE AT ALL.
#
# It collapsed a player's whole positional profile to 1.0/0.5/0.0 off his top position -- an
# AMC/ST, a pure ST and a six-position utility attacker all became the single number 1.0. It
# is also not a quantity the game plausibly holds: the save stores 15 familiarities, not an
# attacking-ness score, so a feature shaped like that is our invention rather than a decoding
# of anything. Offered against a no-fwd alternative it earned its place for exactly one
# attribute of fifteen, which is what you would expect of a coincidence.
#
# It survives ONLY inside `MOD.predict`, which is the incumbent being measured against, not a
# candidate. Position now enters as familiarities: GK_FAM, NAT (natural-position flags) or POS.
_LEAN = ("own", "partner", "CA", "PA", "own*CA")
_BASE = _LEAN + ("mean9",)
# TWO CANDIDATES, NOT SEVEN -- because nested selection PAYS for every candidate it is
# offered. The inner fold picks on ~670 rows, so a candidate that is never genuinely best
# still wins folds by chance and drags the outer score down with it. Measured on 840 rows,
# same protocol throughout, shrinking the pool is monotonically better:
#
#     all 7                         68.1%        lean, gk, shared        68.7%
#     drop pos                      68.2%        gk, shared              69.3%
#     drop pos, nat                 68.6%        shared alone            66.1%
#
# The two kept are the two POLES, and they have different jobs rather than different sizes:
#   gk      the richest least-squares shape (it strictly contains `lean` and `base`), and it
#           wins every goalkeeping attribute, where the GK familiarity is what separates a
#           keeper's real Handling from an outfielder's floored 1.
#   shared  three parameters, grid-searched, and it wins seven of the nine outfield ones.
# `frozen`, `lean` and `base` are nested subsets of `gk` that the inner CV cannot reliably
# tell apart at this n; `nat` and `pos` spend 15 free parameters each on 840 rows.
#
# HONEST CAVEAT: this pool was chosen by looking at the table above, which is outer-level
# selection bias -- 69.3% is optimistic by however much that costs. The evidence worth
# trusting is the MONOTONE TREND and its mechanism, not the winning number.
SETS = {
    "gk":     _BASE + ("GK_FAM",),   # 8 params -- the richest least-squares shape
    # SHARED: three parameters, and the only candidate not fitted by least squares.
    #
    #     displayed = floor(beta*(w*own + (1-w)*partner) + gamma*CA + alpha)
    #
    # `gamma` is NOT free. It is the ONE shared per-player CA shift, fitted jointly across the
    # outfield entangled attributes and then held fixed -- residuals of a byte-only fit
    # correlate +0.66 across those attributes and a single per-row shift explains 69.3% of
    # their variance, so fourteen separate CA terms are fourteen estimates of one number. A
    # free per-attribute loading was measured and is WORSE (55.1% vs 57.7%).
    #
    # `beta`, `w` and `alpha` are GRID-SEARCHED on exact matches rather than least-squared.
    # That is the whole point: least squares minimises squared error while we score exact
    # matches, and on Aerial the same change was worth +16.7 points with no new inputs.
    # See docs/ATTRIBUTE_MODEL_HANDOFF.md.
    "shared": ("own", "partner", "CA"),
}

# Grid for the shared candidate. beta spans the range a byte->display slope actually takes
# (measured 0.070 for Decisions to 0.125 for Dribbling); alpha is the rounding offset, which
# every fold of the 2024 fit pushed negative.
# _ALPHA is a search AROUND the least-squares intercept, not an absolute range. The intercept
# these models need is about -20 to -35 (an unwrapped byte is ~170-330 and the display value is
# 1-20), so an absolute window would have to be both huge and fine. Seeding it from the
# residual mean makes the search two orders of magnitude smaller and cannot miss the optimum
# by more than the window.
_BETA = np.arange(0.04, 0.201, 0.0025)
_ALPHA = np.arange(-2.5, 2.51, 0.05)
_W = np.arange(0.0, 1.001, 0.05)

# The nine OUTFIELD entangled attributes. gamma is fitted from these, on non-GK players only:
# a GK attribute on an outfielder is pinned at the display floor (Communication is 1 for 100%
# of outfield truth rows), so including them would fit gamma to a constant.
_OUTFIELD_ENTANGLED = ("Crossing", "Dribbling", "Tackling", "Shooting", "Passing",
                       "Decisions", "Creativity", "Movement", "Positioning")
# The five that only a keeper really has; on an outfielder they sit at the display floor.
GK_ATTRS = ("Handling", "Kicking", "Reflexes", "Communication", "Throwing")


def _shared_gamma(Y, OWN, ca, mask):
    """The one CA slope, fitted jointly across the outfield entangled attributes.

    Alternating least squares: per-attribute slope+intercept given the shift, then the shift
    given the residuals. Linear in CA -- a quadratic term was measured and adds exactly
    nothing (R^2 0.896 either way)."""
    g = np.zeros(int(mask.sum()))
    gc = np.array([0.0, 0.0])
    for _ in range(10):
        resid = []
        for i in range(len(Y)):
            y, o = Y[i][mask], OWN[i][mask]
            k = ~np.isnan(y)
            if k.sum() < 10:
                continue
            A = np.c_[o[k], np.ones(int(k.sum()))]
            b, *_ = np.linalg.lstsq(A, y[k] - g[k], rcond=None)
            r = np.full(len(y), np.nan)
            r[k] = y[k] - A @ b
            resid.append(r)
        if not resid:
            return gc
        with np.errstate(invalid="ignore"):
            m = np.nanmean(np.array(resid), axis=0)
        ok = ~np.isnan(m)
        gc = np.polyfit(ca[mask][ok], m[ok], 1)
        g = np.polyval(gc, ca[mask])
    return gc


def _grid_fit(own, partner, ca, y, gc, has_partner):
    """(beta, w, alpha) maximising EXACT matches. Vectorised over alpha."""
    shift = np.polyval(gc, ca)          # the shared per-player CA term, held fixed
    best, arg = -1.0, (0.1, 1.0, 0.0)
    for w in (_W if has_partner else (1.0,)):
        blend = w * own + (1 - w) * partner if has_partner else own
        for beta in _BETA:
            v = beta * blend + shift
            a0 = float(np.mean(y - v))            # the least-squares intercept for this beta
            grid = a0 + _ALPHA
            hit = (np.clip(np.floor(v[None, :] + grid[:, None]), 1, 20)
                   == y[None, :]).mean(1)
            k = int(hit.argmax())
            if hit[k] > best:
                best, arg = hit[k], (beta, w, float(grid[k]))
    return arg


def _shared_predict(own, partner, ca, gc, arg, has_partner):
    beta, w, alpha = arg
    blend = w * own + (1 - w) * partner if has_partner else own
    return np.floor(beta * blend + np.polyval(gc, ca) + alpha)


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
        if n == "POS":
            f += list(fam)
        elif n == "NAT":
            f += [1.0 if v >= 20 else 0.0 for v in fam]
        elif n == "GK_FAM":
            f += [fam[POS.index("GK")]]
        elif n == "HID":
            f += [r[bi[h]] for h in HIDDEN]
        else:
            f += [vals[n]]
    return f + [1.0]


def score(pred, y):
    p = np.clip(np.rint(pred), 1, 20)
    return (p == y).mean(), (np.abs(p - y) <= 1).mean()


# The DECODER, and why it is worth a parameter of its own.
#
# Least squares minimises squared error; we score exact matches. Those are different
# objectives, and the rounding step sits between them with a free offset nobody had tuned.
# Tuning it
# on the training fold is worth +8.5 points on its own -- as much as the whole feature-
# selection apparatus -- and every fold of every attribute picks a NEGATIVE offset, which says
# the game's decoder is not round-half-up.
#
# It needs no schema: when decoding by rounding, shifting the prediction by `o` is identical
# to adding `o` to the intercept, so the tuned decoder is folded into the stored coefficients
# and the generated SQL keeps rounding exactly as before.
_OFFSETS = np.arange(-1.5, 1.51, 0.05)


def tune_offset(pred, y):
    """The offset that maximises EXACT matches on this (training) data."""
    best, bo = -1.0, 0.0
    for o in _OFFSETS:
        s = (np.clip(np.rint(pred + o), 1, 20) == y).mean()
        if s > best:
            best, bo = s, o
    return float(bo)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="fm-frem.duckdb")
    ap.add_argument("--write", action="store_true", help="replace staging.attribute_model")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--min-players", type=int, default=20,
                    help="refuse to refit an attribute whose own population has fewer distinct "
                         "players than this; keep the incumbent coefficients instead. The "
                         "learning curve is flat in ROWS and only bends in PLAYERS, so players "
                         "is the honest unit.")
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
          f"{'new ex':>9}{'new ±1':>9}{'n':>7}  features")
    # Joint inputs for the `shared` candidate: the outfield entangled targets, their own
    # bytes, CA, and who is a keeper. gamma is fitted from THESE, once per training mask.
    ca_all = np.array([r[1] for r in rows], float)
    is_gk = np.array([r[pi + POS.index("GK")] == 20 for r in rows])
    if is_gk.sum() < 30:
        print(f"note: only {int(is_gk.sum())} goalkeeper rows — the five GK attributes are "
              f"scored on those alone and their numbers are indicative at best\n")
    Y_j = np.array([[r[ai + ATTR_ORDER.index(a)] for r in rows] for a in _OUTFIELD_ENTANGLED],
                   float)
    OWN_j = np.array([[MOD.uw(r[bi[COLS[MOD.FROZEN[a][0]]]]) for r in rows]
                      for a in _OUTFIELD_ENTANGLED], float)
    _gcache = {}

    def gamma_for(mask):
        """The shared CA shift for a training mask, cached -- nested CV asks for it often."""
        key = mask.tobytes()
        if key not in _gcache:
            _gcache[key] = _shared_gamma(Y_j, OWN_j, ca_all, mask & ~is_gk)
        return _gcache[key]

    out, tot = [], np.zeros(4)
    for attr, (own, partner, ffeats, fcoef) in MOD.FROZEN.items():
        y = np.array([r[ai + ATTR_ORDER.index(attr)] for r in rows], float)
        keep = ~np.isnan(y)
        # NESTED selection. Choosing the feature set by the same CV score you then report is
        # selection bias -- with three candidates and fifteen attributes it flatters the
        # result for free. So the set is chosen INSIDE each training fold, and the outer fold
        # scores whatever that choice produced, on players it has never seen.
        pop0 = keep & (is_gk if attr in GK_ATTRS else ~is_gk)
        n_players = len({t for t, m in zip(tids, pop0) if m})
        if n_players < a.min_players:
            # NOT ENOUGH PLAYERS TO FIT THIS ONE. Frem has 7 goalkeepers, so the five keeper
            # attributes were being fitted on 66 rows over 7 people -- and it showed: on the
            # Bucaspor hold-out the refit scored 24.8% against the frozen model's 28.0%, i.e.
            # refitting them made things WORSE on a career it had not seen. Keeping the
            # incumbent is the honest outcome, and this is a SAMPLE-SIZE rule rather than a
            # score-based one, so it cannot be an accidental way of picking the winner.
            fz = np.array([MOD.predict(attr, _buf(r, bi), 60, r[1], r[2],
                                       sum(r[bi[c]] for c in MEAN9) / 9.0,
                                       _fwd(r, pi)) for r in rows], float)
            fex, f1 = score(fz[pop0], y[pop0])
            print(f"{attr:<15}{fex:>9.1%}{f1:>10.1%}{'—':>8}{'—':>9}"
                  f"{int(pop0.sum()):>7}  kept (only {n_players} players)")
            own_off, partner_off, ffeat, fcoef = MOD.FROZEN[attr]
            out.append((attr, own_off, partner_off, tuple(f for f in ffeat if f != "fwd"),
                        np.array([c for f, c in zip(ffeat, fcoef) if f != "fwd"]
                                 + [fcoef[-1]]), fex, fex))
            tot += (fex, f1, fex, f1)
            continue
        own_b = np.array([MOD.uw(r[bi[COLS[own]]]) for r in rows], float)
        par_b = (np.array([MOD.uw(r[bi[COLS[partner]]]) for r in rows], float)
                 if partner is not None else np.zeros(len(rows)))
        cand = {}
        for label, names in SETS.items():
            if label == "shared":
                cand[label] = (("own", "partner", "CA") if partner is not None
                               else ("own", "CA"), None)
                continue
            nm = tuple(n for n in ffeats if n != "fwd") if names is None else names
            if partner is None:
                nm = tuple(n for n in nm if n != "partner")
            cand[label] = (nm, np.array([features(r, bi, pi, own, partner, nm)
                                         for r in rows], float))

        def fit_predict(label, tr, te):
            """Predictions for `te` from a model fitted on `tr`. Both boolean row masks."""
            if label == "shared":
                gc = gamma_for(tr)
                arg = _grid_fit(own_b[tr], par_b[tr], ca_all[tr], y[tr], gc, partner is not None)
                return _shared_predict(own_b[te], par_b[te], ca_all[te], gc, arg,
                                       partner is not None)
            X = cand[label][1]
            c, *_ = np.linalg.lstsq(X[tr], y[tr], rcond=None)
            return X[te] @ c + tune_offset(X[tr] @ c, y[tr])

        pred = np.empty(len(rows))
        chosen = []
        for k in range(folds):
            te = fold == k
            tr = ~te & keep
            inner = np.array([fmap[t] for t in tids[tr]]) % (folds - 1)
            idx = np.flatnonzero(tr)
            pick, pick_ex = None, -1.0
            for label in cand:
                ip = np.empty(tr.sum())
                for j in range(folds - 1):
                    ite = inner == j
                    if ite.all() or not ite.any():
                        continue
                    m_tr = np.zeros(len(rows), bool); m_tr[idx[~ite]] = True
                    m_te = np.zeros(len(rows), bool); m_te[idx[ite]] = True
                    ip[ite] = fit_predict(label, m_tr, m_te)
                e, _ = score(ip, y[tr])
                if e > pick_ex:
                    pick, pick_ex = label, e
            chosen.append(pick)
            pred[te] = fit_predict(pick, tr, te)
        # SCORE EACH ATTRIBUTE ON THE POPULATION THAT HAS IT.
        #
        # A goalkeeping attribute is pinned at the display floor for an outfielder --
        # Communication is 1 on all 774 outfield truth rows -- so scoring it over everyone
        # measures how often we predict 1, not whether we can decode a keeper's hands. Before
        # this split Communication reported 92.4% (= 774/840) while scoring 6.1% on the 66 rows
        # that are actually keepers. The pooled number was true and meaningless.
        pop = keep & (is_gk if attr in GK_ATTRS else ~is_gk)
        ex, w1 = score(pred[pop], y[pop])
        label = max(set(chosen), key=chosen.count)          # the set the folds mostly agreed on
        names = cand[label][0]
        if label == "shared":
            # Stored as ordinary linear coefficients -- floor(b*(w*own + (1-w)*partner) +
            # gamma*CA + alpha) IS linear, so it needs no schema and the generated SQL is
            # unchanged. The floor-vs-round difference is absorbed by alpha (floor(x + a) ==
            # round(x + a - 0.5) away from exact ties).
            gc = gamma_for(keep)
            beta, w, alpha = _grid_fit(own_b[keep], par_b[keep], ca_all[keep], y[keep], gc,
                                       partner is not None)
            coef = ([beta * w, beta * (1 - w)] if partner is not None else [beta])
            coef += [gc[0], gc[1] + alpha - 0.5]
        else:
            X = cand[label][1]
            coef, *_ = np.linalg.lstsq(X[keep], y[keep], rcond=None)
            coef = coef.copy()
            coef[-1] += tune_offset(X[keep] @ coef, y[keep])  # decoder -> the intercept
        best = (ex, w1, label, names, coef)
        # the incumbent, scored on the same rows
        fz = np.array([MOD.predict(attr, _buf(r, bi), 60, r[1], r[2],
                                   sum(r[bi[c]] for c in MEAN9) / 9.0,
                                   _fwd(r, pi)) for r in rows], float)
        fex, f1 = score(fz[pop], y[pop])
        ex, w1, label, names, coef = best
        print(f"{attr:<15}{fex:>9.1%}{f1:>10.1%}{ex:>8.1%}{w1:>9.1%}"
              f"{int(pop.sum()):>7}  {label}")
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
            flat += ([f"NAT_{q}" for q in POS] if nm == "NAT" else
                     POS if nm == "POS" else
                     HIDDEN if nm == "HID" else
                     ["GK"] if nm == "GK_FAM" else [nm])
        for nm, c in list(zip(flat, coef)) + [("intercept", coef[-1])]:
            rows.append((attr, nm, float(c), own, partner, "refit-2026-09-17"))
    con.executemany("INSERT INTO staging.attribute_model VALUES (?,?,?,?,?,?)", rows)
    con.close()
    print(f"wrote {len(rows)} coefficients to staging.attribute_model in {db}")
    print("run:  uv run python load_duckdb.py --refresh-only --db " + db)


if __name__ == "__main__":
    raise SystemExit(main())
