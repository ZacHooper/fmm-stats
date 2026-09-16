"""Recover FM's positional CA weighting (docs/ATTRIBUTE_MODEL_HANDOFF.md).

Run: uv run python archive/ca_weight_set.py <store.duckdb>

Recover FM's CA weight set: regress CA on all 34 attribute slots, standardised.

Standardised betas are comparable across attributes with different spreads, so the ranking IS
the weight ranking. Run per TOP POSITION as well as pooled -- FM weights CA by position, and
pooling a CB's finishing with a striker's hides exactly the effect we're looking for.
"""
import sys, duckdb, numpy as np

DB = sys.argv[1]
ENT = ["crossing_src","dribbling_src","tackling_src","finishing_src","long_shot_src",
       "passing_src","decision_src","creativity_src","movement_src","positioning_src",
       "handling_src","kicking_src","aerial_gk_src","reflexes_src","communication_src",
       "throwing_src"]
PLAIN = ["heading_src","unselfishness_src","pace_src","strength_src","stamina_src",
         "technique_src","aggression_src","leadership_src","agility_src"]
HID = ["jumping","consistency","big_match","injury_prone","versatility","set_pieces",
       "penalty","work_rate","flair"]
ALL = ENT + PLAIN + HID
POS = ["GK","SW","DL","DC","DR","DMC","ML","MC","MR","AML","AMC","AMR","ST","DML","DMR"]

c = duckdb.connect(DB, read_only=True)
df = c.sql(f"""
  SELECT ca, is_gk, positions, {', '.join(ALL)}
  FROM staging.players
  WHERE NOT is_staff AND has_attributes AND ca > 0 AND ca <= pa
""").df().dropna()

import json
def top_pos(p):
    d = json.loads(p) if isinstance(p, str) else (p or {})
    return max(d, key=lambda k: (d[k], -POS.index(k))) if d else None
df["top"] = df["positions"].map(top_pos)

def prep(d):
    X = d[ALL].to_numpy(float).copy()
    for i, a in enumerate(ALL):
        if a in ENT:
            col = X[:, i]; X[:, i] = np.where(col < 128, col + 256, col) * 0.115 - 20
    return X, d["ca"].to_numpy(float)

def fit(name, d, show=14):
    if len(d) < 400: return
    X, ca = prep(d)
    keep = [i for i in range(X.shape[1]) if X[:, i].std() > 1e-6]
    Z = (X[:, keep] - X[:, keep].mean(0)) / X[:, keep].std(0)
    y = (ca - ca.mean()) / ca.std()
    b, *_ = np.linalg.lstsq(np.c_[Z, np.ones(len(y))], y, rcond=None)
    pred = np.c_[Z, np.ones(len(y))] @ b
    r2 = 1 - ((y - pred) ** 2).sum() / (y ** 2).sum()
    print(f"=== {name}  n={len(d):,}   R2={r2:.3f} ===")
    order = sorted(range(len(keep)), key=lambda k: -abs(b[k]))
    for k in order[:show]:
        a = ALL[keep[k]]
        kind = "ent" if a in ENT else ("plain" if a in PLAIN else "hidden")
        bar = ("#" if b[k] > 0 else "-") * int(abs(b[k]) * 60)
        print(f"  {a:<20}{b[k]:>7.3f}  {kind:<7}{bar}")
    print()

fit("OUTFIELD (pooled)", df[df.is_gk == 0], show=16)
fit("GOALKEEPERS", df[df.is_gk == 1], show=16)
for p in ["DC","MC","ST","AMC","DL","AML"]:
    fit(f"top position = {p}", df[(df.is_gk == 0) & (df["top"] == p)], show=10)
