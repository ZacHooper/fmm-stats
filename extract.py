#!/usr/bin/env python3
"""
Extract the current state of an FMM22 save into a labelled output bundle.

    python3 extract.py path/to/save.fms [--label 2022-end] [--out output]

Architecture: scrape each region of the save independently into keyed tables, then
join. The player INFO section is the identity spine (one row per player, ~31k, with
every foreign key); attributes join on SID, clubs on club_tid, names on TID. See
fmparser/staging.py.

Writes output/<label>/:
    players.json / players.csv   whole player DB: identity + attributes where they exist
    matches.json                 full season: per-player stats, events, team stats, formation
    player_match_stats.csv       flat one-row-per-(match, player), with the team played for
    transfers.json               players whose current club differs from a team they played for
    clubs.json                   club TID -> name
    summary.json                 counts, date range, how the label was derived

The label defaults to <season-end-year>-<period>, from the save's latest match date
(Aug-Sep=start, Oct-Feb=mid, Mar-Jul=end). Override with --label.
"""
import argparse
import csv
import json
import os
from collections import Counter

from fmparser.save import Save
from fmparser import matches as M
from fmparser import attributes as A
from fmparser import reference as R
from fmparser import staging as S
from fmparser import tagged as T
from fmparser import lightresults as L


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


_PHASES = ("start", "mid", "end")


def parse_label(label):
    """Inverse of auto_label: label string -> (season:int, phase:str).

    season is the end-year of the campaign (21/22 -> 2022), matching auto_label.
    Handles the current form '2022-end' and the legacy form '21-22-end'
    (where the second two-digit group is the end year). Raises ValueError on
    anything else so callers can fall back to summary.json or --season/--phase.
    """
    parts = label.split("-")
    if len(parts) < 2 or parts[-1] not in _PHASES:
        raise ValueError(f"unrecognised label {label!r}")
    phase = parts[-1]
    head = parts[:-1]
    if len(head) == 1 and head[0].isdigit() and len(head[0]) == 4:
        return int(head[0]), phase          # 2022-end
    if len(head) == 2 and all(p.isdigit() and len(p) == 2 for p in head):
        return 2000 + int(head[1]), phase    # 21-22-end -> 2022
    raise ValueError(f"unrecognised label {label!r}")


def build_database(mm, season, info):
    """Whole-DB player rows via staging + join. Returns (players, club_names).
    `info` is the shared player-info spine ({tid: identity}) scraped once in main()."""
    attrs = S.scrape_attributes(mm)        # {sid: attribute record}
    status = S.scrape_contract_status(mm, info)   # {tid: squad-status code}

    # names + exact attributes for the managed squad (snapshot)
    bounds = A.snapshot_bounds(mm)
    own_names = A.own_squad(mm, *bounds)
    own_exact = {}
    for tid in own_names:
        r = A.attr_record(mm, tid, bounds=bounds)
        if r:
            own_exact[tid] = {"attrs": A.decode(r["attrs"]),
                              "feet": {"left": r["feet"][0], "right": r["feet"][1]},
                              "value": r["value"]}

    # resolve club names only for clubs that actually have loaded players (they exist,
    # so the lookup is cheap) plus clubs that appeared in matches
    club_ids = {p["club_tid"] for p in info.values()
                if p["sid"] in attrs and p["club_tid"] != S.NO_CLUB}
    for m in season:
        club_ids.add(m["home_tid"])
        club_ids.add(m["away_tid"])
    club_names = {}
    for ct in club_ids:
        n = R.resolve_club(mm, ct, "long")
        if n:
            club_names[ct] = n

    def club_label(ct):
        if ct == S.NO_CLUB:
            return "Free agent"
        return club_names.get(ct, f"#{ct}")

    players, staff = {}, {}
    for tid, p in info.items():
        # SID == ffffffff means no linked player record -> staff (manager/coach/scout).
        # Confirmed: these average age 45 (68% over 40) vs 26 for players. There's also
        # an explicit type flag at info+33 (1=player/0=staff) that agrees ~99%; the ~0.7%
        # disagreement is likely player-coaches (both roles). We classify by SID, which
        # handles them correctly (a player-coach has a real SID -> counted as a player).
        # Not worth special-casing further for now.
        if p["sid"] == "ffffffff":
            staff[str(tid)] = {"tid": tid, "name": own_names.get(tid),
                               "club": club_label(p["club_tid"]),
                               "club_tid": p["club_tid"], "dob": p["dob"],
                               "nationality_id": p["nationality_id"]}
            continue
        rec = attrs.get(p["sid"])
        sc = status.get(tid)
        row = {"tid": tid, "name": own_names.get(tid),
               "club": club_label(p["club_tid"]), "club_tid": p["club_tid"],
               "dob": p["dob"], "nationality_id": p["nationality_id"],
               "has_attributes": rec is not None,
               "squad_status": sc,
               "loaned_out": sc == S.LOAN_STATUS and p["club_tid"] != S.NO_CLUB}
        if rec:
            row["is_gk"] = int(rec["positions"].get("GK", 0) == 20)
            row["ca"], row["pa"] = rec["ca"], rec["pa"]
            row["reputation"] = rec["reputation"]
            row["positions"] = rec["positions"]
            if tid in own_exact:           # own squad: exact snapshot attributes
                row["attributes"] = {a: own_exact[tid]["attrs"][a] for a in A.ATTR_ORDER}
                row["estimated"] = {a: False for a in A.ATTR_ORDER}
                row["feet"] = own_exact[tid]["feet"]
                row["value"] = own_exact[tid]["value"]
            else:                          # everyone else: estimated (+/-1)
                est, _, _ = A.estimate_player(mm, rec)
                row["attributes"] = {a: est[a]["val"] for a in A.ATTR_ORDER}
                row["estimated"] = {a: est[a]["est"] for a in A.ATTR_ORDER}
                row["feet"] = rec["feet"]
        else:                              # identity only (free agents / no record)
            row.update({"is_gk": None, "ca": None, "pa": None, "reputation": None,
                        "positions": {}, "feet": None,
                        "attributes": None, "estimated": None})
        players[str(tid)] = row
    return players, staff, club_names


