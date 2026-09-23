#!/usr/bin/env python3
"""Query a career store — raw SQL or named reports.

    uv run python fmq.py labels                          # snapshots in the store
    uv run python fmq.py sql "SELECT ..."                # arbitrary query
    uv run python fmq.py output --since 2027-01-01       # our current squad's G/A/key passes
    uv run python fmq.py output --club OB --vs Frem      # who from OB has produced against us
    uv run python fmq.py matches --opp OB                # results, one row per match
    uv run python fmq.py moves --since 2026-07-02        # squad changes between two snapshots
    uv run python fmq.py growth "Chukwuani"              # a player's attributes over time
    uv run python fmq.py table --season 2026             # a league table from the fixture list
    uv run python fmq.py scout OB --venue A --fixture 2027-05-02   # opposition report (saved)
    uv run python fmq.py scouts --opp OB                 # the scout log
    uv run python fmq.py grade OB --fixture 2027-05-02 --result "W 2-1 (A)" --note "..."

Reads the career's published store from R2 by default (cached; see fmstats/store.py) and says
which snapshot it is reading on stderr. `--db <path>` reads a local store instead, `--refresh`
re-checks R2 now, `--offline` never touches the network. Every report is built on the `mart`
schema, which already applies the correctness rules (one row per match, genuine squad
membership, person_id rather than recycled tids).
"""
import argparse
import sys

import pandas as pd

from fmstats import league, scout, stats, store

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 40)
pd.set_option("display.max_colwidth", 60)


def _show(df, limit=None, empty="(no rows)"):
    if df is None or df.empty:
        print(empty)
        return
    if limit:
        df = df.head(limit)
    print(df.to_string(index=False, na_rep=""))


def _club(st, name_or_tid, what="club"):
    """(tid, name) for a club argument, defaulting to ours. Lists the alternatives when the
    best match is not the only plausible one."""
    if name_or_tid is None:
        row = st.con.execute("SELECT name FROM mart.clubs WHERE season=? AND phase=? "
                             "AND club_tid=?", [st.season, st.phase,
                                                st.career.managed_tid]).fetchone()
        return st.career.managed_tid, row[0] if row else st.career.name
    m = scout.resolve_club(st, name_or_tid)
    if m.empty:
        raise SystemExit(f"no {what} matching '{name_or_tid}'")
    top = m.iloc[0]["name"]
    best = m[(m["tier"] == m.iloc[0]["tier"]) & (m["domestic"] == m.iloc[0]["domestic"])
             & ~m["name"].str.startswith(top + " ").fillna(False)]
    if st.career.managed_tid in set(best["tid"]):
        return st.career.managed_tid, best.loc[best["tid"] == st.career.managed_tid,
                                               "name"].iat[0]
    if len(best) > 1:
        alts = ", ".join(f"{r['name']} ({int(r['tid'])})" for _, r in best.iloc[1:4].iterrows())
        print(f"'{name_or_tid}' -> {m.iloc[0]['name']} ({int(m.iloc[0]['tid'])}); "
              f"also matched {alts} — pass a tid to pick another.", file=sys.stderr)
    return int(m.iloc[0]["tid"]), m.iloc[0]["name"]


def _reserve_of(st, club_tid):
    """The reserve side's tid for a club, or None — ours from the career registry, anyone
    else's by the '<name> Reserves' naming the save uses."""
    if club_tid == st.career.managed_tid:
        return st.career.reserve_tid
    row = st.con.execute("""
        SELECT r.club_tid FROM mart.clubs c JOIN mart.clubs r
          ON (r.season, r.phase) = (c.season, c.phase) AND r.name = c.name || ' Reserves'
        WHERE (c.season, c.phase, c.club_tid) = (?, ?, ?)""",
                         [st.season, st.phase, club_tid]).fetchone()
    return row[0] if row else None


# --------------------------------------------------------------------------- basic
def cmd_labels(st, a):
    _show(st.con.execute("""SELECT label, season, phase, phase_date, latest_match, is_preseason
                            FROM mart.snapshots ORDER BY snap_ix""").df())


def cmd_sql(st, a):
    _show(st.con.execute(a.query).df(), a.limit)


