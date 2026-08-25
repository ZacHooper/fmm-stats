#!/usr/bin/env python3
"""
Load fm-parser extract bundles into a DuckDB store.

    uv run python load_duckdb.py output/2022-end [--db fm.duckdb]
    uv run python load_duckdb.py output --all
    uv run python load_duckdb.py output/my-label --season 2024 --phase mid
    uv run python load_duckdb.py output/2022-end --include core,light,standings
    uv run python load_duckdb.py output --all --reset

The tables in the `staging` schema are a 1:1 mirror of the JSON/CSV that the
extractors write to output/<label>/ (same grain, minimal reshaping) — every row
stamped with season (int end-year, 21/22 -> 2022) and phase (start/mid/end).
Analytical views in the default `main` schema are the transformed layer on top;
see create_views(). Loads are idempotent: re-loading a label replaces exactly
that (season, phase) slice.

duckdb is imported only here; the extractors stay pure-stdlib.
"""
import argparse
import csv
import datetime
import glob
import json
import os
import sys

import duckdb
import pandas as pd     # bulk-insert path in _insert(); see its docstring for why

# Reuse the season/phase math and field lists from the extractors (pure-stdlib import).
from extract import parse_label
from fmparser.attributes import ATTR_ORDER
from fmparser import matches as M
from fmparser.mart import create_mart, drop_mart

# ---------------------------------------------------------------------------
# schema
# ---------------------------------------------------------------------------

# team_stats side columns, inlined onto matches as home_* / away_*
_TS_KEYS = ["shots", "shots_on_target", "rating", "players_used", "passes",
            "passes_completed", "tackles", "tackles_won", "crosses", "interceptions"]

# match-XI stat fields (authoritative list from matches.py). tid_int -> tid,
# posOrder -> pos_order; the rest map straight through.
_XI = M._XI_FIELDS  # noqa: SLF001 (intentional reuse of the canonical list)


def _attr_cols_ddl():
    cols = [f'"{a}" INTEGER' for a in ATTR_ORDER]
    cols += [f'"{a}_est" BOOLEAN' for a in ATTR_ORDER]
    return ",\n    ".join(cols)


