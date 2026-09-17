"""Is there a PATTERN to which attributes we get wrong?

Per attribute, alongside accuracy: the bias (are we systematically high or low), the spread of
the underlying byte (a byte that barely varies is easy), how close the values sit to the
display floor, and how much the attribute matters to the player's own position. The last is the
interesting hypothesis -- an attribute irrelevant to a player (a centre-back's finishing) may be
stored carelessly by the game and so be intrinsically noisier than one it actually uses.
"""
import sys, os, numpy as np, duckdb
sys.path.insert(0, os.getcwd())
import load_duckdb as L
from fmparser import model as MOD
DB = sys.argv[1]
con = duckdb.connect(DB, read_only=True)
spec, feats = {}, {}
for a, f, c, o, p in con.execute("SELECT attribute,feature,coef,own_offset,partner_offset "
                                 "FROM staging.attribute_model").fetchall():
    spec.setdefault(a, {"own": o, "partner": p, "coef": {}})["coef"][f] = c
for a, d in spec.items():
    feats[a] = "shared(3)" if set(d["coef"]) <= {"own", "partner", "CA", "intercept"} else "gk(8)"
ENT = list(spec)
BYTE = {a: [k for k, v in {**__import__("fmparser.attributes", fromlist=["x"]).SRC_OFFSETS}.items()
            if k == spec[a]["own"]] for a in ENT}
from fmparser.attributes import SRC_OFFSETS
COL = {a: SRC_OFFSETS[spec[a]["own"]] for a in ENT}
msel = ", ".join(f'{L._model_expr(a, spec[a], "staging")} AS m_{a}, e."{a}" AS t_{a}, '
                 f'p.{COL[a]} AS b_{a}' for a in ENT)
d = con.execute(f'''SELECT p.is_gk, {msel} FROM staging.players p
                    JOIN staging.player_attributes_exact e USING (season, phase, tid)
                    WHERE e."Passing" IS NOT NULL''').df()
gk = d.is_gk.to_numpy().astype(bool)
GKA = {"Handling", "Kicking", "Reflexes", "Communication", "Throwing"}

print(f"{'attribute':<15}{'model':<10}{'exact':>7}{'±1':>7}{'bias':>7}{'sd':>6}"
      f"{'byte sd':>9}{'true sd':>9}{'at floor':>9}{'scored on':>10}")
rows = []
for a in ENT:
    m = d[f"m_{a}"].to_numpy(float); t = d[f"t_{a}"].to_numpy(float)
    b = d[f"b_{a}"].to_numpy(float); b = np.where(b < 128, b + 256, b)
    sub = gk if a in GKA else ~gk          # score each on the population that HAS the attribute
    m, t, b = m[sub], t[sub], b[sub]
    k = ~np.isnan(t); m, t, b = m[k], t[k], b[k]
    e = m - t
    rows.append((a, feats[a], (e == 0).mean(), (np.abs(e) <= 1).mean(), e.mean(), e.std(),
                 b.std(), t.std(), (t <= 2).mean(), "GK" if a in GKA else "outfield", t, e))
    print(f"{a:<15}{feats[a]:<10}{rows[-1][2]:>6.1%}{rows[-1][3]:>7.1%}{e.mean():>+7.2f}"
          f"{e.std():>6.2f}{b.std():>9.1f}{t.std():>9.2f}{(t<=2).mean():>8.1%}"
          f"{rows[-1][9]:>10}")

print("\nwhat predicts an attribute's exact-match rate? (corr across the 14)")
ex = np.array([r[2] for r in rows])
for lab, v in (("spread of the TRUE value (sd)", np.array([r[7] for r in rows])),
               ("spread of the source byte (sd)", np.array([r[6] for r in rows])),
               ("share of values at the floor (<=2)", np.array([r[8] for r in rows])),
               ("|bias|", np.abs([r[4] for r in rows]))):
    print(f"  {lab:<36}{np.corrcoef(v, ex)[0,1]:>+6.2f}")

print("\nerror vs the TRUE value, pooled over all 14 (is a high attribute harder?)")
T = np.concatenate([r[10] for r in rows]); E = np.concatenate([r[11] for r in rows])
for lo, hi in [(1,3),(4,6),(7,9),(10,12),(13,15),(16,20)]:
    k = (T >= lo) & (T <= hi)
    if k.sum() > 30:
        print(f"  true {lo:>2}-{hi:<2}  n={k.sum():>5}   exact {(E[k]==0).mean():>6.1%}"
              f"   mean err {E[k].mean():>+6.2f}   |err|>=2 {(np.abs(E[k])>=2).mean():>6.1%}")