# --------------------------------------------------------------------------- output
def cmd_output(st, a):
    """Per-player production for one club — see fmstats/stats.py."""
    tid, name = _club(st, a.club)
    title = [name]
    vs_tid = None
    if a.vs:
        vs_tid, vs_name = _club(st, a.vs, "opponent")
        title.append(f"vs {vs_name}")
    if a.season:
        title.append(f"season {a.season}")
    if a.since:
        title.append(f"since {a.since}")
    out = stats.player_output(st, tid, vs_tid, a.season, a.since)
    df = out.players.drop(columns="person_id")
    if df.empty:
        print(f"{' · '.join(title)}: no competitive appearances")
        return
    if not a.include_departed:
        df = df[df["still_here"]].drop(columns="still_here")
    sort = {"ga": ["g", "a", "kp"], "goals": ["g"], "assists": ["a"], "kp": ["kp"],
            "shots": ["sh"], "rating": ["rating"], "mins": ["mins"]}[a.sort]
    keys = (["_ga"] if a.sort == "ga" else []) + sort
    df = df.assign(_ga=df["g"] + df["a"]).sort_values(
        keys + ["player"], ascending=[False] * len(keys) + [True]).drop(columns="_ga")
    scope = "incl. players who have left" if a.include_departed else "current squad only"
    print(f"{' · '.join(title)} — {out.n_matches} competitive matches, {scope}")
    _show(df, a.limit)
    if out.unresolved:
        print(f"({out.unresolved} appearances by players the store could not name are excluded)")


# --------------------------------------------------------------------------- matches
def cmd_matches(st, a):
    tid, name = _club(st, a.club)
    where, params = ["club_tid = ?"], [tid]
    if not a.all:
        where.append("is_competitive")
    if a.opp:
        opp_tid, _ = _club(st, a.opp, "opponent")
        where.append("opp_tid = ?")
        params.append(opp_tid)
    if a.season:
        where.append("season = ?")
        params.append(a.season)
    if a.since:
        where.append("date >= CAST(? AS DATE)")
        params.append(a.since)
    if a.comp:
        where.append("competition ILIKE ?")
        params.append(f"%{a.comp}%")
    df = st.con.execute(f"""
        SELECT date, venue AS v, opponent, gf || '-' || ga AS score, result AS res,
               competition, our_shots || '-' || opp_shots AS shots,
               our_shots_on_target || '-' || opp_shots_on_target AS on_target
        FROM mart.club_matches WHERE {' AND '.join(where)} ORDER BY date""", params).df()
    if not df.empty:
        w, d, l = (int((df["res"] == r).sum()) for r in "WDL")
        print(f"{name}: {len(df)} matches, W{w} D{d} L{l}")
    _show(df, a.limit)


# --------------------------------------------------------------------------- moves
def cmd_moves(st, a):
    """Squad changes between two snapshots, from each club's squad array (mart.club_roster),
    with the club's reserve side counted as the same club. A move is only known to have
    happened BETWEEN the two snapshot dates; the save does not date it more precisely."""
    tid, name = _club(st, a.club)
    snaps = st.con.execute("SELECT season, phase, phase_date, label FROM mart.snapshots "
                           "ORDER BY snap_ix").df()
    if a.since:
        before = snaps[snaps["phase_date"] <= pd.Timestamp(a.since)]
        if before.empty:
            raise SystemExit(f"no snapshot on or before {a.since}")
        old = before.iloc[-1]
    else:
        old = snaps.iloc[-2]
    new = snaps.iloc[-1]
    clubs = [int(t) for t in (tid, _reserve_of(st, tid)) if t]
    ph = ",".join("?" * len(clubs))
    df = st.con.execute(f"""
        WITH o AS (SELECT DISTINCT person_id, name FROM mart.club_roster
                   WHERE season = ? AND phase = ? AND club_tid IN ({ph})),
             n AS (SELECT DISTINCT person_id, name FROM mart.club_roster
                   WHERE season = ? AND phase = ? AND club_tid IN ({ph}))
        SELECT 'in' AS move, n.name AS player,
               (SELECT any_value(club) FROM mart.player_snapshots p
                WHERE p.person_id = n.person_id AND (p.season, p.phase) = (?, ?)) AS "from/to"
        FROM n WHERE n.person_id NOT IN (SELECT person_id FROM o)
        UNION ALL
        SELECT 'out', o.name,
               (SELECT any_value(club) FROM mart.player_snapshots p
                WHERE p.person_id = o.person_id AND (p.season, p.phase) = (?, ?))
        FROM o WHERE o.person_id NOT IN (SELECT person_id FROM n)
        ORDER BY 1, 2""",
                         [int(old["season"]), old["phase"], *clubs,
                          int(new["season"]), new["phase"], *clubs,
                          int(old["season"]), old["phase"], int(new["season"]),
                          new["phase"]]).df()
    print(f"{name}: squad changes between {old['phase_date']:%Y-%m-%d} ({old['label']}) and "
          f"{new['phase_date']:%Y-%m-%d} ({new['label']})")
    _show(df, a.limit, empty="no changes")


