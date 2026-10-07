#!/usr/bin/env python3
"""Export the career as JSON for the web app from the site marts (`site.*`).

    uv run python scripts/export_data.py                      # newest snapshot, default career
    uv run python scripts/export_data.py --snapshot 2028-05-09
    uv run python scripts/export_data.py --season 2028 --phase 2028-05-09
    uv run python scripts/export_data.py --upload-all         # push all.json to R2

Design: ship DATA, not rendered answers. The app computes ratings itself, because a role
rating is just `SUM(attribute x weight)` and the whole weight table is 5 KB — so shipping
attributes plus weights is both SMALLER than shipping precomputed ratings and strictly more
capable. Tactic switching, live weight tuning and fit percentiles then all work in the browser,
offline, for every player, with no rebuild.

The one thing the browser cannot derive is **level**: ability percentiles come from the game's
overall-ability number, and that number must never leave the machine (house rule — see
CLAUDE.md). So level percentiles are precomputed here, per (player, position) and per scope,
and the ability itself is dropped. `check_immersion()` proves no raw-ability key made it out.

Three files by size, because the budget is a phone on cellular:

  api/core.json   ~150 KB   our clubs + every club in the division ladder, full attributes.
                            Loaded on boot; covers squad, compare, recruitment, the profile.
  api/all.json    ~3.9 MB   EVERY player in the save. Lazy — only fetched when you search
                            outside the ladder. **Goes to R2, never to git**: it rewrites
                            wholesale each import and minified JSON deltas badly.
  the rest        ~200 KB   squad detail, the loan outlook, matches. Small, committed.
"""
import argparse
import datetime
import gzip
import json
import os
import shutil
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))

from _export_db import _json_clean                                         # noqa: E402
from dbopen import open_readonly as _open_readonly                    # noqa: E402

R2_REMOTE = os.environ.get("FM_R2_REMOTE", "r2:fmm-stats")
# Absolute, because an agent that only ever saw index.json (no page it was linked from) has no
# base URL to resolve a relative path against — it can only follow links it can already see.
SITE_URL = os.environ.get("FM_SITE_URL", "https://fmm-stats.zac-g-hooper.workers.dev")
BANNED_KEYS = {"ca", "pa", "current_ability", "potential_ability", "aca"}
IMMERSION = ("Ability is expressed as percentiles and division ranks only — the raw ability "
             "number never leaves the machine that built this.")

# --------------------------------------------------------------------------- player rows
PLAYER_FIELDS = ["tid", "name", "club_tid", "dob", "value", "wage", "expiry",
                 "attrs", "positions", "shirt", "height", "weight"]
ALL_PLAYER_FIELDS = PLAYER_FIELDS + ["origin_club_tid", "capital_eligible"]

PROFILE_EXTRA_FIELDS = [
    "nationality", "foot_left", "foot_right", "preferred_squad_number", "joined_date",
    "international_caps", "international_goals", "u21_caps", "u21_goals",
    "reputation", "current_reputation", "world_reputation",
    "adaptability", "ambition", "determination", "loyalty", "pressure",
    "professionalism", "sportsmanship", "temperament", "jumping", "consistency",
    "big_match", "injury_prone", "versatility", "set_pieces", "penalty",
    "work_rate", "flair"]
PROFILE_FIELDS = ALL_PLAYER_FIELDS + PROFILE_EXTRA_FIELDS
PROFILE_COLS = PROFILE_EXTRA_FIELDS


def jdefault(o):
    if isinstance(o, datetime.datetime):
        return o.isoformat()
    if isinstance(o, datetime.date):
        return o.isoformat()[:10]
    if hasattr(o, "item"):
        return o.item()
    return str(o)


def write_json(path, payload, clean=_json_clean):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(clean(payload), f, ensure_ascii=False, default=jdefault,
                  separators=(",", ":"))
    n = os.path.getsize(path)
    with open(path, "rb") as f:
        gz = len(gzip.compress(f.read(), 6))
    return n, gz


def check_immersion(paths):
    """Refuse any raw-ability key at any depth, in any emitted file."""
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
    """One player as the app's positional row (PLAYER_FIELDS, then
    ALL_PLAYER_FIELDS' two and PROFILE_EXTRA_FIELDS with `profile`)."""
    row = [r["tid"], r["name"], r["team_tid"], day(r["dob"]), num(r["value"]),
           num(r["wage_gbp"]), day(r["contract_expiry"]),
           [num(r[a]) for a in attrs],
           [[p["position"], p["familiarity"], pct(p["level_league"]), pct(p["level_global"])]
            for p in (r["positions"] or [])],
           num(r["squad_number"]), num(r["height_cm"]), num(r["weight_kg"])]
    if profile:
        row += [num(r["origin_club_tid"]),
                None if r["capital_eligible"] is None else bool(r["capital_eligible"])]
        row += [day(r[c]) if c == "joined_date" else num(r[c]) for c in PROFILE_COLS]
    return row


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