# NB: no enforced PRIMARY KEYs. DuckDB maintains an ART index per PK, and bulk
# DELETE+INSERT (our idempotent per-label reload) against that index is pathologically
# slow (minutes for ~30k rows). The loader guarantees uniqueness itself (dedup + a
# clean DELETE of the (season,phase) slice before each INSERT), so the natural key is
# documented in a comment per table rather than enforced. Reintroduce PKs only if an
# external writer starts touching these tables.
DDL = [
    "CREATE SCHEMA IF NOT EXISTS staging",

    # natural key: (season, phase). phase is the snapshot's in-game DATE ('YYYY-MM-DD')
    # for match-having saves (season-start day-1 saves get a synthetic 'YYYY-07-01'); the
    # legacy words 'start'/'mid'/'end' are still accepted so pre-existing stores keep working.
    """CREATE TABLE IF NOT EXISTS staging.extracts (
        season INTEGER NOT NULL,
        phase VARCHAR NOT NULL,
        label VARCHAR NOT NULL,
        label_auto VARCHAR,
        source_dir VARCHAR NOT NULL,
        save_path VARCHAR,
        latest_match DATE,
        date_from DATE,
        date_to DATE,
        loaded_at TIMESTAMP NOT NULL,
        row_counts JSON
    )""",

    # natural key: (season, phase, tid)
    """CREATE TABLE IF NOT EXISTS staging.clubs (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        tid INTEGER NOT NULL, name VARCHAR
    )""",

    # natural key: (season, phase, cid)
    """CREATE TABLE IF NOT EXISTS staging.competitions (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        cid INTEGER NOT NULL, uid BIGINT, name VARCHAR, short VARCHAR, code VARCHAR,
        type VARCHAR, type_id INTEGER, nation_id INTEGER, num_teams INTEGER,
        matches_in_save INTEGER
    )""",

    # natural key: (season, phase, cid)
    """CREATE TABLE IF NOT EXISTS staging.leagues (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        cid INTEGER NOT NULL, name VARCHAR, type VARCHAR, nation_id INTEGER,
        nation VARCHAR, reputation INTEGER, member_count INTEGER, fixtures INTEGER
    )""",

    # natural key: (season, phase, league_cid, club_tid, source)
    """CREATE TABLE IF NOT EXISTS staging.league_members (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        league_cid INTEGER NOT NULL, club_tid INTEGER NOT NULL,
        source VARCHAR NOT NULL
    )""",

    # natural key: (season, phase, tid)
    """CREATE TABLE IF NOT EXISTS staging.players (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        tid INTEGER NOT NULL, name VARCHAR, is_staff BOOLEAN NOT NULL DEFAULT FALSE,
        club_tid INTEGER, club VARCHAR, league_cid INTEGER, league VARCHAR,
        dob DATE, nationality_id INTEGER, has_attributes BOOLEAN,
        squad_status INTEGER, loaned_out BOOLEAN, is_gk INTEGER,
        ca INTEGER, pa INTEGER, reputation INTEGER, positions JSON,
        foot_left INTEGER, foot_right INTEGER, player_value BIGINT,
        loaned_in BOOLEAN, parent_club_tid INTEGER, parent_club VARCHAR,
        wage_units INTEGER, wage_gbp BIGINT, contract_expiry DATE, contract_expiry_year INTEGER
    )""",

    # natural key: (season, phase, tid)
    f"""CREATE TABLE IF NOT EXISTS staging.player_attributes (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL, tid INTEGER NOT NULL,
        {_attr_cols_ddl()}
    )""",

    # natural key: (season, phase, anchor)
    """CREATE TABLE IF NOT EXISTS staging.matches (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL, anchor BIGINT NOT NULL,
        date DATE, competition VARCHAR, comp_id INTEGER, home_flag INTEGER,
        home_tid INTEGER, away_tid INTEGER, attendance INTEGER,
        score_home INTEGER, score_away INTEGER, star_home INTEGER, star_away INTEGER,
        formation VARCHAR,
        home_shots INTEGER, home_shots_on_target INTEGER, home_rating DOUBLE,
        home_players_used INTEGER, home_passes INTEGER, home_passes_completed INTEGER,
        home_tackles INTEGER, home_tackles_won INTEGER, home_crosses INTEGER,
        home_interceptions INTEGER,
        away_shots INTEGER, away_shots_on_target INTEGER, away_rating DOUBLE,
        away_players_used INTEGER, away_passes INTEGER, away_passes_completed INTEGER,
        away_tackles INTEGER, away_tackles_won INTEGER, away_crosses INTEGER,
        away_interceptions INTEGER
    )""",

    # natural key: (season, phase, anchor, seq)
    """CREATE TABLE IF NOT EXISTS staging.match_events (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL, anchor BIGINT NOT NULL,
        seq INTEGER NOT NULL, minute INTEGER, added INTEGER, min_display VARCHAR,
        tid INTEGER, type VARCHAR, type_byte INTEGER, b0 INTEGER
    )""",

    # natural key: (season, phase, anchor, side, tid)
    """CREATE TABLE IF NOT EXISTS staging.match_player_stats (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL, anchor BIGINT NOT NULL,
        side VARCHAR NOT NULL CHECK (side IN ('home','away')),
        tid INTEGER NOT NULL, team_tid INTEGER, opponent_tid INTEGER,
        date DATE, competition VARCHAR,
        pos_order INTEGER, rating INTEGER, goals INTEGER, assists INTEGER,
        passA INTEGER, passC INTEGER, keyPass INTEGER, tackA INTEGER, tackW INTEGER,
        intercept INTEGER, headA INTEGER, headW INTEGER, crossA INTEGER, crossC INTEGER,
        dribbles INTEGER, mistakes INTEGER, shotA INTEGER, shotO INTEGER,
        condition INTEGER, subOn INTEGER, subOff INTEGER, yellow INTEGER
    )""",

    # natural key: (season, phase, league_cid, club_tid, source)
    """CREATE TABLE IF NOT EXISTS staging.standings (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        league_cid INTEGER NOT NULL, club_tid INTEGER NOT NULL,
        pos INTEGER, club VARCHAR, played INTEGER, won INTEGER, drawn INTEGER,
        lost INTEGER, gf INTEGER, ga INTEGER, gd INTEGER, points INTEGER,
        source VARCHAR NOT NULL DEFAULT 'lightresults_computed'
    )""",

    # natural key: (season, phase, home_tid, away_tid, cid, seq)
    """CREATE TABLE IF NOT EXISTS staging.results (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        home_tid INTEGER NOT NULL, away_tid INTEGER NOT NULL, cid INTEGER NOT NULL,
        seq INTEGER NOT NULL, home VARCHAR, away VARCHAR,
        scoreH INTEGER, scoreA INTEGER, competition VARCHAR, copies INTEGER
    )""",

    # natural key: (season, phase, tid, position). Long form of players.positions —
    # every position a player can play (14 FM codes) with familiarity 1..20.
    """CREATE TABLE IF NOT EXISTS staging.player_positions (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL, tid INTEGER NOT NULL,
        position VARCHAR NOT NULL, familiarity INTEGER
    )""",

    # career-history summary, one row per player (from history.json / fmparser.history).
    # origin_club_tid = youth/debut club = the Athletic-Bilbao eligibility key. `confidence` is
    # always 'exact' since 2026-08-19: the player -> history link is a stored pointer
    # (u32 @ P-38 in the attribute record), not an inferred alignment, so the old
    # high/medium/low tail is gone. See fmparser/history.py. natural key: (season, phase, tid).
    """CREATE TABLE IF NOT EXISTS staging.player_history (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL, tid INTEGER NOT NULL,
        origin_club_tid INTEGER, origin_club VARCHAR,
        last_season_club_tid INTEGER, confidence VARCHAR, record_offset BIGINT,
        debut_season INTEGER, debut_end_year INTEGER
    )""",

    # full season-by-season career rows (for display). natural key: (season, phase, tid, seq).
    # A season can appear TWICE for one player: a loan year stores the parent-club row (0 apps)
    # and the loan-club row (fee='loan') separately, exactly as the in-game screen shows them.
    # `goals` is goals CONCEDED for goalkeepers. `rating` is null for pre-career seasons (the
    # game only keeps an average rating for seasons played during your career).
    """CREATE TABLE IF NOT EXISTS staging.player_history_seasons (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL, tid INTEGER NOT NULL,
        seq INTEGER NOT NULL, hist_season INTEGER, end_year INTEGER,
        club_tid INTEGER, fee VARCHAR, apps INTEGER, goals INTEGER,
        assists INTEGER, rating DOUBLE
    )""",

    # injury spells for the MANAGED SQUAD, from the weekly Player-Progress table
    # (fmparser.injuries). One row per spell; captures training injuries too (match_events
    # only has in-match ones). NOTE: loaned-in players' progress data leaves with them, so the
    # snapshot taken BEFORE loans expire holds the completest picture. natural key:
    # (season, phase, tid, seq).
    """CREATE TABLE IF NOT EXISTS staging.player_injuries (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL, tid INTEGER NOT NULL,
        seq INTEGER NOT NULL, spell_start DATE, spell_end DATE, weeks_out INTEGER
    )""",

    # LOAN-OUT spells for the managed squad, from bit 5 of the same weekly Player-Progress
    # status field (fmparser.injuries.ON_LOAN). Exact weekly windows for players we loaned
    # OUT — players loaned IN to us are never flagged here (see staging.players.loaned_in for
    # those). Same two-calendar-year visibility caveat as injuries: union across snapshots.
    # natural key: (season, phase, tid, seq).
    """CREATE TABLE IF NOT EXISTS staging.player_loans (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL, tid INTEGER NOT NULL,
        seq INTEGER NOT NULL, spell_start DATE, spell_end DATE, weeks INTEGER
    )""",

    # GLOBAL config (not per-label): the set of club TIDs whose YOUTH products are eligible
    # under the Athletic-Bilbao origin strategy (e.g. Danish Capital Region). Seeded from
    # seeds/eligible_origin_clubs.csv; curate freely. Join on player_history.origin_club_tid.
    """CREATE TABLE IF NOT EXISTS staging.eligible_origin_clubs (
        club_tid INTEGER NOT NULL, club_name VARCHAR, region VARCHAR
    )""",

    # GLOBAL reference table (not per-label). One row per (method, role, attribute).
    # `method` names a tactic/weight-set: 'black_hawk'/'personal' are seeded from
    # seeds/role_weights.csv; user-defined tactics are added by inserting new methods
    # (e.g. from a dashboard) and are preserved across reloads. Attributes not listed
    # for a (method, role) default to weight 1 in v_player_ratings.
    """CREATE TABLE IF NOT EXISTS staging.role_weights (
        method VARCHAR NOT NULL, role VARCHAR NOT NULL, attribute VARCHAR NOT NULL,
        category VARCHAR, weight INTEGER NOT NULL
    )""",

    # GLOBAL: maps the 14 FM position codes to the 10 rating roles in role_weights.
    """CREATE TABLE IF NOT EXISTS staging.position_role_map (
        position VARCHAR NOT NULL, role VARCHAR NOT NULL
    )""",

    # GLOBAL: app settings (familiarity curve/floor, defaults). Edited by the Config
    # page; seeded with defaults only for keys that don't yet exist.
    """CREATE TABLE IF NOT EXISTS staging.app_config (
        key VARCHAR NOT NULL, value VARCHAR
    )""",

    # IDENTITY BRIDGE. A tid is a SLOT, not a person: FM reuses a retired player's tid for a
    # newgen (829 swaps in the frem store, 1503 in bucaspor). Within one (season,phase) slice a
    # tid is unambiguous, so single-snapshot views are fine — but ANY cross-save per-player join
    # keyed on tid alone splices two people into one career. `dob` separates every recycled slot
    # (2332 changes, 0 collisions, 0 nulls), so (tid,dob) is the person key. See docs/IDS.md.
    # person_id is a stable VARCHAR '<tid>-<dob>' (stable across loads, unlike a dense_rank).
    """CREATE TABLE IF NOT EXISTS staging.persons (
        person_id VARCHAR NOT NULL, tid INTEGER NOT NULL, dob DATE,
        name VARCHAR, first_seen VARCHAR, last_seen VARCHAR, slices INTEGER
    )""",
    # (season,phase,tid) -> person_id. The join bridge every fact table uses; facts keep their
    # tid column untouched, so nothing downstream has to change shape.
    """CREATE TABLE IF NOT EXISTS staging.person_slices (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        tid INTEGER NOT NULL, person_id VARCHAR NOT NULL
    )""",

    # Multi-snapshot archive. staging.* always holds ONE snapshot per (season,phase) =
    # the latest loaded; when a load supersedes a DIFFERENT label in that slice, the
    # outgoing snapshot's players+attributes are copied here first (tagged by label +
    # in-game date). Lets multiple in-season checkpoints coexist for progression without
    # touching the single-snapshot staging layer the dashboard/scout rely on.
    "CREATE SCHEMA IF NOT EXISTS history",
    """CREATE TABLE IF NOT EXISTS history.player_snapshots AS
       SELECT CAST(NULL AS VARCHAR) AS snapshot_label,
              CAST(NULL AS DATE) AS snapshot_date,
              CAST(NULL AS TIMESTAMP) AS archived_at,
              p.*, a.* EXCLUDE (season, phase, tid)
       FROM staging.players p JOIN staging.player_attributes a USING (season, phase, tid)
       LIMIT 0""",
]