_STAT_FIELDS = ["posOrder", "rating", "goals", "assists", "passA", "passC",
                "keyPass", "tackA", "tackW", "intercept", "shotA", "shotO",
                "condition", "subOn", "subOff", "yellow"]


def flatten_matches(season):
    """One row per (match, player), carrying the team actually played for."""
    rows = []
    for m in season:
        for side, team, opp in (("home_xi", m["home_tid"], m["away_tid"]),
                                ("away_xi", m["away_tid"], m["home_tid"])):
            for p in m[side]:
                row = {"date": m["date"], "competition": m["competition"],
                       "tid": p["tid_int"], "team_tid": team, "opponent_tid": opp}
                row.update({k: p[k] for k in _STAT_FIELDS})
                rows.append(row)
    return rows


def build_leagues(mm, valid_clubs, club_nation):
    """Leagues table + club->league map, from the LIGHT RESULTS (fmparser/lightresults):
    every simulated game carries its competition CID, so club->league is read directly
    for the whole DB (all loaded leagues), not just our own. Names are nation-validated
    (comp_detail mis-names some foreign cids). Returns ({cid: league_detail}, {tid: cid})
    keeping only league-type competitions in the table."""
    data = L.build(mm, valid_clubs, club_nation=club_nation)
    club_to_league = data["club_league"]
    leagues = {cid: v for cid, v in data["leagues"].items() if L._is_league(mm, cid)}
    return leagues, club_to_league


def league_label(detail):
    """Human league name: the resolved name, else 'Nation (unnamed)' when only the nation
    is known (foreign comps without a name record), else None."""
    if not detail:
        return None
    if detail.get("name"):
        return detail["name"]
    if detail.get("nation"):
        return f"{detail['nation']} (unnamed)"
    return None


def build_competitions(mm, season):
    """Reference for every competition in the season: name/short/code, type,
    nation, and num_teams (from the tagged region). See fmparser/reference &
    fmparser/tagged."""
    counts = T.league_team_counts(mm)
    comps = {}
    for cid in sorted({m["comp_id"] for m in season if m.get("comp_id")}):
        d = R.comp_detail(mm, cid) or {"cid": cid}
        if "uid" in d:
            d["num_teams"] = counts.get(d["uid"])
        d["matches_in_save"] = sum(1 for m in season if m.get("comp_id") == cid)
        comps[str(cid)] = d
    return comps


