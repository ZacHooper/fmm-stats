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
import numpy as np
import pandas as pd
import streamlit as st

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
# our own directory too: db is imported both as `db` (Streamlit pages, fmq) and as
# `dashboard.db` (scripts run from the repo root), and only the first puts dashboard/ on the
# path — so `import state` needs this to work either way.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import state
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
    # env override wins; else the configured DEFAULT_CAREER if its store exists (stable — not
    # mtime-dependent, so a reseed/write never flips the default); else the newest store on disk.
    if os.environ.get("FM_CAREER"):
        return os.environ["FM_CAREER"]
    avail = available_careers()
    if _careers.DEFAULT_CAREER in avail:
        return _careers.DEFAULT_CAREER
    return (avail or [_careers.DEFAULT_CAREER])[0]


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

# phase is normally the snapshot's in-game DATE ('YYYY-MM-DD'); legacy stores may still
# hold the words start/mid/end. Sentinels map those words to epoch so start<mid<end and
# both conventions sort together (real dates always sort after the sentinels).
_PHASE_SENTINEL = {"start": "0000-00-00", "mid": "0000-00-01", "end": "0000-00-02"}


def _psort_sql(col="phase"):
    """SQL mirror of phase_key: an orderable phase string, date-aware, `col` qualifiable."""
    return (f"CASE {col} WHEN 'start' THEN '0000-00-00' WHEN 'mid' THEN '0000-00-01' "
            f"WHEN 'end' THEN '0000-00-02' ELSE {col} END")


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
                 f"`uv run python load_duckdb.py output/<label> --db {car.db if car else 'fm-<career>.duckdb'}`"
                 f"\n\n(season + phase auto-derive from the save's in-game date.)")
        st.stop()
    # FM_DUCKDB_READONLY=1 lets non-Streamlit callers (e.g. the fmq CLI) attach without
    # taking the single-writer lock, so scouting works while the dashboard is running.
    ro = os.environ.get("FM_DUCKDB_READONLY") == "1"
    con = duckdb.connect(DB_PATH, read_only=ro)
    # Everything below reads mart.*, and the mart is only (re)created by a load — so a store
    # built before it existed, or before an object was added, would fail here with a bare
    # Catalog Error somewhere deep in a page. Say what to run instead.
    has_mart = con.execute("SELECT COUNT(*) FROM information_schema.schemata "
                           "WHERE schema_name = 'mart'").fetchone()[0]
    if not has_mart:
        st.error(f"{DB_PATH} has no `mart` schema. It is built from the staging tables, so "
                 f"nothing needs re-parsing:\n\n"
                 f"`uv run python load_duckdb.py --refresh-only --db {DB_PATH}`")
        st.stop()
    return con


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
    """Sortable, date-aware string for a phase (words -> epoch sentinels)."""
    return _PHASE_SENTINEL.get(phase, str(phase))


# Legacy word-phases have no real date. Season is the campaign's END year (22/23 -> 2023),
# so the campaign runs Jul(season-1) -> Jun(season); place the words at plausible points in
# it so a mixed store still plots on a real time axis.
_PHASE_WORD_MD = {"start": (-1, 7, 1), "mid": (0, 1, 1), "end": (0, 6, 30)}


def phase_date(phase, season):
    """A phase -> real `pd.Timestamp` for time-axis plotting.

    Real 'YYYY-MM-DD' phases parse directly; the legacy words start/mid/end are synthesised
    inside the season's campaign window so both conventions land on one continuous axis.
    """
    word = _PHASE_WORD_MD.get(str(phase))
    if word is not None:
        try:
            yoff, mo, day = word
            return pd.Timestamp(int(season) + yoff, mo, day)
        except (TypeError, ValueError):
            return pd.NaT
    return pd.to_datetime(phase, errors="coerce")


def add_phase_date(df, col="date", phase_col="phase", season_col="season"):
    """Add a real-date column derived from (season, phase) and sort chronologically by it.

    Use this for anything plotted over time: spacing snapshots by their in-game date stops
    two saves taken days apart from looking like a full development step.
    """
    if df is None or df.empty:
        return df
    out = df.copy()
    seasons = out[season_col] if season_col in out else [None] * len(out)
    out[col] = [phase_date(p, s) for p, s in zip(out[phase_col], seasons)]
    return out.sort_values(col, kind="stable")


def even_time_series(dates, values, n=24):
    """Resample an irregular (dates, values) series onto `n` evenly-spaced time points.

    Streamlit's LineChartColumn sparkline spaces every value equally, so a burst of saves
    reads as a long plateau. Interpolating onto a uniform time grid first makes the
    sparkline's shape proportional to elapsed in-game time.
    """
    d = pd.to_datetime(pd.Series(list(dates)), errors="coerce")
    v = pd.Series(list(values), dtype="float64")
    ok = d.notna() & v.notna()
    d, v = d[ok], v[ok]
    if len(d) < 2:
        return [round(y, 1) for y in v.tolist()]
    order = d.argsort()
    d, v = d.iloc[order], v.iloc[order]
    x = d.astype("int64").to_numpy()
    if x[-1] == x[0]:
        return [round(y, 1) for y in v.tolist()]
    grid = [x[0] + (x[-1] - x[0]) * i / (n - 1) for i in range(n)]
    return [round(float(y), 1) for y in np.interp(grid, x, v.to_numpy())]


# --------------------------------------------------------------------------- selectors

def labels_df():
    df = q("SELECT season, phase, label FROM mart.snapshots ORDER BY snap_ix")
    df["ord"] = df["phase"].map(phase_key)
    df = df.sort_values(["season", "ord"]).reset_index(drop=True)
    df["date"] = [phase_date(p, s) for p, s in zip(df["phase"], df["season"])]
    return df


def methods():
    df = q("SELECT DISTINCT method FROM mart.role_weights ORDER BY method")
    return df["method"].tolist()


def roles():
    df = q("SELECT DISTINCT role FROM mart.role_weights ORDER BY role")
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
    car = select_career(sidebar)    # set the active career (DB_PATH + 'us') before querying
    df = labels_df()
    if df.empty:
        st.error("No extracts loaded. Run load_duckdb.py first.")
        st.stop()
    opts = list(df[["season", "phase"]].itertuples(index=False, name=None))
    fmt = lambda sp: f"{sp[0]} · {sp[1]}"
    box = st.sidebar if sidebar else st
    # on a career switch, snap to that career's LATEST save (opts is season/phase-sorted asc,
    # so opts[-1] is newest) rather than carrying over a stale label from the previous career.
    if st.session_state.get("_label_career") != car:
        st.session_state["label_sp"] = opts[-1]
        st.session_state["_label_career"] = car
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