_SEED_METHODS = ("black_hawk", "personal", "frem_counter", "frem_gegenpress",
                 "frem_attacking_ss", "frem_lowblock_overload", "frem_game_state")

# 14 FM position codes -> 10 rating roles. Wide/defensive-mid codes fold into the
# nearest available role (the role vocabulary is narrower than the position codes).
POSITION_ROLE = {
    "GK": "GK", "DL": "LB", "DML": "LB", "DR": "RB", "DMR": "RB", "DC": "CB",
    "DMC": "DM", "MC": "CM", "ML": "AML", "MR": "AMR",
    "AML": "AML", "AMR": "AMR", "AMC": "AMC", "ST": "ST",
}

APP_CONFIG_DEFAULTS = {
    "familiarity_curve": "linear_floor",   # linear_floor | tiers | proportional
    "familiarity_floor": "0.5",            # floor for linear_floor curve
    "default_method": "black_hawk",
}

def phase_sort_sql(col="phase"):
    """SQL for an orderable phase key that works for BOTH the new date-phases
    ('YYYY-MM-DD', which sort chronologically as strings) and the legacy words
    'start'/'mid'/'end' (mapped to epoch sentinels so start<mid<end — preserving the old
    ordering for pre-existing stores). `col` may be table-qualified (e.g. 'a.phase')."""
    return (f"CASE {col} WHEN 'start' THEN '0000-00-00' WHEN 'mid' THEN '0000-00-01' "
            f"WHEN 'end' THEN '0000-00-02' ELSE {col} END")


_PS = phase_sort_sql()

VIEWS = {
    "v_player_attributes": """
        SELECT p.*, a.* EXCLUDE (season, phase, tid)
        FROM staging.players p
        JOIN staging.player_attributes a USING (season, phase, tid)
    """,
    "v_ca_progression": f"""
        SELECT tid, name, season, phase,
               {_PS} AS phase_ord,
               club, ca, pa, reputation
        FROM staging.players
        WHERE NOT is_staff
    """,
    "v_transfers": f"""
        SELECT a.season, a.tid, COALESCE(a.name, b.name) AS name,
               a.phase AS from_phase, b.phase AS to_phase,
               a.club_tid AS from_club_tid, a.club AS from_club,
               b.club_tid AS to_club_tid, b.club AS to_club
        FROM staging.players a
        JOIN staging.players b
          ON a.season = b.season AND a.tid = b.tid
         AND ({phase_sort_sql('a.phase')}) < ({phase_sort_sql('b.phase')})
        WHERE a.club_tid IS DISTINCT FROM b.club_tid
          AND NOT a.is_staff
    """,
    "v_league_table": """
        SELECT s.season, s.phase, s.league_cid, s.pos,
               COALESCE(s.club, c.name) AS club, s.club_tid,
               s.played, s.won, s.drawn, s.lost, s.gf, s.ga, s.gd, s.points, s.source
        FROM staging.standings s
        LEFT JOIN staging.clubs c
          ON (c.season, c.phase, c.tid) = (s.season, s.phase, s.club_tid)
    """,
    "v_match_results": """
        SELECT m.season, m.phase, m.date, m.competition, m.comp_id,
               m.home_tid, hc.name AS home, m.score_home, m.score_away,
               ac.name AS away, m.away_tid, m.attendance, m.formation
        FROM staging.matches m
        LEFT JOIN staging.clubs hc
          ON (hc.season, hc.phase, hc.tid) = (m.season, m.phase, m.home_tid)
        LEFT JOIN staging.clubs ac
          ON (ac.season, ac.phase, ac.tid) = (m.season, m.phase, m.away_tid)
    """,
    "v_top_scorers": """
        SELECT mps.season, mps.tid, any_value(p.name) AS name,
               SUM(mps.goals) AS goals, SUM(mps.assists) AS assists,
               COUNT(*) AS appearances
        FROM staging.match_player_stats mps
        LEFT JOIN staging.players p
          ON (p.season, p.phase, p.tid) = (mps.season, mps.phase, mps.tid)
        GROUP BY mps.season, mps.tid
    """,
}

# Weighted role rating (immersion-safe: derived purely from the 23 attributes, no CA/PA).
# rating = SUM(attribute_value * weight) per (method/tactic, role); attributes not listed
# for that role default to weight 1 (matches fm-data-entry get_weighted_df).
_UNPIVOT = ", ".join(f'"{a}"' for a in ATTR_ORDER)
VIEWS["v_player_ratings"] = f"""
    WITH long AS (
        UNPIVOT staging.player_attributes ON {_UNPIVOT} INTO NAME attribute VALUE value
    ),
    combos AS (SELECT DISTINCT method, role FROM staging.role_weights)
    SELECT l.season, l.phase, l.tid, c.method, c.role,
           SUM(l.value * COALESCE(w.weight, 1)) AS rating
    FROM long l
    CROSS JOIN combos c
    LEFT JOIN staging.role_weights w
      ON w.method = c.method AND w.role = c.role AND w.attribute = LOWER(l.attribute)
    GROUP BY l.season, l.phase, l.tid, c.method, c.role
"""

# Relative standing of each rating (immersion-safe): percentile vs the whole loaded
# population at that (season, phase, method, role). Squad-relative views are then a
# simple club_tid filter on top. Deliberately exposes no ca/pa.
VIEWS["v_player_rating_ranks"] = """
    SELECT r.season, r.phase, r.method, r.role, r.tid, r.rating,
           p.name, p.club, p.club_tid, p.league_cid,
           ROUND(100 * PERCENT_RANK() OVER (
               PARTITION BY r.season, r.phase, r.method, r.role
               ORDER BY r.rating), 1) AS pctile,
           RANK() OVER (
               PARTITION BY r.season, r.phase, r.method, r.role
               ORDER BY r.rating DESC) AS rank_overall
    FROM v_player_ratings r
    JOIN staging.players p USING (season, phase, tid)
    WHERE NOT p.is_staff
"""

# tables each group owns, and the DELETE scope for idempotent reload
GROUPS = ("core", "light", "standings")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _date(s):
    if not s:
        return None
    try:
        return datetime.date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _int(v):
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _load_json(path):
    with open(path) as f:
        return json.load(f)


_INS_VIEW = "_fm_insert_batch"     # registration name reused for every batch, unregistered after


