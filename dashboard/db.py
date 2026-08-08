"""Shared helpers for the FM dashboard: DuckDB connection, cached queries, and the
sidebar selectors (label + tactic) that every page reuses.

Immersion rule: this dashboard never surfaces CA/PA. Player quality is expressed only
through the weighted role rating and its rank/percentile relative to squad and league.
"""
import datetime
import json
import os
import sys
import unicodedata

import duckdb
import pandas as pd
import streamlit as st

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from fmparser import careers as _careers

# Career-aware: one DuckDB store per managed career (fm-<key>.duckdb). The ACTIVE career
# sets the DB path + which club is "us"; a sidebar selector switches it. These globals are
# (re)assigned by _activate_career() at import and on every switch, so pages that read
# db.MANAGED_CLUB_TID / db.OUR_CLUBS / db.DB_PATH each rerun pick up the change.
ACTIVE_CAREER = None
DB_PATH = None
MANAGED_CLUB_TID = None
RESERVE_CLUB_TID = None
OUR_CLUBS = ()


def _career_db_path(car):
    # FM_DUCKDB overrides (used by the fmq CLI to point at a specific/temp copy).
    return os.environ.get("FM_DUCKDB") or os.path.join(REPO, car.db)


def available_careers():
    """Career keys whose DuckDB store exists on disk, newest-first."""
    found = [(os.path.getmtime(os.path.join(REPO, c.db)), k)
             for k, c in _careers.CAREERS.items()
             if os.path.exists(os.path.join(REPO, c.db))]
    return [k for _, k in sorted(found, reverse=True)]


def _default_career_key():
    return os.environ.get("FM_CAREER") or (available_careers() or [_careers.DEFAULT_CAREER])[0]


def _activate_career(key):
    global ACTIVE_CAREER, DB_PATH, MANAGED_CLUB_TID, RESERVE_CLUB_TID, OUR_CLUBS
    ACTIVE_CAREER = _careers.resolve_career(key)
    DB_PATH = _career_db_path(ACTIVE_CAREER)
    MANAGED_CLUB_TID = ACTIVE_CAREER.managed_tid
    RESERVE_CLUB_TID = ACTIVE_CAREER.reserve_tid
    OUR_CLUBS = tuple(t for t in (MANAGED_CLUB_TID, RESERVE_CLUB_TID) if t)


_activate_career(_default_career_key())
try:
    from fmparser.attributes import ATTR_ORDER
except Exception:  # pragma: no cover
    ATTR_ORDER = ["Aerial", "Crossing", "Dribbling", "Shooting", "Passing", "Tackling",
                  "Technique", "Aggression", "Creativity", "Decisions", "Leadership",
                  "Movement", "Positioning", "Teamwork", "Pace", "Stamina", "Strength",
                  "Agility", "Handling", "Kicking", "Reflexes", "Communication", "Throwing"]

PHASE_ORDER = {"start": 0, "mid": 1, "end": 2}


def _dbver():
    """(DB path, mtime) — cache key so a rebuilt store reconnects transparently AND a
    career switch (different DB path) never serves another store's cached rows."""
    try:
        return (DB_PATH, os.path.getmtime(DB_PATH))
    except OSError:
        return (DB_PATH, 0.0)


@st.cache_resource
def _connect(ver):
    if not os.path.exists(DB_PATH):
        car = ACTIVE_CAREER
        st.error(f"No DuckDB store at {DB_PATH} for career '{car.key if car else '?'}'. "
                 f"Build it with:\n\n"
                 f"`uv run python load_duckdb.py output/<label> --db {car.db if car else 'fm-<career>.duckdb'} "
                 f"--season <YYYY> --phase <start|mid|end>`")
        st.stop()
    # FM_DUCKDB_READONLY=1 lets non-Streamlit callers (e.g. the fmq CLI) attach without
    # taking the single-writer lock, so scouting works while the dashboard is running.
    ro = os.environ.get("FM_DUCKDB_READONLY") == "1"
    return duckdb.connect(DB_PATH, read_only=ro)


def _conn():
    return _connect(_dbver())


@st.cache_data(show_spinner=False)
def _q(sql, params, ver):
    return _conn().execute(sql, list(params)).df()


def q(sql, params=None):
    """Query -> DataFrame, cached by (sql, params, db-mtime)."""
    return _q(sql, tuple(params) if params else (), _dbver())


def write(sql, params=None):
    _conn().execute(sql, params or [])
    st.cache_data.clear()


def phase_key(phase):
    return PHASE_ORDER.get(phase, 9)


# --------------------------------------------------------------------------- selectors

def labels_df():
    df = q("SELECT season, phase, label FROM staging.extracts")
    df["ord"] = df["phase"].map(PHASE_ORDER).fillna(9)
    return df.sort_values(["season", "ord"]).reset_index(drop=True)


def methods():
    df = q("SELECT DISTINCT method FROM staging.role_weights ORDER BY method")
    return df["method"].tolist()


def roles():
    df = q("SELECT DISTINCT role FROM staging.role_weights ORDER BY role")
    return df["role"].tolist()


def select_career(sidebar=True):
    """Managed-career selector (one DuckDB per career). Persists in session_state and
    re-points DB_PATH + the 'us' club when switched. Returns the active career key.
    With a single career on disk it activates silently (no widget)."""
    avail = available_careers()
    box = st.sidebar if sidebar else st
    if len(avail) <= 1:
        key = (avail or [_default_career_key()])[0]
    else:
        default = st.session_state.get("career", _default_career_key())
        if default not in avail:
            default = avail[0]
        key = box.selectbox("Career", avail, index=avail.index(default),
                            format_func=lambda k: _careers.CAREERS[k].name, key="career")
    if not ACTIVE_CAREER or key != ACTIVE_CAREER.key:
        for stale in ("label_sp", "league"):   # DB-specific selections don't carry over
            st.session_state.pop(stale, None)
        _activate_career(key)
    return key


def select_label(sidebar=True):
    """Season+phase selector; persists in session_state. Returns (season, phase)."""
    select_career(sidebar)          # set the active career (DB_PATH + 'us') before querying
    df = labels_df()
    if df.empty:
        st.error("No extracts loaded. Run load_duckdb.py first.")
        st.stop()
    opts = list(df[["season", "phase"]].itertuples(index=False, name=None))
    fmt = lambda sp: f"{sp[0]} · {sp[1]}"
    box = st.sidebar if sidebar else st
    default = st.session_state.get("label_sp", opts[-1])
    idx = opts.index(default) if default in opts else len(opts) - 1
    sp = box.selectbox("Season · phase", opts, index=idx, format_func=fmt, key="label_sp")
    return sp


def select_method(sidebar=True):
    ms = methods()
    box = st.sidebar if sidebar else st
    cfg_default = config().get("default_method", "black_hawk")
    default = st.session_state.get("method", cfg_default if cfg_default in ms else ms[0])
    idx = ms.index(default) if default in ms else 0
    return box.selectbox("Tactic (weight-set)", ms, index=idx, key="method")


# --------------------------------------------------------------------------- data access

def squad(season, phase):
    """Our full squad: first team + reserves (loaned-out players sit in reserves with
    loaned_out=True, so they're included). Carries status flags for the UI."""
    ph = ",".join("?" * len(OUR_CLUBS))
    df = q(f"SELECT tid, name, club_tid, loaned_out FROM staging.players "
           f"WHERE season=? AND phase=? AND club_tid IN ({ph}) AND NOT is_staff",
           [season, phase, *OUR_CLUBS])
    df["label"] = df.apply(lambda r: player_label(r.tid, r["name"]), axis=1)
    df["status"] = df.apply(
        lambda r: "Loan" if r["loaned_out"] else
        ("Reserve" if r["club_tid"] == RESERVE_CLUB_TID else "First team"), axis=1)
    return by_surname(df, "label").reset_index(drop=True)


def squad_tids(season, phase):
    return set(squad(season, phase)["tid"])


def player_label(tid, name):
    # names are frequently missing (NaN/None) — treat any non-string as unnamed
    if isinstance(name, str) and name:
        return name
    return f"#{int(tid)}"


def surname_key(label):
    """Sort key ordering players by surname (last word), then forename. Unnamed
    (#tid) labels sort last. Use as `key=` in sorted()/sort_values."""
    if not isinstance(label, str) or not label or label.startswith("#"):
        return ("~~~", label or "")
    parts = label.split()
    return (parts[-1].lower(), " ".join(parts[:-1]).lower())


def by_surname(df, name_col="label"):
    """Return df ordered by surname of `name_col`."""
    return (df.assign(_sk=df[name_col].map(surname_key))
              .sort_values("_sk").drop(columns="_sk"))


def attributes_row(season, phase, tid):
    """The 23 wide attributes for one player as a {attribute: value} dict."""
    cols = ", ".join(f'"{a}"' for a in ATTR_ORDER)
    df = q(f"SELECT {cols} FROM staging.player_attributes "
           "WHERE season=? AND phase=? AND tid=?", [season, phase, tid])
    if df.empty:
        return None
    return {a: int(df.iloc[0][a]) for a in ATTR_ORDER if df.iloc[0][a] == df.iloc[0][a]}