def stale_loan_ins(season, phase):
    """Loaned-in tids (for this season, phase) whose loan has actually lapsed even though
    `players.club_tid`/`loaned_in` still reads us — the squad-list row freezes on a loan-in
    the same way attribute rows freeze for reserves (see reserve-marker-stale-attrs); nothing
    rewrites it when the loan ends instead of being renewed.

    Flags a tid when the SAME loan-in relationship has been on the books for 2+ completed
    seasons with ZERO match_player_stats appearances for us since it started — an active loan
    racks up minutes for us; a lapsed one doesn't, no matter how old the flag on his row is.
    A fresh arrival this season has too short a history to trip the 2-season threshold, so
    genuine new loan-ins are never flagged. Verified against fm-frem tid 10409 (Haarbo):
    loaned_in since season 2022, zero appearances for us since, a full alternate-club season
    (172, 33 apps) on the books for 2023 — yet still read loaned_in=True in season 2024."""
    if not _has_table("match_player_stats"):
        return set()
    ph = ",".join("?" * len(OUR_CLUBS))
    cur = q(f"SELECT tid FROM staging.players WHERE season=? AND phase=? "
            f"AND loaned_in AND club_tid IN ({ph})", [season, phase, *OUR_CLUBS])
    if cur.empty:
        return set()
    first_seen = q(f"SELECT tid, MIN(season) AS first_season FROM staging.players "
                   f"WHERE loaned_in AND club_tid IN ({ph}) AND tid IN "
                   f"({','.join('?' * len(cur))}) GROUP BY tid",
                   [*OUR_CLUBS, *[int(t) for t in cur["tid"]]])
    first_by_tid = dict(zip(first_seen["tid"], first_seen["first_season"]))
    stale = set()
    for t in cur["tid"]:
        t = int(t)
        first = first_by_tid.get(t)
        if first is None or season - first < 2:
            continue
        apps = q(f"SELECT COUNT(*) AS c FROM staging.match_player_stats "
                 f"WHERE tid=? AND season>? AND team_tid IN ({ph})", [t, first, *OUR_CLUBS])
        if int(apps["c"].iloc[0]) == 0:
            stale.add(t)
    return stale


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


def role_key_attrs(method, role, min_w=3):
    """Ordered (key-first) list of the ATTRIBUTES that matter for a (method, role) — those
    weighted >= min_w. Powers the attribute 'profile' presets in the shared column picker, so a
    user can one-click a role's key attributes as columns without knowing them by heart."""
    wm = role_weight_map(method, role)
    return sorted((a for a in ATTR_ORDER if wm.get(a.lower(), 1) >= min_w),
                  key=lambda a: (-wm.get(a.lower(), 1), ATTR_ORDER.index(a)))


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
    df = q("SELECT key, value FROM mart.app_config")
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
    """A join of two mart objects rather than a 60-line query.

    This used to compute everything itself: its own club->league CTE (one of five copies), its
    own nation lookup, the 27M-row v_player_ratings join, and both families of window function.
    mart.player_position_fit owns the method-dependent half (eff, pctile_*, rank_*) and
    mart.player_position_levels the method-independent half (level_*, n_*) — split there
    because the level percentiles provably do not vary by tactic.

    IMMERSION, and this is the real gain: `ca` is no longer in scope anywhere in this query, so
    the `SELECT * EXCLUDE (ca)` that used to guard the projection is gone. The guarantee stops
    being "somebody remembered to write EXCLUDE" and becomes "the ability number is not
    reachable from here" — enforced in the mart, where validate_mart.py and
    publish_mart.verify() both scan information_schema for it.

    `curve` and `floor` stay in the signature: they are the cache key. The values themselves now
    come from mart.app_config inside mart.player_position_fit, so the SQL cannot disagree with
    the config the way an interpolated expression could.
    """
    sql = """
    SELECT f.tid, f.position, f.role, f.familiarity, f.base_rating, f.eff,
           f.name, f.club, f.club_tid, f.league_cid, f.nation,
           f.pctile_global, f.pctile_nation, f.pctile_league,
           l.level_global, l.level_nation, l.level_league,
           f.rank_global, f.rank_nation, f.rank_league,
           l.n_global, l.n_nation, l.n_league
    FROM mart.player_position_fit f
    JOIN mart.player_position_levels l USING (season, phase, tid, position)
    WHERE f.season = ? AND f.phase = ? AND f.method = ?
    """
    return _conn().execute(sql, [season, phase, method]).df()


# ----------------------------------------------------------------- ability ranks (no CA out)
# Comparing a player against a DIFFERENT division, or against one specific club's squad, needs
# the game's raw overall-ability number: tactic fit says nothing about level, and the
# precomputed level_* percentiles in effective_table are scoped to the player's OWN league (so
# a reserve-team player is ranked against the reserve league, which is meaningless). Immersion
# rule still holds — these helpers do the ranking INSIDE SQL and return only rank / N, so the
# ability number never leaves db.py. Callers get "6 of 75", never the number behind it.

# club -> league AS AT the snapshot, from the mart. This used to be a hand-rolled arg_max CTE
# here, one of five copies across this file and scripts/export_data.py; mart.club_leagues is
# the single definition now, and it takes (season, phase) instead of a pre-built `ord` string.
_CL_ASAT = """
    SELECT club_tid, league_cid FROM mart.club_leagues
    WHERE season = ? AND phase = ?"""

# `min_fam` keeps makeshift players out of the comparison set: staging.player_positions lists
# every position a player has ANY familiarity in, so an unfiltered pool of "left backs" is
# padded with centre-halves who can shuffle across. Rank against people who actually play there.
_POOL = """
    SELECT p.tid, pp.position, p.ca, p.club_tid, cl.league_cid
    FROM staging.players p
    JOIN staging.player_positions pp ON (pp.season, pp.phase, pp.tid) = (p.season, p.phase, p.tid)
    LEFT JOIN cl ON cl.club_tid = p.club_tid
    WHERE p.season = ? AND p.phase = ? AND NOT p.is_staff AND p.ca IS NOT NULL
      AND pp.familiarity >= ?"""


