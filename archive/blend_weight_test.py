"""Stage 3 gate: does `blend_w` earn its one parameter?

DIFFERENT MECHANISM from the CA constraint. The constraint says "the weighted sum must equal
CA" and it is too loose to help. blend_w says something else: at a FIXED CA, familiarity
redistributes the attributes -- a striker who can also play DC has tackling and positioning
pulled up and finishing pulled down. That is a per-attribute signal, not a constraint on a sum.

blend_w(player, attr) = sum(familiarity_p * weight[p][attr]) / sum(familiarity_p)

Weights come from the 155k-row per-position regression on RAW BYTES, which are
CA-independent -- so this is not circular the way regressing CA on model output is.
Scored by adding it to the two shipped candidates, nested CV, same folds as the tool.
"""
import sys, os, json, numpy as np
sys.path.insert(0, "scripts"); sys.path.insert(0, os.getcwd())
import fit_attribute_model as F
from fmparser import model as MOD
from fmparser.attributes import ATTR_ORDER
import duckdb

DB = sys.argv[1]
POS = F.POS
GROUPS = {"GK": ["GK"], "DC": ["DC", "SW"], "DL": ["DL", "DR"], "DMC": ["DMC", "DML", "DMR"],
          "MC": ["MC"], "ML": ["ML", "MR"], "AMC": ["AMC"], "AML": ["AML", "AMR"], "ST": ["ST"]}
SLOT2G = {s: g for g, ss in GROUPS.items() for s in ss}
ENT = list(MOD.FROZEN)
con = duckdb.connect(DB, read_only=True)

# --- per-position CA weights from raw bytes, big n, CA-independent ---
BYTES = {a: F.COLS[MOD.FROZEN[a][0]] for a in ENT}
big = con.execute(f'''SELECT ca, positions, is_gk, {", ".join(set(BYTES.values()))}
                      FROM staging.players
                      WHERE ca > 0 AND ca <= pa AND passing_src IS NOT NULL''').df().dropna()
topf = lambda p: (lambda d: max(d, key=lambda k: (d[k], -POS.index(k))) if d else None)(json.loads(p))
big["top"] = big.positions.map(topf)
uw = lambda v: np.where(v < 128, v + 256, v)
W = {}
for g, members in GROUPS.items():
    m = big.top.isin(members).to_numpy()
    if m.sum() < 400: continue
    X = np.c_[[uw(big.loc[m, BYTES[a]].to_numpy(float)) for a in ENT]].T
    y = big.loc[m, "ca"].to_numpy(float)
    Z = (X - X.mean(0)) / X.std(0)
    b, *_ = np.linalg.lstsq(np.c_[Z, np.ones(int(m.sum()))], (y - y.mean())/y.std(), rcond=None)
    W[g] = {a: b[i] for i, a in enumerate(ENT)}
print(f"per-position CA weights from {len(big):,} snapshots, {len(W)} groups\n")

rows, bi, ai, pi = F.load(DB)
tids = np.array([r[0] for r in rows]); uniq = np.array(sorted(set(tids.tolist())))
fmap = {t: i % 5 for i, t in enumerate(np.random.default_rng(0).permutation(uniq))}
fold = np.array([fmap[t] for t in tids])
ca_all = np.array([r[1] for r in rows], float)
is_gk = np.array([r[pi + POS.index("GK")] == 20 for r in rows])
Y_j = np.array([[r[ai + ATTR_ORDER.index(a)] for r in rows] for a in F._OUTFIELD_ENTANGLED], float)
OWN_j = np.array([[MOD.uw(r[bi[F.COLS[MOD.FROZEN[a][0]]]]) for r in rows]
                  for a in F._OUTFIELD_ENTANGLED], float)
cache = {}
def gamma_for(m):
    k = m.tobytes()
    if k not in cache: cache[k] = F._shared_gamma(Y_j, OWN_j, ca_all, m & ~is_gk)
    return cache[k]