# --------------------------------------------------------------------------- growth
def _player(st, q):
    """person_id for a player name (diacritic-insensitive substring) or tid, preferring the
    latest snapshot and our own squad; exits listing candidates when ambiguous."""
    q = str(q).strip()
    if q.isdigit():
        row = st.con.execute("SELECT person_id FROM mart.player_snapshots WHERE tid = ? "
                             "ORDER BY snap_ix DESC LIMIT 1", [int(q)]).fetchone()
        if not row:
            raise SystemExit(f"no player with tid {q}")
        return row[0]
    cands = st.con.execute("""
        SELECT person_id, any_value(name) AS name, arg_max(club, snap_ix) AS club,
               MAX(snap_ix) AS last_ix,
               bool_or(club_tid IN (SELECT club_tid FROM mart.our_clubs)) AS ours
        FROM mart.player_snapshots WHERE name IS NOT NULL
        GROUP BY person_id""").df()
    key = scout._fold(q)
    hit = cands[cands["name"].map(lambda n: key in scout._fold(n))]
    if hit.empty:
        raise SystemExit(f"no player matching '{q}'")
    exact = hit[hit["name"].map(scout._fold) == key]
    hit = exact if not exact.empty else hit
    hit = hit.sort_values(["ours", "last_ix"], ascending=False)
    if len(hit) > 1:
        print(f"{len(hit)} players match '{q}' — showing {hit.iloc[0]['name']}; pass a tid "
              f"for another:", file=sys.stderr)
        for _, r in hit.iloc[1:8].iterrows():
            tid = st.con.execute("SELECT arg_max(tid, snap_ix) FROM mart.player_snapshots "
                                 "WHERE person_id = ?", [r["person_id"]]).fetchone()[0]
            print(f"   {r['name']}  ({r['club']})  tid {tid}", file=sys.stderr)
    return hit.iloc[0]["person_id"]


def cmd_growth(st, a):
    """A player's attributes at every snapshot, plus his Level %ile at his main position.
    Estimated (non-exact) attribute reads are flagged in `est`: a player who was never ours
    carries a model decode, accurate to about ±1."""
    pid = _player(st, a.player)
    attrs = scout.ATTR_ORDER
    df = st.con.execute(f"""
        SELECT phase_date AS date, club, age, is_gk, is_estimated AS est,
               {", ".join(f'"{c}"' for c in attrs)}
        FROM mart.player_snapshots WHERE person_id = ? ORDER BY snap_ix""", [pid]).df()
    if df.empty:
        raise SystemExit("no snapshots for that player")
    lv = st.con.execute("""
        SELECT s.phase_date AS date, p.position AS pos, p.level_league, p.level_nation
        FROM mart.player_primary_position p JOIN mart.snapshots s USING (season, phase)
        WHERE p.person_id = ?""", [pid]).df()
    df = df.merge(lv, on="date", how="left")
    gk = bool(df["is_gk"].iloc[-1])
    keep = [c for c in attrs if gk or c not in scout.ATTR_GROUPS["Goalkeeping"]]
    abbrev = {c: c[:4] for c in keep}
    name = st.con.execute("SELECT any_value(name) FROM mart.player_snapshots WHERE person_id=?",
                          [pid]).fetchone()[0]
    print(f"{name} — attributes per snapshot (level_* = Level %ile at his main position)")
    out = df[["date", "club", "age", "pos", "level_league", "level_nation", "est", *keep]]
    out = out.rename(columns=abbrev)
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    _show(out, a.limit)