def _insert(con, table, cols, rows):
    """Bulk-insert `rows` (a list of tuples matching `cols`) into staging.<table>.

    Goes through a registered DataFrame rather than `executemany`. DuckDB is columnar, so
    binding parameters row-by-row is pathologically slow against it: measured on real data,
    211,362 x 12 player_history_seasons rows took 39.0s via executemany and 0.13s via
    register+INSERT SELECT — 300x. It dominated everything else, at 98.7% of a snapshot load
    (38.1s of 38.6s, of which reading the JSON was 0.48s). Per snapshot this is ~38s -> ~4s.

    dtype=object IS LOAD-BEARING. Letting pandas infer dtypes would silently corrupt data:
    an integer column containing NULLs becomes float64, so 1 -> 1.0 and NULL -> NaN, and NaN
    does not cast back to an integer. Holding Python objects means DuckDB does the conversion
    against the target column type, exactly as executemany did. Verified per table against
    executemany on real rows (all 23 staging tables byte-identical, including `players` with
    17 nullable columns and the date-valued ones) — re-check with that comparison if this
    ever needs to change.
    """
    if not rows:
        return 0
    colsql = ",".join(f'"{c}"' for c in cols)
    df = pd.DataFrame(rows, columns=list(cols), dtype=object)
    con.register(_INS_VIEW, df)
    try:
        con.execute(f"INSERT INTO staging.{table} ({colsql}) "
                    f"SELECT {colsql} FROM {_INS_VIEW}")
    finally:
        con.unregister(_INS_VIEW)
    return len(rows)


def _delete(con, table, season, phase, extra="", params=()):
    con.execute(
        f"DELETE FROM staging.{table} WHERE season=? AND phase=? {extra}",
        [season, phase, *params],
    )


# ---------------------------------------------------------------------------
# group loaders — each returns {table: rowcount}
# ---------------------------------------------------------------------------