def blend(attr):
    out = np.zeros(len(rows))
    for i, r in enumerate(rows):
        fam = r[pi:pi + len(POS)]
        acc = tot = 0.0
        for k, p in enumerate(POS):
            g = SLOT2G.get(p)
            if g in W and fam[k]:
                acc += fam[k] * W[g][attr]; tot += fam[k]
        out[i] = acc / tot if tot else 0.0
    return out

print(f"{'attribute':<15}{'shipped':>9}{'+blend_w':>10}{'delta':>8}")
tot_a = tot_b = 0.0
for attr, (own, partner, ffeats, _) in MOD.FROZEN.items():
    y = np.array([r[ai + ATTR_ORDER.index(attr)] for r in rows], float)
    keep = ~np.isnan(y)
    own_b = np.array([MOD.uw(r[bi[F.COLS[own]]]) for r in rows], float)
    par_b = (np.array([MOD.uw(r[bi[F.COLS[partner]]]) for r in rows], float)
             if partner is not None else np.zeros(len(rows)))
    bw = blend(attr); bwca = bw * ca_all / 100.0
    nm_gk = F.SETS["gk"] if partner is not None else tuple(n for n in F.SETS["gk"] if n != "partner")
    Xgk = np.array([F.features(r, bi, pi, own, partner, nm_gk) for r in rows], float)
    Xgk2 = np.c_[Xgk[:, :-1], bw, bwca, Xgk[:, -1]]
    def fp(lab, tr, te):
        if lab == "shared":
            gc = gamma_for(tr)
            arg = F._grid_fit(own_b[tr], par_b[tr], ca_all[tr], y[tr], gc, partner is not None)
            return F._shared_predict(own_b[te], par_b[te], ca_all[te], gc, arg, partner is not None)
        if lab == "shared+bw":
            gc = gamma_for(tr)
            arg = F._grid_fit(own_b[tr], par_b[tr], ca_all[tr], y[tr], gc, partner is not None)
            base_tr = F._shared_predict(own_b[tr], par_b[tr], ca_all[tr], gc, arg, partner is not None)
            A = np.c_[bw[tr], np.ones(int(tr.sum()))]
            c, *_ = np.linalg.lstsq(A, y[tr] - base_tr, rcond=None)
            return F._shared_predict(own_b[te], par_b[te], ca_all[te], gc, arg,
                                     partner is not None) + np.c_[bw[te], np.ones(int(te.sum()))] @ c
        X = Xgk2 if lab == "gk+bw" else Xgk
        c, *_ = np.linalg.lstsq(X[tr], y[tr], rcond=None)
        return X[te] @ c + F.tune_offset(X[tr] @ c, y[tr])
    def nested(pool):
        pred = np.empty(len(rows))
        for k in range(5):
            te = fold == k; tr = ~te & keep
            inner = np.array([fmap[t] for t in tids[tr]]) % 4
            idx = np.flatnonzero(tr); pick, best = None, -1.0
            for lab in pool:
                ip = np.empty(int(tr.sum()))
                for j in range(4):
                    ite = inner == j
                    if ite.all() or not ite.any(): continue
                    a = np.zeros(len(rows), bool); a[idx[~ite]] = True
                    b2 = np.zeros(len(rows), bool); b2[idx[ite]] = True
                    ip[ite] = fp(lab, a, b2)
                e, _ = F.score(ip, y[tr])
                if e > best: pick, best = lab, e
            pred[te] = fp(pick, tr, te)
        return F.score(pred[keep], y[keep])[0]
    a_ = nested(["gk", "shared"]); b_ = nested(["gk", "shared", "gk+bw", "shared+bw"])
    tot_a += a_; tot_b += b_
    print(f"{attr:<15}{a_:>8.1%}{b_:>9.1%}{b_-a_:>+8.1%}")
n = len(MOD.FROZEN)
print(f"{'MEAN':<15}{tot_a/n:>8.1%}{tot_b/n:>9.1%}{(tot_b-tot_a)/n:>+8.1%}")
