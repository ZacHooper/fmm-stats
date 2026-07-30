#!/usr/bin/env python3
"""
Query the fm-parser DuckDB store — raw SQL or named reports.

    uv run python fmq.py labels                       # what's loaded
    uv run python fmq.py sql "SELECT ..."             # arbitrary query
    uv run python fmq.py league-table 2022 end 228    # standings for a competition
    uv run python fmq.py progression --tid 20648      # CA/PA + rep across phases
    uv run python fmq.py transfers 2022 start end     # club changes between phases
    uv run python fmq.py top-scorers 2022 [--comp 228]
    uv run python fmq.py matches 2022 end [--comp 228]
    uv run python fmq.py scout bergama                # one-shot opposition report

Reports read the transformed-layer views (v_*) created by load_duckdb.py.
"""
import argparse
import os
import sys

import duckdb


def show(con, sql, params=None, limit=100):
    rel = con.execute(sql, params or []) if params else con.sql(sql)
    if hasattr(rel, "show"):
        rel.show(max_rows=limit)
    else:  # con.execute path -> fetch + basic print
        rows = rel.fetchall()
        cols = [d[0] for d in rel.description]
        print(" | ".join(cols))
        for r in rows[:limit]:
            print(" | ".join("" if v is None else str(v) for v in r))


def cmd_labels(con, a):
    show(con, "SELECT season, phase, label, save_path, loaded_at "
              "FROM staging.extracts ORDER BY season, "
              "CASE phase WHEN 'start' THEN 0 WHEN 'mid' THEN 1 ELSE 2 END")


def cmd_sql(con, a):
    show(con, a.query, limit=a.limit)


def cmd_league_table(con, a):
    show(con,
         "SELECT pos, club, played, won, drawn, lost, gf, ga, gd, points, source "
         "FROM v_league_table WHERE season=? AND phase=? AND league_cid=? "
         "ORDER BY source, pos",
         [a.season, a.phase, a.cid], limit=a.limit)


def cmd_progression(con, a):
    show(con,
         "SELECT season, phase, club, ca, pa, reputation "
         "FROM v_ca_progression WHERE tid=? "
         "ORDER BY season, phase_ord",
         [a.tid], limit=a.limit)


def cmd_transfers(con, a):
    show(con,
         "SELECT name, from_club, to_club, from_club_tid, to_club_tid "
         "FROM v_transfers WHERE season=? AND from_phase=? AND to_phase=? "
         "ORDER BY name",
         [a.season, a.from_phase, a.to_phase], limit=a.limit)


def cmd_top_scorers(con, a):
    if a.comp:
        show(con,
             "SELECT any_value(p.name) AS name, mps.tid, SUM(mps.goals) AS goals, "
             "SUM(mps.assists) AS assists, COUNT(*) AS apps "
             "FROM staging.match_player_stats mps "
             "LEFT JOIN staging.players p "
             "  ON (p.season,p.phase,p.tid)=(mps.season,mps.phase,mps.tid) "
             "WHERE mps.season=? AND mps.competition=("
             "  SELECT any_value(name) FROM staging.competitions WHERE season=? AND cid=?) "
             "GROUP BY mps.tid ORDER BY goals DESC",
             [a.season, a.season, a.comp], limit=a.limit)
    else:
        show(con,
             "SELECT name, tid, goals, assists, appearances "
             "FROM v_top_scorers WHERE season=? ORDER BY goals DESC",
             [a.season], limit=a.limit)


def cmd_matches(con, a):
    if a.comp:
        show(con,
             "SELECT date, home, score_home, score_away, away, competition "
             "FROM v_match_results WHERE season=? AND phase=? AND comp_id=? "
             "ORDER BY date",
             [a.season, a.phase, a.comp], limit=a.limit)
    else:
        show(con,
             "SELECT date, home, score_home, score_away, away, competition "
             "FROM v_match_results WHERE season=? AND phase=? ORDER BY date",
             [a.season, a.phase], limit=a.limit)


def _isna(v):
    return v is None or v != v      # v != v catches NaN without importing math


def _num(v):
    return "—" if _isna(v) else v


def _fmt_edge(x):
    return "  —" if _isna(x) else (f"+{x:.1f}" if x >= 0 else f"{x:.1f}")


def _pct(v):
    return "—" if _isna(v) else f"{v:.0f}%"


