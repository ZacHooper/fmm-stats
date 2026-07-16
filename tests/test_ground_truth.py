#!/usr/bin/env python3
"""
Ground-truth regression guard. Asserts the known-correct values still parse, so a
refactor — or a new save that shifts every offset — fails loudly instead of silently.

Requires the save file (gitignored). Run:  python3 tests/test_ground_truth.py
Skips cleanly if the save is absent.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser.save import Save, DEFAULT_SAVE          # noqa: E402
from fmparser import matches as M                     # noqa: E402
from fmparser import attributes as A                  # noqa: E402

# --- ground truth (Karacabey 3-3 Bucaspor, 30 Apr 2022, + two scouted opponents) ---
MATCH = {"home_tid": 6353, "away_tid": 6567}
TEAM_STATS = {
    "home": {"shots": 11, "shots_on_target": 5, "rating": 6.6},
    "away": {"shots": 8, "shots_on_target": 4, "rating": 6.7},
}
FORMATION = "4-1-2-2-1"
# opponent attribute ground truth: exact where the model reads a raw byte, +/-1 elsewhere
PAZARLI = (21365, 85, 105, {"Aerial": 12, "Crossing": 4, "Dribbling": 4, "Passing": 5,
    "Shooting": 4, "Tackling": 12, "Technique": 7, "Aggression": 17, "Creativity": 5,
    "Decisions": 12, "Leadership": 12, "Movement": 10, "Positioning": 13,
    "Teamwork": 12, "Pace": 11, "Stamina": 10, "Strength": 12})
AKYUZ = (21124, 90, 110, {"Aerial": 11, "Agility": 12, "Handling": 12, "Kicking": 11,
    "Reflexes": 13, "Throwing": 10, "Aggression": 15, "Creativity": 4, "Decisions": 9,
    "Leadership": 12, "Positioning": 14, "Teamwork": 9, "Pace": 7, "Stamina": 10,
    "Strength": 14, "Technique": 8})   # Communication omitted (known leadership-boost gap)


def _check(cond, msg, fails):
    if not cond:
        fails.append(msg)


def run(save_path=DEFAULT_SAVE):
    if not os.path.exists(save_path):
        print(f"SKIP: save not found at {save_path}")
        return 0
    s = Save(save_path)
    fails = []

    season = M.extract_season(s.mm)
    _check(len(season) == 74, f"expected 74 matches, got {len(season)}", fails)

    match = next((m for m in season if m["home_tid"] == MATCH["home_tid"]
                  and m["away_tid"] == MATCH["away_tid"]), None)
    _check(match is not None, "3-3 match not found", fails)
    if match:
        _check(match["score"] == {"home": 3, "away": 3},
               f"score wrong: {match['score']}", fails)
        _check(match["formation"] == FORMATION,
               f"formation wrong: {match['formation']}", fails)
        for side, exp in TEAM_STATS.items():
            ts = match["team_stats"][side]
            for k, v in exp.items():
                _check(ts[k] == v, f"{side} {k}: {ts[k]} != {v}", fails)

    total, off_total = 0, 0
    for tid, ca, pa, gt in (PAZARLI, AKYUZ):
        rec = A.record_for(s.mm, tid)
        _check(rec is not None, f"record for {tid} not found", fails)
        if not rec:
            continue
        _check(rec["ca"] == ca, f"{tid} CA {rec['ca']} != {ca}", fails)
        _check(rec["pa"] == pa, f"{tid} PA {rec['pa']} != {pa}", fails)
        attrs, _, _ = A.estimate_player(s.mm, rec)
        total += len(gt)
        off_total += sum(1 for k, v in gt.items() if abs(attrs[k]["val"] - v) > 1)
    # documented held-out accuracy is ~93% within +/-1; guard the aggregate rate
    rate = 1 - off_total / total if total else 0
    _check(rate >= 0.90,
           f"within-+/-1 rate {rate:.0%} below 90% ({off_total}/{total} off)", fails)

    s.close()
    if fails:
        print("FAIL:")
        for f in fails:
            print("  -", f)
        return 1
    print(f"PASS: 74 matches, 3-3 team stats + formation, opponents "
          f"{1 - off_total/total:.0%} within +/-1")
    return 0


if __name__ == "__main__":
    sys.exit(run())
