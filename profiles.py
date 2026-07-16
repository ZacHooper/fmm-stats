#!/usr/bin/env python3
"""
Unified player profiles for the managed squad — joins the four structures we cracked:
  - name        (squad.py, from squad snapshots)
  - info/Step 2 (info.py: DOB, nationality, club TID, SID)
  - attributes  (attrs.py: confirmed 1-20 attributes + positions)
  - match stats (season_data.json: aggregated per player across the season)

Join keys: TID (present in every structure). SID additionally links info <-> match
blocks (they carry the same SID), confirming the join.
"""
import json
from fmtool import Save
from info import parse_info
from attrs import attr_record, decode, POSITIONS


def season_aggregate():
    """Per-TID totals across all matches in season_data.json."""
    season = json.load(open("season_data.json"))
    agg = {}
    for m in season:
        for b in m["home_xi"] + m["away_xi"]:
            t = b["tid_int"]
            a = agg.setdefault(t, {"apps": 0, "goals": 0, "assists": 0,
                                   "rating_sum": 0, "rating_n": 0})
            # count an appearance if they were on the pitch (played minutes)
            played = b["posOrder"] <= 11 or b["subOn"] != 255
            if played:
                a["apps"] += 1
                a["goals"] += b["goals"]
                a["assists"] += b["assists"]
                a["rating_sum"] += b["rating"]
                a["rating_n"] += 1
    for a in agg.values():
        a["avg_rating"] = round(a["rating_sum"] / a["rating_n"], 2) if a["rating_n"] else None
        del a["rating_sum"], a["rating_n"]
    return agg


def build(mm):
    squad = json.load(open("bucaspor_players.json"))   # {tid: name}
    agg = season_aggregate()
    out = {}
    for tid_s, name in squad.items():
        tid = int(tid_s)
        info = parse_info(mm, tid) or {}
        rec = attr_record(mm, tid)
        positions = rec["positions"] if rec else {}
        attributes = decode(rec["attrs"]) if rec else {}
        out[tid_s] = {
            "name": name,
            "dob": info.get("dob"),
            "nationality": info.get("nationality"),
            "club_tid": info.get("club_tid"),
            "sid": info.get("sid"),
            "positions": positions,
            "attributes": attributes,
            "season": agg.get(tid, {"apps": 0, "goals": 0, "assists": 0, "avg_rating": None}),
        }
    return out


if __name__ == "__main__":
    s = Save()
    profiles = build(s.mm)
    json.dump(profiles, open("player_profiles.json", "w"), ensure_ascii=False, indent=1)
    print(f"{len(profiles)} unified profiles -> player_profiles.json\n")
    rows = sorted(profiles.values(), key=lambda p: -p["season"]["goals"])
    print(f"{'player':20} {'pos':6} {'DOB':>11} {'app':>3} {'G':>3} {'A':>3} {'rtg':>4} "
          f"{'Fin':>3} {'Pac':>3} {'Tck':>3}")
    for p in rows[:12]:
        pos = max(p["positions"], key=p["positions"].get) if p["positions"] else "?"
        a = p["attributes"]; ss = p["season"]
        print(f"{p['name']:20} {pos:6} {str(p['dob']):>11} {ss['apps']:>3} {ss['goals']:>3} "
              f"{ss['assists']:>3} {str(ss['avg_rating']):>4} "
              f"{a.get('Shooting','-'):>3} {a.get('Pace','-'):>3} {a.get('Tackling','-'):>3}")
