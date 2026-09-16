"""Classify all 23 displayed attributes by HOW the save gives them to us.

  DIRECT     one plain 1-20 byte, displayed verbatim -- nothing to model
  COMPOSITE  a function of two plain 1-20 bytes -- a closed form, no CA
  MODELLED   an entangled 0-255 byte that needs the shared CA shift to decode

Every claim is measured on the exact-truth rows (managed-club snapshot, an independent source
from the global record), held out by player where a fit is involved. GK attributes are scored
on GOALKEEPERS only: an outfielder's value is pinned at the display floor, so scoring them
pooled measures how often we guess 1.
"""
import sys, duckdb, numpy as np
DB = sys.argv[1]
SRC = {  # displayed attribute -> (bytes it is built from, kind)
 "Pace":(["pace_src"],"direct"), "Strength":(["strength_src"],"direct"),
 "Stamina":(["stamina_src"],"direct"), "Technique":(["technique_src"],"direct"),
 "Aggression":(["aggression_src"],"direct"), "Leadership":(["leadership_src"],"direct"),
 "Agility":(["agility_src"],"direct"),
 "Teamwork":(["unselfishness_src","work_rate"],"composite"),
 "Aerial":(["heading_src","jumping"],"composite"),
 "Crossing":(["crossing_src"],"modelled"), "Dribbling":(["dribbling_src"],"modelled"),
 "Tackling":(["tackling_src"],"modelled"), "Shooting":(["finishing_src","long_shot_src"],"modelled"),
 "Passing":(["passing_src"],"modelled"), "Decisions":(["decision_src"],"modelled"),
 "Creativity":(["creativity_src"],"modelled"), "Movement":(["movement_src"],"modelled"),
 "Positioning":(["positioning_src"],"modelled"),
 "Handling":(["handling_src"],"modelled"), "Kicking":(["kicking_src"],"modelled"),
 "Reflexes":(["reflexes_src"],"modelled"), "Communication":(["communication_src"],"modelled"),
 "Throwing":(["throwing_src"],"modelled")}
GKATTR = {"Handling","Kicking","Reflexes","Communication","Throwing"}
ENT = {"crossing_src","dribbling_src","tackling_src","finishing_src","long_shot_src",
       "passing_src","decision_src","creativity_src","movement_src","positioning_src",
       "handling_src","kicking_src","aerial_gk_src","reflexes_src","communication_src",
       "throwing_src"}
cols = sorted({b for bs, _ in SRC.values() for b in bs})
c = duckdb.connect(DB, read_only=True)
df = c.sql(f"""SELECT e.*, p.ca, p.is_gk, {', '.join('p.'+b for b in cols)}
               FROM staging.player_attributes_exact e JOIN staging.players p USING (tid, phase)
               WHERE e."Crossing" IS NOT NULL""").df()
print(f"{len(df)} truth rows, {df.tid.nunique()} players "
      f"({int(df.is_gk.sum())} GK rows, {int((~df.is_gk.astype(bool)).sum())} outfield)\n")
tids = df.tid.to_numpy(); uniq = np.array(sorted(set(tids.tolist())))
fo = {t: i % 5 for i, t in enumerate(np.random.default_rng(0).permutation(uniq))}
FOLD = np.array([fo[t] for t in tids])

def B(col, m):
    v = df[col].to_numpy(float)[m]
    return np.where(v < 128, v + 256, v) if col in ENT else v

def cv(Xs, y, fold):
    pred = np.empty(len(y)); offs = np.arange(-1, 1.01, 0.02)
    for k in range(5):
        te = fold == k
        if te.sum() == 0 or (~te).sum() < 5: return float("nan")
        A = np.c_[tuple(Xs) + (np.ones(len(y)),)]
        b, *_ = np.linalg.lstsq(A[~te], y[~te], rcond=None)
        o = max(offs, key=lambda v: (np.clip(np.rint(A[~te] @ b + v), 1, 20) == y[~te]).mean())
        pred[te] = A[te] @ b + o
    return (np.clip(np.rint(pred), 1, 20) == y).mean()

print(f"{'attribute':<14}{'kind':<11}{'source byte(s)':<30}"
      f"{'byte only':>10}{'+CA shift':>11}{'CA buys':>9}  scored on")
rows = []
for a, (bs, kind) in SRC.items():
    m = (df.is_gk == 1).to_numpy() if a in GKATTR else (df.is_gk == 0).to_numpy()
    who = "GKs" if a in GKATTR else "outfield"
    y = df[a].to_numpy(float)[m]; fold = FOLD[m]
    Xs = tuple(B(col, m) for col in bs)
    if kind == "direct":
        ex = float((Xs[0] == y).mean()); base = nf = ex; gain = 0.0
        note = "byte == displayed value"
    else:
        base = cv(Xs, y, fold)
        nf = cv(Xs + (df.ca.to_numpy(float)[m],), y, fold)
        gain = nf - base
        note = ""
    rows.append((a, kind, "+".join(bs), base, nf, gain, who, note))

for a, kind, src, base, nf, gain, who, note in rows:
    g = "" if kind == "direct" else f"{gain:>+8.1%}"
    print(f"{a:<14}{kind:<11}{src:<30}{base:>9.1%}{nf:>10.1%}{g:>9}  {who}"
          f"{'  ' + note if note else ''}")