def role_weight_map(method, role):
    """{attribute_lower: weight} for a (method, role); unlisted attrs are absent (=>1)."""
    df = q("SELECT attribute, weight FROM staging.role_weights "
           "WHERE method=? AND role=?", [method, role])
    return dict(zip(df["attribute"], df["weight"]))


def rating_from_attrs(attr_values, method, role):
    """Compute the weighted rating for an arbitrary {AttrName: value} dict, matching
    v_player_ratings / fm-data-entry (unlisted attributes weight 1)."""
    wmap = role_weight_map(method, role)
    return sum(v * wmap.get(a.lower(), 1) for a, v in attr_values.items())


# --------------------------------------------------------------------------- attribute groups
# Technical/Mental/Physical/Goalkeeping split (covers all 23) for grouped radar + charts.
# Agility lives in Goalkeeping (it's a keeper attribute in FMM).
ATTR_GROUPS = {
    "Technical": ["Crossing", "Dribbling", "Shooting", "Passing", "Tackling",
                  "Technique", "Aerial"],
    "Mental": ["Aggression", "Creativity", "Decisions", "Leadership", "Movement",
               "Positioning", "Teamwork"],
    "Physical": ["Pace", "Stamina", "Strength"],
    "Goalkeeping": ["Agility", "Handling", "Kicking", "Reflexes", "Throwing",
                    "Communication"],
}

# importance -> colour (used instead of ★▲△ symbols)
WEIGHT_COLOR = {4: "#d62728", 3: "#ff7f0e", 2: "#2a9d8f", 1: "#444444"}
WEIGHT_NAME = {4: "key", 3: "important", 2: "useful", 1: "—"}


def attr_group(attribute):
    for g, members in ATTR_GROUPS.items():
        if attribute in members:
            return g
    return "Other"


def color_label(attr, wmap):
    """HTML-coloured attribute label by its weight in the role (for chart tick text)."""
    c = WEIGHT_COLOR.get(wmap.get(attr.lower(), 1), "#444444")
    return f"<span style='color:{c}'>{attr}</span>"


# position code -> pitch unit, for team-level aggregation
POSITION_UNIT = {
    "GK": "GK",
    "DC": "Defense", "DL": "Defense", "DR": "Defense", "DML": "Defense", "DMR": "Defense",
    "DMC": "Midfield", "MC": "Midfield", "ML": "Midfield", "MR": "Midfield",
    "AMC": "Attack", "AML": "Attack", "AMR": "Attack", "ST": "Attack",
}
UNIT_ORDER = ["GK", "Defense", "Midfield", "Attack"]


# --------------------------------------------------------------------------- config
def config():
    df = q("SELECT key, value FROM staging.app_config")
    return dict(zip(df["key"], df["value"]))


def set_config(key, value):
    write("DELETE FROM staging.app_config WHERE key=?", [key])
    _conn().execute("INSERT INTO staging.app_config VALUES (?, ?)", [key, str(value)])
    st.cache_data.clear()


# --------------------------------------------------------------------------- config bundle
# Export/import all tweakable global config as a plain dict (→ JSON in the UI). Same shape is
# baked at build time by load_duckdb.seed_config_bundle, so an exported blob can be committed
# as seeds/config_bundle.json to become the default next build.
def export_config_bundle():
    """{version, app_config, role_weights, position_role_map} — JSON-serialisable."""
    rw = q("SELECT method, role, attribute, category, weight FROM staging.role_weights "
           "ORDER BY method, role, attribute")
    rows = [{"method": r.method, "role": r.role, "attribute": r.attribute,
             "category": r.category, "weight": int(r.weight)} for r in rw.itertuples()]
    return {"version": 1, "app_config": config(), "role_weights": rows,
            "position_role_map": pos_role_map()}


def import_config_bundle(bundle):
    """Apply an exported bundle to the DB. app_config keys are set; role_weights are replaced
    per included method (others untouched); position_role_map replaced if present. Returns a
    summary. Validates before any write so a bad blob can't leave partial state."""
    if not isinstance(bundle, dict):
        raise ValueError("expected a JSON object")
    ac = bundle.get("app_config") or {}
    rows = bundle.get("role_weights") or []
    for r in rows:
        if not all(k in r for k in ("method", "role", "attribute", "weight")):
            raise ValueError("role_weights rows need method, role, attribute, weight")
    prm = bundle.get("position_role_map") or {}

    for k, v in ac.items():
        set_config(k, str(v))
    con = _conn()
    methods = sorted({r["method"] for r in rows})
    if methods:
        ph = ",".join("?" * len(methods))
        con.execute(f"DELETE FROM staging.role_weights WHERE method IN ({ph})", methods)
        con.executemany(
            "INSERT INTO staging.role_weights (method, role, attribute, category, weight) "
            "VALUES (?,?,?,?,?)",
            [(r["method"], r["role"], r["attribute"], r.get("category"), int(r["weight"]))
             for r in rows])
    if prm:
        con.execute("DELETE FROM staging.position_role_map")
        con.executemany("INSERT INTO staging.position_role_map VALUES (?,?)", list(prm.items()))
    st.cache_data.clear()
    return {"app_config": len(ac), "methods": methods, "position_role_map": len(prm)}


def familiarity_params():
    c = config()
    try:
        floor = float(c.get("familiarity_floor", 0.5))
    except ValueError:
        floor = 0.5
    return c.get("familiarity_curve", "linear_floor"), floor


def familiarity_multiplier(fam):
    """Python mirror of _mult_sql for the calculator (entered players)."""
    curve, floor = familiarity_params()
    fam = max(1, min(20, int(fam)))
    if curve == "proportional":
        return fam / 20.0
    if curve == "tiers":
        return (1.0 if fam >= 18 else 0.95 if fam >= 15 else 0.85 if fam >= 10
                else 0.70 if fam >= 5 else 0.50)
    return floor + (1 - floor) * (fam / 20.0)


def _mult_sql(col, curve, floor):
    """SQL expression turning a familiarity value (1..20) into a rating multiplier."""
    if curve == "proportional":
        return f"({col}/20.0)"
    if curve == "tiers":
        return (f"CASE WHEN {col}>=18 THEN 1.0 WHEN {col}>=15 THEN 0.95 "
                f"WHEN {col}>=10 THEN 0.85 WHEN {col}>=5 THEN 0.70 ELSE 0.50 END")
    return f"({floor} + (1-{floor})*({col}/20.0))"          # linear_floor (default)


def pos_role_map():
    df = q("SELECT position, role FROM staging.position_role_map")
    return dict(zip(df["position"], df["role"]))


# --------------------------------------------------------------------------- effective ratings
def effective_table(season, phase, method):
    """Every player × position: base role rating, familiarity multiplier, effective
    rating, and percentile/rank within league / nation / globally at that position.
    Config-driven curve; cached per (season, phase, method, curve, floor)."""
    curve, floor = familiarity_params()
    return _effective_cached(season, phase, method, curve, floor, _dbver())


@st.cache_data(show_spinner=False)
def _effective_cached(season, phase, method, curve, floor, ver):
    mult = _mult_sql("pp.familiarity", curve, floor)
    sql = f"""
    -- resolve each club's league from ANY label that has it (light-results are sparse at
    -- season start, so 2023-start borrows the club's 2022 league). Leagues are stable
    -- within a season; picks the latest label that carries a mapping.
    WITH cl AS (
        SELECT club_tid, arg_max(league_cid, ord) AS league_cid
        FROM (SELECT club_tid, league_cid,
                     season*10 + CASE phase WHEN 'start' THEN 0 WHEN 'mid' THEN 1
                                            ELSE 2 END AS ord
              FROM staging.league_members
              WHERE source='club_league' AND league_cid IS NOT NULL)
        GROUP BY club_tid
    ),
    lgn AS (SELECT cid, any_value(nation) AS nation FROM staging.leagues
            WHERE nation IS NOT NULL GROUP BY cid),
    base AS (
        SELECT pp.tid, pp.position, prm.role, pp.familiarity,
               r.rating AS base_rating, r.rating * {mult} AS eff,
               p.name, p.club, p.club_tid, cl.league_cid, lgn.nation, p.ca
        FROM staging.player_positions pp
        JOIN staging.position_role_map prm ON prm.position = pp.position
        JOIN v_player_ratings r
          ON (r.season, r.phase, r.tid) = (pp.season, pp.phase, pp.tid)
         AND r.method = ? AND r.role = prm.role
        JOIN staging.players p
          ON (p.season, p.phase, p.tid) = (pp.season, pp.phase, pp.tid)
        LEFT JOIN cl ON cl.club_tid = p.club_tid
        LEFT JOIN lgn ON lgn.cid = cl.league_cid
        WHERE pp.season=? AND pp.phase=? AND NOT p.is_staff
    )
    -- `level_*` is a TACTIC-AGNOSTIC quality percentile from the game's overall-ability
    -- number, ranked within the same position/scope windows as the fit percentiles above.
    -- Immersion rule: the raw ability number is NEVER exposed — only this percentile is,
    -- so `ca` is EXCLUDE-d from the projection and must not be re-added downstream.
    SELECT * EXCLUDE (ca),
        ROUND(100*PERCENT_RANK() OVER (PARTITION BY position ORDER BY eff), 1) AS pctile_global,
        ROUND(100*PERCENT_RANK() OVER (PARTITION BY position, nation ORDER BY eff), 1) AS pctile_nation,
        ROUND(100*PERCENT_RANK() OVER (PARTITION BY position, league_cid ORDER BY eff), 1) AS pctile_league,
        ROUND(100*PERCENT_RANK() OVER (PARTITION BY position ORDER BY ca), 1) AS level_global,
        ROUND(100*PERCENT_RANK() OVER (PARTITION BY position, nation ORDER BY ca), 1) AS level_nation,
        ROUND(100*PERCENT_RANK() OVER (PARTITION BY position, league_cid ORDER BY ca), 1) AS level_league,
        RANK() OVER (PARTITION BY position ORDER BY eff DESC) AS rank_global,
        RANK() OVER (PARTITION BY position, nation ORDER BY eff DESC) AS rank_nation,
        RANK() OVER (PARTITION BY position, league_cid ORDER BY eff DESC) AS rank_league,
        COUNT(*) OVER (PARTITION BY position) AS n_global,
        COUNT(*) OVER (PARTITION BY position, nation) AS n_nation,
        COUNT(*) OVER (PARTITION BY position, league_cid) AS n_league
    FROM base
    """
    return _conn().execute(sql, [method, season, phase]).df()


