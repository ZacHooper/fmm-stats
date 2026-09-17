"""Does the exact-vs-+/-1 trade matter where it is actually SURFACED -- the role ratings?

The decoder's objective is a dial. Optimising EXACT matches converted near-misses into hits but
made +/-1 WORSE for four attributes (Dribbling -12.4, Tackling -6.3, Passing -6.0, Crossing
-2.3). Whether that is a bad trade depends on what the error does downstream: a role rating is
a weighted mean over ~15-23 attributes, so independent errors partly cancel and a fatter tail
partly does not.

Computed per player: the role rating from the MODEL's attributes vs from the TRUTH, for every
role in our tactic. Reports the rating error and, more importantly, how often the model's
ranking of the squad differs from the truth's -- ranking is what a depth chart actually uses.
"""
import sys, os, numpy as np, duckdb
sys.path.insert(0, os.getcwd())
import load_duckdb as L
DB, METHOD = sys.argv[1], sys.argv[2]
con = duckdb.connect(DB, read_only=True)
spec = {}
for a, f, c, o, p in con.execute("SELECT attribute,feature,coef,own_offset,partner_offset "
                                 "FROM staging.attribute_model").fetchall():
    spec.setdefault(a, {"own": o, "partner": p, "coef": {}})["coef"][f] = c
W = [(r, a.capitalize(), w) for r, a, w in con.execute(
        "SELECT role, attribute, weight FROM staging.role_weights WHERE method = ?",
        [METHOD]).fetchall()]   # role_weights stores attributes lowercase; the model uses Title
if not W:
    print(f"no weights for {METHOD}")
    raise SystemExit(0)
roles = sorted({r for r, _, _ in W})
A23 = sorted({a for _, a, _ in W})
wt = {}
for r, a, w in W:
    wt.setdefault(r, {})[a] = w
msel = ", ".join(f'{L._model_expr(a, spec[a], "staging")} AS m_{a}' if a in spec
                 else f'e."{a}" AS m_{a}' for a in A23)
d = con.execute(f'''SELECT p.tid, p.phase, {msel}, {", ".join(f'e."{a}" AS t_{a}' for a in A23)}
                    FROM staging.players p
                    JOIN staging.player_attributes_exact e USING (season, phase, tid)
                    WHERE e."Passing" IS NOT NULL''').df().dropna()
print(f"{METHOD}: {len(roles)} roles, {len(d)} player-snapshots with full truth\n")
print(f"  {'role':<28}{'mean |rating err|':>19}{'max':>7}{'rank swaps':>13}")
tot, swaps_t, pairs_t = [], 0, 0
GAPS, ALLG = [], []
for r in roles:
    w = np.array([wt[r].get(a, 1.0) for a in A23], float)
    M = d[[f"m_{a}" for a in A23]].to_numpy(float) @ w / w.sum()
    T = d[[f"t_{a}" for a in A23]].to_numpy(float) @ w / w.sum()
    err = np.abs(M - T)
    # ranking disagreement, within each snapshot (a depth chart is per-squad, per-date)
    sw = pr = 0
    for ph, idx in d.groupby("phase").indices.items():
        m, t = M[idx], T[idx]
        for i in range(len(idx)):
            for j in range(i + 1, len(idx)):
                if t[i] == t[j]:
                    continue
                pr += 1
                if (m[i] > m[j]) != (t[i] > t[j]):
                    sw += 1
                    GAPS.append(abs(t[i] - t[j]))
                ALLG.append(abs(t[i] - t[j]))
    swaps_t += sw; pairs_t += pr; tot.append(err.mean())
    print(f"  {r:<28}{err.mean():>18.3f}{err.max():>7.2f}{sw/pr if pr else 0:>12.1%}")
print(f"\n  {'MEAN':<28}{np.mean(tot):>18.3f}{'':>7}{swaps_t/pairs_t:>12.1%}")
print(f"\n  a role rating is on the 1-20 attribute scale, so {np.mean(tot):.2f} is "
      f"{np.mean(tot)/20*100:.1f}% of full range")
print(f"  {swaps_t/pairs_t:.1%} of ordered player pairs come out in the WRONG ORDER "
      f"({pairs_t:,} pairs compared)")
G = np.array(GAPS); AG = np.array(ALLG)
print(f"\n  BUT: how far apart were the players we got backwards?")
print(f"    median TRUE gap in a swapped pair   {np.median(G):.2f} rating pts")
print(f"    90th percentile                     {np.quantile(G, 0.9):.2f}")
print(f"    median gap over ALL pairs           {np.median(AG):.2f}")
for thr in (0.1, 0.25, 0.5, 1.0):
    near = AG <= thr
    sw_near = (G <= thr).sum()
    print(f"    pairs closer than {thr:>4.2f}: {near.mean():>5.1%} of all pairs, "
          f"and {sw_near/len(G):>5.1%} of all swaps")