def main():
    t0 = time.time()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--career")
    ap.add_argument("--snapshot", help="the snapshot date to export (default: the newest)")
    ap.add_argument("--season", type=int, help="snapshot season")
    ap.add_argument("--phase", help="snapshot phase (date)")
    ap.add_argument("--out", default=os.path.join(REPO, "site", "api"))
    ap.add_argument("--method", help="default weight-set (the app can switch client-side)")
    ap.add_argument("--upload-all", action="store_true",
                    help="rclone all.json to R2 (where the Pages Function streams it from)")
    ap.add_argument("--skip-all", action="store_true", help="skip the every-player file")
    ap.add_argument("--no-check", action="store_true")
    a = ap.parse_args()

    out = os.path.abspath(a.out)
    import careers as C
    car = C.resolve_career(a.career or C.DEFAULT_CAREER)
    store = os.environ.get("FM_DUCKDB") or os.path.join(REPO, car.db)
    con, used = _open_readonly(store, tag="export")
    if used != os.path.abspath(store):
        print(f"(live store is locked — exporting from a copy at {used})")
    from fmparser.model import ATTR_ORDER
    attrs = list(ATTR_ORDER)

    if a.snapshot:
        d = a.snapshot
    elif a.season and a.phase:
        d = con.execute("SELECT snapshot_date FROM site.snapshots WHERE season = ? AND phase = ?",
                        [a.season, a.phase]).fetchone()
        if not d:
            raise SystemExit(f"no snapshot {a.season}/{a.phase} in this store")
        d = d[0]
    else:
        d = con.execute(
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
        n, gz = write_json(os.path.join(out, name), payload, _json_clean)
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
    squad_pids = {q["person_id"] for q in squad}
    keep_teams = {c["team_tid"] for c in clubs
                  if c["league_cid"] in {cid for cid, _ in ladder[:3]}} | set(our_tids)

    emit("core.json", {
        "attrs": attrs,
        "fields": PLAYER_FIELDS,
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
            "profile_fields": PROFILE_EXTRA_FIELDS,
            "profile": {str(q["tid"]): player_row(by_pid[q["person_id"]], attrs, True)[14:]
                        for q in squad}},
        "note": IMMERSION,
        # the ladder clubs' players, and our squad wherever their records are: a loanee to
        # us is at his parent club's team, and the app finds our squad by squad_tids
        "players": [player_row(p, attrs) for p in players
                    if p["team_tid"] in keep_teams or p["person_id"] in squad_pids]})

    emit("clubs.json", {
        "club_fields": ["tid", "name", "league_cid", "league_name", "nation", "reputation"],
        "clubs": [[c["team_tid"], c["name"], c["league_cid"], c["league_name"], c["nation"],
                   c["reputation"]] for c in clubs],
        "note": "Every club in the save. No players or attributes here — see core.json (ladder "
                "clubs, full attributes) or /api/all (every player) for those."})

    all_path = os.path.join(out, "all.json")
    if not a.skip_all:
        emit("all.json", {"attrs": attrs, "fields": PROFILE_FIELDS,
                          "players": [player_row(p, attrs, True) for p in players],
                          "note": IMMERSION})
        if a.upload_all:
            if shutil.which("rclone") is None:
                print("  ! rclone not installed — all.json not uploaded")
            else:
                r = subprocess.run(["rclone", "copyto", all_path,
                                    f"{R2_REMOTE}/site-data/all.json"],
                                   capture_output=True, text=True)
                print("  uploaded all.json to R2" if r.returncode == 0
                      else f"  ! upload failed: {(r.stderr or '').strip()[:120]}")

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
                "club is seen only while the save covers it. " + IMMERSION})

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

    # ------------------------------------------------------------ loans.json
    min_fam = int(cfg["min_familiarity"])
    fallback = cfg["fallback_formation"]
    loan_ladder = [(r["cid"], r["name"]) for r in s.rows(
        """SELECT DISTINCT c.league_cid AS cid, l.name, c.ladder_rank
           FROM site.loan_clubs c
           JOIN site.leagues l ON l.snapshot_date = c.snapshot_date AND l.cid = c.league_cid
           WHERE c.snapshot_date = ? ORDER BY c.ladder_rank""", [d])]
    formations = {str(r["team_tid"]): r["formation"] for r in s.rows(
        "SELECT team_tid, formation FROM site.loan_clubs WHERE snapshot_date = ? "
        "ORDER BY league_cid, team_tid", [d])}
    slots = {}
    for r in s.rows("SELECT * FROM site.formation_slots "
                    "ORDER BY formation_order, position_order"):
        slots.setdefault(r["formation"], {})[r["position"]] = r["slots"]
    loans = {}
    for r in s.rows("""SELECT * FROM site.loan_outlook WHERE snapshot_date = ?
                       ORDER BY person_id, familiarity DESC, position, ladder_rank,
                                club_tid""", [d]):
        if r["person_id"] not in tid_of:
            continue
        entry = loans.setdefault(str(tid_of[r["person_id"]]),
                                 {"loaned_to": r["loaned_to_club_tid"], "positions": {}})
        rows = entry["positions"].setdefault(r["position"], [])
        if not rows or rows[-1][0] != r["league_cid"]:
            rows.append([r["league_cid"], pct(r["lvl"]), r["n"], []])
        if r["club_tid"] is not None:
            rows[-1][3].append([r["club_tid"], r["rank"], r["slots"], pct(r["line"])])
    emit("loans.json", {
        "snapshot": {"season": season, "phase": phase, "min_familiarity": min_fam},
        "ladder": [{"cid": c, "name": n} for c, n in loan_ladder],
        "formations": formations,
        "fallback_formation": fallback,
        "slots": slots,
        "row_fields": ["league_cid", "lvl", "n", "clubs"],
        "club_fields": ["club_tid", "rank", "slots", "line"],
        "players": dict(sorted(loans.items(), key=lambda kv: int(kv[0]))),
        "note": "lvl = his Level %ile at the position in that division. Per club: rank = his "
                "place among that club's players at the position (1 = first choice), slots = "
                "how many start there in the manager's preferred formation, line = Level %ile "
                "of the weakest of them (null = the club has no natural player for that slot, "
                "so he walks in). He starts iff rank <= slots. " + IMMERSION})

    # ------------------------------------------------------------ forecast.json
    cells, buckets = {}, {}
    for r in s.rows("""SELECT attribute, age_now, value_now, horizon_age, median, p25, p75,
                              bucket
                       FROM site.forecast
                       ORDER BY attribute, age_now, value_now, horizon_age"""):
        buckets[r["attribute"]] = r["bucket"]
        cells.setdefault(r["attribute"], {}).setdefault(str(r["age_now"]), {}).setdefault(
            str(r["value_now"]), {})[str(r["horizon_age"])] = [
                round(float(r["median"]), 1), round(float(r["p25"])), round(float(r["p75"]))]
    emit("forecast.json", {
        "attrs": attrs,
        "buckets": dict(sorted(buckets.items())),
        "horizons": [21, 24],
        "cells": cells,
        "ageCurve": [[r["age"], round(float(r["median"]), 1), round(float(r["p25"]), 1),
                      round(float(r["p75"]), 1)]
                     for r in s.rows("SELECT age, median, p25, p75 FROM site.age_curve "
                                     "ORDER BY age")],
        "note": "Empirical lookup over the whole save (~25k players tracked across snapshots), "
                "not a per-player prediction: current value + age predicts a future value well "
                "(R^2=0.85 for Crossing), but a starting attribute like Technique does NOT "
                "predict how FAST another attribute grows (+0.000 R^2 beyond current value) — "
                "a technical player is simply already ahead, not accelerating. Fixed attributes "
                "(Agility, Technique) never move in real play; unmodelled ones are decoded too "
                "coarsely outside our own squad to forecast honestly. " + IMMERSION})

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
                # per season, oldest first, the last the season in progress; `season` is the
                # end year of the newest completed one, `live` whether the game updates them
                "seasons": [num(round(float(v), 2)) for v in r["coefficient_history"] or []]
                if any(r["coefficient_history"] or []) else None,
                "season": r["coefficient_season"], "live": bool(r["coefficient_is_live"]),
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
    # History for the World chart: every snapshot's value for each league, club and nation the
    # page lists. Run-length encoded per series as a flat [i0, v0, i1, v1, ...] of change
    # points (i indexes `dates`; v null = absent from that snapshot on): a club's reputation
    # holds still for months at a time, so this is ~5x smaller than one value per snapshot.
    hist_dates = [r["snapshot_date"] for r in s.rows(
        "SELECT snapshot_date FROM site.snapshots ORDER BY snapshot_date")]
    at = {dt: i for i, dt in enumerate(hist_dates)}

    def rle(points):
        out, last = [], object()
        for i in range(len(hist_dates)):
            v = points.get(i)
            if v != last:
                out += [i, v]
                last = v
        return out

    def series(sql, key, fields):
        acc = {}
        for r in s.rows(sql):
            per = acc.setdefault(r[key], {f: {} for f in fields})
            for f, conv in fields.items():
                per[f][at[r["snapshot_date"]]] = conv(r[f])
        return {k: {f: rle(v) for f, v in per.items()} for k, per in acc.items()}

    flt = lambda dp: (lambda v: None if v is None else num(round(float(v), dp)))  # noqa: E731
    lg_hist = series("SELECT snapshot_date, cid, reputation, skill_idx FROM site.leagues",
                     "cid", {"reputation": num, "skill_idx": flt(1)})
    tiers = {r["cid"]: r["tier"] for r in s.rows(
        "SELECT cid, tier FROM site.leagues WHERE snapshot_date = ?", [d])}
    club_hist = series("SELECT snapshot_date, team_tid, reputation FROM site.clubs",
                       "team_tid", {"reputation": num})
    nation_hist = series("""SELECT snapshot_date, name, world_rank, ranking_points, coefficient
                            FROM site.nations""", "name",
                         {"world_rank": num, "ranking_points": flt(0), "coefficient": flt(2)})
    history = {
        "dates": [day(dt) for dt in hist_dates],
        "leagues": {str(r["cid"]): {"tier": tiers.get(r["cid"]), **lg_hist[r["cid"]]}
                    for r in leagues if r["cid"] in lg_hist},
        "clubs": {str(c["team_tid"]): club_hist[c["team_tid"]]["reputation"]
                  for c in clubs if c["squad_size"] > 0 and c["team_tid"] in club_hist},
        "nations": {n["name"]: nation_hist[n["name"]] for n in nations
                    if n["name"] in nation_hist},
    }

    emit("world.json", {
        "our_nation": our_nation,
        "nations": nations,
        "history": history,
        "places": {"denmark": home,
                   "origins": [{"tid": r["team_tid"], "club": r["club"],
                                "players": list(r["players"]), **place(r)}
                               for r in origins if r["latitude"] is not None]},
        "origins_unresolved": unresolved,
        "note": "Nations: world ranking + UEFA coefficient (mart.nations); `seasons` is the "
                "coefficient per season, oldest first, the last the season in progress, `season` "
                "the end year of the newest completed one, `live` false where the game never "
                "updates them. Maps: club stadiums "
                "in our nation's leagues, and our current squad's resolved origin clubs — a "
                "player's origin club can't always be resolved ("
                f"{unresolved} of the current squad aren't shown on the origins map for that "
                "reason, not because they lack one). History: each listed league's reputation "
                "and skill index, each club's reputation and each nation's rank, points and "
                "coefficient on every snapshot in `history.dates`, run-length encoded as flat "
                "[index, value, ...] change points (a null value: absent from then on)."})

    # ------------------------------------------------------------ index.json
    files = {k: f"{SITE_URL}/api/{k}.json" for k in
             ("core", "clubs", "squad", "forecast", "loans", "matches", "registration",
              "world")}
    files["all_players"] = f"{SITE_URL}/api/all"
    files["database"] = f"s3://fmm-stats/site-data/fm-{car.key}.duckdb"
    emit("index.json", {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "career": {"key": car.key, "name": car.name, "managed_tid": managed,
                   "reserve_tid": reserve},
        "snapshot": {"season": season, "phase": phase, "default_method": method,
                     "min_familiarity": int(cfg["min_familiarity"])},
        "snapshots": [{"season": r["season"], "phase": day(r["snapshot_date"]),
                       "label": r["label"]}
                      for r in s.rows("SELECT season, snapshot_date, label "
                                      "FROM site.snapshots ORDER BY snapshot_date")],
        "ladder": [{"cid": c, "name": n} for c, n in ladder[:3]],
        "files": files,
        "agent_guide": f"{SITE_URL}/AGENTS.md",
        "guides": {"scout an opponent": f"{SITE_URL}/guides/scout.md",
                   "register the squad": f"{SITE_URL}/guides/registration.md"},
        "how_to_read_this": ("Rows in core/matches are POSITIONAL ARRAYS with a sibling "
                             "*_fields array naming the slots. Role ratings are NOT stored — "
                             "compute SUM(attribute x weight) from core.tactics, where an "
                             "attribute the role does not list weighs 1. Read AGENTS.md "
                             "first."),
        "counts": {n: {"bytes": b, "gzip": g} for n, b, g in written},
        "immersion_rule": IMMERSION,
        "caveats": INDEX_CAVEATS})

    if not a.no_check:
        bad = check_immersion([os.path.join(out, n) for n, _b, _g in written])
        if bad:
            print("\nIMMERSION RULE VIOLATED — raw ability leaked into exported JSON:")
            for f, k in bad:
                print(f"  {f}: key {k!r}")
            return 1
        print("  immersion check: no raw-ability key in any exported file ✓")
    con.close()
    print(f"done: {len(written)} endpoints exported in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