def eligibility_frame(season, phase):
    """Per-player career origin + Athletic-Bilbao eligibility for the snapshot. Returns
    tid, origin_club_tid, origin_club, last_season_club, confidence, eligible (origin in
    staging.eligible_origin_clubs). Only high/medium confidence is reliably aligned."""
    return _eligibility_cached(season, phase, _dbver())


@st.cache_data(show_spinner=False)
def _eligibility_cached(season, phase, ver):
    sql = """
        SELECT h.tid, h.origin_club_tid,
               COALESCE(oc.name, '#' || h.origin_club_tid) AS origin_club,
               COALESCE(lc.name, '#' || h.last_season_club_tid) AS last_season_club,
               h.confidence,
               (e.club_tid IS NOT NULL) AS eligible
        FROM staging.player_history h
        LEFT JOIN staging.clubs oc
          ON (oc.season, oc.phase, oc.tid) = (h.season, h.phase, h.origin_club_tid)
        LEFT JOIN staging.clubs lc
          ON (lc.season, lc.phase, lc.tid) = (h.season, h.phase, h.last_season_club_tid)
        LEFT JOIN staging.eligible_origin_clubs e ON e.club_tid = h.origin_club_tid
        WHERE h.season = ? AND h.phase = ?
    """
    return _conn().execute(sql, [season, phase]).df()


# --------------------------------------------------------------------------- shortlist
# A persistent scouting shortlist, stored in the career's own DuckDB (staging.shortlist,
# GLOBAL — not per season/phase). Each row: a prospect with a snapshot of their attributes
# + positions so it renders even for players not in the current squad/snapshot. `tid` is set
# for players added by look-up (null for manual entries).

def _ensure_shortlist():
    write("""CREATE TABLE IF NOT EXISTS staging.shortlist (
        id BIGINT, tid INTEGER, name VARCHAR,
        positions VARCHAR, attributes VARCHAR, source VARCHAR)""")


def shortlist_get():
    """DataFrame of the shortlist with `positions`/`attributes` parsed to dicts."""
    _ensure_shortlist()
    df = q("SELECT id, tid, name, positions, attributes, source FROM staging.shortlist "
           "ORDER BY name")
    if not df.empty:
        df["positions"] = df["positions"].map(lambda s: json.loads(s) if s else {})
        df["attributes"] = df["attributes"].map(lambda s: json.loads(s) if s else {})
    return df


def shortlist_add(name, positions, attributes, tid=None, source="manual"):
    _ensure_shortlist()
    nid = int(q("SELECT COALESCE(MAX(id), 0) + 1 AS n FROM staging.shortlist")["n"].iloc[0])
    write("INSERT INTO staging.shortlist VALUES (?,?,?,?,?,?)",
          [nid, tid, name, json.dumps(positions or {}),
           json.dumps({k: int(v) for k, v in (attributes or {}).items()}), source])
    return nid


def shortlist_remove(sid):
    _ensure_shortlist()
    write("DELETE FROM staging.shortlist WHERE id = ?", [int(sid)])


def player_search(query, season, phase, limit=50):
    """Players (not staff) whose name matches `query`, for the shortlist look-up."""
    return q("""SELECT tid, name, club, club_tid FROM staging.players
                WHERE season=? AND phase=? AND NOT is_staff AND name ILIKE ?
                ORDER BY name LIMIT ?""", [season, phase, f"%{query}%", limit])


def _ref_date(season, phase):
    """Approx in-game calendar date for a snapshot (season = campaign end-year), for age."""
    if phase == "start":
        return datetime.date(season - 1, 7, 1)
    if phase == "mid":
        return datetime.date(season, 1, 1)
    return datetime.date(season, 5, 1)


def player_bio(season, phase, tids):
    """{tid: {'Age': int|None, 'Value': int|None, 'Club': str}} for the snapshot. Age is
    derived from dob vs the snapshot's approx date; Value is the parsed player value (raw
    units). Wage is NOT parsed from the save, so there's no wage column."""
    tids = [int(t) for t in tids if t is not None]
    if not tids:
        return {}
    ref = _ref_date(season, phase)
    ph = ",".join("?" * len(tids))
    df = q(f"SELECT tid, dob, player_value, club FROM staging.players "
           f"WHERE season=? AND phase=? AND tid IN ({ph})", [season, phase, *tids])
    out = {}
    for r in df.itertuples():
        age = None
        if pd.notna(r.dob):
            d = r.dob if isinstance(r.dob, datetime.date) else pd.to_datetime(r.dob).date()
            age = ref.year - d.year - ((ref.month, ref.day) < (d.month, d.day))
        out[int(r.tid)] = {
            "Age": age,
            "Value": int(r.player_value) if pd.notna(r.player_value) else None,
            "Club": r.club}
    return out


def attach_bio(rows, season, phase, tid_col="tid"):
    """Add Age / Value / Origin / Loan columns to a player frame (keyed by `tid_col`), so any
    player table can expose them. Age & Value from the snapshot; Origin from parsed career
    history; Loan = the parent club for loaned-IN players (else None). Rows with a null tid
    (manual prospects) get None. Returns a copy."""
    r = rows.copy()
    tids = [int(t) for t in r[tid_col].dropna().unique()]
    bio = player_bio(season, phase, tids)
    elig = eligibility_frame(season, phase)
    origin = dict(zip(elig["tid"], elig["origin_club"])) if not elig.empty else {}
    ln = q("SELECT tid, parent_club FROM staging.players "
           "WHERE season=? AND phase=? AND loaned_in", [season, phase])
    loan = dict(zip(ln["tid"], ln["parent_club"])) if not ln.empty else {}

    def _g(t, field):
        return bio.get(int(t), {}).get(field) if pd.notna(t) else None
    r["Age"] = r[tid_col].map(lambda t: _g(t, "Age"))
    r["Value"] = r[tid_col].map(lambda t: _g(t, "Value"))
    r["Origin"] = r[tid_col].map(lambda t: origin.get(int(t)) if pd.notna(t) else None)
    r["Loan"] = r[tid_col].map(lambda t: loan.get(int(t)) if pd.notna(t) else None)
    return r


def player_positions_map(season, phase, tid):
    """{position code: familiarity} for one player in the snapshot."""
    df = q("SELECT position, familiarity FROM staging.player_positions "
           "WHERE season=? AND phase=? AND tid=?", [season, phase, int(tid)])
    return {r.position: int(r.familiarity) for r in df.itertuples()}