def _rank_args(season, phase, tid_positions, min_fam):
    """(VALUES clause, params) shared by both rank helpers. The leading params are the two
    _CL_ASAT binds; the rest are _POOL's."""
    vals = ", ".join(f"({int(t)}, '{str(pos)}')" for t, pos in tid_positions)
    return vals, [season, phase, season, phase, int(min_fam)]


def comparison_leagues(season, phase, limit=3):
    """Our own league plus the next lower-reputation leagues in the same nation — the natural
    ladder to judge a squad player against (his division, then the ones he could be loaned to).
    Returns [(cid, name), ...] strongest first, ours always at index 0 when known."""
    mine = my_league(season, phase)
    lg = q("""SELECT cid, any_value(name) AS name, any_value(nation) AS nation,
                     max(reputation) AS rep, max(type) AS type
              FROM staging.leagues WHERE season=? AND phase=? GROUP BY cid""", [season, phase])
    if lg.empty or mine is None:
        return [(mine, None)] if mine else []
    nat = lg.loc[lg["cid"] == mine, "nation"]
    nation = nat.iloc[0] if not nat.empty else None
    same = lg[(lg["nation"] == nation) & lg["type"].notna()].sort_values("rep", ascending=False)
    ours_rep = lg.loc[lg["cid"] == mine, "rep"]
    below = same[same["rep"] < (ours_rep.iloc[0] if not ours_rep.empty else 0)]
    out = [(mine, lg.loc[lg["cid"] == mine, "name"].iloc[0])]
    out += [(int(r.cid), r.name) for r in below.head(max(0, limit - 1)).itertuples()]
    return out


@st.cache_data(show_spinner=False)
def ability_rank_leagues(season, phase, tid_positions, league_cids, min_fam=0, ver=None):
    """rank / N by ability for each (tid, position) within each league, position-matched and
    restricted to players with familiarity >= min_fam there. The player himself is always
    counted in N exactly once, so "1 of 95" reads naturally even when he doesn't play in that
    league. Returns tid, position, league_cid, rank, n."""
    if not tid_positions or not league_cids:
        return pd.DataFrame(columns=["tid", "position", "league_cid", "rank", "n"])
    vals, params = _rank_args(season, phase, tid_positions, min_fam)
    cids = ", ".join(str(int(c)) for c in league_cids)
    sql = f"""
    WITH cl AS ({_CL_ASAT}), pool AS ({_POOL}),
         tgt AS (SELECT po.tid, po.position, po.ca FROM pool po
                 JOIN (VALUES {vals}) v(tid, position)
                   ON v.tid = po.tid AND v.position = po.position)
    SELECT t.tid, t.position, l.league_cid,
           1 + COUNT(CASE WHEN o.ca > t.ca THEN 1 END) AS rank,
           1 + COUNT(o.tid) AS n
    FROM tgt t
    CROSS JOIN (SELECT DISTINCT league_cid FROM pool WHERE league_cid IN ({cids})) l
    LEFT JOIN pool o
      ON o.position = t.position AND o.league_cid = l.league_cid AND o.tid <> t.tid
    GROUP BY 1, 2, 3"""
    return _conn().execute(sql, params).df()


@st.cache_data(show_spinner=False)
def ability_rank_clubs(season, phase, tid_positions, league_cid, min_fam=0, ver=None):
    """rank / N by ability for each (tid, position) inside EVERY club's squad in one league —
    i.e. "how many bodies would be ahead of him if we loaned him there", counting only players
    with familiarity >= min_fam there. Rank 1 means he'd be their first choice in that
    position. Returns tid, position, club_tid, club, rank, n."""
    if not tid_positions or league_cid is None:
        return pd.DataFrame(columns=["tid", "position", "club_tid", "club", "rank", "n"])
    vals, params = _rank_args(season, phase, tid_positions, min_fam)
    sql = f"""
    WITH cl AS ({_CL_ASAT}), pool AS ({_POOL}),
         tgt AS (SELECT po.tid, po.position, po.ca FROM pool po
                 JOIN (VALUES {vals}) v(tid, position)
                   ON v.tid = po.tid AND v.position = po.position),
         hosts AS (SELECT DISTINCT club_tid FROM pool WHERE league_cid = {int(league_cid)})
    SELECT t.tid, t.position, h.club_tid,
           COALESCE(any_value(c.name), '#' || h.club_tid) AS club,
           1 + COUNT(CASE WHEN o.ca > t.ca THEN 1 END) AS rank,
           1 + COUNT(o.tid) AS n
    FROM tgt t
    CROSS JOIN hosts h
    LEFT JOIN pool o
      ON o.position = t.position AND o.club_tid = h.club_tid AND o.tid <> t.tid
    LEFT JOIN staging.clubs c ON c.tid = h.club_tid AND c.season = ? AND c.phase = ?
    GROUP BY 1, 2, 3"""
    return _conn().execute(sql, [*params, season, phase]).df()


def eligibility_frame(season, phase):
    """Per-player career origin + Athletic-Bilbao eligibility for the snapshot. Returns
    tid, origin_club_tid, origin_club, last_season_club, confidence, eligible (origin in
    staging.eligible_origin_clubs).

    Since 2026-08-19 every row is confidence='exact': a player's career-history chain head is
    a STORED POINTER in his attribute record (u32 @ P-38), not a positional guess, so origin
    club can be trusted outright. The 'low' handling below is now only a guard for slices
    loaded by the old parser."""
    return _eligibility_cached(season, phase, _dbver())


