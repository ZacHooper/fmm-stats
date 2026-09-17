"""FM's positional CA weighting, with the two things that make a naive version wrong fixed.

  1. CROSS-GROUP BYTES EXCLUDED. An outfielder's GK bytes sit below the display floor and sink
     further as CA rises, so a pooled fit hands them a large NEGATIVE weight that is pure
     artifact. GK-only bytes are dropped from outfield fits and vice versa; the exclusion is
     evidenced below rather than assumed.
  2. PER-ATTRIBUTE DISPLAY SCALE. An entangled byte spans 8.0-14.4 raw units per display point
     depending on the attribute, so converting them all at one rate mis-scales the
     unstandardised weights (Decisions by 1.65x). Slopes come from the exact-truth fit.

Standardised betas are invariant to that scale, so the share table is safe either way and is
the one to trust.
"""
import sys, json, duckdb, numpy as np

DB = sys.argv[1]
GK_ONLY = ["handling_src","kicking_src","aerial_gk_src","reflexes_src","communication_src",
           "throwing_src"]
OUT_ONLY = ["crossing_src","dribbling_src","tackling_src","finishing_src","long_shot_src",
            "passing_src","decision_src","creativity_src","movement_src","positioning_src"]
PLAIN = ["heading_src","unselfishness_src","pace_src","strength_src","stamina_src",
         "technique_src","aggression_src","leadership_src","agility_src"]
HID = ["jumping","consistency","big_match","injury_prone","versatility","set_pieces",
       "penalty","work_rate","flair"]
ALL = OUT_ONLY + GK_ONLY + PLAIN + HID
ENT = set(OUT_ONLY) | set(GK_ONLY)
# display-scale slopes from the exact-truth fit; the rest are plain 1-20 bytes (slope 1)
SLOPE = {"crossing_src":0.1144,"dribbling_src":0.1248,"tackling_src":0.1071,
         "finishing_src":0.0860,"passing_src":0.1203,"decision_src":0.0695,
         "creativity_src":0.1014,"movement_src":0.1124,"positioning_src":0.1005}
LABEL = {c: c.replace("_src","").replace("decision","decisions")
             .replace("long_shot","long shots").replace("aerial_gk","aerial (GK)")
             .replace("_"," ") for c in ALL}
POS = ["GK","SW","DL","DC","DR","DMC","ML","MC","MR","AML","AMC","AMR","ST","DML","DMR"]
GROUPS = [("GK",["GK"]),("DC",["DC"]),("DL/DR",["DL","DR"]),("DMC",["DMC","DML","DMR"]),
          ("MC",["MC"]),("ML/MR",["ML","MR"]),("AMC",["AMC"]),("AML/AMR",["AML","AMR"]),
          ("ST",["ST"])]

c = duckdb.connect(DB, read_only=True)
df = c.sql(f"""SELECT ca, is_gk, positions, {', '.join(ALL)} FROM staging.players
               WHERE NOT is_staff AND has_attributes AND ca > 0 AND ca <= pa""").df().dropna()
df["top"] = df.positions.map(
    lambda p: (lambda d: max(d, key=lambda k: (d[k], -POS.index(k))) if d else None)(json.loads(p)))

X0 = df[ALL].to_numpy(float).copy()
for i, a in enumerate(ALL):
    if a in ENT:
        col = X0[:, i]
        X0[:, i] = np.where(col < 128, col + 256, col) * SLOPE.get(a, 0.115)
ca0 = df["ca"].to_numpy(float)

print("evidence for excluding cross-group bytes. Outfielders only; the byte is shown unwrapped")
print("and as the display value it decodes to. A GK byte on an outfielder decodes AT OR BELOW")
print("the floor of 1 and sinks further as CA rises, so the fit can use it as a -CA proxy:")
for a in GK_ONLY + ["tackling_src"]:
    m = (df.is_gk == 0).to_numpy()
    v = df[a].to_numpy(float)[m]
    x = np.where(v < 128, v + 256, v)
    y = ca0[m]; q = np.quantile(y, [0.2, 0.8])
    lo, hi = x[y <= q[0]].mean(), x[y >= q[1]].mean()
    d = lambda u: u * 0.115 - 20
    print(f"  {LABEL[a]:<16} lowCA {lo:>5.0f} (-> {d(lo):>5.1f})   "
          f"highCA {hi:>5.0f} (-> {d(hi):>5.1f})   corr {np.corrcoef(x, y)[0,1]:>+5.2f}")
print("  (they are six INDEPENDENT bytes, not one fill -- all six are equal on only 3% of")
print("   outfielders -- but none carries displayable information for one.)")

raw, std, r2s, ns = {}, {}, {}, {}
for name, members in GROUPS:
    m = df["top"].isin(members).to_numpy()
    drop = set(OUT_ONLY) if name == "GK" else set(GK_ONLY)
    keep = [i for i, a in enumerate(ALL) if a not in drop and X0[m, i].std() > 1e-6]
    X, y = X0[m][:, keep], ca0[m]
    A = np.c_[X, np.ones(m.sum())]
    b, *_ = np.linalg.lstsq(A, y, rcond=None)
    r2s[name] = 1 - ((y - A @ b) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    ns[name] = int(m.sum())
    raw[name] = {ALL[k]: b[j] for j, k in enumerate(keep)}
    std[name] = {ALL[k]: b[j] * X[:, j].std() / y.std() for j, k in enumerate(keep)}

def table(D, unit, fmt, rescale=False, minshow=0.0):
    print(f"\n### {unit}\n")
    if rescale:
        D = {g: {a: (v / sum(x for x in d.values() if x > 0) * 100 if v > 0 else 0)
                 for a, v in d.items()} for g, d in D.items()}
    print("| attribute |" + "".join(f" {g} |" for g, _ in GROUPS))
    print("|---|" + "---|" * len(GROUPS))
    rank = sorted(ALL, key=lambda a: -max(D[g].get(a, 0) for g, _ in GROUPS))
    for a in rank:
        vals = [D[g].get(a, float("nan")) for g, _ in GROUPS]
        if max([v for v in vals if v == v] or [0]) < minshow:
            continue
        print(f"| {LABEL[a]} |" + "".join(f" {fmt(v)} |" for v in vals))
    print("| **n** |" + "".join(f" {ns[g]:,} |" for g, _ in GROUPS))
    print("| **R²** |" + "".join(f" {r2s[g]:.2f} |" for g, _ in GROUPS))

table(std, "Share of the position's CA weight (%)",
      lambda v: "–" if v != v or v < 0.5 else f"{v:.0f}", rescale=True, minshow=1.0)
table(raw, "CA points per +1 display point",
      lambda v: "–" if v != v else f"{v:+.1f}", minshow=0.3)