def load_core(con, d, season, phase):
    counts = {}

    # --- players + staff (identity spine) + wide attributes ------------------
    players = _load_json(os.path.join(d, "players.json"))
    prows, arows = [], []
    seen = set()
    acols = ["season", "phase", "tid"] + ATTR_ORDER + [f"{a}_est" for a in ATTR_ORDER]
    for v in players.values():
        tid = _int(v.get("tid"))
        if tid is None or tid in seen:
            continue
        seen.add(tid)
        feet = v.get("feet") or {}
        prows.append((
            season, phase, tid, v.get("name"), False,
            _int(v.get("club_tid")), v.get("club"),
            _int(v.get("league_cid")), v.get("league"),
            _date(v.get("dob")), _int(v.get("nationality_id")),
            v.get("has_attributes"), _int(v.get("squad_status")),
            v.get("loaned_out"), _int(v.get("is_gk")),
            _int(v.get("ca")), _int(v.get("pa")), _int(v.get("reputation")),
            json.dumps(v.get("positions") or {}),
            _int(feet.get("left")), _int(feet.get("right")),
            _int(v.get("value")),
            bool(v.get("loaned_in")), _int(v.get("parent_club_tid")),
            v.get("parent_club"),
            _int(v.get("wage_units")), _int(v.get("wage_gbp")),
            _date(v.get("contract_expiry")), _int(v.get("contract_expiry_year")),
        ))
        attrs, est = v.get("attributes"), v.get("estimated") or {}
        if attrs:
            arows.append(
                (season, phase, tid)
                + tuple(_int(attrs.get(a)) for a in ATTR_ORDER)
                + tuple(est.get(a) for a in ATTR_ORDER)
            )

    srows = []
    staff_path = os.path.join(d, "staff.json")
    if os.path.exists(staff_path):
        for v in _load_json(staff_path).values():
            tid = _int(v.get("tid"))
            if tid is None or tid in seen:
                continue
            seen.add(tid)
            srows.append((
                season, phase, tid, v.get("name"), True,
                _int(v.get("club_tid")), v.get("club"), None, None,
                _date(v.get("dob")), _int(v.get("nationality_id")),
                False, None, None, None, None, None, None,
                json.dumps({}), None, None, None,
                False, None, None,
                None, None, None, None,
            ))

    pcols = ["season", "phase", "tid", "name", "is_staff", "club_tid", "club",
             "league_cid", "league", "dob", "nationality_id", "has_attributes",
             "squad_status", "loaned_out", "is_gk", "ca", "pa", "reputation",
             "positions", "foot_left", "foot_right", "player_value",
             "loaned_in", "parent_club_tid", "parent_club",
             "wage_units", "wage_gbp", "contract_expiry", "contract_expiry_year"]
    counts["players"] = _insert(con, "players", pcols, prows)
    counts["staff"] = _insert(con, "players", pcols, srows)
    counts["player_attributes"] = _insert(con, "player_attributes", acols, arows)

    # long-form positions (every position a player can play + familiarity)
    pprows = []
    for v in players.values():
        tid = _int(v.get("tid"))
        pos = v.get("positions") or {}
        if tid is None or not pos:
            continue
        for code, fam in pos.items():
            pprows.append((season, phase, tid, code, _int(fam)))
    counts["player_positions"] = _insert(
        con, "player_positions",
        ["season", "phase", "tid", "position", "familiarity"], pprows)

    # --- career history (origin club + season-by-season) ---------------------
    hist_path = os.path.join(d, "history.json")
    if os.path.exists(hist_path):
        hist = _load_json(hist_path)
        hrows, hsrows = [], []
        for k, v in hist.items():
            tid = _int(k)
            if tid is None:
                continue
            hrows.append((season, phase, tid, _int(v.get("origin_club_tid")),
                          v.get("origin_club"), _int(v.get("last_season_club_tid")),
                          v.get("confidence"), _int(v.get("record_offset")),
                          _int(v.get("debut_season")), _int(v.get("debut_end_year"))))
            for seq, s in enumerate(v.get("seasons") or []):
                fee = s.get("fee")
                hsrows.append((season, phase, tid, seq, _int(s.get("season")),
                               _int(s.get("end_year")), _int(s.get("club_tid")),
                               str(fee) if fee is not None else None,
                               _int(s.get("apps")), _int(s.get("goals")),
                               _int(s.get("assists")), s.get("rating")))
        counts["player_history"] = _insert(
            con, "player_history",
            ["season", "phase", "tid", "origin_club_tid", "origin_club",
             "last_season_club_tid", "confidence", "record_offset",
             "debut_season", "debut_end_year"], hrows)
        counts["player_history_seasons"] = _insert(
            con, "player_history_seasons",
            ["season", "phase", "tid", "seq", "hist_season", "end_year",
             "club_tid", "fee", "apps", "goals", "assists", "rating"], hsrows)

    # --- injuries (weekly Player-Progress -> spells; managed squad only) ------
    inj_path = os.path.join(d, "injuries.json")
    if os.path.exists(inj_path):
        inj = _load_json(inj_path)
        irows = []
        for k, spells in inj.items():
            tid = _int(k)
            if tid is None:
                continue
            for seq, sp in enumerate(spells):
                start, end, weeks = sp
                irows.append((season, phase, tid, seq,
                              datetime.date.fromisoformat(start),
                              datetime.date.fromisoformat(end), _int(weeks)))
        counts["player_injuries"] = _insert(
            con, "player_injuries",
            ["season", "phase", "tid", "seq", "spell_start", "spell_end", "weeks_out"], irows)

    # --- loan-out spells (same weekly table, bit 5) --------------------------
    loan_path = os.path.join(d, "loans.json")
    if os.path.exists(loan_path):
        lrows = []
        for k, spells in _load_json(loan_path).items():
            tid = _int(k)
            if tid is None:
                continue
            for seq, (start, end, weeks) in enumerate(spells):
                lrows.append((season, phase, tid, seq,
                              datetime.date.fromisoformat(start),
                              datetime.date.fromisoformat(end), _int(weeks)))
        counts["player_loans"] = _insert(
            con, "player_loans",
            ["season", "phase", "tid", "seq", "spell_start", "spell_end", "weeks"], lrows)

    # --- clubs ---------------------------------------------------------------
    clubs = _load_json(os.path.join(d, "clubs.json"))
    crows = [(season, phase, _int(k), v) for k, v in clubs.items() if _int(k) is not None]
    counts["clubs"] = _insert(con, "clubs", ["season", "phase", "tid", "name"], crows)

    # --- competitions --------------------------------------------------------
    comps = _load_json(os.path.join(d, "competitions.json"))
    comp_cols = ["season", "phase", "cid", "uid", "name", "short", "code", "type",
                 "type_id", "nation_id", "num_teams", "matches_in_save"]
    comp_rows = [(season, phase, _int(v.get("cid")), _int(v.get("uid")), v.get("name"),
                  v.get("short"), v.get("code"), v.get("type"), _int(v.get("type_id")),
                  _int(v.get("nation_id")), _int(v.get("num_teams")),
                  _int(v.get("matches_in_save"))) for v in comps.values()]
    counts["competitions"] = _insert(con, "competitions", comp_cols, comp_rows)

    # --- leagues + members (source='members') --------------------------------
    lg_path = os.path.join(d, "leagues.json")
    if os.path.exists(lg_path):
        leagues = _load_json(lg_path)
        lg_cols = ["season", "phase", "cid", "name", "type", "nation_id", "nation",
                   "reputation", "member_count", "fixtures"]
        lg_rows, mem_rows = [], []
        for v in leagues.values():
            cid = _int(v.get("cid"))
            lg_rows.append((season, phase, cid, v.get("name"), v.get("type"),
                            _int(v.get("nation_id")), v.get("nation"),
                            _int(v.get("reputation")),
                            _int(v.get("member_count")), _int(v.get("fixtures"))))
            for m in v.get("members") or []:
                mem_rows.append((season, phase, cid, _int(m), "members"))
        counts["leagues"] = _insert(con, "leagues", lg_cols, lg_rows)
        counts["league_members(members)"] = _insert(
            con, "league_members",
            ["season", "phase", "league_cid", "club_tid", "source"], mem_rows)

    # --- club -> league (source='club_league') ------------------------------
    # extract.py writes club_league.json (main dir) from the club records — exact and
    # available on day-1, before any match. This is what the dashboard resolves on.
    cl_path = os.path.join(d, "club_league.json")
    if os.path.exists(cl_path):
        rows = [(season, phase, _int(v.get("league_cid")), _int(k), "club_league")
                for k, v in _load_json(cl_path).items() if v.get("league_cid") is not None]
        counts["league_members(club_league)"] = _insert(
            con, "league_members",
            ["season", "phase", "league_cid", "club_tid", "source"], rows)

    # --- matches + events + player stats -------------------------------------
    season_matches = _load_json(os.path.join(d, "matches.json"))
    m_cols = (["season", "phase", "anchor", "date", "competition", "comp_id",
               "home_flag", "home_tid", "away_tid", "attendance", "score_home",
               "score_away", "star_home", "star_away", "formation"]
              + [f"home_{k}" for k in _TS_KEYS] + [f"away_{k}" for k in _TS_KEYS])
    ev_cols = ["season", "phase", "anchor", "seq", "minute", "added", "min_display",
               "tid", "type", "type_byte", "b0"]
    mps_cols = (["season", "phase", "anchor", "side", "tid", "team_tid",
                 "opponent_tid", "date", "competition", "pos_order", "rating"]
                + [f for f in _XI if f not in ("posOrder", "tid_int", "rating")])
    m_rows, ev_rows, mps_rows = [], [], []
    for m in season_matches:
        anchor = _int(m.get("anchor"))
        score = m.get("score") or {}
        ts = m.get("team_stats") or {}
        h = ts.get("home") or {}
        a = ts.get("away") or {}
        home_tid, away_tid = _int(m.get("home_tid")), _int(m.get("away_tid"))
        mdate, comp = _date(m.get("date")), m.get("competition")
        m_rows.append((
            season, phase, anchor, mdate, comp, _int(m.get("comp_id")),
            _int(m.get("home_flag")), home_tid, away_tid, _int(m.get("attendance")),
            _int(score.get("home")), _int(score.get("away")),
            _int(m.get("star_home")), _int(m.get("star_away")), m.get("formation"),
            *[_num(h.get(k)) for k in _TS_KEYS], *[_num(a.get(k)) for k in _TS_KEYS],
        ))
        for i, e in enumerate(m.get("events") or []):
            ev_rows.append((season, phase, anchor, i, _int(e.get("min")),
                            _int(e.get("added")), e.get("min_display"),
                            _int(e.get("tid")), e.get("type"),
                            _int(e.get("type_byte")), _int(e.get("b0"))))
        for side, team_tid, opp_tid in (("home", home_tid, away_tid),
                                        ("away", away_tid, home_tid)):
            side_seen = set()
            for x in m.get(f"{side}_xi") or []:
                tid = _int(x.get("tid_int"))
                if tid is None or tid in side_seen:
                    continue
                side_seen.add(tid)
                mps_rows.append((
                    season, phase, anchor, side, tid, team_tid, opp_tid, mdate, comp,
                    _int(x.get("posOrder")), _int(x.get("rating")),
                    *[_int(x.get(f)) for f in _XI
                      if f not in ("posOrder", "tid_int", "rating")],
                ))
    counts["matches"] = _insert(con, "matches", m_cols, m_rows)
    counts["match_events"] = _insert(con, "match_events", ev_cols, ev_rows)
    counts["match_player_stats"] = _insert(con, "match_player_stats", mps_cols, mps_rows)
    return counts


def _num(v):
    """int-or-float passthrough for team_stats (rating is a float)."""
    if v is None or v == "":
        return None
    return v


def load_light(con, d, season, phase):
    counts = {}
    ld = os.path.join(d, "light_results")

    res_path = os.path.join(ld, "results.csv")
    if os.path.exists(res_path):
        rows, seq = [], {}
        with open(res_path, newline="") as f:
            for r in csv.DictReader(f):
                key = (_int(r["home_tid"]), _int(r["away_tid"]), _int(r["cid"]))
                seq[key] = seq.get(key, -1) + 1
                rows.append((season, phase, key[0], key[1], key[2], seq[key],
                             r.get("home") or None, r.get("away") or None,
                             _int(r.get("scoreH")), _int(r.get("scoreA")),
                             r.get("competition") or None, _int(r.get("copies"))))
        counts["results"] = _insert(
            con, "results",
            ["season", "phase", "home_tid", "away_tid", "cid", "seq", "home",
             "away", "scoreH", "scoreA", "competition", "copies"], rows)

    # NOTE: club->league (source='club_league') is loaded by load_core from the MAIN-dir
    # club_league.json — the exact, complete club-record map (light-results ∪ club records).
    # It is deliberately NOT reloaded here: the light_results/club_league.json is only the
    # light-results-derived SUBSET (drops clubs whose league isn't a resolved league-type,
    # e.g. Frem's Danish 3. Division cid 1147), and reloading it used to clobber the exact
    # map. See _clear_group: 'club_league' now belongs to the 'core' group.
    return counts


