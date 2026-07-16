#!/usr/bin/env python3
"""
Dump actual vs estimated attribute values for the Bucaspor squad, so the gap can be
eyeballed. Also prints the fitted linear formula per attribute.

- 7 single-byte attrs (Pace, Strength, Stamina, Technique, Aggression, Leadership,
  Agility) and Teamwork are EXACT (byte / floor-average) -> delta always 0.
- The 14 technical/GK attrs are ESTIMATED via the best regression from regress.py.

Outputs long-form `attr_estimates.csv`: name, position, is_gk, ca, attribute, actual,
estimated, delta.  Run: python3 estimate_dump.py
"""
import csv
import math
import numpy as np
from fmtool import Save
from regress import load, regress, TARGETS, uw, NINE, GK_ATTRS

EXACT_SINGLE = {"Pace": -24, "Strength": -23, "Stamina": -22, "Technique": -21,
                "Aggression": -19, "Leadership": -16, "Agility": -5}


def feat_vec(r, combo, own_off, partner):
    mm = r["mm"]
    own = uw(mm[r["P"] + own_off])
    vals = {"own": own, "CA": r["ca"], "PA": r["pa"], "mean9": r["mean9"],
            "own*CA": own * r["ca"] / 100, "fwd": r["fwd"]}
    if partner is not None:
        vals["partner"] = uw(mm[r["P"] + partner])
    return [vals[f] for f in combo] + [1.0]


if __name__ == "__main__":
    s = Save()
    rows = load(s.mm)
    out = []
    formulas = {}
    # fit each regressed attribute once, keep (combo, coef, subset-membership)
    for attr, (own_off, partner) in TARGETS.items():
        exact, within1, r2, combo, coef, n = regress(rows, attr)
        formulas[attr] = (combo, coef, r2, exact, within1, n)
    for r in rows:
        k = r["disp"]
        mm = r["mm"]
        for attr, off in EXACT_SINGLE.items():
            out.append([r["name"], r["top"], r["is_gk"], r["ca"], attr,
                        k[attr], mm[r["P"] + off], 0])
        tw = math.floor((mm[r["P"] - 25] + mm[r["P"] - 9]) / 2)
        out.append([r["name"], r["top"], r["is_gk"], r["ca"], "Teamwork",
                    k["Teamwork"], tw, tw - k["Teamwork"]])
        for attr, (own_off, partner) in TARGETS.items():
            combo, coef, *_ = formulas[attr]
            # only predict where the player is in the model's training subset
            if attr in GK_ATTRS and r["is_gk"] != 1:
                continue
            est = int(round(float(np.dot(feat_vec(r, combo, own_off, partner), coef))))
            est = max(1, min(20, est))
            out.append([r["name"], r["top"], r["is_gk"], r["ca"], attr,
                        k[attr], est, est - k[attr]])
    with open("attr_estimates.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "position", "is_gk", "ca", "attribute",
                    "actual", "estimated", "delta"])
        w.writerows(out)
    print(f"{len(out)} rows -> attr_estimates.csv\n")
    print("Fitted formula per estimated attribute (coef per feature, last = intercept):")
    for attr, (combo, coef, r2, exact, within1, n) in formulas.items():
        terms = "  ".join(f"{c:+.3f}*{f}" for c, f in zip(coef, combo))
        print(f"  {attr:12} R²={r2:.2f} ±1={within1}/{n}: {terms}  {coef[-1]:+.2f}")
