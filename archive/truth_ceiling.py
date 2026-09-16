"""Two checks.

(A) CEILING. The 7 'exact' attributes are read straight from a plain byte, so any disagreement
    with the managed-club snapshot is the two sources disagreeing, not a decode error. Whatever
    that rate is, it caps what ANY model of the entangled attributes can score.

(B) VERSATILITY. Hypothesis: positional familiarity spreads a fixed CA over more attributes, so
    at the same CA a player familiar in more positions is worse at each. Tested at fixed CA and
    fixed top position, and in the specific form 'an ST who can also play DC'.
"""
import sys, json, duckdb, numpy as np
DB = sys.argv[1]
DIRECT = {"Pace":"pace_src","Strength":"strength_src","Stamina":"stamina_src",
          "Technique":"technique_src","Aggression":"aggression_src",
          "Leadership":"leadership_src","Agility":"agility_src"}
c = duckdb.connect(DB, read_only=True)
d = c.sql(f"""SELECT e.*, {', '.join('p.'+v for v in DIRECT.values())}
              FROM staging.player_attributes_exact e JOIN staging.players p USING (tid, phase)
              WHERE e."Crossing" IS NOT NULL AND NOT p.is_gk""").df()
print(f"(A) agreement between the global record's plain byte and the snapshot's exact value,")
print(f"    {len(d)} outfield truth rows:\n")
exact, w1 = [], []
for a, col in DIRECT.items():
    x, y = d[col].to_numpy(float), d[a].to_numpy(float)
    e, o = (x == y).mean(), (np.abs(x - y) <= 1).mean()
    exact.append(e); w1.append(o)
    print(f"    {a:<12}{e:>7.1%} exact{o:>9.1%} within 1   mean signed diff {np.mean(x-y):>+5.2f}")
print(f"    {'MEAN':<12}{np.mean(exact):>7.1%}      {np.mean(w1):>7.1%}")
print("    -> no model of the ENTANGLED attributes can beat this; it is the same two sources.\n")

POS = ["GK","SW","DL","DC","DR","DMC","ML","MC","MR","AML","AMC","AMR","ST","DML","DMR"]
df = c.sql("""SELECT ca, positions, finishing_src, passing_src, tackling_src, positioning_src,
                     dribbling_src, crossing_src, decision_src, creativity_src, movement_src
              FROM staging.players
              WHERE NOT is_staff AND has_attributes AND ca > 0 AND ca <= pa AND NOT is_gk""").df()
pos = df.positions.map(json.loads)
df["top"] = pos.map(lambda p: max(p, key=lambda k: (p[k], -POS.index(k))) if p else None)
df["breadth"] = pos.map(lambda p: sum(1 for v in p.values() if v >= 15))
df["famsum"] = pos.map(lambda p: sum(p.values()))
ENT = ["finishing_src","passing_src","tackling_src","positioning_src","dribbling_src",
       "crossing_src","decision_src","creativity_src","movement_src"]
for col in ENT:
    v = df[col].to_numpy(float)
    df[col] = np.where(v < 128, v + 256, v) * 0.115 - 20

print("(B) effect of positional breadth, CONTROLLING for CA and top position.")
print("    coefficient = display points per extra position at familiarity >= 15\n")
print(f"    {'attribute':<14}" + "".join(f"{p:>9}" for p in ["DC","MC","ST","AML/AMR"]))
for col in ENT:
    line = f"    {col.replace('_src',''):<14}"
    for p, members in [("DC",["DC"]),("MC",["MC"]),("ST",["ST"]),("AML/AMR",["AML","AMR"])]:
        g = df[df.top.isin(members)]
        A = np.c_[g.ca.to_numpy(float), g.breadth.to_numpy(float), np.ones(len(g))]
        b, *_ = np.linalg.lstsq(A, g[col].to_numpy(float), rcond=None)
        line += f"{b[1]:>+9.2f}"
    print(line)
print(f"\n    (n: DC {len(df[df.top=='DC']):,}  MC {len(df[df.top=='MC']):,}  "
      f"ST {len(df[df.top=='ST']):,}  AML/AMR {len(df[df.top.isin(['AML','AMR'])]):,};"
      f" mean breadth {df.breadth.mean():.2f})")

print("\n    your specific case -- STs matched on CA, split by whether they can also play DC:")
st = df[df.top == "ST"].copy()
st["dcfam"] = pos[st.index].map(lambda p: p.get("DC", 0))
st["caband"] = (st.ca // 10) * 10
a = st[st.dcfam >= 15]; b_ = st[st.dcfam <= 5]
print(f"    {'attribute':<14}{'ST+DC':>9}{'ST only':>9}{'diff':>8}   (CA-band weighted, "
      f"n={len(a):,} vs {len(b_):,})")
for col in ENT:
    ma = a.groupby("caband")[col].mean(); mb = b_.groupby("caband")[col].mean()
    w = a.groupby("caband").size().reindex(ma.index).astype(float)
    common = ma.index.intersection(mb.index)
    ma, mb, w = ma[common], mb[common], w[common]
    va, vb = (ma*w).sum()/w.sum(), (mb*w).sum()/w.sum()
    print(f"    {col.replace('_src',''):<14}{va:>9.2f}{vb:>9.2f}{va-vb:>+8.2f}")