def _backfill_competition(con, season, phase):
    """Detailed `matches` (and their per-player `match_player_stats`) carry a `comp_id`
    but a NULL `competition` NAME for LEAGUE games: the extractor resolves cup/friendly
    names but league names live in `staging.leagues`, not competitions.json (light-results
    also drops unresolved league-type cids like Denmark's 3. Division = 1147 — see the note
    in load_light). Backfill the name from `leagues` by comp_id, then propagate to the
    per-player stat lines by anchor, so competition filters/tables aren't blank for the
    league (the bulk of games)."""
    con.execute("""
        UPDATE staging.matches m SET competition = l.nm
        FROM (SELECT cid, any_value(name) AS nm FROM staging.leagues
              WHERE name IS NOT NULL GROUP BY cid) l
        WHERE m.competition IS NULL AND m.comp_id = l.cid
          AND m.season = ? AND m.phase = ?
    """, [season, phase])
    con.execute("""
        UPDATE staging.match_player_stats mps SET competition = m.competition
        FROM staging.matches m
        WHERE mps.competition IS NULL AND mps.anchor = m.anchor
          AND (mps.season, mps.phase) = (m.season, m.phase)
          AND mps.season = ? AND mps.phase = ?
    """, [season, phase])


def load_standings(con, d, season, phase):
    sd = os.path.join(d, "light_results", "standings")
    if not os.path.isdir(sd):
        return {}
    cols = ["season", "phase", "league_cid", "club_tid", "pos", "club", "played",
            "won", "drawn", "lost", "gf", "ga", "gd", "points", "source"]
    rows = []
    for path in sorted(glob.glob(os.path.join(sd, "*.csv"))):
        cid = _int(os.path.splitext(os.path.basename(path))[0])
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                rows.append((season, phase, cid, _int(r["club_tid"]), _int(r["pos"]),
                             r.get("club"), _int(r["played"]), _int(r["won"]),
                             _int(r["drawn"]), _int(r["lost"]), _int(r["gf"]),
                             _int(r["ga"]), _int(r["gd"]), _int(r["points"]),
                             "lightresults_computed"))
    return {"standings": _insert(con, "standings", cols, rows)}


# DELETE scope so a reload of one group leaves the others intact
def _clear_group(con, group, season, phase):
    if group == "core":
        for t in ("players", "player_attributes", "player_positions",
                  "player_history", "player_history_seasons", "player_injuries",
                  "player_loans",
                  "clubs", "competitions", "leagues", "matches", "match_events",
                  "match_player_stats"):
            _delete(con, t, season, phase)
        _delete(con, "league_members", season, phase, "AND source='members'")
        # club->league (exact club-record map) is a core artifact (main-dir club_league.json)
        _delete(con, "league_members", season, phase, "AND source='club_league'")
    elif group == "light":
        _delete(con, "results", season, phase)
    elif group == "standings":
        _delete(con, "standings", season, phase,
                "AND source='lightresults_computed'")


_GROUP_FN = {"core": load_core, "light": load_light, "standings": load_standings}


def _archive_snapshot(con, season, phase, label, snap_date):
    """Copy the current (season,phase) players+attributes into history.player_snapshots
    before the slice is overwritten, so a superseded in-season checkpoint is retained for
    progression. Idempotent per snapshot_label."""
    con.execute("DELETE FROM history.player_snapshots WHERE snapshot_label=?", [label])
    con.execute(
        """INSERT INTO history.player_snapshots
           SELECT ?, ?, ?, p.*, a.* EXCLUDE (season, phase, tid)
           FROM staging.players p JOIN staging.player_attributes a USING (season, phase, tid)
           WHERE p.season=? AND p.phase=?""",
        [label, snap_date, datetime.datetime.now(), season, phase])
    return con.execute("SELECT COUNT(*) FROM history.player_snapshots "
                       "WHERE snapshot_label=?", [label]).fetchone()[0]


def _detect_groups(d):
    present = []
    if os.path.exists(os.path.join(d, "players.json")):
        present.append("core")
    ld = os.path.join(d, "light_results")
    if os.path.exists(os.path.join(ld, "results.csv")) or \
       os.path.exists(os.path.join(ld, "club_league.json")):
        present.append("light")
    if os.path.isdir(os.path.join(ld, "standings")):
        present.append("standings")
    return present


# ---------------------------------------------------------------------------
# per-label orchestration
# ---------------------------------------------------------------------------

def resolve_season_phase(label, d, override):
    # 1) explicit --season/--phase override always wins (manual force / re-slice).
    if override[0] is not None and override[1] is not None:
        return override
    summ_path = os.path.join(d, "summary.json")
    summ = _load_json(summ_path) if os.path.exists(summ_path) else {}
    # 2) authoritative explicit fields written by extract.py: season (end-year) + phase
    #    (the in-game date). A match-less day-1 save has season but phase=None -> synthesise
    #    a season-start date so it still sorts first and coexists with dated in-season saves.
    s_season, s_phase = summ.get("season"), summ.get("phase")
    if s_season is not None:
        season = override[0] if override[0] is not None else int(s_season)
        phase = override[1] or s_phase or f"{season - 1:04d}-07-01"
        return season, phase
    # 2b) match-less save with no season in summary but season given on the CLI.
    if override[0] is not None:
        return override[0], (override[1] or f"{override[0] - 1:04d}-07-01")
    # 3) legacy fallback: parse the label string (old 'YYYY-mid' form).
    try:
        return parse_label(label)
    except ValueError:
        pass
    auto = summ.get("label_auto")
    if auto:
        try:
            return parse_label(auto)
        except ValueError:
            pass
    raise SystemExit(
        f"cannot derive season/phase from label {label!r}; "
        f"pass --season and --phase explicitly")


def load_label(con, d, include, override=(None, None)):
    label = os.path.basename(os.path.normpath(d))
    season, phase = resolve_season_phase(label, d, override)
    groups = [g for g in _detect_groups(d) if g in include]
    if not groups:
        print(f"  {label}: nothing to load (no matching groups present)")
        return season, phase

    summ = {}
    sp = os.path.join(d, "summary.json")
    if os.path.exists(sp):
        summ = _load_json(sp)

    con.execute("BEGIN TRANSACTION")
    try:
        # multi-snapshot: archive a superseded (different-label) snapshot before overwrite
        if "core" in groups:
            prior = con.execute(
                "SELECT label, COALESCE(date_to, latest_match) FROM staging.extracts "
                "WHERE season=? AND phase=?", [season, phase]).fetchone()
            if prior and prior[0] != label:
                n = _archive_snapshot(con, season, phase, prior[0], prior[1])
                new_end = _date((summ.get("date_range") or [None, None])[1]) \
                    or _date(summ.get("latest_match"))
                warn = ""
                if prior[1] and new_end and new_end < prior[1]:
                    warn = (f"  ⚠ this snapshot ({new_end}) is OLDER than the one it replaces "
                            f"({prior[1]}) — it will become current")
                print(f"  archived superseded {prior[0]} ({prior[1]}) -> history "
                      f"({n} players){warn}")
        counts = {}
        for g in groups:
            _clear_group(con, g, season, phase)
            counts.update(_GROUP_FN[g](con, d, season, phase))
        _backfill_competition(con, season, phase)
        rng = summ.get("date_range") or [None, None]
        _delete(con, "extracts", season, phase)
        # save_path is stored as a BASENAME, not the absolute path the extract recorded.
        # staging.extracts is the rebuild recipe (scripts/export_manifest.py reads it), and an
        # absolute /Users/<you>/Downloads/... path silently makes that recipe machine-specific,
        # so it can't rebuild the store on another laptop. The archive resolves it under
        # $FM_SAVES_DIR/<career>/ instead. source_dir stays absolute: it points at output/,
        # which is a local build artefact rather than part of the recipe.
        con.execute(
            "INSERT INTO staging.extracts VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [season, phase, label, summ.get("label_auto"), os.path.abspath(d),
             os.path.basename(summ.get("save") or "") or None,
             _date(summ.get("latest_match")),
             _date(rng[0]), _date(rng[1]), datetime.datetime.now(),
             json.dumps(counts)])
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise

    _crosscheck(label, counts, summ.get("counts") or {})
    summary = "  ".join(f"{k} {v}" for k, v in counts.items())
    print(f"  loaded {label} (season {season}, {phase}): {summary}")
    return season, phase


