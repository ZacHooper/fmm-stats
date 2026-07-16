#!/usr/bin/env python3
"""
Export a CALIBRATION CSV pairing each Bucaspor player's DISPLAYED attributes
(from the clean 62 MB squad snapshot) with the RAW bytes of their 78-byte global
record (~5 MB region), so the displayed<->raw relationship can be modelled in a
sheet.

Why this works: our own squad is the only set where we have BOTH forms —
 - displayed 1-20 values (validated vs in-game screenshots) via attrs.py, and
 - the raw global record located via SID (league_attrs.record_for).

Columns:
  name, tid, position, age, is_gk, snap_CA, snap_PA, rec_CA, rec_PA, foot_L, foot_R
  attr:<Name>   -> displayed value for each of the 23 visible attributes
  b<rel>        -> raw byte at offset (positions_start + rel), rel = -55..+22
                   (rel 0..14 = positions, 15/16 = feet, 17-18 CA, 19-20 PA, 21-22 rep)

The 9 offsets already solved (byte == displayed value): b-29 Aerial, b-25 Teamwork,
b-24 Pace, b-23 Strength, b-22 Stamina, b-21 Technique, b-19 Aggression,
b-16 Leadership, b-5 Agility. The other 14 visibles are the targets to model.
"""
import csv
import json
from fmtool import Save
from info import info_offset, parse_info
from attrs import attr_record, decode, POSITIONS
from league_attrs import record_for

ATTR_ORDER = ["Aerial", "Agility", "Communication", "Handling", "Kicking",
              "Throwing", "Reflexes", "Crossing", "Dribbling", "Passing",
              "Shooting", "Tackling", "Technique", "Aggression", "Creativity",
              "Decisions", "Leadership", "Movement", "Positioning", "Teamwork",
              "Pace", "Stamina", "Strength"]
REL = list(range(-55, 23))   # byte columns relative to positions start P

PERSONALITY = ["Adaptability", "Ambition", "Determination", "Loyalty",
               "PressureHandling", "Professionalism", "Sportsmanship", "Temperament"]

# The attribute block sits at b-34..b-1 in EXACT rough-guide Step-6 order
# (offset = guide# - 35). Proven by the confirmed 1-20 anchors below, which all
# land where the guide predicts. Format: rel -> (name, kind).
#   kind "ok"     = confirmed, byte == displayed value (1-20)
#   kind "team"   = confirmed Teamwork component: Teamwork = floor((b-25 + b-9)/2)
#   kind "?dbl"   = doubled attr component (Shooting=Fin+LongShots, Aerial=Head+Jump)
#   kind "?"      = guide-order hypothesis, NOT reconciled (likely 0-255-scale input)
#   kind "hidden" = hidden attribute (not shown in-game)
GUIDE_MAP = {
    -34: ("Crossing", "?"), -33: ("Dribbling", "?"), -32: ("Tackling", "?"),
    -31: ("Shooting.Finishing", "?dbl"), -30: ("Shooting.LongShots", "?dbl"),
    -29: ("Aerial.Heading", "?dbl"), -28: ("Aerial.Jumping", "?dbl"),
    -27: ("Passing", "?"), -26: ("Decisions", "?"),
    -25: ("Teamwork.Unselfish", "team"), -24: ("Pace", "ok"), -23: ("Strength", "ok"),
    -22: ("Stamina", "ok"), -21: ("Technique", "ok"), -20: ("Consistency", "hidden"),
    -19: ("Aggression", "ok"), -18: ("BigMatches", "hidden"),
    -17: ("InjuryProneness", "hidden"), -16: ("Leadership", "ok"),
    -15: ("Versatility", "hidden"), -14: ("SetPieces", "hidden"),
    -13: ("Penalties", "hidden"), -12: ("Creativity", "?"), -11: ("Movement", "?"),
    -10: ("Positioning", "?"), -9: ("Teamwork.WorkRate", "team"),
    -8: ("Flair", "hidden"), -7: ("Handling", "?"), -6: ("Kicking", "?"),
    -5: ("Agility", "ok"), -4: ("AerialGK", "?"), -3: ("Reflexes", "?"),
    -2: ("Communication", "?"), -1: ("Throwing", "?"),
}


def label(rel):
    """Self-documenting column header for a byte at offset (P+rel)."""
    if 0 <= rel <= 14:
        return f"{rel}|pos:{POSITIONS[rel]}"
    if rel in (15, 16):
        return f"{rel}|foot{'L' if rel == 15 else 'R'}"
    if rel in (17, 18):
        return f"{rel}|CA{'lo' if rel == 17 else 'hi'}"
    if rel in (19, 20):
        return f"{rel}|PA{'lo' if rel == 19 else 'hi'}"
    if rel in (21, 22):
        return f"{rel}|rep{'lo' if rel == 21 else 'hi'}"
    if -42 <= rel <= -39:
        return f"{rel}|SID"
    if -50 <= rel <= -43:
        return f"{rel}|?{PERSONALITY[rel + 50]}"       # maybe: personality block
    if rel in GUIDE_MAP:
        name, kind = GUIDE_MAP[rel]
        pfx = "" if kind == "ok" else ("=" if kind == "team" else "?")
        return f"{rel}|{pfx}{name}"
    return f"{rel}|?"


def rows(mm):
    squad = json.load(open("bucaspor_players.json"))
    out = []
    for tid_s, name in squad.items():
        tid = int(tid_s)
        snap = attr_record(mm, tid)
        rec = record_for(mm, tid)          # locates the 5 MB record + gives P
        info = parse_info(mm, tid)
        if not (snap and rec and info):
            continue
        P = rec["P"]
        disp = decode(snap["attrs"])
        snap_ca = int.from_bytes(mm[snap["M"] + 35:snap["M"] + 37], "little")
        snap_pa = int.from_bytes(mm[snap["M"] + 37:snap["M"] + 39], "little")
        top = max(snap["positions"], key=snap["positions"].get) if snap["positions"] else "?"
        age = 2022 - int(info["dob"][:4]) if info["dob"] else ""
        r = {"name": name, "tid": tid, "position": top, "age": age,
             "is_gk": int(snap["positions"].get("GK", 0) == 20),
             "snap_CA": snap_ca, "snap_PA": snap_pa,
             "rec_CA": rec["ca"], "rec_PA": rec["pa"],
             "foot_L": rec["feet"]["left"], "foot_R": rec["feet"]["right"]}
        for a in ATTR_ORDER:
            r[f"attr:{a}"] = disp.get(a, "")
        for rel in REL:
            r[label(rel)] = mm[P + rel]
        out.append(r)
    return out


if __name__ == "__main__":
    s = Save()
    data = rows(s.mm)
    cols = (["name", "tid", "position", "age", "is_gk", "snap_CA", "snap_PA",
             "rec_CA", "rec_PA", "foot_L", "foot_R"]
            + [f"attr:{a}" for a in ATTR_ORDER]
            + [label(rel) for rel in REL])
    with open("calibration.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(data)
    print(f"{len(data)} players x {len(cols)} cols -> calibration.csv")
