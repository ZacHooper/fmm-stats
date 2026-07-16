#!/usr/bin/env python3
"""
PRODUCTION league-wide attribute estimator.

Emits the full displayed attribute set (23 visible attrs) for every league player,
combining three sources of decode:
  1. EXACT single bytes (raw 1-20):  Pace, Strength, Stamina, Technique, Aggression,
     Leadership, Agility.                                   -> read straight off P+offset
  2. EXACT formula:  Teamwork = floor((Unselfish + WorkRate)/2).
  3. ESTIMATED (±1) via the regression trained on the 28 Bucaspor players (the only set
     with BOTH the raw bytes and the displayed values):  Crossing, Dribbling, Tackling,
     Shooting, Aerial, Passing, Decisions, Creativity, Movement, Positioning, and the GK
     cluster Handling, Kicking, Reflexes, Communication, Throwing.

Accuracy of (3): ~63% exact, ~93% within ±1 on the held-out Bucaspor set (see
ATTRIBUTE_DECODING.md). (1) and (2) are exact. So each player row is a mix of exact and
±1 values; the `est` flag per attribute records which is which.

Inputs:  league_attrs.json (record locations + exact-9 + CA/PA/pos/feet), the save file,
         bucaspor_players.json (own-squad names), tid_club.json + clubs.json (club names).
Outputs: league_player_attrs.json  (full structured data)
         league_player_attrs.csv   (one row per player, wide format)
Run:     python3 estimate_attrs.py
"""
import csv
import json
import math
import numpy as np
from fmtool import Save
from regress import load, regress, TARGETS, uw, NINE, GK_ATTRS

# exact single-byte attributes: offset relative to positions start P
EXACT_SINGLE = {"Pace": -24, "Strength": -23, "Stamina": -22, "Technique": -21,
                "Aggression": -19, "Leadership": -16, "Agility": -5}
# display order for the CSV / output (idx9 is a hidden attr, omitted)
ATTR_ORDER = ["Aerial", "Crossing", "Dribbling", "Shooting", "Passing", "Tackling",
              "Technique", "Aggression", "Creativity", "Decisions", "Leadership",
              "Movement", "Positioning", "Teamwork", "Pace", "Stamina", "Strength",
              "Agility", "Handling", "Kicking", "Reflexes", "Communication", "Throwing"]


def feat_vec(mm, P, ca, pa, mean9, fwd, combo, own_off, partner):
    own = uw(mm[P + own_off])
    vals = {"own": own, "CA": ca, "PA": pa, "mean9": mean9,
            "own*CA": own * ca / 100, "fwd": fwd}
    if partner is not None:
        vals["partner"] = uw(mm[P + partner])
    return [vals[f] for f in combo] + [1.0]


def fwd_of(positions):
    top = max(positions, key=positions.get) if positions else ""
    if top in ("ST", "AML", "AMR", "AMC"):
        return 1.0
    if top in ("ML", "MR", "MC", "DMC", "DML", "DMR"):
        return 0.5
    return 0.0


def estimate_player(mm, rec, models):
    """Full 23-attr set for one league player record (from league_attrs.json)."""
    P = rec["P"]
    ca, pa = rec["ca"], rec["pa"]
    is_gk = int(rec["positions"].get("GK", 0) == 20)
    fwd = fwd_of(rec["positions"])
    mean9 = sum(rec["attributes"].values()) / len(rec["attributes"])
    out = {}
    # (1) exact single bytes
    for attr, off in EXACT_SINGLE.items():
        out[attr] = {"val": mm[P + off], "est": False}
    # (2) exact formula
    tw = math.floor((mm[P - 25] + mm[P - 9]) / 2)
    out["Teamwork"] = {"val": max(1, min(20, tw)), "est": False}
    # (3) regressed
    for attr, (combo, coef, own_off, partner) in models.items():
        v = float(np.dot(feat_vec(mm, P, ca, pa, mean9, fwd, combo, own_off, partner), coef))
        out[attr] = {"val": max(1, min(20, int(round(v)))), "est": True}
    return out, is_gk, fwd


def main():
    s = Save()
    mm = s.mm
    # train once on Bucaspor
    rows = load(mm)
    models = {}
    for attr, (own_off, partner) in TARGETS.items():
        _, _, _, combo, coef, _ = regress(rows, attr)
        models[attr] = (combo, coef, own_off, partner)

    league = json.load(open("league_attrs.json"))
    names = {int(k): v for k, v in json.load(open("bucaspor_players.json")).items()}
    tid_club = {int(k): v for k, v in json.load(open("tid_club.json")).items()}
    clubs = json.load(open("clubs.json"))

    def club_name(tid):
        ct = tid_club.get(tid)
        return clubs.get(str(ct), {}).get("long", str(ct)) if ct else "?"

    out = {}
    for tid_s, rec in league.items():
        tid = int(tid_s)
        attrs, is_gk, fwd = estimate_player(mm, rec, models)
        out[tid_s] = {
            "tid": tid, "name": names.get(tid, f"#{tid}"), "club": club_name(tid),
            "is_gk": is_gk, "ca": rec["ca"], "pa": rec["pa"],
            "reputation": rec["reputation"], "positions": rec["positions"],
            "feet": rec["feet"],
            "attributes": {a: attrs[a]["val"] for a in ATTR_ORDER},
            "estimated": {a: attrs[a]["est"] for a in ATTR_ORDER},
        }
    json.dump(out, open("league_player_attrs.json", "w"), ensure_ascii=False, indent=1)

    # wide CSV
    with open("league_player_attrs.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tid", "name", "club", "GK", "CA", "PA", "rep", "positions"]
                   + ATTR_ORDER)
        for p in sorted(out.values(), key=lambda x: (-x["ca"], x["name"])):
            pos = "/".join(k for k, v in sorted(p["positions"].items(),
                                                key=lambda kv: -kv[1]))
            w.writerow([p["tid"], p["name"], p["club"], "Y" if p["is_gk"] else "",
                        p["ca"], p["pa"], p["reputation"], pos]
                       + [p["attributes"][a] for a in ATTR_ORDER])

    n = len(out)
    exact_attrs = len(EXACT_SINGLE) + 1
    print(f"{n} players -> league_player_attrs.json / .csv")
    print(f"  {exact_attrs} exact attrs/player, {len(TARGETS)} estimated (±1, ~93%)")


if __name__ == "__main__":
    main()
