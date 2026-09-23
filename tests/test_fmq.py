#!/usr/bin/env python3
"""fmq / fmstats against a real store: every report agrees with the save's own ground truth.

Checks that a report can only pass by being right:
  * `stats.player_output` totals equal mart.player_seasons for every season — the old
    v_top_scorers summed every snapshot of the match history and read 91 goals where there
    were 30;
  * `club_matches` for us holds one row per match;
  * club lookup resolves abbreviations and does not fall into substrings ("ob" is in "Hobro");
  * `league.league_table` for every completed season reproduces each club's finishing position
    as the SAVE records it (`mart.clubs.last_league_pos` at the next season's first snapshot)
    — a stage filter that let cup ties in, or a split league ranked on points alone, fails it;
  * a scout report's head-to-head matches the match record, the players it credits with goals
    against us account for no more goals than we conceded, and the saved record carries no
    raw ability value at any depth.

Reads the store `fmstats.store` would (R2 cache, or $FM_DUCKDB). Skips when none is available.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.harness import FAIL, PASS, skip                                  # noqa: E402

FORBIDDEN = {"ca", "pa", "current_ability", "potential_ability"}


def _keys(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k, f"{path}.{k}"
            yield from _keys(v, f"{path}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _keys(v, f"{path}[{i}]")


def main():
    try:
        from fmstats import league, scout, stats, store
    except ImportError as e:
        return skip(f"fmstats not importable: {e}")
    try:
        st = store.open_store(announce=False)
    except SystemExit as e:
        return skip(f"no store available ({e})")
    con, us = st.con, st.career.managed_tid
    fails = []

    def check(ok, msg):
        print(("  ok   " if ok else "  FAIL ") + msg)
        if not ok:
            fails.append(msg)

    # --- output totals == the mart's per-season totals, every season
    seasons = [r[0] for r in con.execute(
        "SELECT DISTINCT season FROM mart.player_seasons WHERE team_tid = ? ORDER BY 1",
        [us]).fetchall()]
    for s in seasons:
        out = stats.player_output(st, us, season=s)
        want = con.execute("""SELECT SUM(goals), SUM(assists) FROM mart.player_seasons
                              WHERE team_tid = ? AND season = ? AND person_id IS NOT NULL""",
                           [us, s]).fetchone()
        got = (int(out.players["g"].sum()), int(out.players["a"].sum()))
        check(got == (int(want[0] or 0), int(want[1] or 0)),
              f"output {s}: goals/assists {got} == mart.player_seasons {want}")

    # --- one row per match
    dup = con.execute("""SELECT COUNT(*) - COUNT(DISTINCT (date, opp_tid))
                         FROM mart.club_matches WHERE club_tid = ?""", [us]).fetchone()[0]
    check(dup == 0, f"club_matches: {dup} duplicate (date, opponent) rows for us")

    # --- club lookup
    for q, want in (("OB", "Odense Boldklub"), ("FCK", "Football Club København"),
                    ("AGF", "Aarhus Gymnastik Forening"), ("Aarhus", "Aarhus Gymnastik Forening"),
                    ("Hobro", "Hobro Idræts Klub"), ("Brondby", "Brøndbyernes Idrætsforening")):
        m = scout.resolve_club(st, q)
        got = m.iloc[0]["name"] if not m.empty else None
        check(got == want, f"resolve_club({q!r}) -> {got!r}, want {want!r}")

    # --- league tables vs the save's own record of each club's finish
    firsts = con.execute("""SELECT season, arg_min(phase, snap_ix) AS phase
                            FROM mart.snapshots GROUP BY season ORDER BY season""").fetchall()
    n_tables = 0
    for (next_season, phase) in firsts:
        season = next_season - 1
        truth = con.execute("""SELECT club_tid, last_league_pos, last_league FROM mart.clubs
                               WHERE season = ? AND phase = ? AND last_league_pos > 0""",
                            [next_season, phase]).df()
        ours = truth[truth["club_tid"] == us]
        if ours.empty:
            continue
        try:
            lt = league.league_table(st, us, season)
        except LookupError:
            continue
        lg = truth[truth["last_league"] == ours.iloc[0]["last_league"]]
        pos = dict(zip(lt.table["club_tid"], lt.table["pos"]))
        wrong = [(int(r.club_tid), int(r.last_league_pos), pos.get(r.club_tid))
                 for r in lg.itertuples() if pos.get(r.club_tid) != r.last_league_pos]
        n_tables += 1
        check(not wrong and lt.complete,
              f"table {lt.label}: {len(lg)} clubs' positions match the save"
              + (f" — mismatches (tid, save, ours): {wrong}" if wrong else "")
              + ("" if lt.complete else " — but it is marked incomplete"))
    check(n_tables > 0, f"{n_tables} completed season table(s) checked")

    cur = league.league_table(st, us)
    check(cur.complete or cur.table["p"].max() > 0,
          f"current table {cur.label}: complete={cur.complete}, "
          f"{cur.table['p'].min()}-{cur.table['p'].max()} played")

    # --- a scout report, against the most-played league opponent
    opp = con.execute("""SELECT opp_tid FROM mart.club_matches WHERE club_tid = ?
                         AND is_competitive GROUP BY opp_tid ORDER BY COUNT(*) DESC, opp_tid
                         LIMIT 1""", [us]).fetchone()[0]
    rep = scout.scout_report(st, opp)
    played = con.execute("""SELECT COUNT(*), SUM(ga) FROM mart.club_matches
                            WHERE club_tid = ? AND opp_tid = ? AND is_competitive""",
                         [us, opp]).fetchone()
    check(rep["h2h"]["played"] == played[0],
          f"scout {rep['opp']['name']}: h2h played {rep['h2h']['played']} == {played[0]}")
    credited = int(rep["h2h_players"]["goals"].sum()) if not rep["h2h_players"].empty else 0
    check(0 < credited <= int(played[1] or 0),
          f"scout: {credited} goals credited to their players <= {played[1]} conceded")
    check(rep["method"] == (st.career.rating_method or rep["method"]),
          f"scout rated with the career's method ({rep['method']})")
    rec = scout.scout_record(st, rep, venue="H", note="test")
    leaked = [p for k, p in _keys(rec) if str(k).lower() in FORBIDDEN]
    check(not leaked, f"saved scout record carries no raw ability key {leaked or ''}")
    import json
    try:
        json.dumps(rec, allow_nan=False)
        ok = True
    except (TypeError, ValueError):
        ok = False
    check(ok, "saved scout record is strict JSON")

    st.con.close()
    print(f"\n{'FAILED' if fails else 'passed'}: {len(fails)} failure(s)")
    return FAIL if fails else PASS


if __name__ == "__main__":
    sys.exit(main())
