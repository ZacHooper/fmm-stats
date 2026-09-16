"""Aerial weight search + the height test (docs/ca-weighting.md).

Run: uv run python archive/aerial_weight_search.py fm-frem.duckdb

Does height help Aerial? And are 0.30/0.70/+1.0 still the right weights on 4x the data?

Everything CV'd by player, 5 folds, scored on exact matches -- the same protocol as the
decoder, so the numbers are comparable to the 75.7% the closed form scores today.
"""
import sys, itertools, duckdb, numpy as np
DB = sys.argv[1]
c = duckdb.connect(DB, read_only=True)
df = c.sql('''SELECT e."Aerial" y, p.heading_src h, p.jumping j, p.height_cm ht,
                     p.weight_kg wt, p.ca, p.tid, p.is_gk, p.strength_src st, p.agility_src ag
              FROM staging.player_attributes_exact e JOIN staging.players p USING (tid, phase)
              WHERE e."Aerial" IS NOT NULL''').df().dropna(subset=["y", "h", "j"])
print(f"{len(df)} truth rows, {df.tid.nunique()} players "
      f"(height present on {df.ht.notna().mean():.0%})\n")
y = df.y.to_numpy(float); h = df.h.to_numpy(float); j = df.j.to_numpy(float)
ht = df.ht.fillna(df.ht.median()).to_numpy(float); ca = df.ca.to_numpy(float)
wt = df.wt.fillna(df.wt.median()).to_numpy(float)
tids = df.tid.to_numpy(); uniq = np.array(sorted(set(tids.tolist())))
fold = np.array([{t: i % 5 for i, t in
                  enumerate(np.random.default_rng(0).permutation(uniq))}[t] for t in tids])

def cv_ls(X):
    """least squares + a rounding offset tuned on the training fold"""
    pred = np.empty(len(y)); offs = np.arange(-1.5, 1.51, 0.02)
    for k in range(5):
        te = fold == k; tr = ~te
        A = np.c_[X, np.ones(len(y))]
        b, *_ = np.linalg.lstsq(A[tr], y[tr], rcond=None)
        o = max(offs, key=lambda v: (np.clip(np.rint(A[tr] @ b + v), 1, 20) == y[tr]).mean())
        pred[te] = A[te] @ b + o
    p = np.clip(np.rint(pred), 1, 20)
    return (p == y).mean(), (np.abs(p - y) <= 1).mean()

print(f"{'model':<44}{'exact':>8}{'±1':>8}")
# the shipped closed form, as-is
cf = np.clip(np.floor(0.30*h + 0.70*j + 1.0), 1, 20)
print(f"{'shipped: floor(0.30h + 0.70j + 1.0)':<44}{(cf==y).mean():>7.1%}"
      f"{(np.abs(cf-y)<=1).mean():>8.1%}")
for lab, X in [("heading + jumping", np.c_[h, j]),
               ("heading + jumping + height", np.c_[h, j, ht]),
               ("heading + jumping + height + weight", np.c_[h, j, ht, wt]),
               ("heading + jumping + CA", np.c_[h, j, ca]),
               ("heading + jumping + height + CA", np.c_[h, j, ht, ca]),
               ("heading + jumping + strength + agility", np.c_[h, j, df.st, df.ag])]:
    e, w = cv_ls(X)
    print(f"{'lstsq: ' + lab:<44}{e:>7.1%}{w:>8.1%}")

# grid-search the closed form on exact matches, nested by fold
print()
W = np.arange(0.0, 1.01, 0.02); O = np.arange(-1.0, 2.01, 0.1); HW = np.arange(0.0, 0.121, 0.01)
def grid(use_height):
    pred = np.empty(len(y)); picks = []
    for k in range(5):
        te = fold == k; tr = ~te
        best, arg = -1, None
        for w in W:
            base_tr = w*h[tr] + (1-w)*j[tr]
            for hw in (HW if use_height else [0.0]):
                v_tr = base_tr + hw*(ht[tr] - 182.0)
                for o in O:
                    s = (np.clip(np.floor(v_tr + o), 1, 20) == y[tr]).mean()
                    if s > best: best, arg = s, (w, hw, o)
        w, hw, o = arg; picks.append(arg)
        pred[te] = np.clip(np.floor(w*h[te] + (1-w)*j[te] + hw*(ht[te]-182.0) + o), 1, 20)
    return (pred == y).mean(), (np.abs(pred-y) <= 1).mean(), picks
e, w1, picks = grid(False)
print(f"{'grid floor(w*h + (1-w)*j + off)':<44}{e:>7.1%}{w1:>8.1%}   folds chose "
      f"{sorted(set((round(a,2), round(cc,2)) for a,_,cc in picks))}")
e, w1, picks = grid(True)
print(f"{'grid + height term':<44}{e:>7.1%}{w1:>8.1%}   folds chose "
      f"{sorted(set((round(a,2), round(b,3), round(cc,2)) for a,b,cc in picks))}")
