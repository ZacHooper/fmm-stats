#!/usr/bin/env python3
"""
Extract per-player attribute blocks for the managed squad (from squad snapshots).

STATUS: structure located & partially decoded; exact attribute LABELS still need one
in-game attribute screen to confirm (the byte order differs from the community guide).

Per-player record (anchored on the club marker `a7 19 ff ff` at offset M):
  attributes block : mm[M-59 : M-23]   (36 bytes; cols 0..35)
      - cols 0..23  : the 1-20 attributes (role-correlated; see below)
      - cols 24..35 : ability/reputation tail (col24~100, cols31-33 large, col34~64)
  positions block  : mm[M-23 : M-8]    (15 bytes: GK,SW,DL,DC,DR,DMC,ML,MC,MR,
                                         AML,AMC,AMR,ST,DML,DMR; 1-20, 20=natural)
  player TID       : mm[M-8 : M-4]

CONFIRMED so far (no screenshot needed):
  - GK attributes are cols 2,3,4,6 (high only for the keeper).
  - positions block decodes correctly (validated vs in-game roles).
Role hints (hypotheses, pending screenshot):
  - col 11 high for forwards  -> Finishing?
  - col 19 high for centre-back -> Tackling/Marking?
  - col 8/13 high for playmaker MC -> Passing/Technique/Creativity?
"""
import struct
from fmtool import Save
from squad import own_squad, SNAPSHOT_LO, SNAPSHOT_HI, CLUB_MARKER

POSITIONS = ["GK", "SW", "DL", "DC", "DR", "DMC", "ML", "MC", "MR",
             "AML", "AMC", "AMR", "ST", "DML", "DMR"]
GK_ATTR_COLS = [2, 3, 4, 6]

# Attribute byte -> label. The 24 attribute bytes start at M-59 (index 0 here).
# Calibrated vs Demir(GK), Duruk(RB) and Metin Yüksel(DMC) attribute screens.
ATTR_LABELS = {
    0: "Aerial",
    1: "Agility",          # GK screen; Ataş/Efe exact, Demir 9 vs shown 10 (minor)
    2: "Communication",    # raw; DISPLAY modified by leadership (Demir raw10 -> shown 13)
    3: "Handling",         # GK; idx3/idx6 = Handling/Reflexes, order per rough guide
    4: "Kicking",          # GK
    5: "Throwing",         # GK
    6: "Reflexes",         # GK; pair with idx3 (order per rough guide, flag if wrong)
    7: "Crossing",
    8: "Dribbling",
    9: "?hidden|Movement",   # Movement is idx9 or idx18 (both Duruk=7); unresolved
    10: "Passing",
    11: "Shooting",
    12: "Tackling",
    13: "Technique",
    14: "Aggression",
    15: "Creativity",
    16: "Decisions",
    17: "Leadership",
    18: "Movement",
    19: "Positioning",      # Duruk byte 13 vs shown 12 (minor +1)
    20: "Teamwork",
    21: "Pace",
    22: "Stamina",
    23: "Strength",
}
# Confirmed byte offsets, safe to read directly (validated vs 7+ players):
CONFIRMED = {0: "Aerial", 1: "Agility", 2: "Communication", 3: "Handling",
             4: "Kicking", 5: "Throwing", 6: "Reflexes", 7: "Crossing",
             8: "Dribbling", 10: "Passing", 11: "Shooting", 12: "Tackling",
             13: "Technique", 14: "Aggression", 15: "Creativity", 16: "Decisions",
             17: "Leadership", 18: "Movement", 19: "Positioning", 20: "Teamwork",
             21: "Pace", 22: "Stamina", 23: "Strength"}