def player_match_totals(tids):
    """Career (all-season, deduped by latest phase) match-stat totals per player, for the
    given tids. Returns apps/goals/assists/avg rating + attempt & completion sums so
    callers can show both rates and volume."""
    if not tids:
        return pd.DataFrame()
    ph = ",".join("?" * len(tids))
    return q(f"""
        WITH chosen AS (
            WITH mm AS (SELECT DISTINCT season, phase FROM staging.match_player_stats)
            SELECT season, arg_max(phase, CASE phase WHEN 'start' THEN 0 WHEN 'mid' THEN 1
                                                     ELSE 2 END) AS phase
            FROM mm GROUP BY season)
        SELECT m.tid,
               COUNT(*) AS apps,
               SUM(CASE WHEN m.pos_order <= 11 THEN 1 ELSE 0 END) AS starts,
               SUM(CASE WHEN m.subOff = 255 THEN 90 ELSE m.subOff END
                   - CASE WHEN m.subOn = 255 THEN 0 ELSE m.subOn END) AS minutes,
               SUM(m.goals) AS goals, SUM(m.assists) AS assists,
               ROUND(AVG(m.rating), 2) AS avg_rating,
               SUM(m.passA) AS passA, SUM(m.passC) AS passC,
               SUM(m.tackA) AS tackA, SUM(m.tackW) AS tackW,
               SUM(m.headA) AS headA, SUM(m.headW) AS headW,
               SUM(m.crossA) AS crossA, SUM(m.crossC) AS crossC,
               SUM(m.shotA) AS shotA, SUM(m.shotO) AS shotO,
               SUM(m.intercept) AS intercept, SUM(m.keyPass) AS keyPass
        FROM staging.match_player_stats m
        JOIN chosen ch USING (season, phase)
        WHERE m.tid IN ({ph}) AND (m.pos_order <= 11 OR m.subOn <> 255)
        GROUP BY m.tid""", [*tids])


def match_stats_rows(club_tids):
    """Deduped per-player-per-match rows (latest phase per season) for the given clubs'
    players — the basis for the whole-team match-stat grid."""
    if not club_tids:
        return pd.DataFrame()
    ph = ",".join("?" * len(club_tids))
    return q(f"""
        WITH chosen AS (
            WITH mm AS (SELECT DISTINCT season, phase FROM staging.match_player_stats)
            SELECT season, arg_max(phase, CASE phase WHEN 'start' THEN 0 WHEN 'mid' THEN 1
                                                     ELSE 2 END) AS phase
            FROM mm GROUP BY season)
        SELECT m.season, m.tid, m.team_tid, m.opponent_tid, m.date, m.competition,
               m.rating, m.goals, m.assists, m.passA, m.passC, m.keyPass,
               m.tackA, m.tackW, m.intercept, m.headA, m.headW, m.crossA, m.crossC,
               m.dribbles, m.shotA, m.shotO, m.mistakes, m.yellow,
               (m.pos_order <= 11) AS started,
               (m.pos_order <= 11 OR m.subOn <> 255) AS appeared,
               CASE WHEN (m.pos_order <= 11 OR m.subOn <> 255)
                    THEN (CASE WHEN m.subOff = 255 THEN 90 ELSE m.subOff END)
                       - (CASE WHEN m.subOn = 255 THEN 0 ELSE m.subOn END)
                    ELSE 0 END AS minutes
        FROM staging.match_player_stats m
        JOIN chosen ch USING (season, phase)
        WHERE m.team_tid IN ({ph})""", [*club_tids])


def primary_position_map(tids):
    """tid -> primary position (max familiarity across labels)."""
    if not tids:
        return {}
    ph = ",".join("?" * len(tids))
    df = q(f"""SELECT tid, arg_max(position, familiarity) AS pos
               FROM staging.player_positions WHERE tid IN ({ph}) GROUP BY tid""",
           [*tids])
    return dict(zip(df["tid"], df["pos"]))


def primary_position(season, phase, tid):
    """The position with the highest familiarity (FM's 'natural')."""
    df = q("SELECT position, familiarity FROM staging.player_positions "
           "WHERE season=? AND phase=? AND tid=? ORDER BY familiarity DESC, position",
           [season, phase, tid])
    return df.iloc[0]["position"] if not df.empty else None


# --------------------------------------------------------------------------- match-stat aggregation
# Shared by the Player Stats grid and the Squad-tool comparison so both derive
# identical rates/per-90/per-game figures from the same raw match rows.
MATCH_SUMS = ["goals", "assists", "keyPass", "passA", "passC", "tackA", "tackW",
              "headA", "headW", "crossA", "crossC", "shotA", "shotO", "intercept",
              "dribbles", "mistakes", "yellow"]

_MATCH_PG = {"goals": "G/gm", "assists": "A/gm", "G+A": "G+A/gm", "keyPass": "KeyP/gm",
             "passA": "Passes/gm", "passC": "PassC/gm", "tackA": "Tackles/gm",
             "tackW": "TackW/gm", "intercept": "Int/gm", "headW": "HeadW/gm",
             "crossA": "Crosses/gm", "crossC": "CrossC/gm", "dribbles": "Dribbles/gm",
             "shotA": "Shots/gm", "shotO": "SoT/gm", "defAct": "DefActions/gm",
             "mistakes": "Mistakes/gm", "yellow": "Yellows/gm"}
_MATCH_P90 = {"goals": "G/90", "assists": "A/90", "G+A": "G+A/90", "keyPass": "KeyP/90",
              "passA": "Passes/90", "tackA": "Tackles/90", "tackW": "TackW/90",
              "intercept": "Int/90", "headW": "HeadW/90", "shotA": "Shots/90",
              "defAct": "DefActions/90"}

# display name -> aggregated column (clean, friendly labels for the column picker)
MATCH_STAT_DEFS = {
    # per 90
    "G/90": "G/90", "A/90": "A/90", "G+A/90": "G+A/90", "KeyP/90": "KeyP/90",
    "Passes/90": "Passes/90", "Tackles/90": "Tackles/90", "TackW/90": "TackW/90",
    "Int/90": "Int/90", "HeadW/90": "HeadW/90", "Shots/90": "Shots/90",
    "DefAct/90": "DefActions/90",
    # per game
    "G/gm": "G/gm", "A/gm": "A/gm", "G+A/gm": "G+A/gm", "KeyP/gm": "KeyP/gm",
    "Passes/gm": "Passes/gm", "Tackles/gm": "Tackles/gm", "TackW/gm": "TackW/gm",
    "Int/gm": "Int/gm", "HeadW/gm": "HeadW/gm", "Crosses/gm": "Crosses/gm",
    "Dribbles/gm": "Dribbles/gm", "Shots/gm": "Shots/gm", "SoT/gm": "SoT/gm",
    "DefAct/gm": "DefActions/gm", "Mistakes/gm": "Mistakes/gm", "Yellows/gm": "Yellows/gm",
    # success %
    "Pass %": "Pass %", "Tackle %": "Tackle %", "Header %": "Header %",
    "Cross %": "Cross %", "Shot acc %": "Shot acc %", "Conversion %": "Conversion %",
    # totals
    "Goals": "goals", "Assists": "assists", "G+A": "G+A", "Key passes": "keyPass",
    "Pass att": "passA", "Tackle att": "tackA", "Shot att": "shotA",
    "Interceptions": "intercept", "Dribbles": "dribbles",
}

# position-tuned preset views (stats that matter most for that role)
MATCH_PRESETS = {
    "⚽ Forward": ["G/90", "A/90", "Shots/90", "Shot acc %", "Conversion %", "SoT/gm",
                  "KeyP/90", "Dribbles/gm"],
    "🎯 Winger": ["G/90", "A/90", "KeyP/90", "Crosses/gm", "Cross %", "Dribbles/gm",
                 "Shots/90", "Shot acc %"],
    "🎩 Midfielder": ["Passes/90", "Pass %", "KeyP/90", "A/90", "Tackles/gm", "TackW/90",
                     "Int/90", "DefAct/90"],
    "🛡 Defender": ["TackW/90", "Tackle %", "Int/90", "HeadW/90", "Header %", "DefAct/90",
                   "Pass %", "Mistakes/gm"],
    "🧤 Goalkeeper": ["Pass %", "Passes/90", "Mistakes/gm", "Yellows/gm"],
    "Custom": ["G/gm", "A/gm", "Passes/gm", "Pass %", "Tackles/gm", "Tackle %",
               "Shots/gm", "Shot acc %"],
}

# match-output radar axes (display names from MATCH_STAT_DEFS), scaled per axis
OUTPUT_RADARS = {
    "Attack output": ["G/90", "A/90", "Shots/90", "Shot acc %", "Conversion %",
                      "KeyP/90", "Dribbles/gm"],
    "Midfield output": ["Passes/90", "Pass %", "KeyP/90", "A/90", "Tackles/90", "Int/90"],
    "Defensive output": ["TackW/90", "Tackle %", "Int/90", "HeadW/90", "Header %",
                         "DefAct/90"],
}
# keepers: FMM light-parses GK matches (no saves/clean-sheet counters), so the output
# radar uses the distribution/reliability stats we do have.
GK_OUTPUT_RADAR = ["Pass %", "Passes/90", "KeyP/90", "Yellows/gm"]


