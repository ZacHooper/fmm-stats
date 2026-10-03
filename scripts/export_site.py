#!/usr/bin/env python3
"""Export the web app's JSON from the site marts (`site.*`, transform/models/site): the
same files `export_data.py` writes from the old marts, built from the new model, for
comparison until the switch-over (data-layers step 19).

    uv run python scripts/export_site.py --out <dir>                 # newest snapshot
    uv run python scripts/export_site.py --out <dir> --snapshot 2027-06-29
    uv run python scripts/diff_exports.py <old export> <dir>         # the check

Every rule lives in the marts. This script reads `site.*` only, shapes the rows into the
JSON the app reads (positional arrays, dicts keyed by tid) and checks no raw-ability key
left. It never writes into site/api and never uploads: the published files are
export_data.py's until the switch-over.
"""
import argparse
import datetime
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))

import export_data as E                                                    # noqa: E402
from _export_db import _json_clean                                         # noqa: E402
from fmstats import dbopen as _dbopen                                     # noqa: E402

PROFILE_COLS = ["nationality", "foot_left", "foot_right", "preferred_squad_number",
                "joined_date", "international_caps", "international_goals", "u21_caps",
                "u21_goals", "reputation", "current_reputation", "world_reputation",
                "adaptability", "ambition", "determination", "loyalty", "pressure",
                "professionalism", "sportsmanship", "temperament", "jumping", "consistency",
                "big_match", "injury_prone", "versatility", "set_pieces", "penalty",
                "work_rate", "flair"]
assert PROFILE_COLS == E.PROFILE_EXTRA_FIELDS


class Site:
    """The site marts of one store, at one snapshot."""

    def __init__(self, con, snapshot):
        self.con = con
        self.d = snapshot

    def rows(self, sql, params=()):
        cur = self.con.execute(sql, list(params))
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def scalar(self, sql, params=()):
        r = self.con.execute(sql, list(params)).fetchone()
        return r[0] if r else None


def day(v):
    return None if v is None else str(v)[:10]


def num(v):
    """An integer-valued number as int, else as it is."""
    if v is None:
        return None
    if isinstance(v, float):
        return int(v) if v.is_integer() else v
    return int(v) if hasattr(v, "__int__") and not isinstance(v, bool) else v


def pct(v):
    return None if v is None else int(round(float(v)))