@st.cache_data(show_spinner=False)
def _eligibility_cached(season, phase, ver):
    # player_history is parsed on newer stores only; degrade gracefully where it's absent
    # (e.g. a store built before the career-history parser) so bio/Origin just goes blank.
    if not _conn().execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='staging' AND table_name='player_history'").fetchone():
        return pd.DataFrame(columns=["tid", "origin_club_tid", "origin_club",
                                     "last_season_club", "confidence", "eligible"])
    # HISTORICAL: the old parser aligned records to players positionally and marked ~all of
    # them 'low', which resolved to WRONG clubs (a Danish player showing a Belgian origin), so
    # low-confidence rows were blanked rather than asserted as fact. That alignment is gone —
    # fmparser/history.py now follows a stored pointer and every row is 'exact'. The CASEs are
    # kept purely so a store still holding old 'low' rows degrades to blank instead of lying.
    sql = """
        SELECT h.tid,
               CASE WHEN h.confidence = 'low' THEN NULL ELSE h.origin_club_tid END
                 AS origin_club_tid,
               CASE WHEN h.confidence = 'low' THEN NULL
                    ELSE COALESCE(oc.name, '#' || h.origin_club_tid) END AS origin_club,
               CASE WHEN h.confidence = 'low' THEN NULL
                    ELSE COALESCE(lc.name, '#' || h.last_season_club_tid) END
                 AS last_season_club,
               h.confidence,
               (e.club_tid IS NOT NULL AND h.confidence <> 'low') AS eligible
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
# A persistent scouting shortlist. Lives in state/shortlist/<id>.json (mirrored to R2 — see
# dashboard/state.py), NOT in the DuckDB store. It used to be staging.shortlist, which had two
# problems: a store rebuild destroyed it, and it was invisible to a second machine. It also
# needed CREATE TABLE on first read, which crashed any page that touched it against a
# read-only store.
#
# Each entry snapshots the prospect's positions + attributes, so it still renders for players
# who aren't in the current snapshot at all. `tid` is set for players added by look-up (None
# for manual entries).

def shortlist_get():
    """DataFrame of the shortlist: id, tid, name, positions(dict), attributes(dict), source."""
    rows = []
    for key, rec in state.entries("shortlist"):
        rows.append({"id": key,
                     "tid": rec.get("tid"),
                     "name": rec.get("name") or "",
                     "positions": rec.get("positions") or {},
                     "attributes": rec.get("attributes") or {},
                     "source": rec.get("source") or "manual"})
    df = pd.DataFrame(rows, columns=["id", "tid", "name", "positions", "attributes", "source"])
    return df.sort_values("name").reset_index(drop=True) if not df.empty else df


def shortlist_add(name, positions, attributes, tid=None, source="manual"):
    key = state.new_key()
    state.put("shortlist", key, {
        "id": key, "tid": int(tid) if tid is not None else None, "name": name,
        "positions": {str(k): int(v) for k, v in (positions or {}).items()},
        "attributes": {str(k): int(v) for k, v in (attributes or {}).items()},
        "source": source,
        "added_at": datetime.datetime.now().isoformat(timespec="seconds")})
    return key


def shortlist_remove(sid):
    state.delete("shortlist", str(sid))


def player_search(query, season, phase, limit=50):
    """Players (not staff) whose name matches `query`, for the shortlist look-up."""
    return q("""SELECT tid, name, club, club_tid FROM staging.players
                WHERE season=? AND phase=? AND NOT is_staff AND name ILIKE ?
                ORDER BY name LIMIT ?""", [season, phase, f"%{query}%", limit])


def _ref_date(season, phase):
    """In-game calendar date for a snapshot (for age). phase is normally the real date
    ('YYYY-MM-DD') -> use it directly (exact). Legacy word-phases fall back to the old
    per-phase approximation (season = campaign end-year)."""
    try:
        return datetime.date.fromisoformat(phase)
    except (ValueError, TypeError):
        pass
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
    # loaned_in/parent_club are migration-added columns; absent on older un-migrated stores
    if _conn().execute(
            "SELECT 1 FROM information_schema.columns WHERE table_schema='staging' "
            "AND table_name='players' AND column_name='loaned_in'").fetchone():
        ln = q("SELECT tid, parent_club FROM staging.players "
               "WHERE season=? AND phase=? AND loaned_in", [season, phase])
        loan = dict(zip(ln["tid"], ln["parent_club"])) if not ln.empty else {}
    else:
        loan = {}

    def _g(t, field):
        return bio.get(int(t), {}).get(field) if pd.notna(t) else None
    r["Age"] = r[tid_col].map(lambda t: _g(t, "Age"))
    r["Value"] = r[tid_col].map(lambda t: _g(t, "Value"))
    r["Origin"] = r[tid_col].map(lambda t: origin.get(int(t)) if pd.notna(t) else None)
    r["Loan"] = r[tid_col].map(lambda t: loan.get(int(t)) if pd.notna(t) else None)
    return r


def contract_info(season, phase, tids):
    """{tid: {"Wage": £/yr, "Expiry": ISO date}} for the snapshot. Wage/expiry are
    migration-added columns (see load_duckdb); on an un-migrated store (e.g. a Bucaspor
    store not yet re-extracted) they're absent, so return {} and callers just skip them."""
    tids = [int(t) for t in tids]
    if not tids:
        return {}
    if not _conn().execute(
            "SELECT 1 FROM information_schema.columns WHERE table_schema='staging' "
            "AND table_name='players' AND column_name='wage_gbp'").fetchone():
        return {}
    ph = ",".join("?" * len(tids))
    df = q(f"SELECT tid, wage_gbp, contract_expiry FROM staging.players "
           f"WHERE season=? AND phase=? AND tid IN ({ph})", [season, phase, *tids])
    return {int(r.tid): {"Wage": r.wage_gbp, "Expiry": r.contract_expiry}
            for r in df.itertuples()}


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
            SELECT season, arg_max(phase, CASE phase WHEN 'start' THEN '0000-00-00' WHEN 'mid' THEN '0000-00-01'
                                                     WHEN 'end' THEN '0000-00-02' ELSE phase END) AS phase
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
            SELECT season, arg_max(phase, CASE phase WHEN 'start' THEN '0000-00-00' WHEN 'mid' THEN '0000-00-01'
                                                     WHEN 'end' THEN '0000-00-02' ELSE phase END) AS phase
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
    """tid -> primary position (max familiarity across labels).

    Aggregates across every snapshot, so it must exclude slices where the tid belonged to a
    DIFFERENT person (recycling — see docs/IDS.md); otherwise a retired striker's positions
    leak into the newgen who inherited his slot."""
    if not tids:
        return {}
    ph = ",".join("?" * len(tids))
    rows = q(f"""SELECT season, phase, tid, position, familiarity
                 FROM staging.player_positions WHERE tid IN ({ph})""", [*tids])
    rows = keep_current_person(rows)
    if rows.empty:
        return {}
    best = rows.sort_values("familiarity").groupby("tid").last()
    return dict(zip(best.index, best["position"]))


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
#
# This is the last hand-rolled copy of this CTE — mart.club_leagues replaced the other four.
# It survives because leagues_list and teams_in_league want the store-wide answer ("every club
# we have ever seen in this league"), not the as-at one, for browsing. Both take (season, phase)
# and ignore them, which is worth tidying, but making them snapshot-scoped changes what the
# Opposition and Team pages show and there is no golden output to check that against.
_RESOLVED_CL = """
    SELECT club_tid, arg_max(league_cid, ord) AS lc FROM (
        SELECT club_tid, league_cid,
               LPAD(CAST(season AS VARCHAR), 4, '0') ||
               CASE phase WHEN 'start' THEN '0000-00-00' WHEN 'mid' THEN '0000-00-01'
                          WHEN 'end' THEN '0000-00-02' ELSE phase END AS ord
        FROM staging.league_members WHERE source='club_league' AND league_cid IS NOT NULL)
    GROUP BY club_tid"""