# --------------------------------------------------------------------------- table
def cmd_table(st, a):
    """A league table rebuilt from the fixture list (mart.league_tables)."""
    season = a.season or st.season
    if a.league:
        row = st.con.execute("""SELECT club_tid FROM mart.league_tables
                                WHERE season = ? AND league_name ILIKE ?
                                ORDER BY nation = (SELECT nation FROM mart.league_tables
                                                   WHERE season = ? AND club_tid = ?) DESC,
                                         pos LIMIT 1""",
                             [season, f"%{a.league}%", season, st.career.managed_tid]).fetchone()
        if not row:
            raise SystemExit(f"no league matching '{a.league}' in {season - 1}/{str(season)[2:]}")
        seed = row[0]
    else:
        seed, _ = _club(st, a.club)
    try:
        lt = league.league_table(st, seed, season)
    except LookupError as e:
        raise SystemExit(str(e))
    t = lt.table
    name = f"{lt.league} {lt.label}" if lt.league else lt.label
    if lt.complete:
        print(f"{name} (final) — rebuilt from the fixture list")
    else:
        print(f"{name} — AS OF {st.phase_date:%Y-%m-%d}, INCOMPLETE: "
              f"{t['p'].min()}–{t['p'].max()} games played per club. Games after the "
              f"snapshot are not in the store.")
    if lt.nation != "Denmark":
        print(f"({lt.nation or 'this country'} is unverified: only Danish tables have been "
              "checked against the save's own final positions — see mart.league_tables in "
              "fmstats/mart.py)")
    if lt.split:
        print("(split league: group 1 ranks above group 2; points carried over)")
    else:
        t = t.drop(columns="group")
    _show(t.drop(columns="club_tid"))


# --------------------------------------------------------------------------- scouting
def _isna(v):
    return v is None or v != v


def _pct(v):
    return "—" if _isna(v) else f"{v:.0f}%"


def _print_scout(rep):
    o, cov, ov = rep["opp"], rep["coverage"], rep["overall"]
    print(f"\n=== SCOUT: {o['name']} (tid {o['tid']}) — snapshot {rep['phase']} "
          f"· rated with {rep['method']} ===")
    mgr = rep.get("manager")
    if mgr:
        print(f"    manager: {mgr['name']} · preferred {mgr['formation_preferred']} "
              f"({mgr['style']}) · attacking {mgr['formation_attacking']} · "
              f"defensive {mgr['formation_defensive']}")
    if not _isna(ov["us"]) and not _isna(ov["them"]):
        note = "  ⚠️ PARTIAL DATA" if cov["partial"] else ""
        print(f"    team index (best XI, 100=avg for position): us {ov['us']:.0f} "
              f"({_pct(ov['us_pctile'])})  vs  them {ov['them']:.0f} "
              f"({_pct(ov['them_pctile'])})   ({cov['in_frame']} of theirs rated){note}")

    print("\n-- AUTO-READ --")
    for f in rep["flags"]:
        print(f"  • {f}")

    h = rep["h2h"]
    if h["played"]:
        print(f"\n-- HEAD-TO-HEAD --  P{h['played']} W{h['w']} D{h['d']} L{h['l']}  "
              f"GF{h['gf']} GA{h['ga']}  {h['ppg']:.2f} ppg   "
              f"(home W{h['H']['w']} D{h['H']['d']} L{h['H']['l']} · "
              f"away W{h['A']['w']} D{h['A']['d']} L{h['A']['l']})")
        for _, r in h["matches"].iterrows():
            print(f"   {str(r['date'])[:10]} {r['venue']} {int(r['gf'])}-{int(r['ga'])} "
                  f"{r['result']}  shots {int(r['our_shots'])}-{int(r['opp_shots'])}  "
                  f"on target {int(r['our_shots_on_target'])}-{int(r['opp_shots_on_target'])}  "
                  f"{str(r['competition'])[:26]}")
    else:
        print("\n-- HEAD-TO-HEAD --  none on record")

    p = rep["h2h_players"]
    if not p.empty:
        print("\n-- THEIR OUTPUT AGAINST US (still there = at the club now) --")
        cols = ["name", "apps", "minutes", "goals", "assists", "key_passes", "shots",
                "on_target", "avg_rating", "still_there"]
        shown = p[(p["goals"] + p["assists"] + p["key_passes"]) > 0][cols].head(10).copy()
        for c in ("apps", "minutes", "goals", "assists", "key_passes", "shots", "on_target"):
            shown[c] = shown[c].astype("Int64")
        print(shown.to_string(index=False))

    s = rep["strength"]
    if not s.empty:
        print("\n-- UNIT STRENGTH (index: 100 = avg for position under the rating method; "
              "quality: Level %ile) --")
        for _, r in s.iterrows():
            print(f"   {r['unit']:8}  index us {r['us'] if not _isna(r['us']) else '—':>5} "
                  f"them {r['them'] if not _isna(r['them']) else '—':>5}   "
                  f"quality us {_pct(r['us_quality']):>4} them {_pct(r['them_quality']):>4}")
    m = rep["matchups"]
    if not m.empty:
        print("\n-- FACE-OFF MATCHUPS (Level %ile) --")
        for _, r in m.iterrows():
            edge = "—" if _isna(r["edge"]) else f"{r['edge']:+.0f}"
            print(f"   {r['matchup']:30} us {_pct(r['us_quality']):>4}  "
                  f"them {_pct(r['them_quality']):>4}  edge {edge}")

    kp = rep["key_players"]
    if not kp.empty:
        print("\n-- THEIR SQUAD BY LEVEL %ILE (quality, not output — see the table above) --")
        for _, r in kp.head(10).iterrows():
            lvl = "—" if _isna(r["level_league"]) else f"{r['level_league']:.0f}%ile"
            print(f"   {str(r['position']):4} {str(r['name'])[:24]:24} {lvl:>7}   "
                  f"{r['top_attrs']}")
    print()


