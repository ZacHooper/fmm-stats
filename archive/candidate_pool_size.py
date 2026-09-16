"""Does a SMALLER candidate pool score better? Nested selection pays for every candidate.

With 7 candidates and 840 rows the inner fold picks on a noisy estimate, and a candidate that
is never genuinely best still wins folds by chance -- Movement's `nat` (48.9%) beat out
`shared` (52.1%) exactly that way. Fewer candidates = less selection variance. Same nested
protocol throughout, so these numbers stay comparable to the tool's.
"""
import sys, itertools, numpy as np
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

def run(pool):
    tot = 0.0
    for attr, (own, partner, ffeats, _) in MOD.FROZEN.items():
        y = np.array([r[ai + ATTR_ORDER.index(attr)] for r in rows], float)
        keep = ~np.isnan(y)
        own_b = np.array([MOD.uw(r[bi[F.COLS[own]]]) for r in rows], float)
        par_b = (np.array([MOD.uw(r[bi[F.COLS[partner]]]) for r in rows], float)
                 if partner is not None else np.zeros(len(rows)))
        X = {}
        for lab in pool:
            if lab == "shared": continue
            nm = tuple(n for n in ffeats if n != "fwd") if F.SETS[lab] is None else F.SETS[lab]
            if partner is None: nm = tuple(n for n in nm if n != "partner")
            X[lab] = np.array([F.features(r, bi, pi, own, partner, nm) for r in rows], float)
        def fp(lab, tr, te):
            if lab == "shared":
                gc = gamma_for(tr)
                arg = F._grid_fit(own_b[tr], par_b[tr], ca_all[tr], y[tr], gc, partner is not None)
                return F._shared_predict(own_b[te], par_b[te], ca_all[te], gc, arg, partner is not None)
            c, *_ = np.linalg.lstsq(X[lab][tr], y[tr], rcond=None)
            return X[lab][te] @ c + F.tune_offset(X[lab][tr] @ c, y[tr])
        pred = np.empty(len(rows))
        for k in range(5):
            te = fold == k; tr = ~te & keep
            inner = np.array([fmap[t] for t in tids[tr]]) % 4
            idx = np.flatnonzero(tr)
            pick, best = None, -1.0
            for lab in pool:
                ip = np.empty(int(tr.sum()))
                for j in range(4):
                    ite = inner == j
                    if ite.all() or not ite.any(): continue
                    a = np.zeros(len(rows), bool); a[idx[~ite]] = True
                    b = np.zeros(len(rows), bool); b[idx[ite]] = True
                    ip[ite] = fp(lab, a, b)
                e, _ = F.score(ip, y[tr])
                if e > best: pick, best = lab, e
            pred[te] = fp(pick, tr, te)
        tot += F.score(pred[keep], y[keep])[0]
    return tot / len(MOD.FROZEN)

POOLS = [("all 7 (shipped)", list(F.SETS)),
         ("drop pos", [l for l in F.SETS if l != "pos"]),
         ("drop pos, nat", [l for l in F.SETS if l not in ("pos", "nat")]),
         ("frozen, lean, gk, shared", ["frozen", "lean", "gk", "shared"]),
         ("lean, gk, shared", ["lean", "gk", "shared"]),
         ("gk, shared", ["gk", "shared"]),
         ("shared only", ["shared"])]
print(f"{'candidate pool':<28}{'mean exact':>12}")
for lab, pool in POOLS:
    print(f"{lab:<28}{run(pool):>11.1%}")
