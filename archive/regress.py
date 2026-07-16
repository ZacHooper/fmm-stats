#!/usr/bin/env python3
"""
Grid-search regression to decode the 0-255-scale sub-attributes into displayed 1-20
values. Uses the 28 Bucaspor players (only set with BOTH the displayed value and the
raw record bytes).

Model: displayed_attr = round( linear combination of features ), where features can be
 - the attribute's own raw byte at its guide offset (UNWRAPPED: b+256 if b<128, since
   the 0-255 store wraps — strong attrs have low bytes),
 - the partner byte for doubled attrs (Shooting=Finishing+LongShots, Aerial=Head+Jump),
 - CA, PA, mean of the 9 already-solved attributes  (user's "scale by the knowns" theory).

For each attribute it grid-searches every feature subset and reports the best by
exact-round matches (then R²). Run: python3 regress.py
"""
import json
import itertools
import numpy as np
from fmtool import Save
from attrs import attr_record, decode
from league_attrs import record_for

NINE = ["Aerial", "Teamwork", "Pace", "Strength", "Stamina", "Technique",
        "Aggression", "Leadership", "Agility"]
# attribute -> (own guide offset, partner offset or None for doubled attrs)
TARGETS = {
    "Crossing": (-34, None), "Dribbling": (-33, None), "Tackling": (-32, None),
    "Shooting": (-31, -30), "Aerial": (-29, -28), "Passing": (-27, None),
    "Decisions": (-26, None), "Creativity": (-12, None), "Movement": (-11, None),
    "Positioning": (-10, None), "Handling": (-7, None), "Kicking": (-6, None),
    "Reflexes": (-3, None), "Communication": (-2, None), "Throwing": (-1, None),
}
GK_ATTRS = {"Handling", "Kicking", "Reflexes", "Communication", "Throwing"}


def uw(b):
    return b + 256 if b < 128 else b


def load(mm):
    raw = json.load(open("bucaspor_players.json"))
    rows = []
    for tid_s, name in raw.items():
        tid = int(tid_s)
        snap = attr_record(mm, tid)
        rec = record_for(mm, tid)
        if not (snap and rec):
            continue
        k = decode(snap["attrs"])
        P = rec["P"]
        pos = snap["positions"]
        top = max(pos, key=pos.get) if pos else ""
        fwd = 1.0 if top in ("ST", "AML", "AMR", "AMC") else (
            0.5 if top in ("ML", "MR", "MC", "DMC") else 0.0)
        rows.append({"name": name, "P": P, "disp": k,
                     "is_gk": int(pos.get("GK", 0) == 20),
                     "ca": rec["ca"], "pa": rec["pa"], "fwd": fwd, "top": top,
                     "mean9": sum(k[a] for a in NINE) / 9,
                     "mm": mm})
    return rows


def regress(rows, attr):
    own_off, partner = TARGETS[attr]
    sub = [r for r in rows if (r["is_gk"] == 1) == (attr in GK_ATTRS)] \
        if attr in GK_ATTRS else rows
    if len(sub) < 6:
        sub = rows
    mm = rows[0]["mm"]
    own = [uw(mm[r["P"] + own_off]) for r in sub]
    ca = [r["ca"] for r in sub]
    feats = {"own": own, "CA": ca, "PA": [r["pa"] for r in sub],
             "mean9": [r["mean9"] for r in sub],
             "own*CA": [o * c / 100 for o, c in zip(own, ca)],   # multiplicative term
             "fwd": [float(r["fwd"]) for r in sub]}              # position: attacking-ness
    if partner is not None:
        feats["partner"] = [uw(mm[r["P"] + partner]) for r in sub]
    y = np.array([r["disp"][attr] for r in sub], float)
    pool = list(feats)
    best = None
    for k in range(1, len(pool) + 1):
        for combo in itertools.combinations(pool, k):
            X = np.c_[tuple(np.array(feats[f], float) for f in combo) + (np.ones(len(y)),)]
            coef, *_ = np.linalg.lstsq(X, y, rcond=None)
            pred = X @ coef
            exact = int(np.sum(np.round(pred) == y))
            within1 = int(np.sum(np.abs(np.round(pred) - y) <= 1))
            ss = np.sum((y - y.mean()) ** 2)
            r2 = 1 - np.sum((y - pred) ** 2) / ss if ss else 0
            if best is None or (exact, r2) > (best[0], best[1]):
                best = (exact, within1, r2, combo, coef, len(y))
    return best


if __name__ == "__main__":
    s = Save()
    rows = load(s.mm)
    print(f"{len(rows)} players\n{'attr':13} {'exact':>7} {'±1':>7} {'R2':>6}  features")
    tot_ex = tot_w1 = tot_n = 0
    for attr in TARGETS:
        exact, within1, r2, combo, coef, n = regress(rows, attr)
        tot_ex += exact; tot_w1 += within1; tot_n += n
        print(f"  {attr:13} {exact:>3}/{n:<3} {within1:>3}/{n:<3} {r2:>6.2f}  {'+'.join(combo)}")
    print(f"\n  TOTAL exact {tot_ex}/{tot_n} ({100*tot_ex/tot_n:.0f}%)  "
          f"within±1 {tot_w1}/{tot_n} ({100*tot_w1/tot_n:.0f}%)")