def _sync_note(status):
    return {scout.state.SYNCED: "synced to R2",
            scout.state.LOCAL_ONLY: "LOCAL ONLY — no R2 remote configured",
            scout.state.SYNC_FAILED: "⚠ LOCAL ONLY — the push to R2 FAILED"}.get(status, status)


def cmd_scout(st, a):
    tid, _ = _club(st, a.team, "opponent")
    rep = scout.scout_report(st, tid, method=a.method)
    _print_scout(rep)
    if a.no_save:
        return
    mgr = rep.get("manager") or {}
    rec = scout.save_scout(st, rep, venue=a.venue,
                           formation=a.formation or mgr.get("formation_preferred"),
                           style=a.style or mgr.get("style"), note=a.note, fixture=a.fixture)
    print(f"  ✎ saved state/scouts/{rec['_key']}.json ({_sync_note(rec['_sync'])})")
    if not a.fixture:
        print("    no --fixture given: a second scout of this opponent before the next import "
              "will replace this one. Pass the match date to keep both legs.")


def cmd_scouts(st, a):
    s = scout.load_scouts()
    if s.empty:
        print("No saved scouts yet — `fmq scout <team>` saves each run.")
        return
    if a.opp:
        tid, _ = _club(st, a.opp, "opponent")
        s = s[s["opponent_tid"] == tid]
    print(f"{len(s)} saved scout(s):")

    def _s(x):
        return "" if x is None or (isinstance(x, float) and x != x) else str(x)

    for _, r in s.sort_values("saved_at").iterrows():
        ov = r.get("overall") if isinstance(r.get("overall"), dict) else {}
        h = r.get("h2h") if isinstance(r.get("h2h"), dict) else {}
        ctx = " · ".join(x for x in map(_s, (r.get("venue"), r.get("fixture"),
                                             r.get("formation"), r.get("style"))) if x)
        print(f"\n  {str(r['saved_at'])[:16]}  {r['opponent']}  [{r.get('snapshot')}]"
              + (f"  ({ctx})" if ctx else ""))
        bits = []
        if ov.get("us") is not None and ov.get("them") is not None:
            bits.append(f"index {ov['us']:.0f} vs {ov['them']:.0f}")
        if h.get("played"):
            bits.append(f"H2H P{h['played']} W{h.get('w')} D{h.get('d')} L{h.get('l')}")
        if bits:
            print("     " + "   ".join(bits))
        if _s(r.get("note")):
            print(f"     note: {_s(r.get('note'))}")
        if _s(r.get("result_note")):
            res = _s(r.get("result"))
            print(f"     result{' ' + res if res else ''}"
                  f" (graded {_s(r.get('graded_at'))[:16]}): {_s(r.get('result_note'))}")
        revs = r.get("revisions")
        if isinstance(revs, list) and revs:
            print(f"     ({len(revs)} superseded read(s) kept in `revisions`)")


def cmd_grade(st, a):
    tid, name = _club(st, a.team, "opponent")
    try:
        rec = scout.grade_scout(tid, a.note, result=a.result, fixture=a.fixture)
    except ValueError as e:
        raise SystemExit(str(e))
    if rec is None:
        raise SystemExit(f"no saved scout of {name} to grade")
    print(f"graded state/scouts/{rec['_key']}.json ({_sync_note(rec['_sync'])})")