def enrich_match_rows(rows):
    """Add player / opponent / pos / unit / squad labels to raw match_stats_rows()."""
    if rows is None or rows.empty:
        return rows
    rows = rows.copy()
    names = q(f"SELECT tid, any_value(name) AS name FROM staging.players "
              f"WHERE club_tid IN ({','.join(str(int(t)) for t in OUR_CLUBS)}) "
              f"GROUP BY tid")
    nmap = dict(zip(names["tid"], names["name"]))
    rows["player"] = rows["tid"].map(lambda t: player_label(t, nmap.get(t)))
    clubs = q("SELECT season, tid, name FROM staging.clubs")
    cmap = {(s, t): n for s, t, n in zip(clubs["season"], clubs["tid"], clubs["name"])}
    rows["opponent"] = [cmap.get((s, t)) or f"#{int(t)}"
                        for s, t in zip(rows["season"], rows["opponent_tid"])]
    posmap = primary_position_map(rows["tid"].unique().tolist())
    rows["pos"] = rows["tid"].map(posmap)
    rows["unit"] = rows["pos"].map(POSITION_UNIT)
    rows["squad"] = rows["team_tid"].map({MANAGED_CLUB_TID: "First team",
                                          RESERVE_CLUB_TID: "Reserve"})
    return rows


def aggregate_match_stats(f):
    """Per-player aggregate of enriched match rows: apps/mins/rating + every counting
    stat summed, plus derived success %, per-game and per-90 figures. Returns a frame
    with all MATCH_STAT_DEFS columns present so callers just pick display names."""
    agg = f.groupby(["tid", "player", "pos"]).agg(
        Apps=("rating", "size"), Starts=("started", "sum"), Min=("minutes", "sum"),
        Rating=("rating", "mean"), **{s: (s, "sum") for s in MATCH_SUMS}).reset_index()
    agg["Rating"] = agg["Rating"].round(2)
    agg["Sub"] = agg["Apps"] - agg["Starts"]
    apps = agg["Apps"].where(agg["Apps"] != 0)
    mins = agg["Min"].where(agg["Min"] > 0)
    agg["Min/gm"] = (agg["Min"] / apps).round(0)

    def _rate(num, den):
        d = agg[den]
        return (100 * agg[num] / d.where(d != 0)).round(0)   # NaN where no attempts

    agg["G+A"] = agg["goals"] + agg["assists"]
    agg["defAct"] = agg["tackW"] + agg["intercept"] + agg["headW"]
    agg["Pass %"] = _rate("passC", "passA")
    agg["Tackle %"] = _rate("tackW", "tackA")
    agg["Header %"] = _rate("headW", "headA")
    agg["Cross %"] = _rate("crossC", "crossA")
    agg["Shot acc %"] = _rate("shotO", "shotA")
    agg["Conversion %"] = _rate("goals", "shotA")          # goals per shot
    for src, name in _MATCH_PG.items():
        agg[name] = (agg[src] / apps).round(2)
    for src, name in _MATCH_P90.items():
        agg[name] = (90 * agg[src] / mins).round(2)
    return agg


def player_match_agg(tids=None):
    """Career (all-season, latest-phase) per-player match aggregate for our clubs,
    optionally restricted to `tids`. Same columns as aggregate_match_stats()."""
    rows = enrich_match_rows(match_stats_rows(OUR_CLUBS))
    if rows is None or rows.empty:
        return pd.DataFrame()
    rows = rows[rows["appeared"]]
    if tids is not None:
        rows = rows[rows["tid"].isin(set(int(t) for t in tids))]
    if rows.empty:
        return pd.DataFrame()
    return aggregate_match_stats(rows)


def attributes_rows(season, phase, tids):
    """Batch {tid: {attribute: value}} for many players in one query (NaN attrs dropped)."""
    tids = [int(t) for t in (tids or [])]
    if not tids:
        return {}
    cols = ", ".join(f'"{a}"' for a in ATTR_ORDER)
    ph = ",".join("?" * len(tids))
    df = q(f"SELECT tid, {cols} FROM staging.player_attributes "
           f"WHERE season=? AND phase=? AND tid IN ({ph})", [season, phase, *tids])
    out = {}
    for _, r in df.iterrows():
        out[int(r["tid"])] = {a: int(r[a]) for a in ATTR_ORDER if pd.notna(r[a])}
    return out


# --------------------------------------------------------------------------- teams
# club->league resolved across ALL labels (latest label that carries a mapping), so
# season-start labels with sparse light-results still get their league.
_RESOLVED_CL = """
    SELECT club_tid, arg_max(league_cid, ord) AS lc FROM (
        SELECT club_tid, league_cid,
               season*10 + CASE phase WHEN 'start' THEN 0 WHEN 'mid' THEN 1 ELSE 2 END AS ord
        FROM staging.league_members WHERE source='club_league' AND league_cid IS NOT NULL)
    GROUP BY club_tid"""


def my_league(season, phase):
    df = q(f"SELECT lc FROM ({_RESOLVED_CL}) WHERE club_tid=?", [MANAGED_CLUB_TID])
    return int(df.iloc[0]["lc"]) if not df.empty and pd.notna(df.iloc[0]["lc"]) else None


def leagues_list(season, phase):
    """Leagues (resolved across labels) with names + nation + club count."""
    return q(f"""WITH res AS ({_RESOLVED_CL})
                 SELECT res.lc AS cid, any_value(lg.name) AS name,
                        any_value(lg.nation) AS nation, COUNT(*) AS clubs
                 FROM res LEFT JOIN staging.leagues lg ON lg.cid=res.lc
                 GROUP BY res.lc ORDER BY clubs DESC""")


def teams_in_league(season, phase, league_cid):
    df = q(f"""WITH res AS ({_RESOLVED_CL})
               SELECT res.club_tid AS tid, any_value(c.name) AS name
               FROM res LEFT JOIN staging.clubs c ON c.tid=res.club_tid
               WHERE res.lc=? GROUP BY res.club_tid""", [league_cid])
    if df.empty:                       # no league data yet (e.g. day-1 save, no results)
        return df
    df["name"] = df.apply(lambda r: r["name"] if isinstance(r["name"], str) and r["name"]
                          else f"#{int(r.tid)}", axis=1)
    return df


def team_player_frame(season, phase, method, club_tids):
    """Per-player rows for the given clubs: 23 attributes + primary position/unit +
    effective rating at primary position. Basis for team aggregates."""
    if not club_tids:
        return pd.DataFrame()
    eff = effective_table(season, phase, method)
    eff = eff[eff["club_tid"].isin(club_tids)].copy()
    if eff.empty:
        return eff
    # primary position row per player (max familiarity)
    prim = eff.loc[eff.groupby("tid")["familiarity"].idxmax()].copy()
    prim["unit"] = prim["position"].map(POSITION_UNIT)
    return prim


def team_attribute_frame(season, phase, method, club_tids):
    """Per-player rows for the given clubs: club_tid, tid, primary position, unit, eff
    rating, and the 23 attributes — the basis for unit/position-filtered team aggregates."""
    tf = team_player_frame(season, phase, method, club_tids)
    if tf.empty:
        return pd.DataFrame()
    ca = club_attributes(season, phase, club_tids)
    if ca.empty:
        return pd.DataFrame()
    base = tf[["tid", "club_tid", "position", "unit", "eff"]]
    return base.merge(ca.drop(columns=["club_tid"]), on="tid", how="inner")


# team-level per-match stats stored on staging.matches (home_/away_ prefixed)
MATCH_TEAM_STATS = ["shots", "shots_on_target", "passes", "passes_completed",
                    "tackles", "tackles_won", "crosses", "interceptions"]


def our_match_history(seasons=None):
    """Per-match frame for the managed club (latest phase per season). Columns: season, date,
    competition, formation, opp_tid, opponent, venue (H/A), gf, ga, result (W/D/L), pts, and
    our_<stat>/opp_<stat> for MATCH_TEAM_STATS. `seasons` filters (None = all). Shared by the
    Match-records page, the Team scout head-to-head, and the Records page."""
    chosen = q("""WITH mm AS (SELECT DISTINCT season, phase FROM staging.matches)
                  SELECT season, arg_max(phase, CASE phase WHEN 'start' THEN 0 WHEN 'mid' THEN 1
                                                           ELSE 2 END) AS phase
                  FROM mm GROUP BY season ORDER BY season""")
    if chosen.empty:
        return pd.DataFrame()
    if seasons is not None:
        chosen = chosen[chosen["season"].isin(list(seasons))]
    sel_cols = ", ".join(f"home_{k}, away_{k}" for k in MATCH_TEAM_STATS)
    frames = []
    for _, r in chosen.iterrows():
        frames.append(q(
            f"""SELECT season, date, competition, formation, home_tid, away_tid,
                       score_home, score_away, {sel_cols}
                FROM staging.matches
                WHERE season=? AND phase=? AND (home_tid=? OR away_tid=?)""",
            [int(r.season), r.phase, MANAGED_CLUB_TID, MANAGED_CLUB_TID]))
    m = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if m.empty:
        return m
    clubs = q("SELECT season, tid, name FROM staging.clubs")
    cmap = {(s, t): n for s, t, n in zip(clubs["season"], clubs["tid"], clubs["name"])}
    home = m["home_tid"] == MANAGED_CLUB_TID
    m["opp_tid"] = m["away_tid"].where(home, m["home_tid"])
    m["opponent"] = [cmap.get((s, t)) or f"#{int(t)}"
                     for s, t in zip(m["season"], m["opp_tid"])]
    m["venue"] = home.map({True: "H", False: "A"})
    m["gf"] = m["score_home"].where(home, m["score_away"])
    m["ga"] = m["score_away"].where(home, m["score_home"])
    m["result"] = m.apply(lambda r: "W" if r.gf > r.ga else ("D" if r.gf == r.ga else "L"),
                          axis=1)
    m["pts"] = m["result"].map({"W": 3, "D": 1, "L": 0})
    for k in MATCH_TEAM_STATS:
        m[f"our_{k}"] = m[f"home_{k}"].where(home, m[f"away_{k}"])
        m[f"opp_{k}"] = m[f"away_{k}"].where(home, m[f"home_{k}"])
    return m


