#!/usr/bin/env python3
"""Export the career as JSON for the web app — the data half of the static site.

    uv run python scripts/export_data.py                      # newest snapshot, default career
    uv run python scripts/export_data.py --season 2024 --phase 2023-07-02
    uv run python scripts/export_data.py --upload-all         # push all.json to R2

Design: ship DATA, not rendered answers. The app computes ratings itself, because a role
rating is just `SUM(attribute x weight)` and the whole weight table is 5 KB — so shipping
attributes plus weights is both SMALLER than shipping precomputed ratings and strictly more
capable. Tactic switching, live weight tuning and fit percentiles then all work in the browser,
offline, for every player, with no rebuild.

The one thing the browser cannot derive is **level**: ability percentiles come from the game's
overall-ability number, and that number must never leave the machine (house rule — see
CLAUDE.md). So level percentiles are precomputed here, per (player, position) and per scope,
and the ability itself is dropped. `--check` proves no raw-ability key made it out.

Three files by size, because the budget is a phone on cellular:

  api/core.json   ~150 KB   our clubs + every club in the division ladder, full attributes.
                            Loaded on boot; covers squad, positions, compare, opposition.
  api/all.json    ~3.9 MB   EVERY player in the save. Lazy — only fetched when you search
                            outside the ladder. **Goes to R2, never to git**: it rewrites
                            wholesale each import and minified JSON deltas badly, which is
                            exactly how .git reached 257 MB with the DuckDB stores in it.
  the rest        ~200 KB   squad detail, the position review, matches. Small, committed.

Everything else the app shows — records, awards, per-player match aggregates, H2H, growth
trajectories — is computed in the browser from `matches.json` and `squad.json`, so those
sections need no exporter support and no new file when a question changes.
"""
import argparse
import datetime
import gzip
import json
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))

import _dbopen                                                          # noqa: E402

R2_REMOTE = os.environ.get("FM_R2_REMOTE", "r2:fmm-stats")
BANNED_KEYS = {"ca", "pa", "current_ability", "potential_ability", "aca"}
IMMERSION = ("Ability is expressed as percentiles and division ranks only — the raw ability "
             "number never leaves the machine that built this.")


def jdefault(o):
    if isinstance(o, datetime.datetime):
        return o.isoformat()
    if isinstance(o, datetime.date):
        return o.isoformat()[:10]
    if hasattr(o, "item"):
        return o.item()
    return str(o)


def write_json(path, payload, clean):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(clean(payload), f, ensure_ascii=False, default=jdefault,
                  separators=(",", ":"))
    n = os.path.getsize(path)
    with open(path, "rb") as f:
        gz = len(gzip.compress(f.read(), 6))
    return n, gz


def check_immersion(paths):
    """Refuse any raw-ability key at any depth, in any emitted file.

    A parse rather than a grep: `{"CA": ...}` would slip past a case-sensitive grep, and the
    word 'ca' inside prose would false-positive. Percentiles and ranks are the only sanctioned
    ability exposure and they never use these names."""
    bad = []

    def walk(o, f):
        if isinstance(o, dict):
            for k, v in o.items():
                if str(k).strip().lower() in BANNED_KEYS:
                    bad.append((f, k))
                walk(v, f)
        elif isinstance(o, list):
            for v in o:
                walk(v, f)

    for p in paths:
        if p.endswith(".json") and os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                walk(json.load(fh), os.path.basename(p))
    return bad


# --------------------------------------------------------------------------- player rows
PLAYER_FIELDS = ["tid", "name", "club_tid", "dob", "value", "wage", "expiry",
                 "attrs", "positions"]


