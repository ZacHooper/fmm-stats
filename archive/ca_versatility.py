"""Does positional familiarity redistribute a fixed CA across attributes?

The claim: CA is a familiarity-weighted blend of the per-position weight vectors, so adding
familiarity in a position pulls that position's attributes up and everything else down.

Test 1  continuous, full n: for every ST, regress each attribute on CA and DC familiarity.
Test 2  the general form: build each player's BLENDED weight vector (familiarity-weighted
        average of the recovered per-position weights) and ask whether, at fixed CA, a player
        is strong exactly where his blended weight is high. One number decides it.
"""
import sys, json, duckdb, numpy as np
DB = sys.argv[1]
POS = ["GK","SW","DL","DC","DR","DMC","ML","MC","MR","AML","AMC","AMR","ST","DML","DMR"]
ENT = ["finishing_src","passing_src","tackling_src","positioning_src","dribbling_src",
       "crossing_src","decision_src","creativity_src","movement_src"]
PLN = ["pace_src","strength_src","stamina_src","technique_src","heading_src","agility_src"]
A = ENT + PLN
c = duckdb.connect(DB, read_only=True)
df = c.sql(f"""SELECT ca, positions, {', '.join(A)} FROM staging.players
               WHERE NOT is_staff AND has_attributes AND ca > 0 AND ca <= pa AND NOT is_gk""").df()
pos = df.positions.map(json.loads)
X = df[A].to_numpy(float).copy()
for i, col in enumerate(A):
    if col in ENT:
        X[:, i] = np.where(X[:, i] < 128, X[:, i] + 256, X[:, i]) * 0.115 - 20
ca = df.ca.to_numpy(float)
top = pos.map(lambda p: max(p, key=lambda k: (p[k], -POS.index(k))) if p else None).to_numpy()

print("TEST 1 -- every ST, regressed on CA and DC familiarity (1-20).")
print("         coefficient = display points per +10 DC familiarity, CA held fixed\n")
m = top == "ST"
dc = pos[m].map(lambda p: p.get("DC", 1)).to_numpy(float)
print(f"    {'attribute':<14}{'per +10 DC fam':>16}")
for i, col in enumerate(A):
    M = np.c_[ca[m], dc, np.ones(m.sum())]
    b, *_ = np.linalg.lstsq(M, X[m, i], rcond=None)
    print(f"    {col.replace('_src',''):<14}{b[1]*10:>+16.2f}")
print(f"    (n={m.sum():,} STs; DC familiarity ranges {dc.min():.0f}-{dc.max():.0f}, "
      f"mean {dc.mean():.1f})")

# ---- Test 2: blended weight vector ----
GROUPS = {"GK":["GK"],"DC":["DC","SW"],"DL":["DL","DR"],"DMC":["DMC","DML","DMR"],
          "MC":["MC"],"ML":["ML","MR"],"AMC":["AMC"],"AML":["AML","AMR"],"ST":["ST"]}
SLOT2G = {s: g for g, ss in GROUPS.items() for s in ss}
W = {}
for g, members in GROUPS.items():
    if g == "GK": continue
    mm = np.isin(top, members)
    if mm.sum() < 500: continue
    Z = (X[mm] - X[mm].mean(0)) / X[mm].std(0)
    y = (ca[mm] - ca[mm].mean()) / ca[mm].std()
    b, *_ = np.linalg.lstsq(np.c_[Z, np.ones(mm.sum())], y, rcond=None)
    W[g] = b[:-1]

def blend(p):
    acc, tot = np.zeros(len(A)), 0.0
    for slot, fam in p.items():
        g = SLOT2G.get(slot)
        if g in W:
            acc += fam * W[g]; tot += fam
    return acc / tot if tot else None

BW = np.array([blend(p) if blend(p) is not None else np.full(len(A), np.nan) for p in pos])
ok = ~np.isnan(BW[:, 0]) & (top != "GK")
print(f"\nTEST 2 -- blended weight vector, {ok.sum():,} outfielders.")
print("         within each attribute, residualise on CA, then ask how the residual tracks")
print("         that player's blended weight for the attribute:\n")
res, bw = [], []
for i, col in enumerate(A):
    x, y = ca[ok], X[ok, i]
    b = np.polyfit(x, y, 1)
    r = (y - np.polyval(b, x)); r = (r - r.mean()) / r.std()
    w = BW[ok, i]; w = (w - w.mean()) / w.std()
    res.append(r); bw.append(w)
    print(f"    {col.replace('_src',''):<14}corr(CA-residual, blended weight) {np.corrcoef(r, w)[0,1]:>+6.2f}")
r, w = np.concatenate(res), np.concatenate(bw)
print(f"\n    POOLED over all {len(A)} attributes: {np.corrcoef(r, w)[0,1]:+.2f}  (n={len(r):,})")
