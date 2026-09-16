"""Outer-CV exact-match score of EVERY candidate, per attribute -- what nested selection hides.

Nested selection reports the score of whatever the inner fold chose, which is the honest
number. This is the diagnostic view: it shows what each candidate would have scored on its
own, so a candidate that never gets picked can be told apart from one that is broken.
"""
import sys, os, numpy as np
sys.path.insert(0, "scripts"); sys.path.insert(0, ".")
import fit_attribute_model as F
from fmparser import model as MOD
from fmparser.attributes import ATTR_ORDER

rows, bi, ai, pi = F.load(sys.argv[1])
tids = np.array([r[0] for r in rows]); uniq = np.array(sorted(set(tids.tolist())))
fmap = {t: i % 5 for i, t in enumerate(np.random.default_rng(0).permutation(uniq))}
fold = np.array([fmap[t] for t in tids])
ca_all = np.array([r[1] for r in rows], float)
is_gk = np.array([r[pi + F.POS.index("GK")] == 20 for r in rows])
Y_j = np.array([[r[ai + ATTR_ORDER.index(a)] for r in rows] for a in F._OUTFIELD_ENTANGLED], float)
OWN_j = np.array([[MOD.uw(r[bi[F.COLS[MOD.FROZEN[a][0]]]]) for r in rows]
                  for a in F._OUTFIELD_ENTANGLED], float)
cache = {}
def gamma_for(m):
    k = m.tobytes()
    if k not in cache: cache[k] = F._shared_gamma(Y_j, OWN_j, ca_all, m & ~is_gk)
    return cache[k]

labels = list(F.SETS)
print(f"{'attribute':<14}" + "".join(f"{l:>9}" for l in labels))
tot = {l: 0.0 for l in labels}
for attr, (own, partner, ffeats, _) in MOD.FROZEN.items():
    y = np.array([r[ai + ATTR_ORDER.index(attr)] for r in rows], float)
    keep = ~np.isnan(y)
    own_b = np.array([MOD.uw(r[bi[F.COLS[own]]]) for r in rows], float)
    par_b = (np.array([MOD.uw(r[bi[F.COLS[partner]]]) for r in rows], float)
             if partner is not None else np.zeros(len(rows)))
    line = f"{attr:<14}"
    for lab in labels:
        pred = np.empty(len(rows))
        for k in range(5):
            te = fold == k; tr = ~te & keep
            if lab == "shared":
                gc = gamma_for(tr)
                arg = F._grid_fit(own_b[tr], par_b[tr], ca_all[tr], y[tr], gc, partner is not None)
                pred[te] = F._shared_predict(own_b[te], par_b[te], ca_all[te], gc, arg,
                                             partner is not None)
            else:
                nm = tuple(n for n in ffeats if n != "fwd") if F.SETS[lab] is None else F.SETS[lab]
                if partner is None: nm = tuple(n for n in nm if n != "partner")
                X = np.array([F.features(r, bi, pi, own, partner, nm) for r in rows], float)
                c, *_ = np.linalg.lstsq(X[tr], y[tr], rcond=None)
                pred[te] = X[te] @ c + F.tune_offset(X[tr] @ c, y[tr])
        e, _ = F.score(pred[keep], y[keep])
        tot[lab] += e
        line += f"{e:>8.1%}"
    print(line)
print(f"{'MEAN':<14}" + "".join(f"{tot[l]/len(MOD.FROZEN):>8.1%}" for l in labels))