def player_rows(db, pd, season, phase, ATTR_ORDER, club_tids=None, levels=None):
    """Columnar player rows: positional arrays, no repeated keys (that alone is ~40% of the
    bytes at this row count). `positions` is [[code, familiarity, lvl_league, lvl_nation,
    lvl_global], ...] — the level percentiles are the sanctioned form of ability, precomputed
    because the browser can't derive them without the number itself."""
    cols = ", ".join(f'pa."{a}"' for a in ATTR_ORDER)
    where, params = "", [season, phase]
    if club_tids is not None:
        where = f" AND p.club_tid IN ({','.join('?' * len(club_tids))})"
        params += list(club_tids)
    df = db.q(f"""SELECT p.tid, p.name, p.club_tid, p.dob, p.player_value, p.wage_gbp,
                         p.contract_expiry, {cols}
                  FROM staging.players p
                  JOIN staging.player_attributes pa USING (season, phase, tid)
                  WHERE p.season=? AND p.phase=? AND NOT p.is_staff{where}""", params)
    pos = db.q("SELECT tid, position, familiarity FROM staging.player_positions "
               "WHERE season=? AND phase=?", [season, phase])
    pmap = {}
    for r in pos.itertuples():
        lv = (levels or {}).get((int(r.tid), r.position), (None, None))
        pmap.setdefault(int(r.tid), []).append(
            [r.position, int(r.familiarity), lv[0], lv[1]])

    def iv(v):
        return None if pd.isna(v) else int(v)

    def sv(v):
        return None if pd.isna(v) else str(v)[:10]

    rows = []
    for r in df.to_dict("records"):
        tid = int(r["tid"])
        rows.append([tid, r["name"] if isinstance(r["name"], str) else None,
                     iv(r["club_tid"]), sv(r["dob"]), iv(r["player_value"]),
                     iv(r["wage_gbp"]), sv(r["contract_expiry"]),
                     [iv(r[a]) for a in ATTR_ORDER], pmap.get(tid, [])])
    return rows