def _crosscheck(label, counts, expected):
    for key in ("players", "staff", "matches"):
        if key in expected and key in counts and counts[key] != expected[key]:
            print(f"  ! {label}: {key} loaded {counts[key]} "
                  f"but summary.json says {expected[key]}")


# ---------------------------------------------------------------------------
# schema bootstrap + CLI
# ---------------------------------------------------------------------------

def create_schema(con):
    for stmt in DDL:
        con.execute(stmt)
    _migrate(con)


# Column additions for stores created before a schema change (CREATE TABLE IF NOT EXISTS
# won't add columns to an existing table). Each is idempotent.
_MIGRATIONS = [
    "ALTER TABLE staging.players ADD COLUMN IF NOT EXISTS loaned_in BOOLEAN",
    "ALTER TABLE staging.players ADD COLUMN IF NOT EXISTS parent_club_tid INTEGER",
    "ALTER TABLE staging.players ADD COLUMN IF NOT EXISTS parent_club VARCHAR",
    "ALTER TABLE staging.players ADD COLUMN IF NOT EXISTS wage_units INTEGER",
    "ALTER TABLE staging.players ADD COLUMN IF NOT EXISTS wage_gbp BIGINT",
    "ALTER TABLE staging.players ADD COLUMN IF NOT EXISTS contract_expiry DATE",
    "ALTER TABLE staging.players ADD COLUMN IF NOT EXISTS contract_expiry_year INTEGER",
    "ALTER TABLE staging.leagues ADD COLUMN IF NOT EXISTS reputation INTEGER",
    # 2026-08-19: career history re-decoded (linked-list chains + the P-38 link), which also
    # yielded assists, average rating and the debut season. See fmparser/history.py.
    "ALTER TABLE staging.player_history ADD COLUMN IF NOT EXISTS debut_season INTEGER",
    "ALTER TABLE staging.player_history ADD COLUMN IF NOT EXISTS debut_end_year INTEGER",
    "ALTER TABLE staging.player_history_seasons ADD COLUMN IF NOT EXISTS assists INTEGER",
    "ALTER TABLE staging.player_history_seasons ADD COLUMN IF NOT EXISTS rating DOUBLE",
]


def _migrate(con):
    for stmt in _MIGRATIONS:
        try:
            con.execute(stmt)
        except Exception as e:            # older DuckDB without IF NOT EXISTS -> ignore dups
            if "already exists" not in str(e).lower():
                raise
    _drop_extracts_phase_check(con)


def _drop_extracts_phase_check(con):
    """Stores created before phase became a date have CHECK(phase IN ('start','mid','end'))
    on staging.extracts, which now rejects date-valued phases. DuckDB can't drop an unnamed
    CHECK in place, so rebuild the table (data + column types preserved) without it.
    Idempotent: a no-op once the constraint is gone."""
    has_check = con.execute(
        "SELECT COUNT(*) FROM duckdb_constraints() "
        "WHERE table_name = 'extracts' AND constraint_type = 'CHECK'").fetchone()[0]
    if not has_check:
        return
    con.execute("CREATE OR REPLACE TABLE staging._extracts_mig AS "
                "SELECT * FROM staging.extracts")
    con.execute("DROP TABLE staging.extracts")
    con.execute("ALTER TABLE staging._extracts_mig RENAME TO extracts")


def seed_role_weights(con):
    """(Re)seed the built-in tactic weight-sets from seeds/role_weights.csv, leaving
    any user-defined tactics untouched. Idempotent: replaces only the built-in methods."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seeds",
                        "role_weights.csv")
    if not os.path.exists(path):
        print(f"  ! role_weights seed missing at {path}; skipping")
        return
    ph = ",".join("?" * len(_SEED_METHODS))
    con.execute(f"DELETE FROM staging.role_weights WHERE method IN ({ph})",
                list(_SEED_METHODS))
    con.execute(
        "INSERT INTO staging.role_weights (method, role, attribute, category, weight) "
        "SELECT method, role, attribute, category, weight FROM read_csv_auto(?)", [path])


def seed_eligible_origin_clubs(con):
    """(Re)seed the Athletic-Bilbao eligible-origin-club list from
    seeds/eligible_origin_clubs.csv (replace). Curate that CSV to define which clubs'
    youth products count as eligible (e.g. Danish Capital Region)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seeds",
                        "eligible_origin_clubs.csv")
    if not os.path.exists(path):
        print(f"  ! eligible_origin_clubs seed missing at {path}; skipping")
        return
    rows = []
    with open(path, encoding="utf-8") as fh:
        reader = csv.reader(r for r in fh if r.strip() and not r.lstrip().startswith("#"))
        header = next(reader, None)                 # skip the column header
        for r in reader:
            if len(r) >= 1 and _int(r[0]) is not None:
                rows.append((_int(r[0]), r[1] if len(r) > 1 else None,
                             r[2] if len(r) > 2 else None))
    con.execute("DELETE FROM staging.eligible_origin_clubs")
    con.executemany("INSERT INTO staging.eligible_origin_clubs "
                    "(club_tid, club_name, region) VALUES (?,?,?)", rows)


def seed_reference(con):
    """Seed the static position->role map (replace) and app_config defaults (only for
    keys that don't yet exist, so Config-page edits survive reloads)."""
    con.execute("DELETE FROM staging.position_role_map")
    con.executemany("INSERT INTO staging.position_role_map VALUES (?,?)",
                    list(POSITION_ROLE.items()))
    for k, v in APP_CONFIG_DEFAULTS.items():
        con.execute(
            "INSERT INTO staging.app_config SELECT ?, ? "
            "WHERE NOT EXISTS (SELECT 1 FROM staging.app_config WHERE key=?)", [k, v, k])