def player_row(r, attrs, profile=False):
    """One player as the app's positional row (export_data.PLAYER_FIELDS, then
    ALL_PLAYER_FIELDS' two and PROFILE_EXTRA_FIELDS with `profile`)."""
    row = [r["tid"], r["name"], r["team_tid"], day(r["dob"]), num(r["value"]),
           num(r["wage_gbp"]), day(r["contract_expiry"]),
           [num(r[a]) for a in attrs],
           [[p["position"], p["familiarity"], pct(p["level_league"]), pct(p["level_global"])]
            for p in (r["positions"] or [])],
           num(r["squad_number"]), num(r["height_cm"]), num(r["weight_kg"])]
    if profile:
        row += [num(r["origin_club_tid"]), bool(r["capital_eligible"])]
        row += [day(r[c]) if c == "joined_date" else num(r[c]) for c in PROFILE_COLS]
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--career")
    ap.add_argument("--snapshot", help="the snapshot date to export (default: the newest)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--method", help="default weight-set (the app can switch client-side)")
    ap.add_argument("--min-fam", type=int, default=15)
    ap.add_argument("--skip-all", action="store_true", help="skip the every-player file")
    ap.add_argument("--no-check", action="store_true")
    a = ap.parse_args()

    out = os.path.abspath(a.out)
    if os.path.commonpath([out, os.path.join(REPO, "site")]) == os.path.join(REPO, "site"):
        raise SystemExit("export_site.py writes to a scratch directory, never site/: the "
                         "published files are export_data.py's until the switch-over")
    import careers as C
    car = C.resolve_career(a.career or C.DEFAULT_CAREER)
    store = os.environ.get("FM_DUCKDB") or os.path.join(REPO, car.db)
    con, used = _dbopen.open_readonly(store, tag="export-site")
    from fmparser.model import ATTR_ORDER
    attrs = list(ATTR_ORDER)

    d = a.snapshot or con.execute(
        "SELECT snapshot_date FROM site.snapshots WHERE is_latest").fetchone()[0]
    s = Site(con, d)
    season = s.scalar("SELECT season FROM site.snapshots WHERE snapshot_date = ?", [d])
    if season is None:
        raise SystemExit(f"no snapshot {d} in this store")
    phase = day(d)
    cfg = dict(con.execute("SELECT key, value FROM site.config").fetchall())
    method = a.method or cfg.get("default_method")
    ours = s.rows("SELECT team_tid, is_managed FROM site.our_teams "
                  "ORDER BY is_first_team DESC, team_tid")
    managed = next(t["team_tid"] for t in ours if t["is_managed"])
    reserve = next((t["team_tid"] for t in ours if not t["is_managed"]), None)
    our_tids = [t["team_tid"] for t in ours]
    os.makedirs(out, exist_ok=True)
    print(f"exporting {car.key} {season}/{phase} from site.* -> {out}")

    written = []

    def emit(name, payload):
        n, gz = E.write_json(os.path.join(out, name), payload, _json_clean)
        written.append((name, n, gz))
        print(f"  {name:22} {n / 1024:8.0f} KB raw  {gz / 1024:7.0f} KB gzip")

    # ------------------------------------------------------------ reference tables
    ladder = [(r["cid"], r["name"]) for r in s.rows(
        "SELECT cid, name FROM site.leagues WHERE snapshot_date = ? "
        "AND ladder_rank IS NOT NULL ORDER BY ladder_rank", [d])]
    clubs = s.rows("""SELECT team_tid, name, league_cid, league_name, nation, reputation,
                             squad_size
                      FROM site.clubs WHERE snapshot_date = ? AND is_listed
                      ORDER BY team_tid""", [d])
    listed_leagues = {c["league_cid"] for c in clubs}
    leagues = [r for r in s.rows("""SELECT cid, name, nation, reputation, member_count,
                                           skill_idx, rated
                                    FROM site.leagues
                                    WHERE snapshot_date = ? AND name IS NOT NULL
                                    ORDER BY reputation DESC NULLS LAST, cid""", [d])
               if r["cid"] in listed_leagues]
    tactics = {}
    for r in s.rows("SELECT method, role, attribute, weight FROM site.role_weights "
                    "ORDER BY method, role, attribute"):
        tactics.setdefault(r["method"], {}).setdefault(r["role"], {})[r["attribute"]] = \
            int(r["weight"])
    pos_role = {r["position"]: r["role"] for r in
                s.rows("SELECT position, role FROM site.position_roles ORDER BY position")}
    floor = float(cfg.get("familiarity_floor", 0.5))

    # ------------------------------------------------------------ players
    players = s.rows("SELECT * FROM site.players WHERE snapshot_date = ? ORDER BY tid", [d])
    squad = s.rows("""SELECT q.person_id, p.tid, q.status, q.is_loan_in,
                             q.loaned_to_club_tid
                      FROM site.squad q
                      JOIN site.players p USING (snapshot_date, person_id)
                      WHERE q.snapshot_date = ? ORDER BY p.tid""", [d])
    by_pid = {p["person_id"]: p for p in players}
    keep_teams = {c["team_tid"] for c in clubs
                  if c["league_cid"] in {cid for cid, _ in ladder[:3]}} | set(our_tids)

    emit("core.json", {
        "attrs": attrs,
        "fields": E.PLAYER_FIELDS,
        "clubs": [[c["team_tid"], c["name"], c["league_cid"], c["squad_size"], c["nation"],
                   c["reputation"]] for c in clubs if c["squad_size"] > 0],
        "clubs_without_players": sum(1 for c in clubs if c["squad_size"] == 0),
        "club_fields": ["tid", "name", "league_cid", "players", "nation", "reputation"],
        "leagues": [[r["cid"], r["name"], r["nation"], r["reputation"], r["member_count"],
                     None if r["skill_idx"] is None else float(r["skill_idx"]), r["rated"]]
                    for r in leagues],
        "league_fields": ["cid", "name", "nation", "reputation", "clubs", "skill_idx", "rated"],
        "tactics": tactics,
        "pos_role": pos_role,
        "familiarity": {"curve": cfg.get("familiarity_curve", "linear_floor"),
                        "floor": floor},
        "ours": {
            "clubs": our_tids,
            "managed_tid": managed, "reserve_tid": reserve,
            "status": {str(q["tid"]): q["status"] for q in squad},
            "loaned_in": [q["tid"] for q in squad if q["is_loan_in"]],
            "squad_tids": [q["tid"] for q in squad],
            "origin": {str(q["tid"]): by_pid[q["person_id"]]["origin_club"]
                       for q in squad if by_pid[q["person_id"]].get("origin_club")},
            "capital_eligible": sorted(q["tid"] for q in squad
                                       if by_pid[q["person_id"]]["capital_eligible"]),
            "development": {str(q["tid"]): by_pid[q["person_id"]]["development"]
                            for q in squad if by_pid[q["person_id"]]["development"]},
            "profile_fields": E.PROFILE_EXTRA_FIELDS,
            "profile": {str(q["tid"]): player_row(by_pid[q["person_id"]], attrs, True)[14:]
                        for q in squad}},
        "note": E.IMMERSION,
        "players": [player_row(p, attrs) for p in players
                    if p["team_tid"] in keep_teams]})

    emit("clubs.json", {
        "club_fields": ["tid", "name", "league_cid", "league_name", "nation", "reputation"],
        "clubs": [[c["team_tid"], c["name"], c["league_cid"], c["league_name"], c["nation"],
                   c["reputation"]] for c in clubs],
        "note": "Every club in the save. No players or attributes here — see core.json (ladder "
                "clubs, full attributes) or /api/all (every player) for those."})

    if not a.skip_all:
        emit("all.json", {"attrs": attrs, "fields": E.PROFILE_FIELDS,
                          "players": [player_row(p, attrs, True) for p in players],
                          "note": E.IMMERSION})

    # ------------------------------------------------------------ squad.json
    # Trajectories, spells and moves for the current squad; career history for everyone
    # ever in our squad who is in this snapshot. Keyed by the tid each holds on it.
    tid_of = {p["person_id"]: p["tid"] for p in players}
    cur = [q["person_id"] for q in squad]
    cols = ", ".join(f'"{x}"' for x in attrs)
    traj, spells, moves, chist = {}, {}, {}, {}
    for r in s.rows(f"""SELECT person_id, season, snapshot_date, {cols}
                        FROM site.players JOIN site.snapshots USING (snapshot_date)
                        WHERE person_id IN (SELECT unnest(?))
                        ORDER BY person_id, snapshot_date""", [cur]):
        traj.setdefault(str(tid_of[r["person_id"]]), []).append(
            [r["season"], day(r["snapshot_date"]), [num(r[x]) for x in attrs]])
    for r in s.rows("""SELECT person_id, spell_type, club_tid, from_date, to_date
                       FROM site.player_spells WHERE person_id IN (SELECT unnest(?))
                       ORDER BY person_id, from_date, spell_type, club_tid""", [cur]):
        spells.setdefault(str(tid_of[r["person_id"]]), []).append(
            [r["spell_type"], r["club_tid"], day(r["from_date"]), day(r["to_date"])])
    for r in s.rows("""SELECT person_id, move_date, from_club_tid, to_club_tid, move_type,
                              fee_type, fee_gbp
                       FROM site.player_moves WHERE person_id IN (SELECT unnest(?))
                       ORDER BY person_id, move_date, to_club_tid""", [cur]):
        moves.setdefault(str(tid_of[r["person_id"]]), []).append(
            [day(r["move_date"]), r["from_club_tid"], r["to_club_tid"], r["move_type"],
             r["fee_type"], num(r["fee_gbp"])])
    ever = [pid for (pid,) in con.execute(
        "SELECT DISTINCT person_id FROM site.squad").fetchall() if pid in tid_of]
    for r in s.rows("""SELECT person_id, season, club, fee_label, apps, goals, assists, rating
                       FROM site.player_career WHERE person_id IN (SELECT unnest(?))
                       ORDER BY person_id, line_index""", [ever]):
        chist.setdefault(str(tid_of[r["person_id"]]), []).append({
            "end_year": r["season"], "club": r["club"], "fee": r["fee_label"],
            "apps": r["apps"], "goals": r["goals"], "assists": r["assists"],
            "rating": None if r["rating"] is None else round(float(r["rating"]), 2)})
    emit("squad.json", {
        "attrs": attrs, "trajectories": dict(sorted(traj.items(), key=lambda kv: int(kv[0]))),
        "career_history": dict(sorted(chist.items(), key=lambda kv: int(kv[0]))),
        "spell_fields": ["type", "club_tid", "from", "to"],
        "spells": dict(sorted(spells.items(), key=lambda kv: int(kv[0]))),
        "move_fields": ["date", "from_club_tid", "to_club_tid", "move_type", "fee_type",
                        "fee_gbp"],
        "moves": dict(sorted(moves.items(), key=lambda kv: int(kv[0]))),
        "note": "spells: type is at_club / loan_in / loan_out / injured; `to` null = "
                "ongoing. Injuries are recorded for our squad only, and a spell at another "
                "club is seen only while the save covers it. " + E.IMMERSION})

    # ------------------------------------------------------------ matches.json
    def rowify(rows, fields, rename=None):
        rename = rename or {}
        return [[day(r[rename.get(f, f)]) if f == "date" else r[rename.get(f, f)]
                 for f in fields] for r in rows]

    stats = [c[0][4:] for c in con.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'site' "
        "AND table_name = 'matches' AND column_name LIKE 'our\\_%' ESCAPE '\\' "
        "ORDER BY ordinal_position").fetchall()]
    mfields = ["season", "date", "competition", "venue", "opponent", "opp_tid", "gf", "ga",
               "result", "pts", "formation", "attendance", "stage_kind", "stage", "matchday",
               "leg", "tie_gf", "tie_ga", "went_through", "extra_time", "pens_for",
               "pens_against"] + [f"{side}_{st}" for st in stats for side in ("our", "opp")]
    matches = s.rows("SELECT * FROM site.matches ORDER BY season, match_date, opp_tid")
    pfields = ["season", "tid", "opponent_tid", "date", "competition", "rating", "rating_adj",
               "goals", "assists", "minutes", "started", "position", "passA", "passC",
               "keyPass", "tackA", "tackW", "intercept", "headA", "headW", "crossA", "crossC",
               "dribbles", "shotA", "shotO", "mistakes", "yellow"]
    prename = {"date": "match_date", "passA": "passes", "passC": "passes_completed",
               "keyPass": "key_passes", "tackA": "tackles", "tackW": "tackles_won",
               "intercept": "interceptions", "headA": "headers", "headW": "headers_won",
               "crossA": "crosses", "crossC": "crosses_completed", "shotA": "shots",
               "shotO": "shots_on_target", "yellow": "yellows"}
    apps = s.rows("SELECT * FROM site.match_players ORDER BY season, match_date, tid")
    for r in apps:
        r["rating_adj"] = None if r["rating_adj"] is None else round(r["rating_adj"], 2)
    names = {r["person_id"]: r["name"] for r in s.rows(
        """SELECT person_id, arg_max(name, snapshot_date) AS name FROM site.players
           WHERE person_id IN (SELECT DISTINCT person_id FROM site.match_players)
           GROUP BY person_id""")}
    att_fields = ["season", "n_games", "avg_att", "max_att"]
    fin_fields = ["season", "phase", "n_owned", "n_loan_in", "value_gbp", "n_value_est",
                  "wage_gbp"]
    fin = s.rows("SELECT *, snapshot_date AS phase FROM site.finances ORDER BY snapshot_date")
    for r in fin:
        r["phase"] = day(r["phase"])
        for k in ("value_gbp", "wage_gbp"):
            r[k] = None if r[k] is None else float(r[k])
    emit("matches.json", {
        "match_fields": mfields,
        "matches": rowify(matches, mfields, {"date": "match_date"}),
        "player_fields": pfields,
        "player_rows": rowify(apps, pfields, prename),
        "player_names": {str(t): names[p] for t, p in sorted(
            {(r["tid"], r["person_id"]) for r in apps}) if names.get(p)},
        "attendance_fields": att_fields,
        "attendance": rowify(s.rows("SELECT * FROM site.attendance ORDER BY season"),
                             att_fields),
        "finance_fields": fin_fields,
        "finances": rowify(fin, fin_fields),
        "note": "Only the managed club's matches are richly parsed, so these are our records. "
                "Match detail lives in a fixed-size ring buffer the game overwrites as a "
                "season runs, so an early game may be absent from a late save."})

    # ------------------------------------------------------------ registration.json
    rules = s.rows("""SELECT tier, league_name, a_list_max, hg_min, hg_club_min, b_list_under_age,
                             min_matchday_age, nation, u21_on
                      FROM site.registration_rules WHERE snapshot_date = ?""", [d])
    reg_fields = ["tid", "age", "b_list", "hg_club", "hg_basis", "hg_association",
                  "months_club", "months_to_go", "hg_eta", "window_open", "origin_club",
                  "origin_nation", "via_academy"]
    reg = s.rows("SELECT * FROM site.registration WHERE snapshot_date = ?", [d])
    emit("registration.json", {
        "snapshot": {"season": season, "phase": phase},
        "rules": ({**rules[0], "u21_on": day(rules[0]["u21_on"])} if rules else None),
        "fields": reg_fields,
        "players": sorted(
            [[tid_of[r["person_id"]], num(r["age"]), bool(r["b_list"]), bool(r["hg_club"]),
              r["hg_basis"], bool(r["hg_association"]),
              None if r["months_club"] is None else float(r["months_club"]),
              None if r["months_to_go"] is None else float(r["months_to_go"]),
              day(r["hg_eta"]), bool(r["window_open"]), r["origin_club"], r["origin_nation"],
              bool(r["via_academy"])]
             for r in reg if r["person_id"] in tid_of]),
        "note": "Squad registration is a self-imposed rule — FMM22 does not model it. "
                "Home-grown status is derived from origin club, career history and observed "
                "spells; see docs/danish-registration-rules.md."})

    # ------------------------------------------------------------ world.json
    our_nation = s.scalar("SELECT nation FROM site.clubs WHERE snapshot_date = ? "
                          "AND team_tid = ?", [d, managed])
    nations = [{"name": r["name"], "rank": r["world_rank"],
                "points": None if r["ranking_points"] is None else float(r["ranking_points"]),
                "coefficient": None if r["coefficient"] is None else float(r["coefficient"]),
                "rival": r["rival"]}
               for r in s.rows("SELECT * FROM site.nations WHERE snapshot_date = ? "
                               "ORDER BY world_rank, name", [d])]

    def place(r):
        return {"stadium": r["stadium"], "capacity": num(r["capacity"]),
                "lat": None if r["latitude"] is None else float(r["latitude"]),
                "lon": None if r["longitude"] is None else float(r["longitude"])}

    home = [{"tid": r["team_tid"], "club": r["club"], "league": r["league_name"],
             **place(r), "tier": r["tier"]}
            for r in s.rows("""SELECT * FROM site.places
                               WHERE snapshot_date = ? AND is_listed AND team_type <> 'reserve'
                                 AND nation = ?
                                 AND latitude IS NOT NULL AND longitude IS NOT NULL
                               ORDER BY team_tid""", [d, our_nation])]
    home = [{k: h[k] for k in ("tid", "club", "league", "stadium", "capacity", "lat", "lon",
                               "tier")} for h in home]
    origins = s.rows("""SELECT p.origin_club_tid AS team_tid, any_value(pl.club) AS club,
                               list(p.name ORDER BY p.name) AS players,
                               any_value(pl.stadium) AS stadium,
                               any_value(pl.capacity) AS capacity,
                               any_value(pl.latitude) AS latitude,
                               any_value(pl.longitude) AS longitude
                        FROM site.squad q
                        JOIN site.players p USING (snapshot_date, person_id)
                        LEFT JOIN site.places pl
                          ON pl.snapshot_date = q.snapshot_date
                         AND pl.team_tid = p.origin_club_tid
                        WHERE q.snapshot_date = ? AND p.origin_club_tid IS NOT NULL
                        GROUP BY p.origin_club_tid ORDER BY p.origin_club_tid""", [d])
    unresolved = s.scalar("""SELECT count(*) FROM site.squad q
                             JOIN site.players p USING (snapshot_date, person_id)
                             WHERE q.snapshot_date = ? AND p.origin_club_tid IS NULL""", [d])
    emit("world.json", {
        "our_nation": our_nation,
        "nations": nations,
        "places": {"denmark": home,
                   "origins": [{"tid": r["team_tid"], "club": r["club"],
                                "players": list(r["players"]), **place(r)}
                               for r in origins if r["latitude"] is not None]},
        "origins_unresolved": unresolved,
        "note": "Nations: world ranking + UEFA coefficient (mart.nations). Maps: club stadiums "
                "in our nation's leagues, and our current squad's resolved origin clubs — a "
                f"player's origin club can't always be resolved ({unresolved} of the current "
                "squad aren't shown on the origins map for that reason, not because they lack "
                "one)."})

    # ------------------------------------------------------------ index.json
    files = {k: f"{E.SITE_URL}/api/{k}.json" for k in
             ("core", "clubs", "squad", "forecast", "loans", "matches", "registration",
              "world")}
    files["all_players"] = f"{E.SITE_URL}/api/all"
    files["database"] = f"s3://fmm-stats/site-data/fm-{car.key}.duckdb"
    emit("index.json", {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "career": {"key": car.key, "name": car.name, "managed_tid": managed,
                   "reserve_tid": reserve},
        "snapshot": {"season": season, "phase": phase, "default_method": method,
                     "min_familiarity": a.min_fam},
        "snapshots": [{"season": r["season"], "phase": day(r["snapshot_date"]),
                       "label": r["label"]}
                      for r in s.rows("SELECT season, snapshot_date, label "
                                      "FROM site.snapshots ORDER BY snapshot_date")],
        "ladder": [{"cid": c, "name": n} for c, n in ladder[:3]],
        "files": files,
        "agent_guide": f"{E.SITE_URL}/AGENTS.md",
        "guides": {"scout an opponent": f"{E.SITE_URL}/guides/scout.md",
                   "register the squad": f"{E.SITE_URL}/guides/registration.md"},
        "how_to_read_this": ("Rows in core/matches are POSITIONAL ARRAYS with a sibling "
                             "*_fields array naming the slots. Role ratings are NOT stored — "
                             "compute SUM(attribute x weight) from core.tactics, where an "
                             "attribute the role does not list weighs 1. Read AGENTS.md "
                             "first."),
        "counts": {n: {"bytes": b, "gzip": g} for n, b, g in written},
        "immersion_rule": E.IMMERSION,
        "caveats": INDEX_CAVEATS})

    if not a.no_check:
        bad = E.check_immersion([os.path.join(out, n) for n, _b, _g in written])
        if bad:
            print("\nIMMERSION RULE VIOLATED — raw ability leaked into exported JSON:")
            for f, k in bad:
                print(f"  {f}: key {k!r}")
            return 1
        print("  immersion check: no raw-ability key in any exported file ✓")
    con.close()
    return 0


INDEX_CAVEATS = [
    "Opponent tactics and formation are NOT in the save — ask the manager for the in-game "
    "scout's formation and style before advising on a match.",
    "Opponent attribute values are model estimates (±1) except pace and physicals.",
    "Squad status and loan flags are unreliable; rank by minutes played instead.",
    "Ratings shown are computed in the browser from attributes x role weights, so they "
    "follow whichever tactic is selected.",
    "Squad registration (A/B lists, home grown) is a SELF-IMPOSED rule — FMM22 does not model "
    "it and the save contains none of it. Home-grown status is derived; see "
    "guides/registration.md for what the evidence is and where it is thin."]


if __name__ == "__main__":
    sys.exit(main())
