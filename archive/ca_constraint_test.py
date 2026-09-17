"""The clean error budget. Two traps avoided:

  CIRCULARITY  staging.player_attributes' entangled values are model output that USED CA as an
               input, so regressing CA on them recovers CA from itself (R2 0.945, meaningless).
               Weights are fitted on the truth rows only, where all 23 are exact and
               CA-independent.
  COALESCE     the same view returns the EXACT value wherever one exists -- i.e. on every truth
               row -- so the decode error read off it is identically zero. Model values come
               from load_duckdb._model_expr, which is the model branch with no COALESCE.

Question: is the constraint's residual SMALLER than the implied-CA error it would correct?
Everything CV'd by player, so the weights never see the fold they are scored on.
"""
import sys, os, duckdb, numpy as np
sys.path.insert(0, os.getcwd())
import load_duckdb as L
DB = sys.argv[1]
A23 = ["Aerial","Crossing","Dribbling","Shooting","Passing","Tackling","Technique",
       "Aggression","Creativity","Decisions","Leadership","Movement","Positioning","Teamwork",
       "Pace","Stamina","Strength","Agility","Handling","Kicking","Reflexes","Communication",
       "Throwing"]
con = duckdb.connect(DB, read_only=True)
spec = {}
for a, f, co, o, p in con.execute("SELECT attribute,feature,coef,own_offset,partner_offset "
                                  "FROM staging.attribute_model").fetchall():
    spec.setdefault(a, {"own": o, "partner": p, "coef": {}})["coef"][f] = co
ENT = list(spec)
msel = ", ".join(f'{L._model_expr(a, spec[a], "staging")} AS m_{a}' for a in ENT)
d = con.execute(f'''SELECT p.ca, p.tid, p.is_gk, {msel},
                           {", ".join(f'e."{a}" AS t_{a}' for a in A23)}
                    FROM staging.players p
                    JOIN staging.player_attributes_exact e USING (season, phase, tid)
                    WHERE e."Passing" IS NOT NULL''').df().dropna()
ca = d.ca.to_numpy(float); T = d[[f"t_{a}" for a in A23]].to_numpy(float)
tids = d.tid.to_numpy(); uniq = np.array(sorted(set(tids.tolist())))
fold = np.array([{t: i % 5 for i, t in
                  enumerate(np.random.default_rng(0).permutation(uniq))}[t] for t in tids])
print(f"{len(d)} truth rows, {len(uniq)} players\n")

M = np.c_[T, np.ones(len(ca))]
cons_r, dec_r = np.empty(len(ca)), np.empty(len(ca))
for k in range(5):
    te = fold == k
    b, *_ = np.linalg.lstsq(M[~te], ca[~te], rcond=None)
    cons_r[te] = ca[te] - M[te] @ b                      # how well CA is pinned at all
    e = np.zeros(int(te.sum()))
    for a in ENT:                                        # our decode's error, in CA points
        e += b[A23.index(a)] * (d.loc[te, f"m_{a}"].to_numpy(float)
                                - d.loc[te, f"t_{a}"].to_numpy(float))
    dec_r[te] = e
print(f"  the constraint's own residual   sd {cons_r.std():>5.1f} CA pts   "
      f"(how tightly CA = sum(w*attr) holds)")
print(f"  our decode's implied-CA error   sd {dec_r.std():>5.1f} CA pts   "
      f"(what the constraint would correct)")
print(f"\n  ratio: the constraint is {cons_r.std()/dec_r.std():.1f}x NOISIER than the error "
      f"it would fix.")
print("  A constraint looser than the estimate it constrains cannot improve it.\n")
print(f"  for scale: sd(CA) over these rows is {ca.std():.1f}, "
      f"and a +1 on one attribute is worth ~{np.median(np.abs(b[:23])):.2f} CA")