def write_players_csv(path, players):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tid", "name", "club", "club_tid", "loan", "league", "league_cid",
                    "GK", "CA", "PA", "rep", "dob", "nat", "positions"] + A.ATTR_ORDER)
        # attributed players first (by CA desc), then identity-only rows
        def sortkey(p):
            return (0 if p["has_attributes"] else 1, -(p["ca"] or 0), p["tid"])
        for p in sorted(players.values(), key=sortkey):
            pos = "/".join(k for k, v in sorted(p["positions"].items(),
                                                key=lambda kv: -kv[1]))
            attr = p["attributes"] or {}
            w.writerow([p["tid"], p["name"] or "", p["club"], p["club_tid"],
                        "Y" if p.get("loaned_out") else "",
                        p.get("league") or "", p.get("league_cid") or "",
                        "Y" if p["is_gk"] else "", p["ca"] or "", p["pa"] or "",
                        p["reputation"] or "", p["dob"] or "", p["nationality_id"], pos]
                       + [attr.get(a, "") for a in A.ATTR_ORDER])


def write_match_stats_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        cols = ["date", "competition", "tid", "team_tid", "opponent_tid"] + _STAT_FIELDS
        w.writerow(cols)
        for r in rows:
            w.writerow([r[c] for c in cols])


def main():
    ap = argparse.ArgumentParser(description="Extract an FMM22 save's current state.")
    ap.add_argument("save", help="path to the .fms save file")
    ap.add_argument("--label", help="output label (default: auto <year>-<period>)")
    ap.add_argument("--out", default="output", help="output root (default: output/)")
    args = ap.parse_args()

    s = Save(args.save)
    mm = s.mm
    season = M.extract_season(mm)
    auto, latest = auto_label(season)
    label = args.label or auto
    dest = os.path.join(args.out, label)
    os.makedirs(dest, exist_ok=True)

    info = S.scrape_players(mm)            # player-info spine (scraped once, shared)
    players, staff, club_names = build_database(mm, season, info)
    match_rows = flatten_matches(season)
    competitions = build_competitions(mm, season)

    # leagues + club->league (from light results), then stamp each player with their league
    valid_clubs = {p["club_tid"] for p in info.values() if p["club_tid"] != S.NO_CLUB}
    club_nation = L.club_nations(info, S.NO_CLUB)
    leagues, club2league = build_leagues(mm, valid_clubs, club_nation)
    for p in players.values():
        lc = club2league.get(p["club_tid"])
        p["league_cid"] = lc
        p["league"] = league_label(leagues.get(lc))

    def dump(name, obj, indent=1):
        with open(os.path.join(dest, name), "w", newline="") as f:
            json.dump(obj, f, ensure_ascii=False, indent=indent)

    dump("players.json", players, indent=None)     # ~24k players -> compact
    dump("staff.json", staff, indent=None)         # ~7k non-players (identity only)
    dump("matches.json", season)
    dump("competitions.json", competitions)
    dump("leagues.json", {str(c): d for c, d in sorted(leagues.items())})
    dump("clubs.json", {str(t): n for t, n in sorted(club_names.items())})
    write_players_csv(os.path.join(dest, "players.csv"), players)
    write_match_stats_csv(os.path.join(dest, "player_match_stats.csv"), match_rows)

    attributed = sum(1 for p in players.values() if p["has_attributes"])
    dates = sorted(m["date"] for m in season if m["date"])
    summary = {
        "label": label, "label_auto": auto,
        "label_source": "argument" if args.label else "auto",
        "save": os.path.abspath(args.save),
        "latest_match": latest, "date_range": [dates[0], dates[-1]] if dates else None,
        "competitions": dict(Counter(m.get("competition") for m in season)),
        "counts": {"matches": len(season), "player_match_lines": len(match_rows),
                   "players": len(players), "players_with_attributes": attributed,
                   "staff": len(staff), "competitions": len(competitions),
                   "leagues": len(leagues), "clubs_named": len(club_names)},
    }
    dump("summary.json", summary)

    print(f"extracted -> {dest}/")
    print(f"  matches {len(season)}  players {len(players)} "
          f"({attributed} with attributes)  staff {len(staff)}  "
          f"leagues {len(leagues)}  clubs {len(club_names)}")
    print(f"  label {label} (auto {auto}, latest match {latest})")
    s.close()


if __name__ == "__main__":
    main()
