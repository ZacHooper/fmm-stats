"""Zac's question, in its sharpest form.

If CA is a weighted sum of the BYTES -- not the displayed attributes, which are a rounded,
clipped view of them -- and we already hold all 34 bytes exactly, then CA is REDUNDANT: it
can only tell us something to the extent it depends on things we cannot see. So the useful
quantity is not CA but the SURPRISE in CA:

    surprise = CA - sum(w * byte)

Q1  how tight is CA = sum(w * byte)?  (tight => the constraint is redundant, not merely loose)
Q2  does `surprise` beat raw CA as the decoder's CA term?

Position groups resolved in SQL; weights fitted on a sample, which is ample for 35 parameters.
"""
import sys, os, duckdb, numpy as np
sys.path.insert(0, "scripts"); sys.path.insert(0, os.getcwd())
import fit_attribute_model as F
from fmparser import model as MOD
from fmparser.attributes import (ATTR_ORDER, SRC_OFFSETS, PLAIN_OFFSETS, HIDDEN_OFFSETS)

DB = sys.argv[1]
POS = F.POS
SLOTS = list(SRC_OFFSETS.values()) + list(PLAIN_OFFSETS.values()) + list(HIDDEN_OFFSETS.values())
ENTC = set(SRC_OFFSETS.values())
GRP = {"GK": ["GK"], "DC": ["DC", "SW"], "DL": ["DL", "DR"], "DMC": ["DMC", "DML", "DMR"],
       "MC": ["MC"], "ML": ["ML", "MR"], "AMC": ["AMC"], "AML": ["AML", "AMR"], "ST": ["ST"]}
S2G = {s: g for g, ss in GRP.items() for s in ss}
RANK = {p: i for i, p in enumerate(POS)}
con = duckdb.connect(DB, read_only=True)

# GK/outfield only. The per-position version needs a correlated subquery over
# staging.player_positions, which DuckDB evaluates for all 650k rows BEFORE the sample and which
# never returned. The split that matters here is the keeper one anyway: Q1 asks how much of CA
# the bytes explain, and position refines that rather than deciding it.
big = con.execute(f"SELECT tid, ca, is_gk, {', '.join(SLOTS)} FROM staging.players "
                  "WHERE ca > 0 AND ca <= pa AND passing_src IS NOT NULL "
                  "USING SAMPLE 150000 ROWS").df().dropna()
big["g"] = np.where(big.is_gk.astype(bool), "GK", "outfield")
X = big[SLOTS].to_numpy(float).copy()
for i, s in enumerate(SLOTS):
    if s in ENTC:
        X[:, i] = np.where(X[:, i] < 128, X[:, i] + 256, X[:, i])
ca = big.ca.to_numpy(float)
tids = big.tid.to_numpy(); uq = np.array(sorted(set(tids.tolist())))
fold = np.array([{t: i % 5 for i, t in enumerate(np.random.default_rng(1).permutation(uq))}[t]
                 for t in tids])
print(f"Q1  CA = sum(w * raw byte)   {len(big):,} snapshots, {len(SLOTS)} bytes, CV by player\n")
print(f"    {'group':<8}{'n':>9}{'R2':>8}{'CA resid sd':>14}")
COEF, pr = {}, np.full(len(ca), np.nan)
for g in ("outfield", "GK"):
    m = (big.g == g).to_numpy()
    if m.sum() < 500: continue
    A = np.c_[X[m], np.ones(int(m.sum()))]; y = ca[m]; f = fold[m]; p = np.empty(int(m.sum()))
    for k in range(5):
        te = f == k
        b, *_ = np.linalg.lstsq(A[~te], y[~te], rcond=None); p[te] = A[te] @ b
    COEF[g], *_ = np.linalg.lstsq(A, y, rcond=None); pr[m] = p
    r = y - p
    print(f"    {g:<8}{int(m.sum()):>9,}{1-(r**2).sum()/((y-y.mean())**2).sum():>8.3f}{r.std():>12.1f}")
ok = ~np.isnan(pr)
print(f"    {'ALL':<8}{int(ok.sum()):>9,}{'':>8}{(ca[ok]-pr[ok]).std():>12.1f}"
      f"   <- best-case constraint (our decode's implied-CA error is 6.1)\n")

rows, bi, ai, pi = F.load(DB)
rca = np.array([r[1] for r in rows], float)
rg = ["GK" if r[pi + POS.index("GK")] == 20 else "outfield" for r in rows]
Xr = np.array([[MOD.uw(r[bi[s]]) if s in ENTC else r[bi[s]] for s in SLOTS] for r in rows], float)
sur = np.array([rca[i] - (float(np.r_[Xr[i], 1.0] @ COEF[rg[i]]) if rg[i] in COEF else 0.0)
                for i in range(len(rows))])
print(f"Q2  surprise = CA - sum(w*byte):  mean {sur.mean():+.2f}, sd {sur.std():.2f} "
      f"(raw CA sd {rca.std():.1f})\n")
rt = np.array([r[0] for r in rows]); uq2 = np.array(sorted(set(rt.tolist())))
fmap = {t: i % 5 for i, t in enumerate(np.random.default_rng(0).permutation(uq2))}
f2 = np.array([fmap[t] for t in rt])
gk = np.array([r[pi + POS.index("GK")] == 20 for r in rows])
Yj = np.array([[r[ai+ATTR_ORDER.index(a)] for r in rows] for a in F._OUTFIELD_ENTANGLED], float)
Oj = np.array([[MOD.uw(r[bi[F.COLS[MOD.FROZEN[a][0]]]]) for r in rows]
               for a in F._OUTFIELD_ENTANGLED], float)
cc = {}
def gam(m, drv, tag):
    k = (m.tobytes(), tag)
    if k not in cc: cc[k] = F._shared_gamma(Yj, Oj, drv, m & ~gk)
    return cc[k]
print(f"    {'attribute':<15}{'raw CA':>9}{'surprise':>10}{'delta':>8}")
t1 = t2 = 0.0
for attr, (own, partner, _, _) in MOD.FROZEN.items():
    y = np.array([r[ai+ATTR_ORDER.index(attr)] for r in rows], float); keep = ~np.isnan(y)
    ob = np.array([MOD.uw(r[bi[F.COLS[own]]]) for r in rows], float)
    pb = (np.array([MOD.uw(r[bi[F.COLS[partner]]]) for r in rows], float)
          if partner is not None else np.zeros(len(rows)))
    res = []
    for tag, drv in (("ca", rca), ("sur", sur)):
        pred = np.empty(len(rows))
        for k in range(5):
            te = f2 == k; tr = ~te & keep
            gc = gam(tr, drv, tag)
            arg = F._grid_fit(ob[tr], pb[tr], drv[tr], y[tr], gc, partner is not None)
            pred[te] = F._shared_predict(ob[te], pb[te], drv[te], gc, arg, partner is not None)
        res.append(F.score(np.clip(pred[keep], 1, 20), y[keep])[0])
    t1 += res[0]; t2 += res[1]
    print(f"    {attr:<15}{res[0]:>8.1%}{res[1]:>10.1%}{res[1]-res[0]:>+8.1%}")
n = len(MOD.FROZEN)
print(f"    {'MEAN':<15}{t1/n:>8.1%}{t2/n:>10.1%}{(t2-t1)/n:>+8.1%}")