def level_map(db, season, phase, method):
    """{(tid, position): (lvl_league, lvl_global)} from effective_table, which already
    EXCLUDEs the ability number — so this is the only ability that ever ships, and only as a
    percentile."""
    eff = db.effective_table(season, phase, method)

    def pc(v):
        return None if v != v else int(round(float(v)))

    return {(int(r.tid), r.position): (pc(r.level_league), pc(r.level_global))
            for r in eff.itertuples()}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--career")
    ap.add_argument("--season", type=int)
    ap.add_argument("--phase")
    ap.add_argument("--method", help="default weight-set (the app can switch client-side)")
    ap.add_argument("--min-fam", type=int, default=None)
    ap.add_argument("--out", default=os.path.join(REPO, "site", "api"))
    ap.add_argument("--upload-all", action="store_true",
                    help="rclone all.json to R2 (where the Pages Function streams it from)")
    ap.add_argument("--skip-all", action="store_true",
                    help="skip the 3.9 MB every-player export (faster iteration)")
    ap.add_argument("--no-check", action="store_true")
    a = ap.parse_args()

    if a.career:
        os.environ["FM_CAREER"] = a.career
    from fmparser import careers as C
    car = C.resolve_career(a.career or C.DEFAULT_CAREER)
    store = os.environ.get("FM_DUCKDB") or os.path.join(REPO, car.db)
    if not os.path.exists(store):
        raise SystemExit(f"no store at {store} — build it with scripts/rebuild.py")
    con, used = _dbopen.open_readonly(store, tag="export")
    con.close()
    if used != os.path.abspath(store):
        print(f"(live store is locked — exporting from a copy at {used})")
    os.environ["FM_DUCKDB"] = used
    os.environ["FM_DUCKDB_READONLY"] = "1"

    sys.path.insert(0, os.path.join(REPO, "dashboard"))
    import logging

    class _Quiet(logging.Filter):
        def filter(self, rec):
            return "No runtime found" not in rec.getMessage()

    def quieten():
        f = _Quiet()
        for n in [x for x in logging.root.manager.loggerDict if x.startswith("streamlit")]:
            lg = logging.getLogger(n)
            lg.addFilter(f)
            for h in lg.handlers:
                h.addFilter(f)

    import streamlit                                                   # noqa: F401
    quieten()
    import pandas as pd
    import db
    import positions as P
    quieten()
    from fmparser.attributes import ATTR_ORDER

    season, phase = a.season, a.phase
    if season is None or phase is None:
        s, p = db.latest_snapshot()
        season, phase = season or s, phase or p
    if season is None:
        raise SystemExit("no snapshots loaded in this store")
    method = a.method or db.config().get("default_method") or db.methods()[0]
    min_fam = P.DEFAULT_MIN_FAM if a.min_fam is None else a.min_fam
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    built = datetime.datetime.now().isoformat(timespec="seconds")
    print(f"exporting {car.key} {season}/{phase} · default tactic {method} -> {out}")

    written = []

    def emit(name, payload):
        n, gz = write_json(os.path.join(out, name), payload, db._json_clean)
        written.append((name, n, gz))
        print(f"  {name:22} {n / 1024:8.0f} KB raw  {gz / 1024:7.0f} KB gzip")
        return n

    # ---------------------------------------------------------------- reference tables
    ladder = db.comparison_leagues(season, phase, limit=3)
    ladder = [(c, n) for c, n in ladder if c is not None]
    ladder_cids = [c for c, _ in ladder]

    clubs = db.q("""WITH cl AS (
        SELECT club_tid, arg_max(league_cid, ord) AS league_cid FROM (
          SELECT club_tid, league_cid,
                 LPAD(CAST(season AS VARCHAR),4,'0') || phase AS ord
          FROM staging.league_members WHERE source='club_league' AND league_cid IS NOT NULL)
        GROUP BY club_tid)
        SELECT c.tid, any_value(c.name) AS name, any_value(cl.league_cid) AS league_cid,
               COUNT(DISTINCT p.tid) AS players
        FROM staging.clubs c
        LEFT JOIN cl ON cl.club_tid = c.tid
        LEFT JOIN staging.players p
          ON p.tid IS NOT NULL AND p.club_tid = c.tid AND p.season=? AND p.phase=?
             AND NOT p.is_staff
        WHERE c.season=? AND c.phase=? GROUP BY c.tid""", [season, phase, season, phase])
    leagues = db.q("""SELECT cid, any_value(name) AS name, any_value(nation) AS nation,
                             max(reputation) AS reputation, max(member_count) AS clubs
                      FROM staging.leagues WHERE season=? AND phase=? AND name IS NOT NULL
                      GROUP BY cid ORDER BY reputation DESC NULLS LAST""", [season, phase])
    # Skill index: average player ability per league, normalised 0-100 across ranked leagues.
    # Immersion-safe in the same way the Level percentile is — a CA-DERIVED INDEX, never the
    # number. The raw average is computed here and dropped before anything is written, so the
    # ability itself cannot leave even by accident.
    skill = db.q("""WITH cl AS (
        SELECT club_tid, arg_max(league_cid, ord) AS league_cid FROM (
          SELECT club_tid, league_cid,
                 LPAD(CAST(season AS VARCHAR),4,'0') || phase AS ord
          FROM staging.league_members WHERE source='club_league' AND league_cid IS NOT NULL)
        GROUP BY club_tid)
        SELECT cl.league_cid AS cid, AVG(p.ca) AS aca, COUNT(*) AS rated
        FROM staging.players p JOIN cl ON cl.club_tid = p.club_tid
        WHERE p.season=? AND p.phase=? AND NOT p.is_staff AND p.ca IS NOT NULL
        GROUP BY cl.league_cid HAVING COUNT(*) >= 20""", [season, phase])
    skill_idx = {}
    if not skill.empty:
        lo, hi = float(skill["aca"].min()), float(skill["aca"].max())
        rng = (hi - lo) or 1.0
        for r in skill.itertuples():
            skill_idx[int(r.cid)] = (round(100 * (float(r.aca) - lo) / rng, 1), int(r.rated))
    del skill                                   # the raw averages never reach a payload

    rw = db.q("SELECT method, role, attribute, weight FROM staging.role_weights")
    tactics = {}
    for r in rw.itertuples():
        tactics.setdefault(r.method, {}).setdefault(r.role, {})[r.attribute] = int(r.weight)
    prm = db.q("SELECT position, role FROM staging.position_role_map")
    curve, floor = db.familiarity_params()

    # ---------------------------------------------------------------- our squad extras
    sq = db.squad(season, phase)
    elig = db.eligibility_frame(season, phase)
    origin = dict(zip(elig["tid"], elig["origin_club"])) if not elig.empty else {}
    capital = {int(t) for t, e in zip(elig["tid"], elig["eligible"]) if e} \
        if not elig.empty else set()
    has_loan = not db.q("SELECT 1 AS ok FROM information_schema.columns WHERE "
                        "table_schema='staging' AND table_name='players' AND "
                        "column_name='loaned_in'").empty
    loaned_in = [int(t) for t in db.q(
        "SELECT tid FROM staging.players WHERE season=? AND phase=? AND loaned_in",
        [season, phase])["tid"]] if has_loan else []

    levels = level_map(db, season, phase, method)

    # ---------------------------------------------------------------- core.json
    keep = set(int(t) for t in clubs.loc[clubs["league_cid"].isin(ladder_cids), "tid"])
    keep |= {int(t) for t in db.OUR_CLUBS if t}
    core_players = player_rows(db, pd, season, phase, ATTR_ORDER,
                               club_tids=sorted(keep), levels=levels)
    emit("core.json", {
        "attrs": list(ATTR_ORDER),
        "fields": PLAYER_FIELDS,
        "players": core_players,
        # only clubs with a squad: an empty club can't be rendered anywhere, and they were
        # half the rows. The count is reported so their absence is stated, not silent.
        "clubs": [[int(r.tid), r.name, None if pd.isna(r.league_cid) else int(r.league_cid),
                   int(r.players)] for r in clubs.itertuples() if int(r.players) > 0],
        "clubs_without_players": int((clubs["players"] == 0).sum()),
        "club_fields": ["tid", "name", "league_cid", "players"],
        "leagues": [[int(r.cid), r.name, r.nation,
                     None if pd.isna(r.reputation) else int(r.reputation),
                     None if pd.isna(r.clubs) else int(r.clubs),
                     skill_idx.get(int(r.cid), (None, None))[0],
                     skill_idx.get(int(r.cid), (None, None))[1]]
                    for r in leagues.itertuples()],
        "league_fields": ["cid", "name", "nation", "reputation", "clubs", "skill_idx", "rated"],
        "tactics": tactics,
        "pos_role": dict(zip(prm["position"], prm["role"])),
        "familiarity": {"curve": curve, "floor": floor},
        "ours": {
            "clubs": [int(t) for t in db.OUR_CLUBS if t],
            "managed_tid": db.MANAGED_CLUB_TID, "reserve_tid": db.RESERVE_CLUB_TID,
            "status": {str(int(t)): s for t, s in zip(sq["tid"], sq["status"])},
            "loaned_in": loaned_in,
            # our squad only: eligibility_frame covers the whole snapshot, and shipping all
            # 23,799 origin clubs put 556 KB into a file loaded on every page view
            "origin": {str(int(t)): origin[t] for t in sq["tid"]
                       if origin.get(t)},
            "capital_eligible": sorted(capital & {int(t) for t in sq["tid"]})},
        "note": IMMERSION})

    # ---------------------------------------------------------------- squad.json
    # Attributes at EVERY snapshot, so the app can draw growth under any tactic — the
    # trajectory is the thing Development exists for, and it can't be recovered from one slice.
    ours_tids = sorted({int(t) for t in db.q(
        f"SELECT DISTINCT tid FROM staging.players WHERE club_tid IN "
        f"({','.join('?' * len(db.OUR_CLUBS))}) AND NOT is_staff",
        list(db.OUR_CLUBS))["tid"]})
    # note: ours_tids is EVER-ours (career history is worth keeping for a player who left);
    # trajectories below use only the CURRENT squad.
    # Every snapshot the player EXISTS in, not only the ones he spent with us. A summer
    # signing was in the save all along at another club, and his growth before he arrived is
    # exactly what you want to see when judging him — filtering on club_tid gave every new
    # arrival a blank trend.
    #
    # Widening to the whole file means crossing tid recycling: a tid retired and reissued to a
    # newgen would splice two different people into one trajectory. keep_current_person drops
    # the slices where this tid belonged to somebody else (a no-op for tids never reused).
    cur_tids = sorted({int(t) for t in db.squad(season, phase)["tid"]})
    cols = ", ".join(f'pa."{x}"' for x in ATTR_ORDER)
    hist = db.q(f"""SELECT pa.season, pa.phase, pa.tid, {cols}
                    FROM staging.player_attributes pa
                    WHERE pa.tid IN ({','.join('?' * len(cur_tids))})
                    ORDER BY pa.season, pa.phase""", cur_tids) if cur_tids else pd.DataFrame()
    before = len(hist)
    hist = db.keep_current_person(hist)
    if len(hist) != before:
        print(f"  (dropped {before - len(hist)} attribute rows where a tid was a different "
              f"person — recycling)")
    traj = {}
    for r in hist.to_dict("records"):
        traj.setdefault(str(int(r["tid"])), []).append(
            [int(r["season"]), r["phase"],
             [None if pd.isna(r[x]) else int(r[x]) for x in ATTR_ORDER]])
    # Career history repeats in every snapshot, so read it from the requested one only —
    # a UNION across snapshots would multiply every season row by 12.
    careers = db.q(f"""SELECT h.tid, h.end_year, h.club_tid, c.name AS club, h.fee,
                              h.apps, h.goals, h.assists, h.rating
                       FROM staging.player_history_seasons h
                       LEFT JOIN staging.clubs c
                         ON (c.season, c.phase, c.tid) = (h.season, h.phase, h.club_tid)
                       WHERE h.season=? AND h.phase=?
                         AND h.tid IN ({','.join('?' * len(ours_tids))})
                       ORDER BY h.tid, h.seq""", [season, phase, *ours_tids]) \
        if ours_tids else pd.DataFrame()
    chist = {}
    for r in (careers.to_dict("records") if not careers.empty else []):
        chist.setdefault(str(int(r["tid"])), []).append({
            "end_year": None if pd.isna(r["end_year"]) else int(r["end_year"]),
            "club": r["club"] if isinstance(r["club"], str) else (
                None if pd.isna(r["club_tid"]) else f"#{int(r['club_tid'])}"),
            "fee": r["fee"] if isinstance(r["fee"], str) else None,
            "apps": None if pd.isna(r["apps"]) else int(r["apps"]),
            "goals": None if pd.isna(r["goals"]) else int(r["goals"]),
            "assists": None if pd.isna(r["assists"]) else int(r["assists"]),
            "rating": None if pd.isna(r["rating"]) else round(float(r["rating"]), 2)})
    emit("squad.json", {"attrs": list(ATTR_ORDER), "trajectories": traj,
                        "career_history": chist, "note": IMMERSION})

    # ---------------------------------------------------------------- positions.json
    D = P.build(season, phase, method, min_fam=min_fam, excl_loanees=True)
    if "error" in D:
        print(f"  ! position review unavailable: {D['error']}")
        emit("positions.json", {"error": D["error"]})
    else:
        emit("positions.json", {
            "snapshot": {"season": season, "phase": phase, "method": method,
                         "min_familiarity": min_fam, "slots": D["slots"],
                         "division": D["our_lg"], "division_cid": D["our_cid"],
                         "ladder": [{"cid": c, "name": n} for c, n in D["ladder"]]},
            # Server-side because ability ranks need the ability number. Everything else in
            # the app recomputes on a tactic switch; this one is pinned to `method`.
            "summary": [{**{k: v for k, v in r._asdict().items() if k != "Index"},
                         "rank_ours": (list(r.rank_ours) if r.rank_ours else None)}
                        for r in D["summary"].itertuples()],
            "depth": [{"role": role, "slots": D["slots"].get(role, 1),
                       "players": [{
                           "tid": int(r["tid"]), "depth": int(r["depth"]),
                           "position": r["position"],
                           "familiarity": int(r["familiarity"]),
                           "fit_pctile_division": r["fit_div"],
                           "ability_pctile_division": r["div_pct"],
                           "ability_rank": {str(c): list(D["ranks"][(int(r["tid"]),
                                                                     r["position"], c)])
                                            for c, _ in D["ladder"]
                                            if (int(r["tid"]), r["position"], c) in D["ranks"]},
                           "first_choice_below": {
                               str(c): D["starts_at"].get((int(r["tid"]), r["position"], c), 0)
                               for c, _ in D["lower"]},
                           "hosts": {str(c): [[h.club, int(h.rank), int(h.n)]
                                              for h in D["best_hosts"][
                                                  (int(r["tid"]), r["position"], c)]
                                              .head(5).itertuples()]
                                     for c, _ in D["lower"]
                                     if (int(r["tid"]), r["position"], c) in D["best_hosts"]},
                           "read": r["read"], "also": r["also"]}
                           for _, r in D["per_role"][D["per_role"]["role"] == role]
                           .sort_values("eff", ascending=False).iterrows()]}
                      for role in D["roles_present"]],
            "note": IMMERSION})

    # ---------------------------------------------------------------- matches.json
    # Raw-ish: the app computes records, awards, H2H, per-player aggregates and differentials
    # from this. One dataset instead of four pages' worth of precomputed answers.
    hist_m = db.our_match_history()
    mps = db.match_stats_rows(db.OUR_CLUBS)
    mfields = ["season", "date", "competition", "venue", "opponent", "opp_tid", "gf", "ga",
               "result", "pts", "formation"]
    if not hist_m.empty:      # dedupe: opp_tid is already in the identity block above
        mfields += [c for c in hist_m.columns
                    if c.startswith(("our_", "opp_")) and c not in mfields]
    pfields = ["season", "tid", "opponent_tid", "date", "competition", "rating", "goals",
               "assists", "minutes", "started", "passA", "passC", "keyPass", "tackA",
               "tackW", "intercept", "headA", "headW", "crossA", "crossC", "dribbles",
               "shotA", "shotO", "mistakes", "yellow"]

    def rowify(df, fields):
        if df is None or df.empty:
            return []
        have = [f for f in fields if f in df.columns]
        recs = df[have].to_dict("records")
        return [[None if pd.isna(r[f]) else (r[f].isoformat()[:10]
                                             if hasattr(r[f], "isoformat") else
                                             (bool(r[f]) if isinstance(r[f], bool) else r[f]))
                 for f in have] for r in recs]

    emit("matches.json", {
        "match_fields": [f for f in mfields if not hist_m.empty and f in hist_m.columns],
        "matches": rowify(hist_m, mfields),
        "player_fields": [f for f in pfields if mps is not None and not mps.empty
                          and f in mps.columns],
        "player_rows": rowify(mps[mps["appeared"]] if mps is not None and not mps.empty
                              else mps, pfields),
        "note": "Only the managed club's matches are richly parsed, so these are our records. "
                "Match detail lives in a fixed-size ring buffer the game overwrites as a "
                "season runs, so an early game may be absent from a late save."})

    # ---------------------------------------------------------------- all.json (R2, not git)
    all_path = os.path.join(out, "all.json")
    if a.skip_all:
        print("  all.json               skipped (--skip-all)")
    else:
        rows = player_rows(db, pd, season, phase, ATTR_ORDER, levels=levels)
        n, gz = write_json(all_path, {"attrs": list(ATTR_ORDER), "fields": PLAYER_FIELDS,
                                      "players": rows, "note": IMMERSION}, db._json_clean)
        print(f"  all.json               {n / 1024:8.0f} KB raw  {gz / 1024:7.0f} KB gzip  "
              f"({len(rows)} players — R2 only, NOT git)")
        written.append(("all.json", n, gz))
        if a.upload_all:
            if shutil.which("rclone") is None:
                print("  ! rclone not installed — all.json not uploaded")
            else:
                r = subprocess.run(["rclone", "copyto", all_path,
                                    f"{R2_REMOTE}/site-data/all.json"],
                                   capture_output=True, text=True)
                print("  uploaded all.json to R2" if r.returncode == 0
                      else f"  ! upload failed: {(r.stderr or '').strip()[:120]}")

    # ---------------------------------------------------------------- index.json
    emit("index.json", {
        "generated_at": built,
        "career": {"key": car.key, "name": car.name,
                   "managed_tid": db.MANAGED_CLUB_TID, "reserve_tid": db.RESERVE_CLUB_TID},
        "snapshot": {"season": season, "phase": phase, "default_method": method,
                     "min_familiarity": min_fam},
        "snapshots": db.labels_df()[["season", "phase", "label"]].to_dict("records"),
        "ladder": [{"cid": c, "name": n} for c, n in ladder],
        "files": {"core": "api/core.json", "squad": "api/squad.json",
                  "positions": "api/positions.json", "matches": "api/matches.json",
                  "all_players": "/api/all"},
        "counts": {n: {"bytes": b, "gzip": g} for n, b, g in written},
        "immersion_rule": IMMERSION,
        "caveats": [
            "Opponent tactics and formation are NOT in the save — ask the manager for the "
            "in-game scout's formation and style before advising on a match.",
            "Opponent attribute values are model estimates (±1) except pace and physicals.",
            "Squad status and loan flags are unreliable; rank by minutes played instead.",
            "staging.standings parses only partially for this career, so there is no league "
            "table; divisions are ranked by squad strength instead.",
            "Ratings shown are computed in the browser from attributes x role weights, so "
            "they follow whichever tactic is selected."]})

    if not a.no_check:
        paths = [os.path.join(out, n) for n, _b, _g in written]
        bad = check_immersion(paths)
        if bad:
            print("\nIMMERSION RULE VIOLATED — raw ability leaked into exported JSON:")
            for f, k in bad:
                print(f"  {f}: key {k!r}")
            return 1
        print("  immersion check: no raw-ability key in any exported file ✓")
    total = sum(b for _n, b, _g in written)
    gztot = sum(g for _n, _b, g in written)
    print(f"  {len(written)} files — {total / 1024:.0f} KB raw, {gztot / 1024:.0f} KB gzip")
    return 0


if __name__ == "__main__":
    sys.exit(main())