DERIVED_RAW = {}
# CONFIRMED holds the raw stored bytes. A few in-game DISPLAYED values are modified:
#   - Communication (idx2) shown value is boosted by leadership (Demir raw10 -> 13).
#   - A captain's Leadership shows boosted (Demir raw9 -> 12).
#   - Minor ±1 drift where a stat changed between the save and a later screenshot.
# Handling/Reflexes (idx3/6) order is per the rough guide — flag if a keeper disproves.
# Only idx9 remains an unmapped (hidden) attribute in the 0-23 block.
# Still open: Handling vs Reflexes order (idx3/6, need Kıvanç Küçükkarış H12/R13).
# NOTE: attribute bytes reflect the SAVE moment; a stat can differ from a later
# screenshot (e.g. Behram pace raw 11 -> shown 10 after ageing). Parsing is correct.


def attr_record(mm, tid):
    """Return {'attrs': [36], 'positions': {pos:val for val>1}, 'M': offset} or None."""
    le = struct.pack("<I", tid)
    pos = SNAPSHOT_LO
    while True:
        i = mm.find(le, pos)
        if i == -1 or i > SNAPSHOT_HI:
            return None
        pos = i + 1
        if mm[i + 8:i + 12] == CLUB_MARKER:
            M = i + 8
            attrs = list(mm[M - 59:M - 23])
            posb = list(mm[M - 23:M - 8])
            positions = {POSITIONS[k]: v for k, v in enumerate(posb) if v > 1}
            # FEET (0-20) live AFTER the club marker: left @M+33, right @M+34.
            # Confirmed vs 10 players incl. an outfield left-footer (Alıç) and a
            # two-footer (Sun): left corr 0.92, right corr 0.97 with in-game foot
            # colours. Demir L20/R5 ("Left Only"), Alıç L20/R9 (Left), all
            # right-footers R20. (Not in the attribute block — hence long-hidden.)
            feet = (mm[M + 33], mm[M + 34])
            return {"attrs": attrs, "positions": positions,
                    "feet": feet, "M": M}


def preferred_foot(feet):
    """Map (left, right) foot ratings (0-20) to an FM-style label. Thresholds
    calibrated vs 10 players: weak foot <=7 -> "... only" (Demir R5, Turan/Efe
    L7); "Either" only when both strong and close (Sun 15/20 shows "Right")."""
    l, r = feet
    if l >= 16 and r >= 16 and abs(l - r) <= 3:
        return "Either"
    if l > r:
        return "Left only" if r <= 7 else "Left"
    if r > l:
        return "Right only" if l <= 7 else "Right"
    return "Either" if l >= 16 else "Right"


def decode(attrs):
    """Return {attribute: value}: confirmed attrs, plus raw (modifier-TODO) values."""
    out = {name: attrs[i] for i, name in CONFIRMED.items()}
    out.update({f"{name}_raw": attrs[i] for i, name in DERIVED_RAW.items()})
    return out


def build(mm):
    squad = own_squad(mm)
    out = {}
    for tid, name in squad.items():
        r = attr_record(mm, tid)
        if r:
            out[tid] = {"name": name, "positions": r["positions"],
                        "attributes": decode(r["attrs"]), "attrs_raw": r["attrs"],
                        "feet": {"left": r["feet"][0], "right": r["feet"][1],
                                 "preferred": preferred_foot(r["feet"])}}
    return out


if __name__ == "__main__":
    import json
    s = Save()
    data = build(s.mm)
    json.dump({str(k): v for k, v in data.items()},
              open("attrs_raw.json", "w"), ensure_ascii=False, indent=1)
    print(f"{len(data)} players -> attrs_raw.json (confirmed attributes decoded)\n")
    for tid, d in list(data.items())[:8]:
        best = ",".join(f"{p}{v}" for p, v in sorted(d["positions"].items(),
                                                     key=lambda x: -x[1])[:3])
        a = d["attributes"]
        print(f"  {d['name']:20} [{best}]  Tec{a['Technique']} Pas{a['Passing']} "
              f"Fin{a['Shooting']} Tck{a['Tackling']} Pac{a['Pace']} Dec{a['Decisions']}")
