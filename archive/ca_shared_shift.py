"""Evidence for the shared-CA-shift model shape (docs/attribute-model.md).

Run: uv run python archive/ca_shared_shift.py <store.duckdb>

Like-for-like: shared-shift vs a per-attribute CA fit of the same data, folds and offset rule.

Variants
  A  byte only                          beta_a*uw + alpha_a
  B  shared shift                       + g(CA), one curve for all 9
  C  shared shift, per-attr loading     + lambda_a * g(CA)
  D  per-attribute CA                   beta_a*uw + b1*CA + b2*PA + b3*uw*CA + alpha_a
Everything CV'd by player, rounding offset chosen inside the training fold only.
"""
import sys, duckdb, numpy as np
DB = sys.argv[1]
OUT = {"Crossing":"crossing_src","Dribbling":"dribbling_src","Tackling":"tackling_src",
       "Shooting":"finishing_src","Passing":"passing_src","Decisions":"decision_src",
       "Creativity":"creativity_src","Movement":"movement_src","Positioning":"positioning_src"}
c = duckdb.connect(DB, read_only=True)
df = c.sql(f"""SELECT e.*, p.ca, p.pa, {', '.join('p.'+v for v in OUT.values())}
               FROM staging.player_attributes_exact e JOIN staging.players p USING (tid, phase)
               WHERE e."Crossing" IS NOT NULL AND NOT p.is_gk""").df()
n = len(df); names = list(OUT)
uw = lambda col: np.where(df[col].to_numpy(float) < 128,
                          df[col].to_numpy(float)+256, df[col].to_numpy(float))
X = np.array([uw(OUT[a]) for a in names]); Y = np.array([df[a].to_numpy(float) for a in names])
ca, pa = df["ca"].to_numpy(float), df["pa"].to_numpy(float)
tids = df.tid.to_numpy(); uniq = np.array(sorted(set(tids.tolist())))
fo = {t: i % 5 for i, t in enumerate(np.random.default_rng(0).permutation(uniq))}
fold = np.array([fo[t] for t in tids])

def off(pred, y):
    o = np.arange(-1.0, 1.01, 0.02)
    return max(o, key=lambda v: (np.clip(np.rint(pred+v), 1, 20) == y).mean())

def fit_shared(tr, loading=False, iters=10):
    g = np.zeros(tr.sum()); lam = np.ones(9)
    for _ in range(iters):
        ab = []
        for i in range(9):
            A = np.c_[X[i][tr], np.ones(tr.sum())]
            b, *_ = np.linalg.lstsq(A, Y[i][tr] - lam[i]*g, rcond=None); ab.append(b)
        res = np.array([Y[i][tr] - (ab[i][0]*X[i][tr] + ab[i][1]) for i in range(9)])
        gc = np.polyfit(ca[tr], (res / lam[:, None]).mean(0), 1)
        g = np.polyval(gc, ca[tr])
        if loading:
            lam = np.array([(res[i] @ g) / (g @ g) for i in range(9)])
    return np.array(ab), gc, lam

def run(kind):
    P = np.empty((9, n))
    for k in range(5):
        te = fold == k; tr = ~te
        if kind in ("B", "C"):
            ab, gc, lam = fit_shared(tr, loading=(kind == "C"))
            for i in range(9):
                f = lambda m: ab[i][0]*X[i][m] + ab[i][1] + lam[i]*np.polyval(gc, ca[m])
                P[i][te] = f(te) + off(f(tr), Y[i][tr])
        else:
            for i in range(9):
                F = ([X[i], np.ones(n)] if kind == "A"
                     else [X[i], ca, pa, X[i]*ca/100, np.ones(n)])
                A = np.array(F).T
                b, *_ = np.linalg.lstsq(A[tr], Y[i][tr], rcond=None)
                P[i][te] = A[te] @ b + off(A[tr] @ b, Y[i][tr])
    Q = np.clip(np.rint(P), 1, 20)
    return (Q == Y).mean(1), (np.abs(Q - Y) <= 1).mean(1)

lab = {"A": "byte only", "B": "shared CA shift", "C": "shared + loading",
       "D": "per-attr CA"}
R = {k: run(k) for k in "ABCD"}
print(f"{'attribute':<14}" + "".join(f"{lab[k]:>18}" for k in "ABCD"))
for i, a in enumerate(names):
    print(f"{a:<14}" + "".join(f"{R[k][0][i]:>17.1%}" for k in "ABCD"))
print(f"{'MEAN exact':<14}" + "".join(f"{R[k][0].mean():>17.1%}" for k in "ABCD"))
print(f"{'MEAN +/-1':<14}" + "".join(f"{R[k][1].mean():>17.1%}" for k in "ABCD"))
print(f"{'free params':<14}" + "".join(f"{v:>17}" for v in (18, 20, 29, 45)))
