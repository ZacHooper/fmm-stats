#!/usr/bin/env python3
"""
Reconstruct HOW a team was fielded in a given match.

The match record does NOT store an explicit per-player position or role/duty. What it
DOES store, and what we combine here:
  - the FORMATION string (e.g. "4-1-2-2-1")            -> season_extract.parse_formation
  - posOrder [block byte 41], the lineup slot 1..11    -> the stat blocks
  - each player's NATURAL positions (15 ratings)       -> league_attrs.record_for

posOrder maps onto the formation lines in order (slot 1 = GK, then each formation line
front-to-back). Within a line, players are placed left->right by the side of their
best-rated natural position. Validated vs ground_truth_match1: 10/11 exact (the 11th,
Sun, is naturally AML but was fielded AMR — an out-of-position call the record can't show).

ROLES/DUTIES are NOT recoverable from the match record — omitted by design, not missed.

Usage: python3 fielding.py <anchor|offset>    # reconstruct one match's XI
"""
from fmtool import Save
from season_extract import (match_anchors, extract_match, parse_formation)
from league_attrs import record_for

# side of a position: -1 left, 0 central, +1 right
_SIDE = {"L": -1, "R": +1, "C": 0}
# vertical depth rank of each position line (0 = own goal, higher = forward)
_DEPTH = {"GK": 0, "D": 1, "WB": 1.5, "DM": 2, "M": 3, "AM": 4, "S": 5, "ST": 5}


def _pos_side(pos):
    if pos.endswith("R"):
        return +1
    if pos.endswith("L"):
        return -1
    return 0


def best_position(rec):
    """Highest-rated natural position for a player record (dict pos->rating)."""
    if not rec or not rec.get("positions"):
        return None
    return max(rec["positions"].items(), key=lambda kv: kv[1])[0]


def parse_formation_lines(formation):
    """"4-1-2-2-1" -> [4,1,2,2,1]  (outfield lines, GK implicit)."""
    if not formation:
        return None
    try:
        return [int(x) for x in formation.split("-")]
    except ValueError:
        return None


def field_team(mm, team, formation, names=None):
    """Return the fielded XI: list of dicts {slot,tid,name,natural,line,x,y}.
    team = list of decoded blocks (a team's XI, already in posOrder). names = optional
    {tid:name}. Placement: line from formation+slot, x from natural-position side."""
    names = names or {}
    starters = sorted([b for b in team if b["posOrder"] <= 11],
                      key=lambda b: b["posOrder"])[:11]
    lines = parse_formation_lines(formation) or []
    # assign each slot (after GK) to a formation line
    # slot 1 = GK; slots 2.. fill lines in order
    line_of = {1: -1}  # -1 = GK line
    slot = 2
    for li, count in enumerate(lines):
        for _ in range(count):
            line_of[slot] = li
            slot += 1
    n_lines = len(lines)
    out = []
    # group players by line so we can place them left->right within the line
    by_line = {}
    for b in starters:
        rec = record_for(mm, b["tid_int"])
        nat = best_position(rec)
        li = line_of.get(b["posOrder"], None)
        by_line.setdefault(li, []).append((b, nat))
    for li, members in by_line.items():
        # sort within the line by natural side (L -> C -> R), tie-break posOrder
        members.sort(key=lambda m: (_pos_side(m[1] or "C"), m[0]["posOrder"]))
        n = len(members)
        for idx, (b, nat) in enumerate(members):
            if li == -1:            # GK
                x, y = 0.5, 0.06
            else:
                y = 0.18 + 0.78 * ((li + 1) / (n_lines + 1))
                x = (idx + 1) / (n + 1)
            out.append({"slot": b["posOrder"], "tid": b["tid_int"],
                        "name": names.get(b["tid_int"], str(b["tid_int"])),
                        "natural": nat, "line": li,
                        "rating": b["rating"], "goals": b["goals"],
                        "x": round(x, 3), "y": round(y, 3)})
    out.sort(key=lambda p: p["slot"])
    return out


def _load_names():
    import json
    import os
    names = {}
    p = "bucaspor_players.json"
    if os.path.exists(p):
        names = {int(k): v for k, v in json.load(open(p)).items()}
    return names


if __name__ == "__main__":
    import sys
    s = Save()
    mm = s.mm
    anchors = match_anchors(mm)
    target = int(sys.argv[1], 0) if len(sys.argv) > 1 else 56546300
    a = min(anchors, key=lambda x: abs(x - target))
    idx = anchors.index(a)
    nxt = anchors[idx + 1] if idx + 1 < len(anchors) else None
    m = extract_match(mm, a, nxt)
    formation = parse_formation(mm, a, nxt)
    names = _load_names()
    print(f"match anchor {a} (0x{a:x})  home {m['hdr']['home_tid']} v away "
          f"{m['hdr']['away_tid']}  formation (managed team) = {formation}\n")
    for label, team in [("HOME", m["home"]), ("AWAY", m["away"])]:
        xi = field_team(mm, team, formation, names)
        print(f"{label}:")
        for p in xi:
            print(f"  slot{p['slot']:>2} {p['natural'] or '?':>4}  "
                  f"rtg{p['rating']} {'G'*p['goals']:<3} {p['name']}")
        print()
