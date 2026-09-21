#!/usr/bin/env python3
"""Build `lab.json` — the data behind the Attribute Lab dashboard.

The Lab is an explorable version of what
[`attribute-stat-correlations`](../docs/agent-context/attribute-stat-correlations.md) reports
as a static table: which attributes drive which match statistics, plus a workbench for
rewriting a role's attribute weights and seeing our squad re-rank underneath.

    uv run python scripts/export_attribute_lab.py                    # -> site-data/lab.json
    uv run python scripts/export_attribute_lab.py --out /tmp/lab.json

Everything statistical is delegated to `attribute_stat_correlations.py` so the Lab and the CLI
can never disagree: this script only chooses the cuts, reshapes to JSON and adds the squad,
the stored weight-sets and the scoring set.

**Never commit the output** — it is derived, and it is written to `site-data/`, which is
gitignored alongside the published DuckDB objects.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import sys

import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)


def _load_asc():
    """Import the correlation tool as a module (its filename isn't importable as-is)."""
    path = os.path.join(REPO, "scripts", "attribute_stat_correlations.py")
    spec = importlib.util.spec_from_file_location("asc", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# The four cuts the manager asked for. The lower-division cut is deliberately absent — it did
# not earn its own column. "League" folds our own players in with the opponents to fill the
# sample out; checked before adopting, that moves no coefficient by more than 0.10.
#   id, label, who, competition, min_minutes
CUTS = [
    ("us_all",     "Us · all divisions", "us",        None,          450),
    ("us_sl",      "Us · Superliga",     "us",        "%Superliga%", 360),
    ("league_all", "League · all",       "both",      None,          180),
    ("league_sl",  "League · Superliga", "both",      "%Superliga%", 180),
    # opponents-only variants, behind the explorer's "exclude our own players" checkbox
    ("opp_all",    "Opponents · all",       "opponents", None,          180),
    ("opp_sl",     "Opponents · Superliga", "opponents", "%Superliga%", 180),
]

UNITS = ["Defence", "Midfield", "Attack", "GK", "pooled"]

# Unit grouping averages away opposite effects. Pace against match rating reads +0.21 for the
# Attack unit while ST is +0.51 and AMC is -0.19; the Defence unit reads +0.06 because 112 of its
# 197 rows are centre-backs, hiding full-backs at +0.22/+0.26. So correlations are also emitted
# per exact POSITION, wherever that cut has the sample for it.
POSITIONS = ["GK", "DL", "DC", "DR", "DML", "DMC", "DMR", "ML", "MC", "MR",
             "AML", "AMC", "AMR", "ST"]

# Statistic groups, so the explorer's picker isn't a flat list of 21.
STAT_GROUPS = [
    ("Defending", [("intercept_90", "Interceptions"), ("tackW_90", "Tackles won"),
                   ("tackA_90", "Tackles attempted"), ("tack_pct", "Tackle success %")]),
    ("Aerial",    [("headW_90", "Headers won"), ("headA_90", "Headers contested"),
                   ("head_pct", "Header win %")]),
    ("Passing",   [("passA_90", "Passes attempted"), ("passC_90", "Passes completed"),
                   ("pass_pct", "Pass completion %")]),
    ("Creating",  [("keyPass_90", "Key passes"), ("assists_90", "Assists"),
                   ("dribbles_90", "Dribbles"), ("crossA_90", "Crosses attempted"),
                   ("crossC_90", "Crosses completed"), ("cross_pct", "Cross completion %")]),
    ("Shooting",  [("shotA_90", "Shots"), ("shotO_90", "Shots on target"),
                   ("sot_pct", "On-target %"), ("goals_90", "Goals")]),
    ("Other",     [("mistakes_90", "Mistakes"), ("rating", "Match rating")]),
]
STATS = [s for _, group in STAT_GROUPS for s in group]

# The outcomes a role can be built for. Each maps to the statistics that define it, and the
# workbench derives weights from their measured correlations.
OUTCOMES = [
    ("win_it_back", "Win it back",  ["intercept_90", "tackW_90"]),
    ("keep_it",     "Keep it",      ["pass_pct"]),
    ("progress_it", "Progress it",  ["dribbles_90", "keyPass_90"]),
    ("create",      "Create",       ["keyPass_90", "assists_90"]),
    ("finish",      "Finish",       ["shotO_90", "goals_90"]),
    ("win_the_air", "Win the air",  ["headW_90"]),
]


def _clean(x):
    """JSON has no NaN; the page branches on null."""
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else x


def build_frame(asc, db, who, competition, min_minutes):
    """One cut's player-seasons. `who='both'` concatenates ours and the opponents'."""
    if who != "both":
        return asc.build(db, min_minutes, competition, who)
    ours, attrs = asc.build(db, min_minutes, competition, "us")
    opp, _ = asc.build(db, min_minutes, competition, "opponents")
    return pd.concat([ours, opp], ignore_index=True), attrs


def correlations(asc, frame, attrs, stat, with_positions=True):
    """{unit: {attr: r}} — inside each unit, plus a unit-demeaned pooled column.

    Delegates every cell to `asc.cell`, so the Lab suppresses exactly what the CLI suppresses:
    an attribute with no spread in that unit, an outcome with no spread at all, or too few rows.
    """
    out = {}
    for unit in ["Defence", "Midfield", "Attack", "GK"]:
        sub = frame[frame.grp == unit].dropna(subset=[stat])
        out[unit] = {a: _clean(_r3(asc.cell(sub, stat, a))) for a in attrs}
    if with_positions:                                 # only where the sample supports it
        for pos in POSITIONS:
            sub = frame[frame.position == pos].dropna(subset=[stat])
            if len(sub) < asc.MIN_N:
                continue
            out["@" + pos] = {a: _clean(_r3(asc.cell(sub, stat, a))) for a in attrs}
    z = frame.dropna(subset=[stat]).copy()
    for c in [stat] + attrs:                           # demean inside unit, then pool
        z[c] = z.groupby("grp")[c].transform(lambda v: v - v.mean())
    pooled = {}
    for a in attrs:                                    # pool only where the attribute varies
        keep = [g for g, sub in frame.groupby("grp")
                if len(sub.dropna(subset=[stat])) >= asc.MIN_N and (sub[a].std() or 0) >= asc.MIN_SD]
        pooled[a] = _clean(_r3(asc.cell(z[z.grp.isin(keep)], stat, a))) if keep else None
    out["pooled"] = pooled
    return out


def spreads(asc, frame, attrs):
    """{group: {attr: sd}} for the attributes that FAILED the spread test.

    The page reads this only to explain a blank cell, so carrying the passing values would
    triple the payload for nothing. An attribute absent from a group's map cleared the bar.
    """
    def low(sub):
        if len(sub) < 2:
            return {}
        return {a: _r3(sub[a].std()) for a in attrs
                if (sub[a].std() or 0) < asc.MIN_SD}
    out = {}
    for unit in ["Defence", "Midfield", "Attack", "GK"]:
        out[unit] = low(frame[frame.grp == unit])
    for pos in POSITIONS:
        sub = frame[frame.position == pos]
        if len(sub) >= asc.MIN_N:
            out["@" + pos] = low(sub)
    return out


def _r3(x):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(x, 2)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--career", default=os.environ.get("FM_CAREER", "frem"))
    p.add_argument("--db", help="path to the store (default: db.py's resolved path)")
    p.add_argument("--out", default=os.path.join(REPO, "site-data", "lab.json"))
    a = p.parse_args()

    os.environ["FM_CAREER"] = a.career
    if a.db:
        os.environ["FM_DUCKDB"] = a.db
    os.environ.setdefault("FM_DUCKDB_READONLY", "1")

    from dashboard import db
    from fmparser.model import ATTR_ORDER
    from fmparser.mart import GK_ONLY_ATTRS

    asc = _load_asc()
    season, phase = db.latest_snapshot()

    # ---- correlations, one block per cut -----------------------------------------------
    cuts, corr, spread = [], {}, {}
    for cid, label, who, comp, mins in CUTS:
        frame, attrs = build_frame(asc, db, who, comp, mins)
        cuts.append({"id": cid, "label": label, "who": who, "min_minutes": mins,
                     "competition": comp or "all",
                     "n": len(frame),
                     "n_by_unit": {u: int((frame.grp == u).sum())
                                   for u in ["Defence", "Midfield", "Attack", "GK"]},
                     "n_by_pos": {p: int(n) for p, n in frame.position.value_counts().items()
                                  if n >= asc.MIN_N}})
        # The opponents-only variants exist to back one checkbox; they do not need the
        # position breakdown as well, and skipping it keeps the payload sane.
        wp = not cid.startswith("opp_")
        corr[cid] = {s: correlations(asc, frame, attrs, s, wp)
                     for s, _ in STATS if s in frame.columns}
        spread[cid] = spreads(asc, frame, attrs)
        print(f"  {label:24s} n={len(frame):<4} {cuts[-1]['n_by_unit']}")

    # ---- our current squad --------------------------------------------------------------
    squad = db.q(f"""
        SELECT s.tid, s.name, p.age
        FROM mart.squad_current s
        LEFT JOIN mart.player_snapshots p
               ON p.tid = s.tid AND p.season = {season} AND p.phase = '{phase}'
        ORDER BY s.name""")
    snap = db.q(f"""SELECT * FROM mart.player_snapshots
                    WHERE season = {season} AND phase = '{phase}'""").set_index("tid")
    # every position a player can fill, with its familiarity — eff is per POSITION, not per role
    pos = db.q(f"""SELECT tid, "position", familiarity FROM mart.player_position_levels
                   WHERE season = {season} AND phase = '{phase}'""")
    by_tid = {t: g[["position", "familiarity"]].values.tolist()
              for t, g in pos.groupby("tid")}

    players = []
    for r in squad.itertuples():
        if r.tid not in snap.index:
            continue
        row = snap.loc[r.tid]
        players.append({
            "tid": int(r.tid), "name": r.name,
            "age": None if pd.isna(r.age) else int(r.age),
            "attrs": [int(row[x]) for x in ATTR_ORDER],           # POSITIONAL — order matters
            "positions": [[q, int(f)] for q, f in by_tid.get(r.tid, [])],
        })

    # ---- stored weight-sets, position map, familiarity curve ---------------------------
    W = db.q("SELECT method, role, attribute, weight FROM mart.role_weights")
    methods = {}
    for r in W.itertuples():
        methods.setdefault(r.method, {}).setdefault(r.role, {})[r.attribute] = int(r.weight)
    cfg = dict(db.q("SELECT key, value FROM staging.app_config").values)
    fam = {"curve": cfg.get("familiarity_curve", "linear_floor"),
           "floor": float(cfg.get("familiarity_floor", 0.5))}
    pos_role = dict(db.q('SELECT "position", role FROM mart.position_roles').values)

    # ---- the scoring set: does a weight-set predict real output? -----------------------
    # asc.build only carries the 17 attributes it correlates; the rating needs all 23, so the
    # full attribute row is joined back on from that season's latest snapshot.
    score_frame, _ = asc.build(db, 450, None, "us")
    score_raw = db.q("""SELECT person_id, season, SUM(minutes) mins,
                               SUM(goals) g, SUM(assists) ast
                        FROM mart.match_player_facts
                        WHERE team_tid IN (SELECT club_tid FROM mart.managed_club)
                          AND is_competitive AND minutes > 0
                        GROUP BY person_id, season""")
    full = db.q("SELECT * FROM mart.player_snapshots")
    full["_k"] = full.phase.map(db.phase_key)          # phase is a DATE, never sort it as text
    full = full.sort_values("_k").groupby(["person_id", "season"], as_index=False).last()

    sf = (score_frame[["person_id", "season", "position", "rating"]]
          .merge(score_raw.drop(columns=[]), on=["person_id", "season"])
          .merge(full[["person_id", "season"] + ATTR_ORDER], on=["person_id", "season"]))
    sf = sf[sf.position.map(pos_role).notna()].copy()
    sf["role"] = sf.position.map(pos_role)
    sf = sf[sf.role != "GK"]
    score_set = [{"role": r.role,
                  "attrs": [int(getattr(r, x)) for x in ATTR_ORDER],
                  "rating": _clean(round(float(r.rating), 3)),
                  "ga90": _clean(round(90 * (r.g + r.ast) / r.mins, 4))}
                 for r in sf.itertuples()]

    out = {
        "generated": pd.Timestamp.now("UTC").strftime("%Y-%m-%d"),
        "career": a.career, "season": int(season), "phase": phase,
        "attrs": ATTR_ORDER, "gk_only": GK_ONLY_ATTRS,
        "statGroups": [{"group": g, "stats": [{"id": i, "label": l} for i, l in ss]}
                       for g, ss in STAT_GROUPS],
        "outcomes": [{"id": i, "label": l, "stats": ss} for i, l, ss in OUTCOMES],
        "units": UNITS, "positions": POSITIONS,
        "cuts": cuts, "corr": corr, "spread": spread,
        "minSd": asc.MIN_SD, "minN": asc.MIN_N,
        "methods": methods, "posRole": pos_role, "fam": fam,
        "rolePositions": {r: sorted(p for p, rr in pos_role.items() if rr == r)
                          for r in sorted(set(pos_role.values()))},
        "squad": players, "scoreSet": score_set,
    }

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as fh:
        json.dump(out, fh, separators=(",", ":"))
    kb = os.path.getsize(a.out) / 1024
    print(f"\nwrote {a.out}  ({kb:.0f} KB)")
    print(f"  {len(players)} squad players · {len(score_set)} scoring rows · "
          f"{len(methods)} methods · {len(cuts)} cuts")
    if kb > 700:
        print("  ⚠️  larger than expected — check for an unfiltered join")
    # ~450 KB is normal now that positions are emitted alongside units.


if __name__ == "__main__":
    main()