def seed_config_bundle(con):
    """Apply a committed config bundle (seeds/config_bundle.json) as the baked default —
    the same shape the dashboard exports (db.export_config_bundle). Runs AFTER
    seed_role_weights/seed_reference so it wins for overlapping methods (e.g. 'personal').
    Absent file = no-op. app_config keys and included tactics are replaced authoritatively."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seeds",
                        "config_bundle.json")
    if not os.path.exists(path):
        return
    with open(path) as f:
        b = json.load(f)
    for k, v in (b.get("app_config") or {}).items():
        con.execute("DELETE FROM staging.app_config WHERE key=?", [k])
        con.execute("INSERT INTO staging.app_config VALUES (?, ?)", [k, str(v)])
    rows = b.get("role_weights") or []
    if rows:
        methods = sorted({r["method"] for r in rows})
        ph = ",".join("?" * len(methods))
        con.execute(f"DELETE FROM staging.role_weights WHERE method IN ({ph})", methods)
        con.executemany(
            "INSERT INTO staging.role_weights (method, role, attribute, category, weight) "
            "VALUES (?,?,?,?,?)",
            [(r["method"], r["role"], r["attribute"], r.get("category"), int(r["weight"]))
             for r in rows])
    prm = b.get("position_role_map") or {}
    if prm:
        con.execute("DELETE FROM staging.position_role_map")
        con.executemany("INSERT INTO staging.position_role_map VALUES (?,?)", list(prm.items()))
    print(f"  seeded config bundle from {os.path.basename(path)} "
          f"({len(b.get('app_config') or {})} settings, {len(rows)} weight rows)")


# person_id for a slice row; '?' when dob is unknown so the row still gets a stable key
# (28 tids appear in match stats but in no players slice at all — they keep tid-only identity).
_PERSON_ID = "concat(CAST(tid AS VARCHAR), '-', COALESCE(CAST(dob AS VARCHAR), '?'))"


def _psort(col="phase"):
    """Chronological sort key for a phase. Phases are in-game dates now; legacy stores may
    still hold the old start/mid/end words, which sort as epoch (before any real date)."""
    return (f"CASE {col} WHEN 'start' THEN '0000-00-00' WHEN 'mid' THEN '0000-00-01' "
            f"WHEN 'end' THEN '0000-00-02' ELSE {col} END")


def rebuild_persons(con):
    """Rebuild the (tid,dob) -> person_id bridge from staging.players.

    Cheap and idempotent: derived entirely from players, so it is rebuilt wholesale after every
    load rather than maintained incrementally. Needs no re-extraction — dob is already present
    in every players slice."""
    ordr = _psort("phase")
    con.execute("DELETE FROM staging.person_slices")
    con.execute(f"""INSERT INTO staging.person_slices (season, phase, tid, person_id)
                    SELECT season, phase, tid, {_PERSON_ID} FROM staging.players""")
    con.execute("DELETE FROM staging.persons")
    con.execute(f"""
        INSERT INTO staging.persons (person_id, tid, dob, name, first_seen, last_seen, slices)
        SELECT {_PERSON_ID}, tid, dob,
               arg_max(name, {ordr}) AS name,
               arg_min(phase, {ordr}) AS first_seen,
               arg_max(phase, {ordr}) AS last_seen,
               COUNT(*) AS slices
        FROM staging.players GROUP BY tid, dob""")
    n, t = con.execute("SELECT COUNT(*), COUNT(DISTINCT tid) FROM staging.persons").fetchone()
    if n > t:
        print(f"  identity bridge: {n} persons across {t} tids "
              f"({n - t} recycled slot(s) — see docs/IDS.md)")


def create_views(con):
    for name, sql in VIEWS.items():
        con.execute(f"CREATE OR REPLACE VIEW {name} AS {sql}")


def reset_schema(con):
    # mart first: its views depend on staging, so dropping staging out from under them
    # would leave dangling definitions behind.
    drop_mart(con)
    con.execute("DROP SCHEMA IF EXISTS staging CASCADE")
    con.execute("DROP SCHEMA IF EXISTS history CASCADE")
    for name in VIEWS:
        con.execute(f"DROP VIEW IF EXISTS {name}")


def discover_labels(root):
    out = []
    for entry in sorted(os.listdir(root)):
        d = os.path.join(root, entry)
        if os.path.isdir(d) and os.path.exists(os.path.join(d, "summary.json")):
            out.append(d)
    return out


def main():
    ap = argparse.ArgumentParser(description="Load fm-parser extracts into DuckDB")
    ap.add_argument("path", nargs="?", help="output/<label> dir, or output root with --all; "
                                            "not needed with --refresh-only")
    ap.add_argument("--db", default="fm.duckdb")
    ap.add_argument("--all", action="store_true",
                    help="load every subdir of PATH containing summary.json")
    ap.add_argument("--include", default=",".join(GROUPS),
                    help=f"comma list of groups to load (default all: {','.join(GROUPS)})")
    ap.add_argument("--season", type=int)
    ap.add_argument("--phase", help="snapshot phase; normally the in-game date "
                    "'YYYY-MM-DD' (auto-derived from summary.json — rarely needed). "
                    "Legacy words start/mid/end still accepted.")
    ap.add_argument("--reset", action="store_true",
                    help="drop and recreate the staging schema + views first")
    ap.add_argument("--refresh-only", action="store_true",
                    help="rebuild the SQL views + the mart layer against an existing store "
                         "and load nothing. Both are just definitions, so a change to "
                         "fmparser/mart.py or VIEWS does not reach a store until something "
                         "re-runs them; without this the only way was a full re-import.")
    args = ap.parse_args()

    if args.path is None and not args.refresh_only:
        ap.error("path is required (or pass --refresh-only to just rebuild views + mart)")

    include = [g.strip() for g in args.include.split(",") if g.strip()]
    bad = [g for g in include if g not in GROUPS]
    if bad:
        ap.error(f"unknown group(s): {bad}; choose from {GROUPS}")

    if args.refresh_only:
        con = duckdb.connect(args.db)
        try:
            create_views(con)
            mart_objects = create_mart(con)
            print(f"{args.db}: {len(VIEWS)} views + {len(mart_objects)} mart objects rebuilt "
                  f"(nothing loaded)")
        finally:
            con.close()
        return

    dirs = discover_labels(args.path) if args.all else [args.path.rstrip("/")]
    if not dirs:
        raise SystemExit(f"no labels found under {args.path}")

    # collision pre-flight: two on-disk labels -> same (season, phase)
    if args.all:
        seen = {}
        for d in dirs:
            label = os.path.basename(os.path.normpath(d))
            try:
                sp = parse_label(label)
            except ValueError:
                continue
            seen.setdefault(sp, []).append(label)
        for sp, labels in seen.items():
            if len(labels) > 1:
                print(f"! WARNING: labels {labels} all map to season {sp[0]} "
                      f"phase {sp[1]!r}; loaded in order, last wins ({labels[-1]}).")

    con = duckdb.connect(args.db)
    try:
        if args.reset:
            reset_schema(con)
        create_schema(con)
        seed_role_weights(con)
        seed_eligible_origin_clubs(con)
        seed_reference(con)
        seed_config_bundle(con)
        print(f"loading into {args.db}")
        ok, fail = 0, 0
        for d in dirs:
            try:
                load_label(con, d, include, (args.season, args.phase))
                ok += 1
            except Exception as e:  # one bad label must not abort a batch
                fail += 1
                print(f"  ! FAILED {os.path.basename(os.path.normpath(d))}: {e}")
        rebuild_persons(con)
        create_views(con)
        mart_objects = create_mart(con)
        print(f"done: {ok} loaded, {fail} failed. views refreshed, "
              f"{len(mart_objects)} mart objects rebuilt.")
    finally:
        con.close()


if __name__ == "__main__":
    main()