def our_penalties(seasons=None):
    """Chronological penalties taken by our players (from match_events, latest phase per
    season, joined to match dates). Columns: season, date, minute, seq, tid, player,
    made (bool: 'penalty'=scored, 'missed_penalty'=missed). For penalty-streak records."""
    df = q("""
        WITH ours AS (SELECT DISTINCT tid FROM staging.players WHERE club_tid IN (?, ?)),
             chosen AS (
               WITH mm AS (SELECT DISTINCT season, phase FROM staging.match_events)
               SELECT season, arg_max(phase, CASE phase WHEN 'start' THEN 0 WHEN 'mid' THEN 1
                                                        ELSE 2 END) AS phase
               FROM mm GROUP BY season),
             nm AS (SELECT tid, any_value(name) AS name FROM staging.players GROUP BY tid)
        SELECT e.season, m.date, m.competition, e.minute, e.seq, e.tid, nm.name AS player,
               (e.type = 'penalty') AS made
        FROM staging.match_events e
        JOIN chosen ch USING (season, phase)
        JOIN staging.matches m ON (e.season, e.phase, e.anchor) = (m.season, m.phase, m.anchor)
        JOIN ours o ON e.tid = o.tid
        LEFT JOIN nm ON nm.tid = e.tid
        WHERE e.type IN ('penalty', 'missed_penalty')
        ORDER BY m.date, e.minute, e.seq""", [MANAGED_CLUB_TID, RESERVE_CLUB_TID])
    if seasons is not None and not df.empty:
        df = df[df["season"].isin(list(seasons))]
    return df


def our_goal_events(seasons=None):
    """Ordered goal-type match_events for our matches (latest phase per season) with our
    perspective. Columns: season, date, competition, anchor, minute, seq, our_goal (bool —
    goal for us), venue, opponent, gf, ga, result. Events reconcile the scoreline ~99%, so a
    per-match running score is reliable (biggest-comeback records)."""
    df = q("""
        WITH ours AS (SELECT DISTINCT tid FROM staging.players WHERE club_tid IN (?, ?)),
             chosen AS (WITH mm AS (SELECT DISTINCT season, phase FROM staging.match_events)
                        SELECT season, arg_max(phase, CASE phase WHEN 'start' THEN 0
                                 WHEN 'mid' THEN 1 ELSE 2 END) AS phase FROM mm GROUP BY season)
        SELECT e.season, m.date, m.competition, e.anchor, e.minute, e.seq, e.type,
               (m.home_tid = ?) AS us_home, m.home_tid, m.away_tid,
               m.score_home, m.score_away, (e.tid IN (SELECT tid FROM ours)) AS by_us
        FROM staging.match_events e
        JOIN chosen ch USING (season, phase)
        JOIN staging.matches m ON (e.season, e.phase, e.anchor) = (m.season, m.phase, m.anchor)
        WHERE (m.home_tid = ? OR m.away_tid = ?) AND e.type IN ('goal', 'penalty', 'own_goal')
        ORDER BY m.date, e.anchor, e.minute, e.seq""",
           [MANAGED_CLUB_TID, RESERVE_CLUB_TID, MANAGED_CLUB_TID,
            MANAGED_CLUB_TID, MANAGED_CLUB_TID])
    if df.empty:
        return df
    og = df["type"] == "own_goal"
    df["our_goal"] = (~og & df["by_us"]) | (og & ~df["by_us"])   # goal in our favour
    df["venue"] = df["us_home"].map({True: "H", False: "A"})
    clubs = q("SELECT season, tid, name FROM staging.clubs")
    cmap = {(s, t): n for s, t, n in zip(clubs["season"], clubs["tid"], clubs["name"])}
    opp = df["away_tid"].where(df["us_home"], df["home_tid"])
    df["opponent"] = [cmap.get((s, t)) or f"#{int(t)}" for s, t in zip(df["season"], opp)]
    df["gf"] = df["score_home"].where(df["us_home"], df["score_away"])
    df["ga"] = df["score_away"].where(df["us_home"], df["score_home"])
    df["result"] = ["W" if a > b else ("D" if a == b else "L")
                    for a, b in zip(df["gf"], df["ga"])]
    if seasons is not None:
        df = df[df["season"].isin(list(seasons))]
    return df


def club_attributes(season, phase, club_tids):
    """Per-player 23 attributes + club_tid for the given clubs."""
    if not club_tids:
        return pd.DataFrame()
    cols = ", ".join(f'pa."{a}"' for a in ATTR_ORDER)
    ph = ",".join("?" * len(club_tids))
    return q(f"""SELECT p.tid, p.club_tid, {cols}
                 FROM staging.player_attributes pa
                 JOIN staging.players p USING (season, phase, tid)
                 WHERE pa.season=? AND pa.phase=? AND p.club_tid IN ({ph})
                   AND NOT p.is_staff""", [season, phase, *club_tids])


# --------------------------------------------------------------------------- scouting
# One-stop opposition report: resolves an opponent, packages the pulls a scout does by
# hand (H2H, unit edges, danger men + league percentiles, standout attributes, coverage
# warning) plus rule-based auto-flags. Consumed by the fmq CLI and the Team scout tab, so
# the logic lives in exactly one place. Opponent *tactics* aren't in the save — the caller
# supplies formation/style separately.

OUTFIELD_GROUPS = ["Technical", "Mental", "Physical"]
OUTFIELD_ATTRS = [a for g in OUTFIELD_GROUPS for a in ATTR_GROUPS[g]]
# pure-GK attributes — excluded when listing an outfield player's top attributes
_GK_ONLY = ("Handling", "Kicking", "Reflexes", "Throwing", "Communication")
# distinctive-but-not-a-threat mentals — a high value here doesn't describe how a player
# hurts you, so they never qualify as a standout
_LOW_SIGNAL = ("Leadership", "Teamwork", "Aggression")
# their-defence soft-spots: (attribute, below-this-is-weak, phrase)
_DEF_SOFT = [("Aerial", 9, "weak in the air"), ("Strength", 8, "physically light"),
             ("Positioning", 9, "poor positioning"), ("Pace", 9, "lacks pace")]
# best XI per unit for a team/unit rating (canonical 4-3-3): GK + 4 def + 3 mid + 3 att
UNIT_XI = {"GK": 1, "Defense": 4, "Midfield": 3, "Attack": 3}


def _fold(s):
    """Casefold + strip diacritics + Turkish dotless-ı so an ASCII query ('kirklareli')
    matches the stored name ('Kırklarelispor')."""
    s = str(s).replace("ı", "i").replace("İ", "i").replace("I", "i").casefold()
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def resolve_club(name_or_tid):
    """Resolve a club-name substring (or a numeric tid) to matching clubs that have
    players. Returns [tid, name, n_players] ordered by squad size desc, so the senior
    side outranks its reserves. Match is diacritic/Turkish-insensitive. Empty if none."""
    s = str(name_or_tid).strip()
    if s.isdigit():
        return q("""SELECT club_tid AS tid, any_value(club) AS name, COUNT(*) AS n_players
                    FROM staging.players WHERE club_tid=? AND NOT is_staff
                    GROUP BY club_tid""", [int(s)])
    allc = q("""SELECT club_tid AS tid, any_value(club) AS name, COUNT(*) AS n_players
                FROM staging.players WHERE club IS NOT NULL AND NOT is_staff GROUP BY club_tid""")
    key = _fold(s)
    hit = allc[allc["name"].map(lambda n: key in _fold(n))]
    return hit.sort_values("n_players", ascending=False).reset_index(drop=True)


def latest_snapshot():
    """(season, phase) of the most recent loaded snapshot — max season, latest phase."""
    df = q("""SELECT season, phase FROM staging.extracts
              ORDER BY season DESC,
                       CASE phase WHEN 'start' THEN 0 WHEN 'mid' THEN 1 ELSE 2 END DESC
              LIMIT 1""")
    if df.empty:
        return None, None
    return int(df.iloc[0]["season"]), df.iloc[0]["phase"]


def _fmt_edge(x):
    return f"+{x:.1f}" if x >= 0 else f"{x:.1f}"