def my_league(season, phase):
    """Our own division AS AT (season, phase).

    It used to use the store-wide resolution and ignore both arguments, which meant it reported
    whatever division we ended up in for every snapshot ever — Frem climbed from the 3. Division
    to the Superliga across this store, so a 2021 snapshot claimed we were in the Superliga.
    mart.club_leagues resolves as-at while still falling back to the most recent EARLIER mapping,
    so the sparse-light-results case the store-wide version existed for is still covered.
    """
    df = q("""SELECT cl.league_cid AS lc FROM mart.club_leagues cl
              WHERE cl.season = ? AND cl.phase = ?
                AND cl.club_tid IN (SELECT club_tid FROM mart.managed_club)""",
           [season, phase])
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
                  SELECT season, arg_max(phase, CASE phase WHEN 'start' THEN '0000-00-00' WHEN 'mid' THEN '0000-00-01'
                                                           WHEN 'end' THEN '0000-00-02' ELSE phase END) AS phase
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


def player_injuries(season):
    """Injury spells for the managed squad in `season`, one row per spell. Sourced from the
    weekly Player-Progress table (captures training injuries too, unlike match_events).

    A season can have several snapshots; loaned-in players' progress data leaves when their
    loans expire, so a later snapshot loses their injuries. We therefore pick the snapshot with
    the MOST complete injury data (max total weeks) for the season. Columns: tid, name, seq,
    spell_start, spell_end, weeks_out."""
    best = q("""SELECT phase FROM staging.player_injuries WHERE season=?
                GROUP BY phase ORDER BY SUM(weeks_out) DESC, COUNT(*) DESC LIMIT 1""", [season])
    if best.empty:
        return pd.DataFrame(columns=["tid", "name", "seq", "spell_start",
                                     "spell_end", "weeks_out"])
    ph = best["phase"].iloc[0]
    return q("""SELECT i.tid, nm.name, i.seq, i.spell_start, i.spell_end, i.weeks_out
                FROM staging.player_injuries i
                LEFT JOIN (SELECT tid, arg_max(name, phase) AS name
                           FROM staging.players WHERE season=? GROUP BY tid) nm ON nm.tid=i.tid
                WHERE i.season=? AND i.phase=?
                ORDER BY i.tid, i.seq""", [season, season, ph])


def _has_table(name):
    """True if staging.<name> exists — older stores predate some of the parsers."""
    return bool(_conn().execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema='staging' "
        "AND table_name=?", [name]).fetchone())


def _merge_ranges(rows, gap_days=8):
    """Merge (start, end, weeks) tuples whose ranges touch or overlap (within `gap_days`).

    Returns [(start, end, weeks)] sorted by start; `weeks` is the largest value any input row
    claimed for the merged range (snapshots agree on a spell they both saw, so this is a
    no-op for duplicates and only matters when one save saw a longer version of the spell)."""
    out = []
    for start, end, weeks in sorted(rows):
        if out and (start - out[-1][1]).days <= gap_days:
            prev = out[-1]
            out[-1] = (prev[0], max(prev[1], end), max(prev[2], weeks))
        else:
            out.append((start, end, weeks))
    return out


# --------------------------------------------------------------------------- person identity
# A tid is a SLOT, not a person: FM reuses a retired player's tid for a newgen (829 swaps in the
# frem store, 1503 in bucaspor). Within ONE (season,phase) slice a tid is unambiguous, so every
# single-snapshot view is already correct — but any CROSS-SAVE per-player join keyed on tid alone
# splices two careers together. dob separates every recycled slot (2332 changes, 0 collisions,
# 0 nulls), so the person key is (tid, dob), materialised as staging.persons/person_slices by the
# loader. See docs/IDS.md.

def _has_persons():
    """True once the loader has built the identity bridge (older stores predate it)."""
    return _has_table("persons") and _has_table("person_slices")


def current_person_ids(tids):
    """{tid: person_id} for the identity holding each tid in the NEWEST snapshot.

    That is the person a caller means by "this player" — the one on screen now."""
    tids = [int(t) for t in tids]
    if not tids or not _has_persons():
        return {}
    ph = ",".join("?" * len(tids))
    df = q(f"""SELECT tid, arg_max(person_id, {_psort_sql('last_seen')}) AS person_id
               FROM staging.persons WHERE tid IN ({ph}) GROUP BY tid""", tids)
    return dict(zip(df["tid"].astype(int), df["person_id"]))


def person_history(tid):
    """Every identity that has ever held `tid`, oldest first — the audit view for recycling.

    Columns: person_id, dob, name, first_seen, last_seen, slices."""
    cols = ["person_id", "dob", "name", "first_seen", "last_seen", "slices"]
    if not _has_persons():
        return pd.DataFrame(columns=cols)
    return q(f"""SELECT person_id, dob, name, first_seen, last_seen, slices
                 FROM staging.persons WHERE tid=?
                 ORDER BY {_psort_sql('first_seen')}""", [int(tid)])


def keep_current_person(df):
    """Drop rows of `df` whose (season, phase, tid) belonged to a DIFFERENT person than the one
    holding that tid now. `df` needs season/phase/tid columns; returned unchanged if the store
    has no identity bridge, or if no tid in the frame was ever recycled (the common case)."""
    if df is None or df.empty or not _has_persons():
        return df
    if not {"season", "phase", "tid"} <= set(df.columns):
        return df
    tids = [int(t) for t in pd.unique(df["tid"])]
    if not tids:
        return df
    ph = ",".join("?" * len(tids))
    recycled = q(f"""SELECT tid FROM staging.persons WHERE tid IN ({ph})
                     GROUP BY tid HAVING COUNT(*) > 1""", tids)
    if recycled.empty:                       # nothing recycled -> nothing to filter
        return df
    hot = set(recycled["tid"].astype(int))
    cur = current_person_ids(sorted(hot))
    ph2 = ",".join("?" * len(hot))
    slices = q(f"""SELECT season, phase, tid, person_id FROM staging.person_slices
                   WHERE tid IN ({ph2})""", sorted(hot))
    owner = {(int(r.season), r.phase, int(r.tid)): r.person_id for r in slices.itertuples()}
    def ok(sn, phse, t):
        t = int(t)
        if t not in hot:
            return True
        who = owner.get((int(sn), phse, t))
        return who is None or who == cur.get(t)
    return df[[ok(a, b, c) for a, b, c in zip(df["season"], df["phase"], df["tid"])]]


