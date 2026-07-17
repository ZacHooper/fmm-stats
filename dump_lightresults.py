#!/usr/bin/env python3
"""
Extract the light results (simulated non-managed games) to a local bundle.

    python3 dump_lightresults.py path/to/save.fms [--label 2022-end] [--out output]

Writes output/<label>/light_results/:
    results.csv      every deduped fixture: home, away, score, competition cid + name
    leagues.json     {cid: name, type, nation, members[...], fixtures} for every competition
    club_league.json {club_tid: {league_cid, league_name}} — club -> league for the whole DB
    standings/<cid>.csv  computed league table per league-type competition (approximate;
                         partial coverage — see fmparser/lightresults.py)

The comp CID is read straight from each record (offset +10); membership and league
assignment need no clustering. Names come from reference.comp_detail (imperfect for some
reserve/foreign comps; the cid grouping is always reliable).
"""
import argparse
import csv
import json
import os

from fmparser.save import Save
from fmparser import staging as S
from fmparser import lightresults as L
from fmparser import reference as R
from fmparser import matches as M
import extract


def main():
    ap = argparse.ArgumentParser(description="Dump light results (whole-DB simulated games).")
    ap.add_argument("save", help="path to the .fms save file")
    ap.add_argument("--label", help="output label (default: auto <year>-<period>)")
    ap.add_argument("--out", default="output", help="output root (default: output/)")
    args = ap.parse_args()

    s = Save(args.save)
    mm = s.mm
    label = args.label or extract.auto_label(M.extract_season(mm))[0]
    dest = os.path.join(args.out, label, "light_results")
    os.makedirs(os.path.join(dest, "standings"), exist_ok=True)

    info = S.scrape_players(mm)
    valid = {p["club_tid"] for p in info.values() if p["club_tid"] != S.NO_CLUB}
    club_nation = L.club_nations(info, S.NO_CLUB)
    data = L.build(mm, valid, club_nation=club_nation)
    records, lgs, club_league = data["records"], data["leagues"], data["club_league"]

    cname = {}
    def club_name(t):
        if t not in cname:
            cname[t] = R.resolve_club(mm, t, "long") or f"#{t}"
        return cname[t]

    # results.csv
    with open(os.path.join(dest, "results.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["home_tid", "home", "away_tid", "away", "scoreH", "scoreA",
                    "cid", "competition", "copies"])
        for r in sorted(records, key=lambda r: (r["cid"], r["home"])):
            comp = lgs[r["cid"]]["name"] or ""
            w.writerow([r["home"], club_name(r["home"]), r["away"], club_name(r["away"]),
                        r["scoreH"], r["scoreA"], r["cid"], comp, r["copies"]])

    # leagues.json (sorted by member count)
    lg_out = {str(cid): v for cid, v in sorted(lgs.items(), key=lambda kv: -kv[1]["member_count"])}
    with open(os.path.join(dest, "leagues.json"), "w") as f:
        json.dump(lg_out, f, ensure_ascii=False, indent=1)

    # club_league.json
    cl_out = {str(t): {"league_cid": cid, "league_name": (lgs.get(cid) or {}).get("name")}
              for t, cid in sorted(club_league.items())}
    with open(os.path.join(dest, "club_league.json"), "w") as f:
        json.dump(cl_out, f, ensure_ascii=False, indent=1)

    # standings per league-type competition
    n_tables = 0
    for cid, v in lgs.items():
        if not L._is_league(mm, cid) or v["member_count"] < 6:
            continue
        members = set(v["members"])
        table = L.league_table(mm, records, cid, members=members)
        with open(os.path.join(dest, "standings", f"{cid}.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["pos", "club_tid", "club", "played", "won", "drawn", "lost",
                        "gf", "ga", "gd", "points"])
            for i, row in enumerate(table, 1):
                w.writerow([i, row["club"], club_name(row["club"]), row["played"],
                            row["won"], row["drawn"], row["lost"], row["gf"], row["ga"],
                            row["gd"], row["points"]])
        n_tables += 1

    named = sum(1 for v in lgs.values() if v["name"])
    print(f"light results -> {dest}/")
    print(f"  {len(records)} fixtures  {len(lgs)} competitions ({named} named)  "
          f"{len(club_league)} clubs -> league  {n_tables} standings tables")
    s.close()


if __name__ == "__main__":
    main()
