#!/usr/bin/env python3
"""
Extract the current state of an FMM22 save into a labelled output bundle.

    python3 extract.py path/to/save.fms [--label 2022-end] [--out output]

Writes output/<label>/:
    matches.json   full season: per-player stats, events, team stats, formation
    players.json   every league player: 23 attributes (exact + estimated), CA/PA, ...
    players.csv    the same, wide format, sorted by CA
    clubs.json     club TID -> name
    summary.json   counts, date range, and how the label was derived

The label defaults to <season-end-year>-<period>, derived from the save's latest
match date (period: Aug-Sep=start, Oct-Feb=mid, Mar-Jul=end). Override with --label.
"""
import argparse
import csv
import json
import os

from fmparser.save import Save
from fmparser import matches as M
from fmparser import attributes as A
from fmparser import reference as R


def _period(month):
    if month in (8, 9):
        return "start"
    if month in (10, 11, 12, 1, 2):
        return "mid"
    return "end"          # Mar-Jul


def auto_label(season):
    """<season-end-year>-<period> from the latest match date."""
    dates = sorted(m["date"] for m in season if m["date"])
    if not dates:
        return "unknown", None
    latest = dates[-1]
    year, month = int(latest[:4]), int(latest[5:7])
    end_year = year + 1 if month >= 8 else year
    return f"{end_year}-{_period(month)}", latest


def build_players(mm, season):
    """League-wide player rows (attributes + identity + club).

    Normally the player set is everyone who appeared in the first team's matches.
    For a fresh season with no matches played, fall back to the managed squad so a
    start-of-season save still yields your team + attributes."""
    from fmparser.regions import MANAGED_CLUB_TID
    bounds = A.snapshot_bounds(mm)
    names = A.own_squad(mm, *bounds)
    # exact attributes for our own squad (from the snapshot) — no estimation needed
    exact = {}
    for tid in names:
        r = A.attr_record(mm, tid, bounds=bounds)
        if r:
            exact[tid] = {"attrs": A.decode(r["attrs"]),
                          "feet": {"left": r["feet"][0], "right": r["feet"][1]}}

    # which club each player last appeared for
    tid_club = {}
    for m in season:
        for side, ct in (("home_xi", m["home_tid"]), ("away_xi", m["away_tid"])):
            for p in m[side]:
                tid_club.setdefault(p["tid_int"], ct)

    tids = A.league_tids(season)
    if not tids:                       # no matches yet -> managed squad only
        tids = sorted(names)
        for t in tids:
            tid_club.setdefault(t, MANAGED_CLUB_TID)

    club_tids = sorted(set(tid_club.values()))
    club_names = {t: R.resolve_club(mm, t, "long") or str(t) for t in club_tids}

    players = {}
    for tid in tids:
        rec = A.record_for(mm, tid)
        if not rec:
            continue
        is_gk = int(rec["positions"].get("GK", 0) == 20)
        ct = tid_club.get(tid)
        if tid in exact:               # own squad: exact snapshot attributes
            attributes = {a: exact[tid]["attrs"][a] for a in A.ATTR_ORDER}
            estimated = {a: False for a in A.ATTR_ORDER}
            feet = exact[tid]["feet"]
        else:                          # opponents: estimated (+/-1)
            est, _, _ = A.estimate_player(mm, rec)
            attributes = {a: est[a]["val"] for a in A.ATTR_ORDER}
            estimated = {a: est[a]["est"] for a in A.ATTR_ORDER}
            feet = rec["feet"]
        players[str(tid)] = {
            "tid": tid, "name": names.get(tid, f"#{tid}"),
            "club": club_names.get(ct, str(ct)) if ct else "?",
            "is_gk": is_gk, "ca": rec["ca"], "pa": rec["pa"],
            "reputation": rec["reputation"], "positions": rec["positions"],
            "feet": feet,
            "attributes": attributes, "estimated": estimated,
        }
    return players, club_names


def write_csv(path, players):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tid", "name", "club", "GK", "CA", "PA", "rep", "positions"]
                   + A.ATTR_ORDER)
        for p in sorted(players.values(), key=lambda x: (-x["ca"], x["name"])):
            pos = "/".join(k for k, v in sorted(p["positions"].items(),
                                                key=lambda kv: -kv[1]))
            w.writerow([p["tid"], p["name"], p["club"], "Y" if p["is_gk"] else "",
                        p["ca"], p["pa"], p["reputation"], pos]
                       + [p["attributes"][a] for a in A.ATTR_ORDER])


def main():
    ap = argparse.ArgumentParser(description="Extract an FMM22 save's current state.")
    ap.add_argument("save", help="path to the .fms save file")
    ap.add_argument("--label", help="output label (default: auto <year>-<period>)")
    ap.add_argument("--out", default="output", help="output root (default: output/)")
    args = ap.parse_args()

    s = Save(args.save)
    season = M.extract_season(s.mm)
    auto, latest = auto_label(season)
    label = args.label or auto
    dest = os.path.join(args.out, label)
    os.makedirs(dest, exist_ok=True)

    players, club_names = build_players(s.mm, season)

    def dump(name, obj):
        with open(os.path.join(dest, name), "w", newline="") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)

    dump("matches.json", season)
    dump("players.json", players)
    dump("clubs.json", {str(t): n for t, n in sorted(club_names.items())})
    write_csv(os.path.join(dest, "players.csv"), players)

    dates = sorted(m["date"] for m in season if m["date"])
    from collections import Counter
    by_comp = Counter(m.get("competition") for m in season)
    summary = {
        "competitions": dict(by_comp),
        "label": label, "label_auto": auto, "label_source": "argument" if args.label else "auto",
        "save": os.path.abspath(args.save),
        "latest_match": latest, "date_range": [dates[0], dates[-1]] if dates else None,
        "counts": {"matches": len(season), "players": len(players),
                   "clubs": len(club_names)},
    }
    dump("summary.json", summary)

    print(f"extracted -> {dest}/")
    print(f"  matches {len(season)}  players {len(players)}  clubs {len(club_names)}")
    print(f"  label {label} (auto {auto}, latest match {latest})")
    s.close()


if __name__ == "__main__":
    main()