def _identity_snapshots(tid):
    """The (season, phase) keys where `tid` was the SAME PERSON it is now.

    Keyed on dob via the identity bridge: 3733 is "Tab Ramos" (b.1966, a free agent) in the
    21/22 saves and "Hervé Buur" (b.2006) at Frem from 22/23, and a career-wide union keyed only
    on tid would splice their timelines. Falls back to the old name-match on stores built before
    the bridge existed. Returns None when the store has nothing for the tid (callers then fall
    back to no filtering)."""
    if _has_persons():
        pid = current_person_ids([tid]).get(int(tid))
        if pid is not None:
            df = q("SELECT season, phase FROM staging.person_slices WHERE tid=? AND person_id=?",
                   [int(tid), pid])
            if not df.empty:
                return {(int(r.season), r.phase) for r in df.itertuples()}
    who = q("SELECT season, phase, name FROM staging.players WHERE tid=?", [int(tid)])
    if who.empty:
        return None
    who = add_phase_date(who)
    current = who.iloc[-1]["name"]
    keep = who[who["name"] == current]
    return {(int(r.season), r.phase) for r in keep.itertuples()}


def _same_identity(df, keys):
    """Keep only rows whose (season, phase) belongs to `keys` (see _identity_snapshots)."""
    if keys is None or df.empty:
        return df
    return df[[(int(sn), ph) in keys for sn, ph in zip(df["season"], df["phase"])]]


def player_injury_spells(tid):
    """Career injury timeline for one player, unioned across EVERY snapshot.

    Each save's weekly Player-Progress series only spans {season-1, season}, so a spell an
    early save recorded is simply absent from later ones — and a loaned-in player's progress
    data leaves with them when the loan ends. Neither save is wrong; they just see different
    windows. So we union every snapshot's spells and merge the overlaps, which is the only way
    to get a player's full injury history out of a set of saves.

    Columns: spell_start, spell_end, weeks_out, days. Empty frame if nothing is recorded."""
    cols = ["spell_start", "spell_end", "weeks_out", "days"]
    if not _has_table("player_injuries"):
        return pd.DataFrame(columns=cols)
    df = _same_identity(
        q("SELECT season, phase, spell_start, spell_end, weeks_out "
          "FROM staging.player_injuries WHERE tid=?", [int(tid)]), _identity_snapshots(tid))
    if df.empty:
        return pd.DataFrame(columns=cols)
    rows = [(pd.to_datetime(r.spell_start).date(), pd.to_datetime(r.spell_end).date(),
             int(r.weeks_out or 0)) for r in df.itertuples()]
    merged = _merge_ranges(rows)
    return pd.DataFrame([{"spell_start": a, "spell_end": b, "weeks_out": w,
                          "days": (b - a).days + 1} for a, b, w in merged])


def player_loan_spells(tid):
    """Loan history for one player, from the three sources we can trust, best-first.

    1. **`staging.player_loans`** — EXACT weekly windows for loans OUT, from bit 5 of the
       Player-Progress status field. Unioned across snapshots and merged, like injuries.
    2. **Career history** (`player_history_seasons.fee = 'loan'`) — a season at a NAMED club
       with apps/goals, back through the player's whole career. Every snapshot parses this now
       (before 2026-08-19 most returned nothing), but keep taking the version with the most
       rows: a loan only appears once the season it belongs to has been written.
    3. **`players.loaned_in`** — a player loaned IN to us, bounded by the snapshot dates that
       observed the loan.

    (1) and (2) describe the same event from different angles when they overlap, so a history
    loan that covers an exact spell is folded into it — exact dates from (1), club and
    appearances from (2) — rather than listed twice.

    `bounded` is True when the dates are approximate (a season window or snapshot bounds) and
    False for the exact weekly spells; `ongoing` marks a loan still running in the newest
    snapshot. Columns: kind ('out'/'history'/'in'), club, season, start, end, apps, goals,
    bounded, ongoing."""
    cols = ["kind", "club", "season", "start", "end", "apps", "goals", "bounded", "ongoing"]
    exact, hist, out = [], [], []

    if _has_table("player_loans"):
        df = _same_identity(
            q("SELECT season, phase, spell_start, spell_end, weeks "
              "FROM staging.player_loans WHERE tid=?", [int(tid)]), _identity_snapshots(tid))
        if not df.empty:
            exact = _merge_ranges([(pd.to_datetime(r.spell_start).date(),
                                    pd.to_datetime(r.spell_end).date(), int(r.weeks or 0))
                                   for r in df.itertuples()], gap_days=22)

    if _has_table("player_history_seasons"):
        h = q("""SELECT h.phase, h.season, h.end_year, h.club_tid, h.fee, h.apps, h.goals,
                        cl.name AS club
                 FROM staging.player_history_seasons h
                 LEFT JOIN staging.clubs cl ON (cl.season, cl.phase, cl.tid)
                                             = (h.season, h.phase, h.club_tid)
                 WHERE h.tid=?""", [int(tid)])
        if not h.empty:
            h = h[h["phase"] == h.groupby("phase").size().idxmax()]   # most complete parse
            for r in h[h["fee"] == "loan"].itertuples():
                y = int(r.end_year)
                hist.append({"kind": "history", "club": r.club or f"club {r.club_tid}",
                             "season": y, "start": datetime.date(y - 1, 7, 1),
                             "end": datetime.date(y, 6, 30), "apps": r.apps, "goals": r.goals,
                             "bounded": True, "ongoing": False})

    # The weekly grid runs to the end of the season, so a spell in force at the save date
    # extends past it — its end is SCHEDULED, not observed. Flag those as ongoing.
    lbl = labels_df()
    newest = lbl["date"].max().date() if not lbl.empty and lbl["date"].notna().any() else None

    # an exact spell and a history row describing the same loan -> one row, best of both
    for a, b, _weeks in exact:
        match = next((x for x in hist if x["start"] <= b and a <= x["end"]), None)
        if match:
            hist.remove(match)
        out.append({"kind": "out", "club": (match or {}).get("club"),
                    "season": b.year + 1 if b.month > 6 else b.year, "start": a, "end": b,
                    "apps": (match or {}).get("apps"), "goals": (match or {}).get("goals"),
                    "bounded": False, "ongoing": bool(newest and b >= newest)})
    out.extend(hist)

    if _conn().execute(
            "SELECT 1 FROM information_schema.columns WHERE table_schema='staging' "
            "AND table_name='players' AND column_name='loaned_in'").fetchone():
        ph = ",".join(str(int(t)) for t in OUR_CLUBS) or "NULL"
        obs = q(f"SELECT season, phase, loaned_in, parent_club FROM staging.players "
                f"WHERE tid=? AND club_tid IN ({ph}) AND NOT is_staff", [int(tid)])
        if not obs.empty:
            obs = add_phase_date(obs)
            latest = obs["date"].max()
            run = None
            for r in obs.itertuples():           # runs of consecutive loaned-in observations
                if r.loaned_in:
                    if run is None:
                        run = {"kind": "in", "club": r.parent_club, "season": int(r.season),
                               "start": r.date.date(), "end": r.date.date(), "apps": None,
                               "goals": None, "bounded": True, "ongoing": False}
                    else:
                        run["end"] = r.date.date()
                elif run is not None:
                    out.append(run); run = None
            if run is not None:
                # loaned in as of the newest snapshot — the spell hasn't been seen to end
                run["ongoing"] = run["end"] == latest.date()
                out.append(run)

    if not out:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(out, columns=cols).sort_values("start").reset_index(drop=True)