def _player_top_attrs(row, rel, n=3, floor=9):
    """A player's most threat-defining attributes for his position, as a compact 'Attr V'
    string on his own row. Scores each attribute (value ≥ floor) by its value plus a boost
    if it's relevant to the position's role — so role-relevant strengths lead, but a
    genuinely elite off-role attribute (a striker's Strength 16) still shows. Low-signal
    mentals (Leadership/Teamwork/Aggression) and pure-GK attrs (for outfield) never qualify.
    `rel` = {position: {attr_lower: role_weight>=2}}."""
    pos = row.get("position")
    cand = [a for a in ATTR_ORDER
            if (pos == "GK" or a not in _GK_ONLY) and a not in _LOW_SIGNAL]
    rw = rel.get(pos, {})
    scored = []
    for a in cand:
        if a not in row or pd.isna(row[a]) or int(row[a]) < floor:
            continue
        v = int(row[a])
        scored.append((a, v, v + 0.6 * rw.get(a.lower(), 0)))
    scored.sort(key=lambda x: (-x[2], -x[1]))     # value, boosted by role relevance
    return ", ".join(f"{a} {v}" for a, v, _ in scored[:n])


def _add_position_index(eff):
    """Add `pos_index`: the role rating standardised WITHIN each position against the global
    position pool, rescaled so 100 = an average player for that position and 15 = one std.
    This is what makes ratings comparable across positions (raw eff runs GK~324 vs ST~404
    purely from role-weight scale). Single-sample / zero-spread positions fall back to 100."""
    if eff.empty:
        eff = eff.copy()
        eff["pos_index"] = pd.Series(dtype=float)
        return eff
    grp = eff.groupby("position")["eff"]
    mean, std = grp.transform("mean"), grp.transform("std")
    eff = eff.copy()
    eff["pos_index"] = (100 + 15 * (eff["eff"] - mean) / std.where(std > 0)).fillna(100.0).round(1)
    return eff


def squad_frame(season, phase, method, club_tids):
    """One coherent per-player frame (primary position row) for the given clubs: eff,
    position-normalised `pos_index`, `pctile_league`, unit, and the 23 attributes. Basis for
    every scout/vs-league aggregation, so index/percentile/attribute reads use the same
    players. `pos_index` is cross-position comparable (100 = league-avg for that position)."""
    eff = _add_position_index(effective_table(season, phase, method))
    if eff.empty:
        return pd.DataFrame()
    prim = eff.loc[eff.groupby("tid")["familiarity"].idxmax()].copy()
    prim = prim[prim["club_tid"].isin(list(club_tids))]
    if prim.empty:
        return prim
    prim["unit"] = prim["position"].map(POSITION_UNIT)
    ca = club_attributes(season, phase, list(club_tids))
    keep = ["tid", "club_tid", "position", "unit", "eff", "pos_index",
            "pctile_league", "level_league"]
    return prim[keep].merge(ca.drop(columns=["club_tid"]), on="tid", how="inner")


def _best_xi(frame_club):
    """Best-N players per unit by position index — a canonical 4-3-3 (GK+4+3+3). Reflects the
    likely matchday XI rather than the whole (depth-diluted) rated squad."""
    parts = [frame_club[frame_club["unit"] == u].sort_values("pos_index", ascending=False).head(k)
             for u, k in UNIT_XI.items()]
    return pd.concat(parts) if parts else frame_club.iloc[0:0]


def team_strength(frame, club_tid):
    """(unit-strength DataFrame, team dict) for a club from a _scout_frame. Aggregates its
    best XI: index = mean position-index (100 = league-average player per position);
    pctile = mean league percentile. Both are cross-position comparable."""
    xi = _best_xi(frame[frame["club_tid"] == club_tid]) if not frame.empty else frame
    rows = []
    for unit in ["Defense", "Midfield", "Attack", "GK"]:
        u = xi[xi["unit"] == unit] if not xi.empty else xi
        rows.append({"unit": unit, "n": len(u),
                     "index": round(u["pos_index"].mean(), 1) if len(u) else None,
                     "pctile": round(u["pctile_league"].mean(), 0) if len(u) else None})
    team = {"index": round(xi["pos_index"].mean(), 1) if not xi.empty else None,
            "pctile": round(xi["pctile_league"].mean(), 0) if not xi.empty else None,
            "n": len(xi) if not xi.empty else 0}
    return pd.DataFrame(rows), team


def squad_key_players(frame, club_tid, method):
    """A club's players ranked by position index (cross-position fair), each with his most
    threat-defining attributes inline (`top_attrs`). Columns: position, eff, pos_index,
    pctile_league, top_attrs. Powers both opponent danger men and our own standouts."""
    of = frame[frame["club_tid"] == club_tid] if not frame.empty else frame
    if of.empty:
        return pd.DataFrame()
    rel = {pos: {a: w for a, w in role_weight_map(method, role).items() if w >= 2}
           for pos, role in pos_role_map().items()}
    ofs = of.sort_values("pos_index", ascending=False)
    cols = ["tid", "position", "eff", "pos_index", "pctile_league"]
    if "level_league" in ofs.columns:
        cols.append("level_league")
    kp = ofs[cols].copy()
    kp["top_attrs"] = [_player_top_attrs(r, rel) for _, r in ofs.iterrows()]
    return kp.reset_index(drop=True)


def _scout_unit_tables(frame, us, opp):
    """(group-level, attribute-level) us-vs-them unit comparison DataFrames for the
    Defense/Midfield/Attack lines. Group frame rows: unit, metric (Overall + the three
    outfield groups), us, them, edge, us_n, them_n. Attr frame rows: unit, attribute,
    us, them, edge. edge = us - them (+ = our advantage); None where a side is empty."""
    grp_rows, attr_rows = [], []
    if frame.empty:
        return pd.DataFrame(), pd.DataFrame()
    for unit in ["Defense", "Midfield", "Attack"]:
        fu = frame[frame["unit"] == unit]
        us_f, them_f = fu[fu["club_tid"] == us], fu[fu["club_tid"] == opp]

        def _val(f, metric):
            if f.empty:
                return None
            if metric == "Overall":
                return round(f["eff"].mean(), 1)
            return round(f[ATTR_GROUPS[metric]].mean(axis=1).mean(), 1)

        for metric in OUTFIELD_GROUPS:   # Overall now comes from the position-index strength
            u, t = _val(us_f, metric), _val(them_f, metric)
            grp_rows.append({"unit": unit, "metric": metric, "us": u, "them": t,
                             "edge": (round(u - t, 1) if u is not None and t is not None else None),
                             "us_n": len(us_f), "them_n": len(them_f)})
        for a in OUTFIELD_ATTRS:
            u = round(us_f[a].mean(), 1) if not us_f.empty else None
            t = round(them_f[a].mean(), 1) if not them_f.empty else None
            attr_rows.append({"unit": unit, "attribute": a, "us": u, "them": t,
                              "edge": (round(u - t, 1) if u is not None and t is not None else None)})
    return pd.DataFrame(grp_rows), pd.DataFrame(attr_rows)


def _scout_flags(overall, strength, attrs_df, key_players, h2h, coverage):
    """Rule-based auto-read: squad strength (position-index), H2H verdict, per-unit edges,
    danger men, and the opponent's exploitable defensive soft-spots. Returns strings."""
    F = []
    if coverage["partial"]:
        F.append(f"⚠️ PARTIAL DATA — only {coverage['in_frame']} rated players "
                 f"({coverage['n_with_attr']}/{coverage['n_players']} with attributes). "
                 "Unit/standout reads are directional; lean on H2H + your in-game scout.")
    u, t, up, tp = (overall.get(k) for k in ("us", "them", "us_pctile", "them_pctile"))
    if u is not None and t is not None:
        d = u - t
        ctx = f" ({up:.0f} vs {tp:.0f} %ile league)" if pd.notna(up) and pd.notna(tp) else ""
        if abs(d) < 3:
            F.append(f"Evenly matched — team index {u:.0f} vs {t:.0f}{ctx}.")
        elif d > 0:
            F.append(f"We're stronger — team index {u:.0f} vs {t:.0f}{ctx}.")
        else:
            F.append(f"They're stronger — team index {t:.0f} vs {u:.0f} to us{ctx}.")
    if h2h.get("played"):
        rec = f"P{h2h['played']} W{h2h['w']} D{h2h['d']} L{h2h['l']}"
        if h2h["w"] == 0 and h2h["played"] >= 3:
            F.append(f"🚩 BOGEY SIDE — never beaten them ({rec}).")
        elif h2h["l"] == 0 and h2h["played"] >= 3:
            F.append(f"✅ We own them ({rec}, {h2h['ppg']:.2f} ppg).")
        else:
            F.append(f"H2H: {rec} ({h2h['ppg']:.2f} ppg).")
    if not strength.empty:
        for _, r in strength[strength["unit"] != "TEAM"].iterrows():
            if pd.isna(r["edge"]):
                continue
            ua = attrs_df[(attrs_df["unit"] == r["unit"]) & attrs_df["edge"].notna()] \
                if not attrs_df.empty else attrs_df
            detail = ""
            if not ua.empty:
                ours = ", ".join(ua.sort_values("edge", ascending=False).head(2)["attribute"])
                theirs = ", ".join(ua.sort_values("edge").head(2)["attribute"])
                detail = f" Our edge: {ours}. Theirs: {theirs}."
            side = "we lead" if r["edge"] >= 0 else "they lead"
            F.append(f"{r['unit']}: {side} ({_fmt_edge(r['edge'])} idx).{detail}")
    if key_players is not None and not key_players.empty:
        men = []
        for _, r in key_players.head(3).iterrows():
            pcl = r.get("pctile_league")
            men.append(f"{r['position']} (idx {r['pos_index']:.0f}"
                       + (f", {pcl:.0f}%ile)" if pd.notna(pcl) else ")"))
        F.append(f"Danger men: {', '.join(men)}.")
    if not attrs_df.empty:
        td = attrs_df[attrs_df["unit"] == "Defense"].set_index("attribute")["them"]
        soft = [f"{lbl} ({a} {td[a]:.0f})" for a, thr, lbl in _DEF_SOFT
                if a in td.index and pd.notna(td[a]) and td[a] < thr]
        if soft:
            F.append(f"Their defence: {', '.join(soft)} — target it.")
    return F