def _print_scout(rep):
    o, cov, ov = rep["opp"], rep["coverage"], rep["overall"]
    print(f"\n=== SCOUT: {o['name']} (tid {o['tid']}) — {rep['season']}/{rep['phase']} "
          f"· {rep['method']} ===")
    if not _isna(ov["us"]) and not _isna(ov["them"]):
        note = "  ⚠️ PARTIAL DATA" if cov["partial"] else ""
        print(f"    team index (best XI, 100=avg for position): us {ov['us']:.0f} "
              f"({_pct(ov['us_pctile'])} league)  vs  them {ov['them']:.0f} "
              f"({_pct(ov['them_pctile'])})   ({cov['in_frame']} of theirs rated){note}")

    print("\n-- AUTO-READ --")
    for f in rep["flags"]:
        print(f"  • {f}")

    h = rep["h2h"]
    if h["played"]:
        print(f"\n-- HEAD-TO-HEAD --  P{h['played']} W{h['w']} D{h['d']} L{h['l']}  "
              f"GF{h['gf']} GA{h['ga']}  {h['ppg']:.2f} ppg")
        for _, r in h["matches"].iterrows():
            print(f"   {str(r['date'])[:10]} {r['venue']} {int(r['gf'])}-{int(r['ga'])} "
                  f"{r['result']}  shots {int(r['our_shots'])}-{int(r['opp_shots'])}  "
                  f"{str(r['competition'])[:26]}")
    else:
        print("\n-- HEAD-TO-HEAD --  none on record")

    s = rep["strength"]
    if not s.empty:
        print("\n-- TEAM & UNIT STRENGTH (index 100=league-avg per position; %ile) --")
        for _, r in s.iterrows():
            print(f"   {r['unit']:8}  us {_num(r['us']):>5} ({_pct(r['us_pctile']):>4})   "
                  f"them {_num(r['them']):>5} ({_pct(r['them_pctile']):>4})   "
                  f"edge {_fmt_edge(r['edge'])}")

    kp = rep["key_players"]
    if not kp.empty:
        print("\n-- THEIR KEY PLAYERS (by position index; names not in save) --")
        for _, r in kp.head(10).iterrows():
            pcl = f"{r['pctile_league']:.0f}%ile" if not _isna(r.get("pctile_league")) else "—"
            print(f"   {str(r['position']):4} index {r['pos_index']:>5.0f}  {pcl:>7}   "
                  f"{r['top_attrs']}")
    print()


def cmd_scout(con, a):
    import logging
    logging.getLogger("streamlit").setLevel(logging.ERROR)
    src = os.path.abspath(a.db)
    path = src
    try:                                    # a live dashboard holds the single-writer lock
        duckdb.connect(src, read_only=True).close()
    except duckdb.Error:
        import shutil, tempfile
        path = os.path.join(tempfile.gettempdir(), "fmq_scout.duckdb")
        shutil.copy2(src, path)
        print("(live DB is locked by another process — scouting a fresh copy)")
    os.environ["FM_DUCKDB"] = path
    os.environ["FM_DUCKDB_READONLY"] = "1"
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard"))
    import db
    matches = db.resolve_club(a.team)
    if matches.empty:
        print(f"No club matching '{a.team}'.")
        return
    if len(matches) > 1:
        print(f"Multiple clubs match '{a.team}':")
        for _, r in matches.iterrows():
            print(f"   {int(r['tid']):6}  {r['name']}  ({int(r['n_players'])} players)")
        print(f"→ scouting the largest squad; pass its tid to pick another.")
    row = matches.iloc[0]
    _print_scout(db.scout_report(int(row["tid"]), season=a.season, phase=a.phase,
                                 method=a.method))


def main():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", default="fm.duckdb")
    common.add_argument("--limit", type=int, default=100)

    ap = argparse.ArgumentParser(description="Query the fm-parser DuckDB store")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("labels", parents=[common]).set_defaults(fn=cmd_labels)

    p = sub.add_parser("sql", parents=[common])
    p.add_argument("query"); p.set_defaults(fn=cmd_sql)

    p = sub.add_parser("league-table", parents=[common])
    p.add_argument("season", type=int); p.add_argument("phase")
    p.add_argument("cid", type=int); p.set_defaults(fn=cmd_league_table)

    p = sub.add_parser("progression", parents=[common])
    p.add_argument("--tid", type=int, required=True); p.set_defaults(fn=cmd_progression)

    p = sub.add_parser("transfers", parents=[common])
    p.add_argument("season", type=int); p.add_argument("from_phase")
    p.add_argument("to_phase"); p.set_defaults(fn=cmd_transfers)

    p = sub.add_parser("top-scorers", parents=[common])
    p.add_argument("season", type=int); p.add_argument("--comp", type=int)
    p.set_defaults(fn=cmd_top_scorers)

    p = sub.add_parser("matches", parents=[common])
    p.add_argument("season", type=int); p.add_argument("phase")
    p.add_argument("--comp", type=int); p.set_defaults(fn=cmd_matches)

    p = sub.add_parser("scout", parents=[common])
    p.add_argument("team", help="opponent club name (substring) or tid")
    p.add_argument("--season", type=int); p.add_argument("--phase")
    p.add_argument("--method", default="buca_433"); p.set_defaults(fn=cmd_scout)

    a = ap.parse_args()
    if a.cmd == "scout":   # uses db.py (its own read-only connection), not the shared con
        a.fn(None, a)
        return
    con = duckdb.connect(a.db, read_only=True)
    try:
        a.fn(con, a)
    finally:
        con.close()


if __name__ == "__main__":
    main()
