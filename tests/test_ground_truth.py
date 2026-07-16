#!/usr/bin/env python3
"""
Ground-truth regression guard for the 2021-22 Bucaspor career. Asserts the
known-correct values still parse, so a refactor — or a save that shifts every offset —
fails loudly instead of silently. (Player values develop season-to-season, so this is
specific to a 21-22 save; a later-season save legitimately differs.)

Requires a 21-22 save (gitignored). Pass one, else the first known name is used:
    python3 tests/test_ground_truth.py [path/to/21-22-save.fms]
Skips cleanly if none is found.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser.save import Save                        # noqa: E402
from fmparser import matches as M                     # noqa: E402
from fmparser import attributes as A                  # noqa: E402

# 21-22 saves to try, in order, if none is passed on the command line
CANDIDATES = ["21-22-end.fms", "21-22-mid.fms", "fm_save1.fms"]

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


def run(save_path=None):
    if save_path is None:
        save_path = next((os.path.join(ROOT, c) for c in CANDIDATES
                          if os.path.exists(os.path.join(ROOT, c))), None)
    if not save_path or not os.path.exists(save_path):
        print("SKIP: no 21-22 save found (tried: " + ", ".join(CANDIDATES) + ")")
        return 0
    s = Save(save_path)
    fails = []
    print(f"(using {os.path.basename(save_path)})")

    season = M.extract_season(s.mm)
    # match COUNT varies by season and how far in the save is, so we don't assert it —
    # finding the specific 3-3 fixture below is what proves match parsing works.
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
    print(f"PASS: 3-3 fixture team stats + formation ({len(season)} matches parsed), "
          f"opponents {1 - off_total/total:.0%} within +/-1")
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1] if len(sys.argv) > 1 else None))