# A player only counts as a peer at a role if he can actually play the position: familiarity
# below this is a makeshift, not a right-back. (Ratings are ALSO scaled by the familiarity
# curve, so a 10/20 is both admitted and discounted.)
MIN_ROLE_FAMILIARITY = 10


def _eff_role_cte(role_param="?", fam_param="?", tid_pred=""):
    """CTE giving one familiarity-ADJUSTED rating per (snapshot, player) at a role.

    A role can be reached from several positions (LB from DL or DML), so take the best
    position: rating is fixed per role, the multiplier comes from that position's familiarity.
    This is the same eff = rating x multiplier the rest of the dashboard ranks on — without it
    a DMC with 10/20 at DR outranks every actual right-back on raw attributes alone."""
    curve, floor = familiarity_params()
    mult = _mult_sql("pp.familiarity", curve, floor)
    return f"""
        SELECT r.season, r.phase, r.tid, r.role,
               MAX(r.rating * {mult}) AS eff, MAX(pp.familiarity) AS fam
        FROM v_player_ratings r
        JOIN staging.player_positions pp USING (season, phase, tid)
        JOIN staging.position_role_map prm
          ON prm.position = pp.position AND prm.role = r.role
        WHERE r.method = ?
          {"AND r.role = " + role_param if role_param else ""}
          AND pp.familiarity >= {fam_param}
          {tid_pred}
        GROUP BY 1, 2, 3, 4"""


def league_options():
    """Leagues in our nation that have clubs, strongest first — the tier ladder, so a benchmark
    can be set to the division above (or below). Columns: cid, name, reputation, clubs.

    `reputation` is a migration-added column; on an un-migrated store it's absent, so fall back
    to ordering by club count (still deterministic, just not tier-ordered)."""
    has_rep = bool(_conn().execute(
        "SELECT 1 FROM information_schema.columns WHERE table_schema='staging' "
        "AND table_name='leagues' AND column_name='reputation'").fetchone())
    rep = "any_value(l.reputation)" if has_rep else "NULL"
    order = "reputation DESC NULLS LAST" if has_rep else "clubs DESC"
    return q(f"""
        WITH ournation AS (
            SELECT any_value(nation_id) AS nid FROM staging.leagues
            WHERE cid IN (SELECT league_cid FROM staging.league_members
                          WHERE source='club_league' AND club_tid=?))
        SELECT l.cid, any_value(l.name) AS name, {rep} AS reputation,
               COUNT(DISTINCT lm.club_tid) AS clubs
        FROM staging.leagues l
        JOIN staging.league_members lm
          ON lm.league_cid = l.cid AND lm.source='club_league'
        WHERE l.name IS NOT NULL
          AND l.nation_id = (SELECT nid FROM ournation)
        GROUP BY l.cid
        ORDER BY {order}""", [MANAGED_CLUB_TID])


def role_benchmarks(role, method, scope, league_cid=None, min_fam=None):
    """Per-snapshot benchmark ratings at `role`, so a trajectory can be read against the
    standard it competes with. All ratings are familiarity-adjusted (see `_eff_role_cte`).

    `scope='squad'`  — every eligible player at our clubs.
    `scope='league'` — ONE ROW PER CLUB: that club's best eligible player at the role. The
        median is then "the typical STARTING <role> in this division", which is the question
        you actually ask of a loan target or a promotion candidate. Taking a median over every
        squad member instead would measure bench depth and would swing with squad sizes.
        `league_cid=None` follows OUR division at each snapshot (so the line steps up when
        we're promoted); pass a cid to pin it to one division across the whole timeline.

    Columns: season, phase, date, best, median, n (peers — clubs for 'league', players for
    'squad')."""
    min_fam = MIN_ROLE_FAMILIARITY if min_fam is None else min_fam
    eff = _eff_role_cte()
    if scope == "squad":
        ph = ",".join(str(int(t)) for t in OUR_CLUBS) or "NULL"
        sql = f"""
            WITH eff AS ({eff}),
            pop AS (SELECT season, phase, tid FROM staging.players
                    WHERE club_tid IN ({ph}) AND NOT is_staff)
            SELECT e.season, e.phase, MAX(e.eff) AS best,
                   MEDIAN(e.eff) AS median, COUNT(*) AS n
            FROM eff e JOIN pop USING (season, phase, tid)
            GROUP BY 1, 2"""
        params = [method, role, min_fam]
    else:
        if league_cid is None:
            league_pred = """lm.league_cid = (SELECT any_value(u.league_cid)
                                              FROM staging.league_members u
                                              WHERE u.source='club_league' AND u.club_tid=?
                                                AND u.season=lm.season AND u.phase=lm.phase)"""
            extra = [MANAGED_CLUB_TID]
        else:
            league_pred = "lm.league_cid = ?"
            extra = [int(league_cid)]
        sql = f"""
            WITH eff AS ({eff}),
            pop AS (
                SELECT p.season, p.phase, p.tid, p.club_tid
                FROM staging.players p
                JOIN staging.league_members lm
                  ON (lm.season, lm.phase, lm.club_tid) = (p.season, p.phase, p.club_tid)
                 AND lm.source='club_league'
                WHERE NOT p.is_staff AND {league_pred}),
            per_club AS (
                SELECT e.season, e.phase, pop.club_tid, MAX(e.eff) AS eff
                FROM eff e JOIN pop USING (season, phase, tid)
                GROUP BY 1, 2, 3)
            SELECT season, phase, MAX(eff) AS best, MEDIAN(eff) AS median, COUNT(*) AS n
            FROM per_club GROUP BY 1, 2"""
        params = [method, role, min_fam, *extra]
    df = q(sql, params)
    return add_phase_date(df) if not df.empty else df


