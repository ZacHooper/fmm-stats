#!/usr/bin/env python3
"""Assert the Attribute Lab's rating arithmetic matches the store's.

CLAUDE.md requires the rating formula to stay identical everywhere it is implemented — the SQL
(`mart.player_role_ratings` / `mart.player_position_fit`), the site's JS (`site/js/data.js`)
and now the Attribute Lab dashboard. That equality was asserted in `docs/TODO.md` on the
strength of a scratchpad check that was never committed, so nothing has been guarding it.

This recomputes `base_rating` and `eff` from `lab.json` exactly as the dashboard does —

    base = SUM over the 23 attributes of value x (weight[role][attr.lower()] or 1)
    eff  = base x (floor + (1 - floor) x clamp(fam, 1, 20) / 20)      # linear_floor curve

— and compares every (player, method, position) against `mart.player_position_fit`.

    uv run python scripts/export_attribute_lab.py --out /tmp/lab.json
    uv run python scripts/check_rating_parity.py /tmp/lab.json

Exit code 1 on any mismatch, so it can gate a publish.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)


def fam_mult(fam, curve, floor):
    """Mirror of famMult in site/js/data.js — the clamp included."""
    f = max(1, min(20, fam or 0))
    if curve == "proportional":
        return f / 20
    if curve == "tiers":
        return 1.0 if f >= 18 else 0.95 if f >= 15 else 0.85 if f >= 10 else 0.7 if f >= 5 else 0.5
    return floor + (1 - floor) * (f / 20)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("lab", help="path to lab.json")
    p.add_argument("--db")
    p.add_argument("--career", default=os.environ.get("FM_CAREER", "frem"))
    p.add_argument("--tol", type=float, default=1e-6)
    a = p.parse_args()

    os.environ["FM_CAREER"] = a.career
    if a.db:
        os.environ["FM_DUCKDB"] = a.db
    os.environ.setdefault("FM_DUCKDB_READONLY", "1")
    from dashboard import db

    lab = json.load(open(a.lab))
    attrs, methods, pos_role = lab["attrs"], lab["methods"], lab["posRole"]
    curve, floor = lab["fam"]["curve"], lab["fam"]["floor"]
    season, phase = lab["season"], lab["phase"]

    tids = [p["tid"] for p in lab["squad"]]
    truth = db.q(f"""SELECT tid, method, "position", familiarity, base_rating, eff
                     FROM mart.player_position_fit
                     WHERE season = {season} AND phase = '{phase}'
                       AND tid IN ({','.join(str(t) for t in tids)})""")
    key = {(int(r.tid), r.method, r.position): (float(r.base_rating), float(r.eff))
           for r in truth.itertuples()}

    checked = bad = missing = 0
    problems = []
    for pl in lab["squad"]:
        vals = dict(zip(attrs, pl["attrs"]))
        for pos, fam in pl["positions"]:
            role = pos_role.get(pos)
            if role is None:
                continue
            for method, roles in methods.items():
                w = roles.get(role, {})
                base = sum(v * w.get(k.lower(), 1) for k, v in vals.items())
                eff = base * fam_mult(fam, curve, floor)
                want = key.get((pl["tid"], method, pos))
                if want is None:
                    missing += 1
                    continue
                checked += 1
                if abs(base - want[0]) > a.tol or abs(eff - want[1]) > a.tol:
                    bad += 1
                    if len(problems) < 10:
                        problems.append(f"  {pl['name']:24s} {pos:>3} {method:22s} "
                                        f"base {base:.3f} vs {want[0]:.3f} · "
                                        f"eff {eff:.3f} vs {want[1]:.3f}")

    print(f"checked {checked} (player, method, position) combinations "
          f"across {len(lab['squad'])} players and {len(methods)} methods")
    if missing:
        print(f"  note: {missing} combinations absent from mart.player_position_fit (skipped)")
    if bad:
        print(f"\nFAIL — {bad} mismatch(es):")
        print("\n".join(problems))
        sys.exit(1)
    print("PASS — the Lab's arithmetic is identical to the store's")


if __name__ == "__main__":
    main()