# --------------------------------------------------------------------------- main
NO_STORE = {"scouts"}


def main():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", default=None, help="read this local store instead of R2")
    common.add_argument("--career", default=None,
                        help="career key: reads the store fm-<key>.duckdb "
                             "(default: $FM_CAREER or frem)")
    common.add_argument("--refresh", action="store_true", help="re-check R2 for a newer store now")
    common.add_argument("--offline", action="store_true", help="never touch the network")
    common.add_argument("--limit", type=int, default=None)

    ap = argparse.ArgumentParser(description="Query a career store")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("labels", parents=[common]).set_defaults(fn=cmd_labels)

    p = sub.add_parser("sql", parents=[common])
    p.add_argument("query")
    p.set_defaults(fn=cmd_sql)

    p = sub.add_parser("output", parents=[common],
                       help="per-player goals/assists/key passes for a club")
    p.add_argument("--club", help="club name, abbreviation or tid (default: us)")
    p.add_argument("--vs", help="only matches against this club")
    p.add_argument("--season", type=int, help="campaign end-year, e.g. 2027 for 2026/27")
    p.add_argument("--since", help="only matches on or after this date (YYYY-MM-DD)")
    p.add_argument("--include-departed", action="store_true",
                   help="also list players no longer at the club")
    p.add_argument("--sort", default="ga",
                   choices=["ga", "goals", "assists", "kp", "shots", "rating", "mins"])
    p.set_defaults(fn=cmd_output)

    p = sub.add_parser("matches", parents=[common])
    p.add_argument("--club", help="default: us")
    p.add_argument("--opp")
    p.add_argument("--season", type=int)
    p.add_argument("--since")
    p.add_argument("--comp", help="competition name substring")
    p.add_argument("--all", action="store_true", help="include friendlies")
    p.set_defaults(fn=cmd_matches)

    p = sub.add_parser("moves", parents=[common],
                       help="squad changes between a snapshot and the latest one")
    p.add_argument("--club", help="default: us")
    p.add_argument("--since", help="compare against the last snapshot on or before this date "
                                   "(default: the previous snapshot)")
    p.set_defaults(fn=cmd_moves)

    p = sub.add_parser("growth", parents=[common], help="a player's attributes over time")
    p.add_argument("player", help="name (substring) or tid")
    p.set_defaults(fn=cmd_growth)

    p = sub.add_parser("table", parents=[common], help="league table from the fixture list")
    p.add_argument("--season", type=int,
                   help="campaign end-year (default: the latest snapshot's season)")
    p.add_argument("--club", help="table of the league this club played in (default: us)")
    p.add_argument("--league", help="league name substring, as of the latest snapshot")
    p.set_defaults(fn=cmd_table)

    p = sub.add_parser("scout", parents=[common], help="opposition report, saved to the log")
    p.add_argument("team", help="opponent name, abbreviation or tid")
    p.add_argument("--method", help="weight-set to rate with (default: the career's)")
    p.add_argument("--venue", choices=["H", "A"])
    p.add_argument("--fixture", help="match date, e.g. 2027-05-02 — keeps the two legs apart")
    p.add_argument("--formation", help="their formation, if fresher than the manager record")
    p.add_argument("--style", help="their style, if fresher than the manager record")
    p.add_argument("--note", help="our plan / key expectations")
    p.add_argument("--no-save", action="store_true")
    p.set_defaults(fn=cmd_scout)

    p = sub.add_parser("scouts", parents=[common], help="list the scout log")
    p.add_argument("--opp")
    p.set_defaults(fn=cmd_scouts)

    p = sub.add_parser("grade", parents=[common], help="grade a saved scout after the match")
    p.add_argument("team")
    p.add_argument("--note", required=True, help="what held, what didn't, and why")
    p.add_argument("--result", help='e.g. "W 2-1 (A)"')
    p.add_argument("--fixture", help="which scout, when there are several")
    p.set_defaults(fn=cmd_grade)

    a = ap.parse_args()
    if a.cmd in NO_STORE and not a.opp:
        a.fn(None, a)
        return
    st = store.open_store(a.career, a.db, refresh=a.refresh, offline=a.offline)
    try:
        a.fn(st, a)
    finally:
        st.con.close()


if __name__ == "__main__":
    sys.exit(main())