def squad_role_series(tids, method, min_fam=1):
    """Familiarity-adjusted rating over time at EVERY role, for a set of players — one query
    for a whole squad, so the growth table can track each player at his own primary role.

    Because the multiplier moves with familiarity, a player who *learns* a position gains
    rating here even with static attributes — which is real development, and invisible in the
    raw weighted rating. Columns: tid, season, phase, date, role, rating, fam."""
    cols = ["tid", "season", "phase", "date", "role", "rating", "fam"]
    if not tids:
        return pd.DataFrame(columns=cols)
    ph = ",".join("?" * len(tids))
    cte = _eff_role_cte(role_param="", tid_pred=f"AND r.tid IN ({ph})")   # no role filter
    df = q(f"""WITH eff AS ({cte})
               SELECT tid, season, phase, role, eff AS rating, fam FROM eff""",
           [method, min_fam, *[int(t) for t in tids]])
    df = keep_current_person(df)      # a recycled tid must not inherit its predecessor's curve
    return add_phase_date(df) if not df.empty else pd.DataFrame(columns=cols)


def squad_role_ranking(season, phase, role, method, min_fam=None):
    """Our squad ranked at `role` in one snapshot by FAMILIARITY-ADJUSTED rating, and limited
    to players who can genuinely play the position (see MIN_ROLE_FAMILIARITY).

    Ranking on raw attributes instead puts a 20-familiarity DMC top of the right-backs.
    Columns: tid, name, rating (effective), fam — best first."""
    min_fam = MIN_ROLE_FAMILIARITY if min_fam is None else min_fam
    ph = ",".join(str(int(t)) for t in OUR_CLUBS) or "NULL"
    return q(f"""
        WITH eff AS ({_eff_role_cte()})
        SELECT e.tid, any_value(p.name) AS name, MAX(e.eff) AS rating, MAX(e.fam) AS fam
        FROM eff e
        JOIN staging.players p USING (season, phase, tid)
        WHERE e.season=? AND e.phase=? AND p.club_tid IN ({ph}) AND NOT p.is_staff
        GROUP BY e.tid
        ORDER BY rating DESC""", [method, role, min_fam, season, phase])


def player_role_series(tids, role, method, min_fam=1):
    """Familiarity-adjusted rating over time at one role, for one or more players — the same
    measure the benchmarks use, so lines on one chart are comparable.

    `min_fam` defaults to 1 here (not MIN_ROLE_FAMILIARITY): for a named line we want the
    player's actual trajectory even in a role he's still learning; the multiplier already
    shows the cost. Columns: tid, season, phase, date, rating, fam."""
    if not tids:
        return pd.DataFrame(columns=["tid", "season", "phase", "date", "rating", "fam", "role"])
    ph = ",".join("?" * len(tids))
    df = q(f"""WITH eff AS ({_eff_role_cte()})
               SELECT tid, season, phase, role, eff AS rating, fam FROM eff
               WHERE tid IN ({ph})""",
           [method, role, min_fam, *[int(t) for t in tids]])
    df = keep_current_person(df)      # a recycled tid must not inherit its predecessor's curve
    return add_phase_date(df) if not df.empty else df


def our_penalties(seasons=None):
    """Chronological penalties taken by our players (from match_events, latest phase per
    season, joined to match dates). Columns: season, date, minute, seq, tid, player,
    made (bool: 'penalty'=scored, 'missed_penalty'=missed). For penalty-streak records."""
    df = q("""
        WITH ours AS (SELECT DISTINCT tid FROM staging.players WHERE club_tid IN (?, ?)),
             chosen AS (
               WITH mm AS (SELECT DISTINCT season, phase FROM staging.match_events)
               SELECT season, arg_max(phase, CASE phase WHEN 'start' THEN '0000-00-00' WHEN 'mid' THEN '0000-00-01'
                                                        WHEN 'end' THEN '0000-00-02' ELSE phase END) AS phase
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
                        SELECT season, arg_max(phase, CASE phase WHEN 'start' THEN '0000-00-00'
                                 WHEN 'mid' THEN '0000-00-01' WHEN 'end' THEN '0000-00-02' ELSE phase END)
                                 AS phase FROM mm GROUP BY season)
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
    # mart.snapshots.snap_ix already encodes "chronological across seasons and phases", so
    # this stops being another copy of the phase-ordering CASE expression.
    df = q("SELECT season, phase FROM mart.snapshots ORDER BY snap_ix DESC LIMIT 1")
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

# Saved scout reports live in state/scouts/<opponent_tid>-<snapshot_label>.json (mirrored to
# R2 — see dashboard/state.py). They were one append-only JSONL; the per-entry split means a
# re-scout PUTs over exactly one object instead of rewriting the whole log, so two devices
# saving different scouts can't clobber each other. LEGACY_SCOUTS is read once by
# scripts/migrate_state.py and then ignored.
LEGACY_SCOUTS_PATH = os.path.join(REPO, "scouts", "scouts.jsonl")


def scout_key(opponent_tid, snapshot_label):
    """Stable object key. Re-scouting the same opponent on the same data snapshot overwrites
    its own entry; a new snapshot (after a re-import) gets a fresh one — the same behaviour the
    JSONL de-duplication gave, but without a read-modify-write."""
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(snapshot_label))
    return f"{int(opponent_tid)}-{safe}"


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
    """All saved scouts as a DataFrame (empty if none), oldest first by save time."""
    rows = [rec for _key, rec in state.entries("scouts")]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    return (df.sort_values("saved_at").reset_index(drop=True)
            if "saved_at" in df.columns else df)


def delete_scout(opponent_tid, snapshot_label):
    """Drop one saved scout."""
    state.delete("scouts", scout_key(opponent_tid, snapshot_label))


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
    state.put("scouts", scout_key(rec["opponent_tid"], rec["snapshot_label"]), rec)
    return rec