def scout_report(opp_tid, season=None, phase=None, method="buca_433"):
    """Structured opposition report (dicts + DataFrames, no rendering). Sections: opp,
    season/phase/method, coverage, overall (position-index team rating + league %ile),
    strength (per-unit index/%ile us-vs-them, best XI), units + unit_attrs (attribute
    edges), key_players (their squad ranked by position index, cross-position fair),
    standouts, h2h, and flags. Shared by the CLI and the Team scout tab."""
    if not season or not phase:
        s, p = latest_snapshot()
        season, phase = season or s, phase or p
    us = MANAGED_CLUB_TID
    nm = q("SELECT any_value(club) AS n FROM staging.players WHERE club_tid=?", [opp_tid])
    opp_name = nm.iloc[0]["n"] if not nm.empty and pd.notna(nm.iloc[0]["n"]) else f"#{opp_tid}"

    cov = q("""SELECT COUNT(*) AS n,
                      COALESCE(SUM(CASE WHEN has_attributes THEN 1 ELSE 0 END), 0) AS attr
               FROM staging.players
               WHERE season=? AND phase=? AND club_tid=? AND NOT is_staff""",
            [season, phase, opp_tid])
    frame = squad_frame(season, phase, method, [opp_tid, us])
    in_frame = int((frame["club_tid"] == opp_tid).sum()) if not frame.empty else 0
    coverage = {"n_players": int(cov.iloc[0]["n"] or 0), "n_with_attr": int(cov.iloc[0]["attr"] or 0),
                "in_frame": in_frame, "partial": in_frame < 11}

    # position-normalised team & unit strength (best XI) for both clubs
    us_units, us_team = team_strength(frame, us)
    op_units, op_team = team_strength(frame, opp_tid)
    strength = us_units.merge(op_units, on="unit", suffixes=("_us", "_them"))
    strength = strength.rename(columns={"index_us": "us", "index_them": "them",
                                        "pctile_us": "us_pctile", "pctile_them": "them_pctile"})
    strength["edge"] = (strength["us"] - strength["them"]).round(1)
    ti, oi = us_team["index"], op_team["index"]
    strength = pd.concat([strength, pd.DataFrame([{
        "unit": "TEAM", "us": ti, "them": oi, "us_pctile": us_team["pctile"],
        "them_pctile": op_team["pctile"], "n_us": us_team["n"], "n_them": op_team["n"],
        "edge": (round(ti - oi, 1) if ti is not None and oi is not None else None)}])],
        ignore_index=True)
    overall = {"us": ti, "them": oi, "us_pctile": us_team["pctile"],
               "them_pctile": op_team["pctile"]}

    groups_df, attrs_df = _scout_unit_tables(frame, us, opp_tid)

    key_players = squad_key_players(frame, opp_tid, method)   # ranked by index, attrs inline

    hist = our_match_history()
    h = hist[hist["opp_tid"] == opp_tid].sort_values(["season", "date"]) if not hist.empty \
        else pd.DataFrame()
    if not h.empty:   # competitive only — friendlies aren't meaningful for a bogey read
        h = h[~h["competition"].str.contains("friend", case=False, na=False)]
    if not h.empty:
        w, d, l = [int((h["result"] == r).sum()) for r in "WDL"]
        h2h = {"played": len(h), "w": w, "d": d, "l": l, "gf": int(h["gf"].sum()),
               "ga": int(h["ga"].sum()), "ppg": round(h["pts"].mean(), 2), "matches": h}
    else:
        h2h = {"played": 0, "matches": h}

    flags = _scout_flags(overall, strength, attrs_df, key_players, h2h, coverage)
    return {"opp": {"tid": opp_tid, "name": opp_name}, "season": season, "phase": phase,
            "method": method, "coverage": coverage, "overall": overall, "strength": strength,
            "units": groups_df, "unit_attrs": attrs_df, "key_players": key_players,
            "h2h": h2h, "flags": flags}


# --------------------------------------------------------------------------- scout log
# Persist scouting reports to a plain JSONL file (survives fm.duckdb rebuilds, git-trackable)
# so we build a scouting history: calibrate reports over time + review the season with what we
# thought before each match. One record per (opponent, data-snapshot); re-running refreshes it.

SCOUTS_PATH = os.path.join(REPO, "scouts", "scouts.jsonl")


def _json_clean(o):
    """Recursively make a value JSON-safe: numpy scalars -> python, NaN -> None."""
    if isinstance(o, dict):
        return {k: _json_clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_json_clean(v) for v in o]
    if hasattr(o, "item"):          # numpy scalar
        o = o.item()
    if isinstance(o, float) and o != o:   # NaN
        return None
    return o


def load_scouts():
    """All saved scouts as a DataFrame (empty if none), newest write last."""
    if not os.path.exists(SCOUTS_PATH):
        return pd.DataFrame()
    rows = []
    with open(SCOUTS_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return pd.DataFrame(rows)


def snapshot_history():
    """Archived (superseded) in-season player snapshots — one row per (label, season, phase)
    with its in-game date + player count. The CURRENT snapshot per (season,phase) is in
    staging; these are the earlier checkpoints kept for progression. Empty if none / no
    history schema (older DB)."""
    try:
        return q("""SELECT snapshot_label, snapshot_date, season, phase, COUNT(*) AS players
                    FROM history.player_snapshots
                    GROUP BY 1, 2, 3, 4 ORDER BY season, snapshot_date""")
    except duckdb.Error:
        return pd.DataFrame()


def save_scout(report, venue=None, formation=None, style=None, note=None, saved_at=None):
    """Append/refresh a scouting report in the JSONL log. Keyed by (opponent_tid, snapshot),
    so re-scouting the same opponent on the same data updates the record; a new data snapshot
    (after a re-import) creates a fresh one. Stores the report's verdict + our supplied
    formation/style/venue/note so 'what we thought' can be reviewed against the result."""
    # the actual save label (distinguishes two vintages of the same season/phase, e.g. a
    # Nov and a March '2024-mid' after a re-import) — so scouts on different data coexist
    lbl = q("SELECT label FROM staging.extracts WHERE season=? AND phase=?",
            [report["season"], report["phase"]])
    snap_label = lbl.iloc[0]["label"] if not lbl.empty else f"{report['season']}-{report['phase']}"
    rec = _json_clean({
        "saved_at": saved_at or datetime.datetime.now().isoformat(timespec="seconds"),
        "opponent_tid": report["opp"]["tid"], "opponent": report["opp"]["name"],
        "snapshot": f"{report['season']}-{report['phase']}", "snapshot_label": snap_label,
        "method": report["method"],
        "venue": venue, "formation": formation, "style": style, "note": note,
        "overall": report["overall"], "coverage": report["coverage"],
        "strength": report["strength"].to_dict("records"),
        "flags": report["flags"],
        "key_players": (report["key_players"].head(8).to_dict("records")
                        if not report["key_players"].empty else []),
        "h2h": {k: report["h2h"].get(k) for k in ("played", "w", "d", "l", "gf", "ga", "ppg")},
    })
    os.makedirs(os.path.dirname(SCOUTS_PATH), exist_ok=True)
    kept = [r for r in (load_scouts().to_dict("records") if os.path.exists(SCOUTS_PATH) else [])
            if not (r.get("opponent_tid") == rec["opponent_tid"]
                    and r.get("snapshot_label") == rec["snapshot_label"])]
    kept.append(rec)
    with open(SCOUTS_PATH, "w", encoding="utf-8") as f:
        for r in kept:
            f.write(json.dumps(r, ensure_ascii=False, allow_nan=False) + "\n")
    return rec
