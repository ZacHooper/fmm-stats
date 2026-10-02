#!/usr/bin/env python3
"""
Load fm-parser extract bundles into a DuckDB store.

    uv run python load_duckdb.py output/2022-end [--db fm.duckdb]
    uv run python load_duckdb.py output --all
    uv run python load_duckdb.py output/my-label --season 2024 --phase mid
    uv run python load_duckdb.py output/2022-end --include core,light
    uv run python load_duckdb.py output --all --reset

The tables in the `raw` schema are a 1:1 mirror of the JSON that the extractors
write to output/<label>/ (same grain, minimal reshaping) — every row stamped with
season (int end-year, 21/22 -> 2022) and phase (the save's in-game date). The
modelled layers on top are the dbt project in transform/ (stg, int) and fmstats/mart.py,
built by create_views() and create_mart(). Loads are idempotent: re-loading a label replaces
exactly that (season, phase) slice.

duckdb is imported only here; the extractors stay pure-stdlib.
"""
import argparse
import csv
import datetime
import json
import os
import re
import sys

import duckdb
import pandas as pd     # bulk-insert path in _insert(); see its docstring for why

# The field lists and reference constants the parser declares.
from fmparser.model import ATTR_ORDER
from fmparser import careers
from fmparser.tables.matches import EVENT_TYPE
from fmparser.tables.training import CONTRACTED as _CONTRACTED
from fmstats import compat as models_compat
from fmstats.mart import create_mart, drop_mart

# ---------------------------------------------------------------------------
# schema
# ---------------------------------------------------------------------------

# team_stats side columns, inlined onto matches as home_* / away_*
_TS_KEYS = ["shots", "shots_on_target", "rating", "players_used", "passes",
            "passes_completed", "tackles", "tackles_won", "crosses", "interceptions"]

# a player's match line, as fmparser/tables/matches.py PLAYER_SLOT names it. posOrder ->
# pos_order; the rest map straight through.
_XI = ["posOrder", "tid", "rating", "goals", "assists", "passA", "passC", "keyPass",
       "tackA", "tackW", "intercept", "headA", "headW", "crossA", "crossC", "dribbles",
       "mistakes", "mistGoal", "shotA", "shotO", "condition", "subOn", "subOff", "yellow"]

# The unnamed 1-20 attribute bytes, taken from the parser rather than retyped, so the
# store cannot drift from the record. See fmparser/tables/player_attributes.py HIDDEN_OFFSETS and
# fmparser/tables/staff.py HIDDEN_OFFSETS for why they are carried but not named.
from fmparser.tables.player_attributes import HIDDEN_OFFSETS as _PLAYER_HIDDEN  # noqa: E402
from fmparser.tables.player_attributes import SRC_OFFSETS as _SRC              # noqa: E402
from fmparser.tables.player_attributes import PLAIN_OFFSETS as _PLAIN            # noqa: E402
SRC_COLS = list(_SRC.values()) + list(_PLAIN.values())
from fmparser.tables.person_info import PERSON_FIELDS as _PERSON        # noqa: E402
PERSON_COLS = list(_PERSON)
# A person's name ids, and the name tables they index (names.json).
NAME_ID_COLS = ["first_name_id", "last_name_id", "common_name_id"]
NAME_TABLES = ("first_names", "surnames", "nicknames")
# Everything off the info record is a small integer except the one date.
PERSON_DATE_COLS = {"joined_date"}
_PERSON_SQL = {c: ("DATE" if c in PERSON_DATE_COLS else "INTEGER") for c in PERSON_COLS}
from fmparser.tables.staff import HIDDEN_OFFSETS as _STAFF_HIDDEN      # noqa: E402
PLAYER_HIDDEN_COLS = list(_PLAYER_HIDDEN.values())
STAFF_HIDDEN_COLS = list(_STAFF_HIDDEN.values())


# Column order for raw.staff_attributes. Must match the DDL below; the value tuple is
# built from this list so the two cannot drift.
STAFF_ATTR_COLS = [
    "season", "phase", "tid",
    "ca", "pa", "home_reputation", "current_reputation", "world_reputation",
    "reputation_tier",
    "attacking_intent", "style",
    "financial_control", "outfield_coaching", "goalkeeping_coaching", "discipline",
    "judging_ability", "judging_potential", "people_management", "motivating",
    "tactical_knowledge", "youth_coaching",
] + STAFF_HIDDEN_COLS + [
    "formation_preferred", "formation_attacking", "formation_defensive",
    "formation_preferred_name", "formation_attacking_name", "formation_defensive_name",
]


# ---------------------------------------------------------------------------- attribute model
# The estimation model, moved OUT of the parser and INTO the database (2026-09-17).
#
# It used to run in extract.py, so only its OUTPUT ever reached the store and retraining meant
# a ~25-minute re-extract of every save before a candidate could be scored. Now the raw bytes
# are stored (attributes.SRC_OFFSETS / PLAIN_OFFSETS) and the coefficients live in a table, so
# a retrain is: write new coefficients, run `--refresh-only`, done. The parser scrapes; the
# database infers.
#
# `raw.player_attributes` is a VIEW over `player_attributes_exact` (what the save states
# outright) and this model (everything else), so every existing consumer is unchanged and the
# `_est` flags still say which is which.
ATTR_MODEL_DDL = """CREATE TABLE IF NOT EXISTS raw.attribute_model (
        attribute VARCHAR NOT NULL, feature VARCHAR NOT NULL, coef DOUBLE NOT NULL,
        own_offset INTEGER, partner_offset INTEGER, fitted VARCHAR
    )"""


def _seed_attribute_model(con, force=False):
    """Seed the coefficient table from fmparser.model.FROZEN unless it already holds a fit.

    The frozen dict stays the DEFAULT so a fresh store reproduces today's numbers exactly; a
    refit overwrites the table and `--refresh-only` picks it up without touching the parser.
    """
    from fmparser import model as _MOD
    # Aerial was fitted until 2026-09-17 and is now a closed form. An existing store still
    # carries its rows; the view no longer reads them, but leaving them there would let a
    # later refit resurrect it. Prune anything that is no longer a fitted attribute.
    con.execute("DELETE FROM raw.attribute_model WHERE attribute NOT IN "
                "(" + ", ".join(repr(a) for a in _MOD.FROZEN) + ")")
    n = con.execute("SELECT count(*) FROM raw.attribute_model").fetchone()[0]
    if n and not force:
        return n
    con.execute("DELETE FROM raw.attribute_model")
    rows = []
    for attr, (own, partner, feats, coef) in _MOD.FROZEN.items():
        for f, c in list(zip(feats, coef)) + [("intercept", coef[-1])]:
            rows.append((attr, f, float(c), own, partner, "frozen-2024-bucaspor-28"))
    con.executemany("INSERT INTO raw.attribute_model VALUES (?,?,?,?,?,?)", rows)
    return len(rows)


# The 15 positions in the order the player record carries their familiarities.
_POSITIONS = ["GK", "SW", "DL", "DC", "DR", "DMC", "ML", "MC", "MR", "AML", "AMC", "AMR",
              "ST", "DML", "DMR"]


def _attr_cols_ddl():
    cols = [f'"{a}" INTEGER' for a in ATTR_ORDER]
    cols += [f'"{a}_est" BOOLEAN' for a in ATTR_ORDER]
    return ",\n    ".join(cols)


# raw.player_scrapbook's columns after (season, phase): (column, SQL type, key in
# player_scrapbook.json). The 23 attributes take the names raw.player_attributes uses.
SCRAPBOOK_COLS = (
    [("list", "INTEGER", "list"), ("list_season", "INTEGER", "list_season"),
     ("slot", "INTEGER", "slot"), ("player_tid", "INTEGER", "player_tid"),
     ("full_name", "VARCHAR", "full_name"), ("first_name", "VARCHAR", "first_name"),
     ("last_name", "VARCHAR", "last_name"), ("club_name", "VARCHAR", "club"),
     ("competition", "VARCHAR", "competition"),
     ("club_tid", "INTEGER", "club_tid"), ("loan_club_tid", "INTEGER", "loan_club_tid"),
     ("scrapbook_date", "DATE", None), ("age", "INTEGER", "age"), ("role", "INTEGER", "role")]
    + [(a, "INTEGER", f"attr_{a.lower()}") for a in ATTR_ORDER]
    + [(c, "INTEGER", c) for c in ("condition", "morale", "form_1", "form_2", "form_3",
                                   "form_4", "form_5")]
    + [("avg_rating", "DOUBLE", "avg_rating")]
    + [(f"pos_{p.lower()}", "INTEGER", f"pos_{p.lower()}") for p in _POSITIONS]
    + [("value", "BIGINT", "value"), ("wage", "BIGINT", "wage")]
    + [(c, "INTEGER", c) for c in ("caps", "intl_goals", "u21_caps", "u21_goals", "apps",
                                   "goals", "conceded", "assists", "yellows", "foot_left",
                                   "foot_right", "colour_1", "colour_2")])


def _scrapbook_cols_ddl():
    return ",\n        ".join(f'"{c}" {t}' for c, t, _ in SCRAPBOOK_COLS)


def _scrapbook_date(e):
    """An entry's date: `scrapbook_day` is the 0-based day of `scrapbook_year`."""
    return (datetime.date(e["scrapbook_year"], 1, 1)
            + datetime.timedelta(e["scrapbook_day"]))


def _exact_cols_ddl():
    # No `_est` columns here: a NULL IS the "not stated" flag, and the view derives the rest.
    return ",\n    ".join(f'"{a}" INTEGER' for a in ATTR_ORDER)


# NB: no enforced PRIMARY KEYs. DuckDB maintains an ART index per PK, and bulk
# DELETE+INSERT (our idempotent per-label reload) against that index is pathologically
# slow (minutes for ~30k rows). The loader guarantees uniqueness itself (dedup + a
# clean DELETE of the (season,phase) slice before each INSERT), so the natural key is
# documented in a comment per table rather than enforced. Reintroduce PKs only if an
# external writer starts touching these tables.
DDL = [
    "CREATE SCHEMA IF NOT EXISTS raw",

    # natural key: (season, phase). phase is the snapshot's in-game DATE ('YYYY-MM-DD')
    # for match-having saves (season-start day-1 saves get a synthetic 'YYYY-07-01'); the
    # legacy words 'start'/'mid'/'end' are still accepted so pre-existing stores keep working.
    """CREATE TABLE IF NOT EXISTS raw.extracts (
        season INTEGER NOT NULL,
        phase VARCHAR NOT NULL,
        label VARCHAR NOT NULL,
        source_dir VARCHAR NOT NULL,
        save_path VARCHAR,
        loaded_at TIMESTAMP NOT NULL,
        row_counts JSON
    )""",

    # natural key: (season, phase, tid)
    """CREATE TABLE IF NOT EXISTS raw.clubs (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        tid INTEGER NOT NULL, name VARCHAR
    )""",

    # Club History -- the Team Records and Player Records tables (fmparser/tables/
    # club_records.py), every written slot of every club. `record_table` is 'overall' or
    # 'season' (the club's current-season table, where `record_season` reads 2020). A record
    # held in two slots, or in both tables, is genuinely stored more than once, so rows are
    # NOT deduplicated here. Nothing should build a fixture list from these rows.
    # natural key: (season, phase, byte_offset)
    """CREATE TABLE IF NOT EXISTS raw.club_records (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        byte_offset BIGINT NOT NULL, club_tid INTEGER NOT NULL, record_table VARCHAR,
        slot INTEGER, category VARCHAR, kind VARCHAR,
        opponent_tid INTEGER, score_for INTEGER, score_against INTEGER,
        value DOUBLE, comp_cid INTEGER, record_season INTEGER, day INTEGER,
        unk10 INTEGER, unk12 INTEGER, unk14 INTEGER
    )""",

    # Player records. `club_tid` is the club whose Club History row holds the block.
    # natural key: (season, phase, byte_offset)
    """CREATE TABLE IF NOT EXISTS raw.player_records (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        byte_offset BIGINT NOT NULL, club_tid INTEGER, record_table VARCHAR,
        slot INTEGER, category VARCHAR, unit VARCHAR, player_tid INTEGER,
        value DOUBLE, record_season INTEGER,
        unk8 BIGINT, unk12 BIGINT, unk16 BIGINT
    )""",

    # Each club's league history, one row per league season: the league, the club's final
    # position and the number of clubs. `year` is the season's START year (2023 = 2023/24).
    # natural key: (season, phase, club_tid, year, cid)
    """CREATE TABLE IF NOT EXISTS raw.club_league_history (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        club_tid INTEGER NOT NULL, cid INTEGER, year INTEGER,
        position INTEGER, teams INTEGER
    )""",

    # The Training page, one row per player: focus role and position, attribute focus and
    # intensity, and the row's contract flag and squad status as stored
    # (fmparser.tables.training). Every player in the world, not just ours.
    # natural key: (season, phase, tid)
    """CREATE TABLE IF NOT EXISTS raw.training (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL, tid INTEGER NOT NULL,
        intensity INTEGER, focus_role INTEGER, focus_attribute INTEGER,
        focus_position VARCHAR, contracted INTEGER, squad_status INTEGER
    )""",

    # The contract grid, every used slot as stored (fmparser.tables.contracts); marker 1 is
    # a current contract. natural key: (season, phase, tid)
    """CREATE TABLE IF NOT EXISTS raw.contracts (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL, tid INTEGER NOT NULL,
        marker INTEGER, wage_units INTEGER, expiry DATE, start_date DATE
    )""",

    # The club record's trailer (fmparser.tables.clubs.CLUB_TABLE). Facts the club
    # record asserts directly, rather than inferred.
    # natural key: (season, phase, tid)
    """CREATE TABLE IF NOT EXISTS raw.club_details (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL, tid INTEGER NOT NULL,
        based_id INTEGER, nation_id INTEGER,
        colours JSON, kits JSON,
        status INTEGER, academy INTEGER, facilities INTEGER,
        att_avg INTEGER, att_min INTEGER, att_max INTEGER, reserves INTEGER,
        league_id INTEGER, other_division INTEGER, other_last_position INTEGER,
        stadium_id INTEGER, last_league INTEGER,
        league_pos INTEGER, reputation INTEGER,
        club_type INTEGER, main_club_tid INTEGER,
        squad_size INTEGER, staff_size INTEGER
    )""",

    # The 40-slot squad array, one row per occupied slot. This is SQUAD MEMBERSHIP (it
    # includes loaned-IN players and excludes reserve-team players); raw.players.club_tid
    # is OWNERSHIP. They legitimately disagree -- see mart.club_roster.
    # natural key: (season, phase, club_tid, player_tid)
    """CREATE TABLE IF NOT EXISTS raw.club_squad (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        club_tid INTEGER NOT NULL, player_tid INTEGER NOT NULL, slot INTEGER
    )""",

    # The 11-slot staff array. It EXCLUDES the manager, which is what makes
    # mart.club_managers exact.
    # natural key: (season, phase, club_tid, staff_tid)
    """CREATE TABLE IF NOT EXISTS raw.club_staff (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        club_tid INTEGER NOT NULL, staff_tid INTEGER NOT NULL, slot INTEGER
    )""",

    # natural key: (season, phase, club_tid, seq)
    """CREATE TABLE IF NOT EXISTS raw.club_affiliates (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        club_tid INTEGER NOT NULL, seq INTEGER,
        club1_tid INTEGER, club2_tid INTEGER,
        start_day INTEGER, start_year INTEGER, end_day INTEGER, end_year INTEGER
    )""",

    # natural key: (season, phase, id)
    """CREATE TABLE IF NOT EXISTS raw.stadiums (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        id INTEGER NOT NULL, uid BIGINT, city_id INTEGER,
        capacity INTEGER, expansion_capacity INTEGER, name VARCHAR
    )""",

    # natural key: (season, phase, id)
    """CREATE TABLE IF NOT EXISTS raw.cities (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        id INTEGER NOT NULL, uid BIGINT, nation_id INTEGER,
        latitude DOUBLE, longitude DOUBLE, attraction INTEGER, region_id INTEGER
    )""",

    # natural key: (season, phase, id)
    """CREATE TABLE IF NOT EXISTS raw.languages (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        id INTEGER NOT NULL, uid BIGINT, name VARCHAR, other_name VARCHAR,
        nation_id INTEGER, difficulty INTEGER
    )""",

    # exchange_rate is units per GBP (Danish Krone 8.699, Czech Koruna 29.81).
    # natural key: (season, phase, uid)
    """CREATE TABLE IF NOT EXISTS raw.currencies (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        uid INTEGER NOT NULL, name VARCHAR, exchange_rate DOUBLE
    )""",

    # natural key: (season, phase, id)
    """CREATE TABLE IF NOT EXISTS raw.nations (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        id INTEGER NOT NULL, uid BIGINT, name VARCHAR, nationality VARCHAR, code VARCHAR,
        continent_id INTEGER, capital_city_id INTEGER, national_stadium_id INTEGER,
        rival_nation_id INTEGER, is_ranked BOOLEAN,
        world_ranking INTEGER, ranking_points INTEGER
    )""",

    # World-ranking history per nation, oldest first (seq 0). The length GROWS with
    # career length (10 entries in 2022, 24 by 2026) -- never assume a fixed count.
    # natural key: (season, phase, nation_id, seq)
    """CREATE TABLE IF NOT EXISTS raw.nation_ranking_history (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        nation_id INTEGER NOT NULL, seq INTEGER NOT NULL, ranking INTEGER
    )""",

    # UEFA country coefficients, oldest first; the last entry is the season in progress and
    # is always 0.0. Only European nations carry these (132 of 251).
    # natural key: (season, phase, nation_id, seq)
    """CREATE TABLE IF NOT EXISTS raw.nation_coefficients (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        nation_id INTEGER NOT NULL, seq INTEGER NOT NULL, coefficient DOUBLE
    )""",

    # The languages each nation speaks, with how well (proficiency 0..100: Denmark reads
    # Danish 100, English 70, Swedish 50).
    # natural key: (season, phase, nation_id, language_id)
    """CREATE TABLE IF NOT EXISTS raw.nation_languages (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        nation_id INTEGER NOT NULL, language_id INTEGER NOT NULL, proficiency INTEGER
    )""",

    # natural key: (season, phase, cid)
    # The whole competition table, every named slot (fmparser/tables/competitions.py).
    # `level` is the 0-indexed division tier: unlike ranking by reputation it places
    # PARALLEL divisions on the same tier.
    # natural key: (season, phase, cid)
    """CREATE TABLE IF NOT EXISTS raw.competitions (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        cid INTEGER NOT NULL, uid BIGINT, name VARCHAR, short VARCHAR, code VARCHAR,
        type VARCHAR, type_id INTEGER, nation_id INTEGER, reputation INTEGER,
        level INTEGER, parent_cid INTEGER
    )""",

    # Each nation's team-count rules (fmparser/tables/rule_files.team_counts): how many
    # teams a competition has. natural key: (season, phase, uid)
    """CREATE TABLE IF NOT EXISTS raw.competition_team_counts (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL, uid BIGINT NOT NULL, teams INTEGER
    )""",

    # Each person's own record as the save stores it. raw.players is a VIEW over this plus
    # our squad's scrapbook entries (squad_scrapbook, below).
    # natural key: (season, phase, tid)
    """CREATE TABLE IF NOT EXISTS raw.players_raw (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        tid INTEGER NOT NULL,
        first_name_id BIGINT, last_name_id BIGINT, common_name_id BIGINT,
        is_staff BOOLEAN NOT NULL DEFAULT FALSE,
        club_tid INTEGER, club VARCHAR,
        dob DATE, nationality_id INTEGER, has_attributes BOOLEAN,
        is_gk INTEGER,
        ca INTEGER, pa INTEGER, reputation INTEGER, positions JSON,
        foot_left INTEGER, foot_right INTEGER,
        -- tail of the global attribute record (see fmparser.attributes.record_tail).
        -- `reputation` above is HOME reputation; these are the other two.
        current_reputation INTEGER, world_reputation INTEGER, international_retired BOOLEAN,
        squad_number INTEGER, preferred_squad_number INTEGER,
        height_cm INTEGER, weight_kg INTEGER,
        -- The 9 attribute bytes the player screen does not show (attributes.HIDDEN_OFFSETS),
        -- named from fmm-editor's Player.cs. Nothing derives from them; see that module for
        -- why the order is trusted.
        jumping INTEGER, consistency INTEGER, big_match INTEGER, injury_prone INTEGER,
        versatility INTEGER, set_pieces INTEGER, penalty INTEGER, work_rate INTEGER,
        flair INTEGER,
        -- The 16 ENTANGLED source bytes (0-255), raw and undecoded (attributes.SRC_OFFSETS).
        -- Stored so the estimation model can be retrained against the store rather than a
        -- full re-extract: scraping and inference are different jobs. Joined to the exact
        -- values our own squad carries (estimated = false), this table IS the training set.
        crossing_src INTEGER, dribbling_src INTEGER, tackling_src INTEGER,
        finishing_src INTEGER, long_shot_src INTEGER, passing_src INTEGER,
        decision_src INTEGER, creativity_src INTEGER, movement_src INTEGER,
        positioning_src INTEGER, handling_src INTEGER, kicking_src INTEGER,
        aerial_gk_src INTEGER, reflexes_src INTEGER, communication_src INTEGER,
        throwing_src INTEGER,
        -- ...and the nine PLAIN bytes, so the whole 34-slot attribute block is here verbatim.
        -- heading_src and unselfishness_src are the load-bearing two: displayed Aerial and
        -- Teamwork are DERIVED from them, so without these the model could not be refitted
        -- against the store alone.
        heading_src INTEGER, unselfishness_src INTEGER, pace_src INTEGER,
        strength_src INTEGER, stamina_src INTEGER, technique_src INTEGER,
        aggression_src INTEGER, leadership_src INTEGER, agility_src INTEGER,
        -- From the INFO record (staging.PERSON_FIELDS), so STAFF carry these too -- they are
        -- facts about a person, not about a player. The 8 personality values are the ones the
        -- Manager Profile screen shows.
        adaptability INTEGER, ambition INTEGER, determination INTEGER, loyalty INTEGER,
        pressure INTEGER, professionalism INTEGER, sportsmanship INTEGER, temperament INTEGER,
        international_caps INTEGER, international_goals INTEGER,
        u21_caps INTEGER, u21_goals INTEGER, joined_date DATE,
        second_nationality_id INTEGER, ethnicity INTEGER
    )""",

    # natural key: (season, phase, tid)
    # What the player's own record states outright: exact values only, NULL where the record
    # does not carry one plainly. raw.player_attributes_exact is a VIEW over this with our
    # squad's scrapbook values in their place; raw.player_attributes is a VIEW over that
    # plus raw.attribute_model.
    f"""CREATE TABLE IF NOT EXISTS raw.player_attributes_exact_raw (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL, tid INTEGER NOT NULL,
        {_exact_cols_ddl()}
    )""",
    ATTR_MODEL_DDL,

    # Every scrapbook entry in the save's 66 player lists (fmparser/tables/player_lists.py):
    # the World Best XI pools (lists 0-30), the Manager's Best Eleven pools (31-61, every player
    # who played for the manager, season by season) and the two all-time pairs (62-65). Each is
    # the player's Scrapbook Profile as of `scrapbook_date`. `list_season` is 65535 while the
    # list's season is in progress.
    # natural key: (season, phase, list, slot)
    f"""CREATE TABLE IF NOT EXISTS raw.player_scrapbook (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        {_scrapbook_cols_ddl()}
    )""",

    # Coaching ability + the manager formation triple, from the STAFF attribute record
    # (fmparser/staff.py). Separate from raw.players because only ~4.2k of ~7.5k staff
    # have one, and none of these columns mean anything for a player.
    # natural key: (season, phase, tid)
    """CREATE TABLE IF NOT EXISTS raw.staff_attributes (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL, tid INTEGER NOT NULL,
        ca INTEGER, pa INTEGER,
        home_reputation INTEGER, current_reputation INTEGER, world_reputation INTEGER,
        reputation_tier VARCHAR,
        attacking_intent INTEGER, style VARCHAR,
        financial_control INTEGER, outfield_coaching INTEGER, goalkeeping_coaching INTEGER,
        discipline INTEGER, judging_ability INTEGER, judging_potential INTEGER,
        people_management INTEGER, motivating INTEGER, tactical_knowledge INTEGER,
        youth_coaching INTEGER,
        -- the 6 unnamed 1-20 attribute bytes (staff.HIDDEN_OFFSETS)
        hidden_s18 INTEGER, hidden_s20 INTEGER, hidden_s24 INTEGER,
        hidden_s26 INTEGER, hidden_s27 INTEGER, hidden_s28 INTEGER,
        formation_preferred INTEGER, formation_attacking INTEGER, formation_defensive INTEGER,
        formation_preferred_name VARCHAR, formation_attacking_name VARCHAR,
        formation_defensive_name VARCHAR
    )""",

    # natural key: (season, phase, anchor); anchor is the match row's offset in the save
    """CREATE TABLE IF NOT EXISTS raw.matches (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL, anchor BIGINT NOT NULL,
        date DATE, competition VARCHAR, comp_id INTEGER, home_flag INTEGER,
        home_tid INTEGER, away_tid INTEGER, attendance INTEGER,
        score_home INTEGER, score_away INTEGER, star_home INTEGER, star_away INTEGER,
        formation VARCHAR, player_of_match INTEGER,
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
    """CREATE TABLE IF NOT EXISTS raw.match_events (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL, anchor BIGINT NOT NULL,
        seq INTEGER NOT NULL, minute INTEGER, added INTEGER, min_display VARCHAR,
        tid INTEGER, type VARCHAR, type_byte INTEGER, b0 INTEGER
    )""",

    # natural key: (season, phase, anchor, side, tid)
    """CREATE TABLE IF NOT EXISTS raw.match_player_stats (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL, anchor BIGINT NOT NULL,
        side VARCHAR NOT NULL CHECK (side IN ('home','away')),
        tid INTEGER NOT NULL, team_tid INTEGER, opponent_tid INTEGER,
        date DATE, competition VARCHAR,
        pos_order INTEGER, rating INTEGER, goals INTEGER, assists INTEGER,
        passA INTEGER, passC INTEGER, keyPass INTEGER, tackA INTEGER, tackW INTEGER,
        intercept INTEGER, headA INTEGER, headW INTEGER, crossA INTEGER, crossC INTEGER,
        dribbles INTEGER, mistakes INTEGER, mistGoal INTEGER, shotA INTEGER, shotO INTEGER,
        condition INTEGER, subOn INTEGER, subOff INTEGER, yellow INTEGER,
        -- real on-pitch position of a STARTER in our own XI ('DR','DMC','AML',...),
        -- decoded from the slot array after the formation string. NULL for the
        -- opposition (the save stores no shape for them) and for substitutes.
        position VARCHAR
    )""",

    # natural key: (season, phase, home_tid, away_tid, cid, seq)
    """CREATE TABLE IF NOT EXISTS raw.results (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        home_tid INTEGER NOT NULL, away_tid INTEGER NOT NULL, cid INTEGER NOT NULL,
        seq INTEGER NOT NULL, home VARCHAR, away VARCHAR,
        scoreH INTEGER, scoreA INTEGER, competition VARCHAR, copies INTEGER
    )""",

    # natural key: (season, phase, home_tid, away_tid, date)
    """CREATE TABLE IF NOT EXISTS raw.world_fixtures (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        home_tid INTEGER NOT NULL, away_tid INTEGER NOT NULL,
        date DATE NOT NULL, year INTEGER NOT NULL,
        round INTEGER,
        home_goals INTEGER, away_goals INTEGER,
        home_pens INTEGER, away_pens INTEGER,
        stage_key INTEGER, seq_id INTEGER,
        season_year INTEGER,
        stage_index INTEGER, round_index INTEGER, subr INTEGER
    )""",

    # natural key: (season, phase, uid, stage_index, round_index). Each competition's
    # stage/round structure from its archive member comp_<uid>.dat; `uid` is
    # raw.competitions.uid, and stage_index/round_index are the numbers
    # world_fixtures carries. Name ids resolve through raw.round_names.
    """CREATE TABLE IF NOT EXISTS raw.competition_rounds (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL, uid BIGINT NOT NULL,
        stage_index INTEGER, stage_code VARCHAR, stage_type INTEGER, stage_teams INTEGER,
        stage_name_id BIGINT, n_groups INTEGER,
        round_index INTEGER, round_name_id BIGINT, round_teams INTEGER, legs INTEGER
    )""",

    # The name tables a person's name ids index, as stored: the browse strings (natural key:
    # (season, phase, ordinal)) and the used slots of the three id-tables, first_names /
    # surnames / nicknames (natural key: (season, phase, name_table, id)).
    """CREATE TABLE IF NOT EXISTS raw.name_strings (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL, ordinal INTEGER NOT NULL, name VARCHAR
    )""",
    """CREATE TABLE IF NOT EXISTS raw.name_ids (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL, name_table VARCHAR NOT NULL,
        id BIGINT NOT NULL, ordinal BIGINT
    )""",

    # natural key: (season, phase, id). The game's stage/round/leg name catalog.
    """CREATE TABLE IF NOT EXISTS raw.round_names (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL, id BIGINT NOT NULL, name VARCHAR
    )""",

    # natural key: (season, phase, tid, position). Long form of players.positions —
    # every position a player can play (14 FM codes) with familiarity 1..20.
    """CREATE TABLE IF NOT EXISTS raw.player_positions (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL, tid INTEGER NOT NULL,
        position VARCHAR NOT NULL, familiarity INTEGER
    )""",

    # career-history summary, one row per player, read from the raw pool in history.json by
    # `load_history`. origin_club_tid = youth/debut club = the Athletic-Bilbao eligibility
    # key; debut_season = the season on the chain's first record, the debut line. `confidence`
    # is always 'exact' (the player -> history link is a stored pointer, the attribute
    # record's `history_head`) and `origin_club` is always NULL (the mart names it); both are
    # kept for the schema. natural key: (season, phase, tid).
    """CREATE TABLE IF NOT EXISTS raw.player_history (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL, tid INTEGER NOT NULL,
        origin_club_tid INTEGER, origin_club VARCHAR,
        last_season_club_tid INTEGER, confidence VARCHAR, record_offset BIGINT,
        debut_season INTEGER, debut_end_year INTEGER
    )""",

    # full season-by-season career rows (for display). natural key: (season, phase, tid, seq).
    # seq -1 is the debut line (the chain's first record, at the origin club); 0.. follow it.
    # A season can appear TWICE for one player: a loan year stores the parent-club row (0 apps)
    # and the loan-club row (fee='loan') separately, exactly as the in-game screen shows them.
    # `goals` is goals CONCEDED for goalkeepers. `rating` is null for pre-career seasons (the
    # game only keeps an average rating for seasons played during your career). Likewise
    # `yellows` / `reds`, 0 for every season before the career.
    """CREATE TABLE IF NOT EXISTS raw.player_history_seasons (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL, tid INTEGER NOT NULL,
        seq INTEGER NOT NULL, hist_season INTEGER, end_year INTEGER,
        club_tid INTEGER, fee VARCHAR, apps INTEGER, goals INTEGER,
        assists INTEGER, rating DOUBLE, yellows INTEGER, reds INTEGER
    )""",

    # The weekly Player Progress table (fmparser/tables/player_progress.py), every used row
    # as stored: the managed squad and reserves, back to each player's first week at the
    # club. A week may appear more than once and the copies may disagree; `status` is the
    # raw bitfield. Injury and loan-out spells are read from it in the mart
    # (mart.progress_weeks). natural key: none -- (season, phase, tid, week) repeats.
    """CREATE TABLE IF NOT EXISTS raw.player_progress (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL, tid INTEGER NOT NULL,
        week DATE NOT NULL, status INTEGER NOT NULL,
        line_0 INTEGER, line_1 INTEGER, line_2 INTEGER,
        line_3 INTEGER, line_4 INTEGER, line_5 INTEGER
    )""",

    # GLOBAL config (not per-label): the set of club TIDs whose YOUTH products are eligible
    # under the Athletic-Bilbao origin strategy (e.g. Danish Capital Region). Seeded from
    # seeds/eligible_origin_clubs.csv; curate freely. Join on player_history.origin_club_tid.
    """CREATE TABLE IF NOT EXISTS raw.eligible_origin_clubs (
        club_tid INTEGER NOT NULL, club_name VARCHAR, region VARCHAR
    )""",

    # GLOBAL reference table (not per-label). One row per (method, role, attribute).
    # `method` names a tactic/weight-set: frem_minmax_4231 and frem_attacking_ss are seeded
    # from seeds/role_weights.csv; user-defined tactics are added by inserting new methods
    # (e.g. from a dashboard) and are preserved across reloads. Attributes not listed
    # for a (method, role) default to weight 1 in v_player_ratings.
    """CREATE TABLE IF NOT EXISTS raw.role_weights (
        method VARCHAR NOT NULL, role VARCHAR NOT NULL, attribute VARCHAR NOT NULL,
        category VARCHAR, weight INTEGER NOT NULL
    )""",

    # GLOBAL: maps the 14 FM position codes to the 10 rating roles in role_weights.
    """CREATE TABLE IF NOT EXISTS raw.position_role_map (
        position VARCHAR NOT NULL, role VARCHAR NOT NULL
    )""",

    # GLOBAL: app settings (familiarity curve/floor, defaults). Edited by the Config
    # page; seeded with defaults only for keys that don't yet exist.
    """CREATE TABLE IF NOT EXISTS raw.app_config (
        key VARCHAR NOT NULL, value VARCHAR
    )""",

    # IDENTITY BRIDGE. A tid is a SLOT, not a person: FM reuses a retired player's tid for a
    # newgen (829 swaps in the frem store, 1503 in bucaspor). Within one (season,phase) slice a
    # tid is unambiguous, so single-snapshot views are fine — but ANY cross-save per-player join
    # keyed on tid alone splices two people into one career. `dob` separates every recycled slot
    # (2332 changes, 0 collisions, 0 nulls), so (tid,dob) is the person key. See docs/IDS.md.
    # person_id is a stable VARCHAR '<tid>-<dob>' (stable across loads, unlike a dense_rank).
    # Multi-snapshot archive. raw.* always holds ONE snapshot per (season,phase) =
    # the latest loaded; when a load supersedes a DIFFERENT label in that slice, the
    # outgoing snapshot's players+attributes are copied here first (tagged by label +
    # in-game date). Lets multiple in-season checkpoints coexist for progression without
    # touching the single-snapshot raw layer the dashboard/scout rely on.
    "CREATE SCHEMA IF NOT EXISTS history",
    """CREATE TABLE IF NOT EXISTS history.player_snapshots AS
       SELECT CAST(NULL AS VARCHAR) AS snapshot_label,
              CAST(NULL AS DATE) AS snapshot_date,
              CAST(NULL AS TIMESTAMP) AS archived_at,
              p.*, a.* EXCLUDE (season, phase, tid)
       FROM raw.players p JOIN raw.player_attributes a USING (season, phase, tid)
       LIMIT 0""",
]

# Which methods the seed CSV owns is read FROM THE CSV, not listed here. The hardcoded list this
# replaced went stale the moment a new method was added to the CSV: seed_role_weights deleted the
# seven it knew about and re-inserted the whole file, so the new method gained a DUPLICATE row set
# on every refresh and the rating view — a LEFT JOIN and a SUM — counted its weights twice. Two
# refreshes took a centre-back's rating from 431 to 777 and silently reordered the depth chart.

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
    "default_method": "frem_attacking_ss",
}

# Dropped if present, never created. Each reads raw across every snapshot without the
# mart's one-row-per-match rule (goal totals come out 2-3x), surfaces raw CA/PA, or reads
# standings that do not parse for this career. The mart and fmq.py answer all five questions.
RETIRED_VIEWS = ("v_ca_progression", "v_transfers", "v_league_table", "v_match_results",
                 "v_top_scorers")

# tables each group owns, and the DELETE scope for idempotent reload
GROUPS = ("core", "light", "world")


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


def _insert(con, table, cols, rows, dtypes=None):
    """Bulk-insert `rows` (a list of tuples matching `cols`) into raw.<table>.

    Goes through a registered DataFrame rather than `executemany`. DuckDB is columnar, so
    binding parameters row-by-row is pathologically slow against it: measured on real data,
    211,362 x 12 player_history_seasons rows took 39.0s via executemany and 0.13s via
    register+INSERT SELECT — 300x. It dominated everything else, at 98.7% of a snapshot load
    (38.1s of 38.6s, of which reading the JSON was 0.48s). Per snapshot this is ~38s -> ~4s.

    dtype=object IS LOAD-BEARING. Letting pandas infer dtypes would silently corrupt data:
    an integer column containing NULLs becomes float64, so 1 -> 1.0 and NULL -> NaN, and NaN
    does not cast back to an integer. Holding Python objects means DuckDB does the conversion
    against the target column type, exactly as executemany did. Verified per table against
    executemany on real rows (all 23 raw tables byte-identical, including `players` with
    17 nullable columns and the date-valued ones) — re-check with that comparison if this
    ever needs to change.
    """
    if not rows:
        return 0
    colsql = ",".join(f'"{c}"' for c in cols)
    df = pd.DataFrame(rows, columns=list(cols), dtype=object)
    # `dtypes` is a narrow escape hatch from the object-dtype rule above, for a NON-NULLABLE
    # column whose values outgrow int32. DuckDB types the registered view by inspecting the
    # object column, so a uid column that starts at 5 and later reaches 4,094,596,727 (the
    # city table) is typed INT32 and then fails mid-scan with "Value out of range for type
    # INT" — even though the target column is BIGINT. Naming the dtype types the view
    # correctly. Only safe where there are no NULLs, which is why it is opt-in per column.
    for col, dt in (dtypes or {}).items():
        df[col] = df[col].astype(dt)
    con.register(_INS_VIEW, df)
    try:
        con.execute(f"INSERT INTO raw.{table} ({colsql}) "
                    f"SELECT {colsql} FROM {_INS_VIEW}")
    finally:
        con.unregister(_INS_VIEW)
    return len(rows)


def _delete(con, table, season, phase, extra="", params=()):
    con.execute(
        f"DELETE FROM raw.{table} WHERE season=? AND phase=? {extra}",
        [season, phase, *params],
    )


# ---------------------------------------------------------------------------
# group loaders — each returns {table: rowcount}
# ---------------------------------------------------------------------------

HISTORY_END = 0xFFFFFFFF
HISTORY_SEASON_BASE = 1971          # end_year = 1971 + the row's season code

# Reading a player's career out of the raw history pool (fmparser/tables/history.py: every
# 16-byte record as stored, plus each player's head record). One record is one line of the
# in-game Player History screen: a season, its club, its fee and its numbers.
#
# A player's records are one chain, followed by `next` from his head. The head must be a
# chain's first record (nothing points at it) inside the pool; anything else means no
# history yet. The head is the DEBUT LINE: the oldest season the pool holds for him, at his
# origin club -- the Athletic-Bilbao eligibility key. For a player whose chain has not been
# reclaimed it is a youth season (age 14-18 for the whole Frem squad at 2027-08-08); an
# academy intake's debut line is his youth-team season, with its appearances. It is written
# to `player_history_seasons` as `seq = -1`, so the lines after it keep `seq` 0, 1, ...;
# what to make of it is the mart's decision. A chain of the debut line alone (an intake in
# his first season) is a history too.
#
# Verified against five in-game Player-History screens (denmark-24-start.fms, 30 Jun 2023):
# every season line matches, and the career Pld/Gls/Ast TOTALS match exactly -- Dirksen
# 198/10/0, Andersson 286/16/2, Thrane 195/26/4, Fugl 46/8/12, Erenbjerg 82/19/3 (two loan
# spells and their loan fee markers included). `scripts/history_v2.py` runs the same SQL.
_HISTORY_CHAIN_SQL = f"""
WITH RECURSIVE chain(tid, seq, row) AS (
    SELECT h.tid, 0, h.head FROM _hist_heads h
    WHERE h.head < (SELECT count(*) FROM _hist_rows)
      AND h.head NOT IN (SELECT next FROM _hist_rows WHERE next <> {HISTORY_END})
    UNION ALL
    SELECT c.tid, c.seq + 1, r.next
    FROM chain c JOIN _hist_rows r ON r.row = c.row
    WHERE r.next <> {HISTORY_END})
SELECT * FROM chain
"""

_HISTORY_SEASONS_SQL = f"""
SELECT ?, ?, c.tid, c.seq - 1, r.season, {HISTORY_SEASON_BASE} + r.season, r.club,
       CASE r.fee WHEN 65535 THEN 'stay' WHEN 65534 THEN 'loan'
                  WHEN 65533 THEN 'free' WHEN 0 THEN 'free'
                  ELSE CAST(r.fee AS VARCHAR) END,
       r.apps, r.goals, r.assists,
       CASE WHEN r.rating = 0 THEN NULL ELSE r.rating / 100.0 END, r.yellows, r.reds
FROM _hist_chain c JOIN _hist_rows r ON r.row = c.row
"""

_HISTORY_SUMMARY_SQL = f"""
WITH ends AS (
    SELECT tid, max(seq) AS last_seq FROM _hist_chain GROUP BY tid)
SELECT ?, ?, e.tid, head.club, NULL, last.club, 'exact', ? + 16 * h.row,
       head.season, {HISTORY_SEASON_BASE} + head.season
FROM ends e
JOIN _hist_chain h ON (h.tid, h.seq) = (e.tid, 0)
JOIN _hist_rows head ON head.row = h.row
JOIN _hist_chain l ON (l.tid, l.seq) = (e.tid, e.last_seq)
JOIN _hist_rows last ON last.row = l.row
"""


def load_history(con, season, phase, hist):
    """raw.player_history (one row per player) and raw.player_history_seasons (one
    per season line), read from the raw history pool. The pool itself is not stored."""
    rows = hist["rows"]
    df = pd.DataFrame({"row": range(hist["count"]),
                       **{k: rows[k] for k in ("club", "fee", "next", "season", "apps",
                                               "goals", "assists", "rating", "yellows",
                                               "reds")}})
    heads = pd.DataFrame({"tid": [int(t) for t in hist["heads"]],
                          "head": list(hist["heads"].values())}, dtype="int64")
    con.register("_hist_rows", df)
    con.register("_hist_heads", heads)
    try:
        con.execute(f"CREATE OR REPLACE TEMP TABLE _hist_chain AS {_HISTORY_CHAIN_SQL}")
        on_chains = con.execute("SELECT count(*) FROM _hist_chain").fetchone()[0]
        con.execute("INSERT INTO raw.player_history (season, phase, tid, origin_club_tid, "
                    "origin_club, last_season_club_tid, confidence, record_offset, "
                    "debut_season, debut_end_year) " + _HISTORY_SUMMARY_SQL,
                    [season, phase, hist["base"]])
        con.execute("INSERT INTO raw.player_history_seasons (season, phase, tid, seq, "
                    "hist_season, end_year, club_tid, fee, apps, goals, assists, rating, "
                    "yellows, reds) "
                    + _HISTORY_SEASONS_SQL, [season, phase])
        n_players, n_seasons = (con.execute(
            f"SELECT count(*) FROM raw.{t} WHERE season = ? AND phase = ?",
            [season, phase]).fetchone()[0]
            for t in ("player_history", "player_history_seasons"))
    finally:
        con.execute("DROP TABLE IF EXISTS _hist_chain")
        con.unregister("_hist_rows")
        con.unregister("_hist_heads")
    # every row of the pool, split by whether a player's chain reaches it
    print(f"  history pool: {hist['count']} rows, {on_chains} on a player's chain, "
          f"{hist['count'] - on_chains} on chains no player points at")
    return {"player_history": n_players, "player_history_seasons": n_seasons}


def load_core(con, d, season, phase):
    counts = {}

    # --- players + staff (identity spine) + wide attributes ------------------
    players = _load_json(os.path.join(d, "players.json"))
    prows, arows = [], []
    seen = set()
    acols = ["season", "phase", "tid"] + ATTR_ORDER
    for v in players.values():
        tid = _int(v.get("tid"))
        if tid is None or tid in seen:
            continue
        seen.add(tid)
        feet = v.get("feet") or {}
        prows.append((
            season, phase, tid, *(_int(v.get(c)) for c in NAME_ID_COLS), False,
            _int(v.get("club_tid")), v.get("club"),
            _date(v.get("dob")), _int(v.get("nationality_id")),
            v.get("has_attributes"), _int(v.get("is_gk")),
            _int(v.get("ca")), _int(v.get("pa")), _int(v.get("reputation")),
            json.dumps(v.get("positions") or {}),
            _int(feet.get("left")), _int(feet.get("right")),
            _int(v.get("current_reputation")), _int(v.get("world_reputation")),
            v.get("international_retired"),
            _int(v.get("squad_number")), _int(v.get("preferred_squad_number")),
            _int(v.get("height_cm")), _int(v.get("weight_kg")),
            *(_int(v.get(c)) for c in PLAYER_HIDDEN_COLS),
            *(_int(v.get(c)) for c in SRC_COLS),
            *(_date(v.get(c)) if c in PERSON_DATE_COLS else _int(v.get(c))
              for c in PERSON_COLS),
        ))
        # EXACT values only. `estimated` marks which of the extract's values the save states
        # outright; anything else is stored NULL and derived by raw.player_attributes.
        attrs, est = v.get("attributes"), v.get("estimated") or {}
        if attrs:
            arows.append(
                (season, phase, tid)
                + tuple(None if est.get(a) else _int(attrs.get(a)) for a in ATTR_ORDER)
            )

    srows, sarows = [], []
    staff_path = os.path.join(d, "staff.json")
    if os.path.exists(staff_path):
        for v in _load_json(staff_path).values():
            tid = _int(v.get("tid"))
            if tid is None or tid in seen:
                continue
            seen.add(tid)
            # only ~4.2k of ~7.5k staff carry an attribute record
            if v.get("formation_preferred") is not None:
                sarows.append((season, phase, tid)
                              + tuple(v.get(c) for c in STAFF_ATTR_COLS[3:]))
            srows.append((
                season, phase, tid, *(_int(v.get(c)) for c in NAME_ID_COLS), True,
                _int(v.get("club_tid")), v.get("club"),
                _date(v.get("dob")), _int(v.get("nationality_id")),
                False, None, None, None, None,
                json.dumps({}), None, None,
                # record_tail + the hidden block: staff have no global attribute record
                # (PlayerId == -1), so both are NULL. Sized from the parser's own tables so
                # this padding cannot fall out of step with the column list below.
                *([None] * 7), *([None] * len(PLAYER_HIDDEN_COLS)),
                *([None] * len(SRC_COLS)),
                # ...but the PERSON block is on the info record, so staff DO have it.
                *(_date(v.get(c)) if c in PERSON_DATE_COLS else _int(v.get(c))
                  for c in PERSON_COLS),
            ))

    pcols = ["season", "phase", "tid", *NAME_ID_COLS, "is_staff", "club_tid", "club",
             "dob", "nationality_id", "has_attributes",
             "is_gk", "ca", "pa", "reputation",
             "positions", "foot_left", "foot_right",
             "current_reputation", "world_reputation", "international_retired",
             "squad_number", "preferred_squad_number", "height_cm", "weight_kg"
             ] + PLAYER_HIDDEN_COLS + SRC_COLS + PERSON_COLS
    counts["players"] = _insert(con, "players_raw", pcols, prows)
    counts["staff"] = _insert(con, "players_raw", pcols, srows)
    counts["staff_attributes"] = _insert(con, "staff_attributes", STAFF_ATTR_COLS, sarows)
    counts["player_attributes"] = _insert(con, "player_attributes_exact_raw", acols, arows)

    # the name tables the name ids above index
    names_path = os.path.join(d, "names.json")
    if os.path.exists(names_path):
        nt = _load_json(names_path)
        counts["name_strings"] = _insert(con, "name_strings",
                                         ["season", "phase", "ordinal", "name"],
                                         [(season, phase, i, s)
                                          for i, s in enumerate(nt.get("strings") or [])])
        counts["name_ids"] = _insert(con, "name_ids",
                                     ["season", "phase", "name_table", "id", "ordinal"],
                                     [(season, phase, t, r["id"], r["ordinal"])
                                      for t in NAME_TABLES for r in nt.get(t) or []])

    # every scrapbook entry of the 66 player lists, as stored
    sb_path = os.path.join(d, "player_scrapbook.json")
    if os.path.exists(sb_path):
        sb = [(season, phase) + tuple(_scrapbook_date(e) if key is None else e.get(key)
                                      for _, _, key in SCRAPBOOK_COLS)
              for e in _load_json(sb_path)]
        counts["player_scrapbook"] = _insert(
            con, "player_scrapbook", ["season", "phase"] + [c for c, _, _ in SCRAPBOOK_COLS], sb)

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
        counts.update(load_history(con, season, phase, _load_json(hist_path)))

    # --- the weekly Player Progress table, as stored ------------------------
    pp_path = os.path.join(d, "player_progress.json")
    if os.path.exists(pp_path):
        lines = [f"line_{i}" for i in range(6)]
        counts["player_progress"] = _insert(
            con, "player_progress", ["season", "phase", "tid", "week", "status", *lines],
            [(season, phase, r["tid"], datetime.date.fromisoformat(r["week"]), r["status"],
              *(r[c] for c in lines)) for r in _load_json(pp_path)])

    # --- clubs: the whole club table, names + the record's trailer ------------
    details = _load_json(os.path.join(d, "clubs.json"))
    if any(not isinstance(v, dict) for v in details.values()):
        raise SystemExit(f"{d}/clubs.json is the old name-only map; re-extract this save")
    counts["clubs"] = _insert(con, "clubs", ["season", "phase", "tid", "name"], [
        (season, phase, _int(v["tid"]), v.get("name")) for v in details.values()])
    cd_cols = ["season", "phase", "tid", "based_id", "nation_id", "colours", "kits",
               "status", "academy", "facilities", "att_avg", "att_min", "att_max",
               "reserves", "league_id", "other_division", "other_last_position",
               "stadium_id", "last_league", "league_pos", "reputation",
               "club_type", "main_club_tid", "squad_size", "staff_size"]
    cd_rows, sq_rows, st_rows, af_rows = [], [], [], []
    for v in details.values():
        tid = _int(v.get("tid"))
        if tid is None:
            continue
        squad = v.get("squad") or []
        staff = v.get("staff") or []
        cd_rows.append((
            season, phase, tid, _int(v.get("based_id")), _int(v.get("nation_id")),
            json.dumps(v.get("colours") or []), json.dumps(v.get("kits") or []),
            _int(v.get("status")), _int(v.get("academy")), _int(v.get("facilities")),
            _int(v.get("att_avg")), _int(v.get("att_min")), _int(v.get("att_max")),
            _int(v.get("reserves")), _int(v.get("league_id")),
            _int(v.get("other_division")), _int(v.get("other_last_position")),
            _int(v.get("stadium_id")), _int(v.get("last_league")),
            _int(v.get("league_pos")), _int(v.get("reputation")),
            _int(v.get("club_type")), _int(v.get("main_club_tid")),
            len(squad), len(staff)))
        for i, pt in enumerate(squad):
            sq_rows.append((season, phase, tid, _int(pt), i))
        for i, stid in enumerate(staff):
            st_rows.append((season, phase, tid, _int(stid), i))
        for i, a in enumerate(v.get("affiliates") or []):
            af_rows.append((season, phase, tid, i, _int(a.get("club1_tid")),
                            _int(a.get("club2_tid")), _int(a.get("start_day")),
                            _int(a.get("start_year")), _int(a.get("end_day")),
                            _int(a.get("end_year"))))
    counts["club_details"] = _insert(con, "club_details", cd_cols, cd_rows)
    counts["club_squad"] = _insert(
        con, "club_squad", ["season", "phase", "club_tid", "player_tid", "slot"], sq_rows)
    counts["club_staff"] = _insert(
        con, "club_staff", ["season", "phase", "club_tid", "staff_tid", "slot"], st_rows)
    counts["club_affiliates"] = _insert(
        con, "club_affiliates",
        ["season", "phase", "club_tid", "seq", "club1_tid", "club2_tid",
         "start_day", "start_year", "end_day", "end_year"], af_rows)

    # --- club history records (team + player) ---------------------------------
    cr_path = os.path.join(d, "club_records.json")
    if os.path.exists(cr_path):
        rows = [(season, phase, _int(v.get("offset")), _int(v.get("club_tid")),
                 v.get("table"), _int(v.get("slot")), v.get("category"), v.get("kind"),
                 _int(v.get("opponent_tid")), _int(v.get("score_for")),
                 _int(v.get("score_against")), v.get("value"), _int(v.get("comp_cid")),
                 _int(v.get("season")), _int(v.get("day")), _int(v.get("unk10")),
                 _int(v.get("unk12")), _int(v.get("unk14")))
                for v in _load_json(cr_path)]
        counts["club_records"] = _insert(
            con, "club_records",
            ["season", "phase", "byte_offset", "club_tid", "record_table", "slot", "category",
             "kind", "opponent_tid", "score_for", "score_against", "value", "comp_cid",
             "record_season", "day", "unk10", "unk12", "unk14"], rows)
    pr_path = os.path.join(d, "player_records.json")
    if os.path.exists(pr_path):
        rows = [(season, phase, _int(v.get("offset")), _int(v.get("club_tid")),
                 v.get("table"), _int(v.get("slot")), v.get("category"),
                 v.get("unit"), _int(v.get("player_tid")), v.get("value"),
                 _int(v.get("season")), _int(v.get("unk8")), _int(v.get("unk12")),
                 _int(v.get("unk16")))
                for v in _load_json(pr_path)]
        counts["player_records"] = _insert(
            con, "player_records",
            ["season", "phase", "byte_offset", "club_tid", "record_table", "slot",
             "category", "unit", "player_tid", "value", "record_season",
             "unk8", "unk12", "unk16"], rows,
            dtypes={"unk8": "int64", "unk12": "int64", "unk16": "int64"})
    lh_path = os.path.join(d, "club_league_history.json")
    if os.path.exists(lh_path):
        rows = [(season, phase, _int(v.get("club_tid")), _int(v.get("cid")),
                 _int(v.get("year")), _int(v.get("position")), _int(v.get("teams")))
                for v in _load_json(lh_path)]
        counts["club_league_history"] = _insert(
            con, "club_league_history",
            ["season", "phase", "club_tid", "cid", "year", "position", "teams"], rows)

    tr_path = os.path.join(d, "training.json")
    if os.path.exists(tr_path):
        rows = [(season, phase, _int(v.get("tid")), _int(v.get("intensity")),
                 _int(v.get("focus_role")), _int(v.get("focus_attribute")),
                 v.get("focus_position"), _int(v.get("contracted")),
                 _int(v.get("squad_status")))
                for v in _load_json(tr_path)]
        counts["training"] = _insert(
            con, "training",
            ["season", "phase", "tid", "intensity", "focus_role", "focus_attribute",
             "focus_position", "contracted", "squad_status"], rows)

    ct_path = os.path.join(d, "contracts.json")
    if os.path.exists(ct_path):
        counts["contracts"] = _insert(
            con, "contracts",
            ["season", "phase", "tid", "marker", "wage_units", "expiry", "start_date"],
            [(season, phase, _int(v["tid"]), _int(v.get("marker")), _int(v.get("wage_units")),
              _date(v.get("expiry")), _date(v.get("start_date")))
             for v in _load_json(ct_path)])

    # --- stadiums + cities ----------------------------------------------------
    sd_path = os.path.join(d, "stadiums.json")
    if os.path.exists(sd_path):
        rows = [(season, phase, _int(v.get("id")), _int(v.get("uid")), _int(v.get("city_id")),
                 _int(v.get("capacity")), _int(v.get("expansion_capacity")), v.get("name"))
                for v in _load_json(sd_path).values()]
        counts["stadiums"] = _insert(
            con, "stadiums", ["season", "phase", "id", "uid", "city_id",
                              "capacity", "expansion_capacity", "name"], rows,
            dtypes={"uid": "int64"})
    ct_path = os.path.join(d, "cities.json")
    if os.path.exists(ct_path):
        rows = [(season, phase, _int(v.get("id")), _int(v.get("uid")),
                 _int(v.get("nation_id")), v.get("latitude"), v.get("longitude"),
                 _int(v.get("attraction")), _int(v.get("region_id")))
                for v in _load_json(ct_path).values()]
        counts["cities"] = _insert(
            con, "cities", ["season", "phase", "id", "uid", "nation_id",
                            "latitude", "longitude", "attraction", "region_id"], rows,
            dtypes={"uid": "int64"})

    # --- languages / currencies / nations -------------------------------------
    lang_path = os.path.join(d, "languages.json")
    if os.path.exists(lang_path):
        rows = [(season, phase, _int(v.get("id")), _int(v.get("uid")), v.get("name"),
                 v.get("other_name"), _int(v.get("nation_id")), _int(v.get("difficulty")))
                for v in _load_json(lang_path).values()]
        counts["languages"] = _insert(
            con, "languages", ["season", "phase", "id", "uid", "name", "other_name",
                               "nation_id", "difficulty"], rows)
    cur_path = os.path.join(d, "currencies.json")
    if os.path.exists(cur_path):
        rows = [(season, phase, _int(v.get("uid")), v.get("name"), v.get("exchange_rate"))
                for v in _load_json(cur_path).values()]
        counts["currencies"] = _insert(
            con, "currencies", ["season", "phase", "uid", "name", "exchange_rate"], rows)
    nat_path = os.path.join(d, "nations.json")
    if os.path.exists(nat_path):
        rows = [(season, phase, _int(v.get("id")), _int(v.get("uid")), v.get("name"),
                 v.get("nationality"), v.get("code"), _int(v.get("continent_id")),
                 _int(v.get("capital_city_id")), _int(v.get("national_stadium_id")),
                 _int(v.get("rival_nation_id")), v.get("is_ranked"),
                 _int(v.get("world_ranking")), _int(v.get("ranking_points")))
                for v in _load_json(nat_path).values()]
        counts["nations"] = _insert(
            con, "nations", ["season", "phase", "id", "uid", "name", "nationality", "code",
                             "continent_id", "capital_city_id", "national_stadium_id",
                             "rival_nation_id", "is_ranked", "world_ranking",
                             "ranking_points"], rows, dtypes={"uid": "int64"})
        hist, coef, langs = [], [], []
        for v in _load_json(nat_path).values():
            nid = _int(v.get("id"))
            for lg in v.get("languages") or []:
                langs.append((season, phase, nid, _int(lg.get("language_id")),
                              _int(lg.get("proficiency"))))
            for i, rk in enumerate(v.get("ranking_history") or []):
                hist.append((season, phase, nid, i, _int(rk)))
            for i, cf in enumerate(v.get("coefficients") or []):
                coef.append((season, phase, nid, i, cf))
        counts["nation_ranking_history"] = _insert(
            con, "nation_ranking_history",
            ["season", "phase", "nation_id", "seq", "ranking"], hist)
        counts["nation_coefficients"] = _insert(
            con, "nation_coefficients",
            ["season", "phase", "nation_id", "seq", "coefficient"], coef)
        counts["nation_languages"] = _insert(
            con, "nation_languages",
            ["season", "phase", "nation_id", "language_id", "proficiency"], langs)

    # --- competitions --------------------------------------------------------
    comps = _load_json(os.path.join(d, "competitions.json"))
    comp_cols = ["season", "phase", "cid", "uid", "name", "short", "code", "type",
                 "type_id", "nation_id", "reputation", "level", "parent_cid"]
    comp_rows = [(season, phase, _int(v.get("cid")), _int(v.get("uid")), v.get("name"),
                  v.get("short"), v.get("code"), v.get("type"), _int(v.get("type_id")),
                  _int(v.get("nation_id")), _int(v.get("reputation")),
                  _int(v.get("level")), _int(v.get("parent_cid"))) for v in comps.values()]
    counts["competitions"] = _insert(con, "competitions", comp_cols, comp_rows)
    tc_path = os.path.join(d, "competition_team_counts.json")
    if os.path.exists(tc_path):
        counts["competition_team_counts"] = _insert(
            con, "competition_team_counts", ["season", "phase", "uid", "teams"],
            [(season, phase, int(u), _int(n)) for u, n in _load_json(tc_path).items()])

    # --- matches + events + player stats -------------------------------------
    # matches.json is the match table as stored (fmparser/tables/matches.py); what the game
    # does not store -- a competition's name, play-off leg labels, a side's star and its
    # summed team stats, which starter stood where -- is derived here, in _match_derived.
    season_matches = _load_json(os.path.join(d, "matches.json"))
    comp_names = {int(k): v.get("name") for k, v in (comps or {}).items()}
    labels = _match_competitions(season_matches, comp_names)
    m_cols = (["season", "phase", "anchor", "date", "competition", "comp_id",
               "home_flag", "home_tid", "away_tid", "attendance", "score_home",
               "score_away", "star_home", "star_away", "formation", "player_of_match"]
              + [f"home_{k}" for k in _TS_KEYS] + [f"away_{k}" for k in _TS_KEYS])
    ev_cols = ["season", "phase", "anchor", "seq", "minute", "added", "min_display",
               "tid", "type", "type_byte", "b0"]
    # `position` is not in _XI: that list mirrors the player slot's own fields, and the
    # starting position comes from our side's position array instead (NULL for the
    # opposition and for substitutes).
    mps_cols = (["season", "phase", "anchor", "side", "tid", "team_tid",
                 "opponent_tid", "date", "competition", "pos_order", "rating"]
                + [f for f in _XI if f not in ("posOrder", "tid", "rating")]
                + ["position"])
    m_rows, ev_rows, mps_rows = [], [], []
    for m, comp in zip(season_matches, labels):
        anchor = _int(m.get("offset"))
        score = m.get("score") or {}
        dv = _match_derived(m)
        h, a = dv["team_stats"]["home"] or {}, dv["team_stats"]["away"] or {}
        home_tid, away_tid = _int(m.get("home_tid")), _int(m.get("away_tid"))
        mdate = _date(m.get("date"))
        m_rows.append((
            season, phase, anchor, mdate, comp, _int(m.get("comp_id")),
            _int(m.get("home_flag")), home_tid, away_tid, _int(m.get("attendance")),
            _int(score.get("home")), _int(score.get("away")),
            dv["star"]["home"], dv["star"]["away"], m.get("formation"),
            _int(m.get("player_of_match")),
            *[_num(h.get(k)) for k in _TS_KEYS], *[_num(a.get(k)) for k in _TS_KEYS],
        ))
        for i, e in enumerate(m.get("events") or []):
            minute, added = _int(e.get("minute")) + 1, _int(e.get("added"))
            ev_rows.append((season, phase, anchor, i, minute, added,
                            f"{minute}+{added}" if added else str(minute),
                            _int(e.get("tid")),
                            EVENT_TYPE.get(e["type_byte"], f"?{e['type_byte']:02x}"),
                            _int(e.get("type_byte")), _int(e.get("b0"))))
        for side, team_tid, opp_tid in (("home", home_tid, away_tid),
                                        ("away", away_tid, home_tid)):
            side_seen = set()
            for x, position in zip(m.get(f"{side}_xi") or [], dv["positions"][side]):
                tid = _int(x.get("tid"))
                if tid is None or tid in side_seen:
                    continue
                side_seen.add(tid)
                mps_rows.append((
                    season, phase, anchor, side, tid, team_tid, opp_tid, mdate, comp,
                    _int(x.get("posOrder")), _int(x.get("rating")),
                    *[_int(x.get(f)) for f in _XI if f not in ("posOrder", "tid", "rating")],
                    position,
                ))
    counts["matches"] = _insert(con, "matches", m_cols, m_rows)
    counts["match_events"] = _insert(con, "match_events", ev_cols, ev_rows)
    counts["match_player_stats"] = _insert(con, "match_player_stats", mps_cols, mps_rows)
    return counts


def _match_competitions(matches, comp_names):
    """Each match's competition label: the competition's name, and for the play-offs (cid
    227) ' Play-Off', plus the leg for a tie played twice -- ' (First Leg)' / ' (Second Leg)'
    by date."""
    labels = [comp_names.get(m.get("comp_id")) for m in matches]
    legs = {}
    for i, m in enumerate(matches):
        if m.get("comp_id") == 227:
            labels[i] = f"{labels[i]} Play-Off"
            legs.setdefault(frozenset((m["home_tid"], m["away_tid"])), []).append(i)
    for tie in legs.values():
        if len(tie) == 2:
            for k, i in enumerate(sorted(tie, key=lambda i: matches[i]["date"] or "")):
                labels[i] += f" ({'First Leg' if k == 0 else 'Second Leg'})"
    return labels


def _match_derived(m):
    """What a match row implies but does not store: per side, the star (best rating, then
    goals, assists, completed passes), the team stats summed over the player lines (the
    rating averaged over players who appeared), and each player's starting position -- our
    side only, since the table holds only our shape."""
    out = {"star": {}, "team_stats": {}, "positions": {}}
    positions = m.get("positions")
    for side in ("home", "away"):
        team = m.get(f"{side}_xi") or []
        ours = m.get("club_tid") == m.get(f"{side}_tid")
        out["positions"][side] = [
            positions[p["posOrder"] - 1] if ours and positions and 1 <= p["posOrder"] <= 11
            else None for p in team]
        if not team:
            out["star"][side] = None
            out["team_stats"][side] = None
            continue
        out["star"][side] = max(team, key=lambda p: (p["rating"], p["goals"], p["assists"],
                                                     p["passC"]))["tid"]
        played = [p["rating"] for p in team if p["posOrder"] <= 11 or p["subOn"] != 0xFF]
        out["team_stats"][side] = {
            "shots": sum(p["shotA"] for p in team),
            "shots_on_target": sum(p["shotO"] for p in team),
            "rating": round(sum(played) / len(played), 1) if played else None,
            "players_used": len(played),
            "passes": sum(p["passA"] for p in team),
            "passes_completed": sum(p["passC"] for p in team),
            "tackles": sum(p["tackA"] for p in team),
            "tackles_won": sum(p["tackW"] for p in team),
            "crosses": sum(p["crossA"] for p in team),
            "interceptions": sum(p["intercept"] for p in team),
        }
    return out


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

    return counts


def _backfill_competition(con, season, phase):
    """A match whose `competition` NAME is still NULL takes it from the competition table by
    comp_id, and the per-player stat lines follow by anchor, so competition filters and
    tables are never blank."""
    con.execute("""
        UPDATE raw.matches m SET competition = l.nm
        FROM (SELECT cid, any_value(name) AS nm FROM raw.competitions
              WHERE name IS NOT NULL GROUP BY cid) l
        WHERE m.competition IS NULL AND m.comp_id = l.cid
          AND m.season = ? AND m.phase = ?
    """, [season, phase])
    con.execute("""
        UPDATE raw.match_player_stats mps SET competition = m.competition
        FROM raw.matches m
        WHERE mps.competition IS NULL AND mps.anchor = m.anchor
          AND (mps.season, mps.phase) = (m.season, m.phase)
          AND mps.season = ? AND mps.phase = ?
    """, [season, phase])


def load_world(con, d, season, phase):
    out = {}
    path = os.path.join(d, "world_fixtures.json")
    data = _load_json(path) if os.path.exists(path) else []
    cols = ["season", "phase", "home_tid", "away_tid", "date", "year", "round",
            "home_goals", "away_goals", "home_pens", "away_pens",
            "stage_key", "seq_id", "season_year", "stage_index", "round_index", "subr"]
    rows = []
    for r in data:
        rows.append((
            season, phase,
            _int(r["home_tid"]), _int(r["away_tid"]), _date(r["date"]), _int(r["year"]), _int(r.get("round")),
            _int(r.get("home_goals")), _int(r.get("away_goals")),
            _int(r.get("home_pens")), _int(r.get("away_pens")),
            _int(r.get("stage_key")), _int(r.get("seq_id")), _int(r.get("season_year")),
            _int(r.get("stage_index")), _int(r.get("round_index")), _int(r.get("subr"))
        ))
    if rows:
        out["world_fixtures"] = _insert(con, "world_fixtures", cols, rows)
    path = os.path.join(d, "competition_rounds.json")
    rules = _load_json(path) if os.path.exists(path) else []
    if rules:
        rcols = ["season", "phase", "uid", "stage_index", "stage_code", "stage_type",
                 "stage_teams", "stage_name_id", "n_groups", "round_index", "round_name_id",
                 "round_teams", "legs"]
        out["competition_rounds"] = _insert(con, "competition_rounds", rcols, [
            (season, phase) + tuple(r.get(c) for c in rcols[2:]) for r in rules])
    path = os.path.join(d, "round_names.json")
    names = _load_json(path) if os.path.exists(path) else []
    if names:
        out["round_names"] = _insert(con, "round_names", ["season", "phase", "id", "name"], [
            (season, phase, r["id"], r["name"]) for r in names])
    return out


# DELETE scope so a reload of one group leaves the others intact
def _clear_group(con, group, season, phase):
    if group == "core":
        for t in ("players_raw", "name_strings", "name_ids",
                  "player_attributes_exact_raw", "player_scrapbook",
                  "staff_attributes", "player_positions",
                  "player_history", "player_history_seasons", "player_progress",
                  "clubs", "club_details", "club_squad", "club_staff", "stadiums", "cities", "languages", "currencies", "nations", "nation_ranking_history",
                  "nation_coefficients", "nation_languages",
                  "club_affiliates", "competitions", "competition_team_counts", "matches",
                  "match_events", "match_player_stats", "club_records", "player_records",
                  "club_league_history", "training", "contracts"):
            _delete(con, t, season, phase)
    elif group == "light":
        _delete(con, "results", season, phase)
    elif group == "world":
        for tbl in ("world_fixtures", "competition_rounds", "round_names"):
            _delete(con, tbl, season, phase)


_GROUP_FN = {"core": load_core, "light": load_light, "world": load_world}


def _archive_snapshot(con, season, phase, label, snap_date):
    """Copy the current (season,phase) players+attributes into history.player_snapshots
    before the slice is overwritten, so a superseded in-season checkpoint is retained for
    progression. Idempotent per snapshot_label."""
    con.execute("DELETE FROM history.player_snapshots WHERE snapshot_label=?", [label])
    # Name every column instead of relying on `p.*, a.*`.
    #
    # This table is created with `CREATE TABLE IF NOT EXISTS ... AS SELECT p.*, a.*`, so its
    # column set is frozen the first time a store is built. A positional INSERT then breaks
    # the moment raw.players gains a column: adding the 7 record-tail fields turned every
    # archive into "table player_snapshots has 78 columns but 85 values were supplied", which
    # failed the whole snapshot load. Resolving the columns against the archive table's OWN
    # schema makes the insert order-independent and additive-safe.
    def cols(tbl):
        return [r[1] for r in con.execute(f"PRAGMA table_info('{tbl}')").fetchall()]
    have = set(cols("history.player_snapshots"))
    pc = [c for c in cols("raw.players") if c in have]
    ac = [c for c in cols("raw.player_attributes")
          if c in have and c not in ("season", "phase", "tid")]
    target = ", ".join(['snapshot_label', 'snapshot_date', 'archived_at']
                       + [f'"{c}"' for c in pc] + [f'"{c}"' for c in ac])
    con.execute(
        f"""INSERT INTO history.player_snapshots ({target})
            SELECT ?, ?, ?, {", ".join([f'p."{c}"' for c in pc] + [f'a."{c}"' for c in ac])}
            FROM raw.players p JOIN raw.player_attributes a USING (season, phase, tid)
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
    if os.path.exists(os.path.join(d, "world_fixtures.json")):
        present.append("world")
    return present


# ---------------------------------------------------------------------------
# per-label orchestration
# ---------------------------------------------------------------------------

def resolve_season_phase(label, d, override):
    """(season, phase): the --season/--phase override, else what extract.py wrote into
    summary.json (phase = the save's header date, season = its campaign). An extract without
    them cannot be placed and is refused."""
    summ_path = os.path.join(d, "summary.json")
    summ = _load_json(summ_path) if os.path.exists(summ_path) else {}
    season = override[0] if override[0] is not None else summ.get("season")
    phase = override[1] or summ.get("phase")
    if season is None or phase is None:
        raise SystemExit(f"{label}: summary.json carries no season/phase (an extract from "
                         f"before header dates?); re-extract it or pass --season and --phase")
    return int(season), phase


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
                "SELECT label FROM raw.extracts WHERE season=? AND phase=?",
                [season, phase]).fetchone()
            if prior and prior[0] != label:
                n = _archive_snapshot(con, season, phase, prior[0], _date(phase))
                print(f"  archived superseded {prior[0]} ({phase}) -> history ({n} players)")
        counts = {}
        for g in groups:
            _clear_group(con, g, season, phase)
            counts.update(_GROUP_FN[g](con, d, season, phase))
        _backfill_competition(con, season, phase)
        _delete(con, "extracts", season, phase)
        # save_path is stored as a BASENAME, not the absolute path the extract recorded.
        # raw.extracts is the rebuild recipe (scripts/export_manifest.py reads it), and an
        # absolute /Users/<you>/Downloads/... path silently makes that recipe machine-specific,
        # so it can't rebuild the store on another laptop. The archive resolves it under
        # $FM_SAVES_DIR/<career>/ instead. source_dir stays absolute: it points at output/,
        # which is a local build artefact rather than part of the recipe.
        con.execute(
            "INSERT INTO raw.extracts (season, phase, label, source_dir, save_path, "
            "loaded_at, row_counts) VALUES (?,?,?,?,?,?,?)",
            [season, phase, label, os.path.abspath(d),
             os.path.basename(summ.get("save") or "") or None,
             datetime.datetime.now(), json.dumps(counts)])
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
    # raw.player_attributes is a VIEW now (exact values + the model in
    # raw.attribute_model), and one DDL statement reads it -- history.player_snapshots is
    # a CREATE TABLE ... AS SELECT that joins it. So the view has to be built partway through
    # the sequence: after the tables it reads exist, before the first statement that needs it.
    # _migrate MUST run before the view is built, not after. The view reads byte columns off
    # raw.players; on a store created before those columns existed, building it first
    # throws and _migrate never runs -- so the store can never heal and EVERY subsequent load
    # fails identically. That deadlock cost a full 25-save rebuild on 2026-09-17: the nine
    # PLAIN_OFFSETS columns were missing, the view asked for `p.heading_src`, and the ALTER
    # that would have added it sat four lines further down.
    # The build is needed only while that table (or the models themselves) does not exist
    # yet: on every later load the models from the last build serve the snapshot archive,
    # and create_views rebuilds them once the load is done.
    def _build_view():
        _migrate(con)
        _seed_attribute_model(con)
        if (models_compat._kind(con, "history.player_snapshots") is None
                or models_compat._kind(con, "int.player_attributes") is None):
            build_models(con, "+int_player_attributes", test=False)   # no data to test yet

    _rename_staging(con)
    _raw_tables(con)
    made_view = False
    for stmt in DDL:
        if not made_view and re.search(r"raw\.player_attributes\b(?!_exact)", stmt):
            _build_view()
            made_view = True
        con.execute(stmt)
    if not made_view:
        _build_view()
    _migrate(con)          # again: tables created later in DDL get their columns too


def _rename_staging(con):
    """Stores built before 2026-10-01 hold the landed tables in a schema named `staging`.
    DuckDB cannot rename a schema or move a table between schemas, so each base table is
    re-created in `raw` from its own DDL (defaults and NOT NULL kept) and its rows copied,
    then `staging` is dropped; the views over it are rebuilt by the loader and create_mart.
    `staging.standings` is not carried: nothing writes or reads it. Idempotent: a no-op once
    `staging` is gone. A published (run-length compacted) copy is refused, since its tables
    are `_rle_*` with expansion views that this cannot rebuild -- republish it instead."""
    if not con.execute("SELECT 1 FROM information_schema.schemata "
                       "WHERE schema_name = 'staging'").fetchone():
        return
    tables = con.execute("SELECT table_name, sql FROM duckdb_tables() "
                         "WHERE schema_name = 'staging' ORDER BY table_name").fetchall()
    if any(t.startswith("_rle_") for t, _ in tables):
        raise SystemExit("this is a published (compacted) store with a `staging` schema; "
                         "rebuild or republish it rather than migrating it in place")
    con.execute("BEGIN")
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS raw")
        for name, ddl in tables:
            if name == "standings":
                continue
            if not con.execute("SELECT 1 FROM duckdb_tables() WHERE schema_name = 'raw' "
                               "AND table_name = ?", [name]).fetchone():
                con.execute(re.sub(r"^CREATE TABLE (staging\.|\"staging\"\.)",
                                   "CREATE TABLE raw.", ddl))
            con.execute(f'INSERT INTO raw."{name}" SELECT * FROM staging."{name}"')
        con.execute("DROP SCHEMA staging CASCADE")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    print(f"  migrated {len(tables)} tables from schema `staging` to `raw`")


def _raw_tables(con, S="raw"):
    """raw.players and raw.player_attributes_exact were TABLES until 2026-09-30 and
    are VIEWS over `players_raw` / `player_attributes_exact_raw` now: rename a store's
    tables to the raw names, and drop the columns the players view now derives."""
    for old in ("players", "player_attributes_exact"):
        kind = con.execute(
            "SELECT table_type FROM information_schema.tables "
            "WHERE table_schema = ? AND table_name = ?", [S, old]).fetchone()
        if kind and kind[0] == "BASE TABLE":
            con.execute(f"ALTER TABLE {S}.{old} RENAME TO {old}_raw")
    if con.execute("SELECT 1 FROM information_schema.tables "
                   "WHERE table_schema = ? AND table_name = 'players_raw'", [S]).fetchone():
        for c in ("player_value", "loaned_in", "parent_club_tid", "parent_club",
                  "attribute_snapshot_date"):
            con.execute(f"ALTER TABLE {S}.players_raw DROP COLUMN IF EXISTS {c}")


# Column additions for stores created before a schema change (CREATE TABLE IF NOT EXISTS
# won't add columns to an existing table). Each is idempotent.
_MIGRATIONS = [
    "ALTER TABLE raw.club_records ADD COLUMN IF NOT EXISTS record_table VARCHAR",
    "ALTER TABLE raw.player_records ADD COLUMN IF NOT EXISTS record_table VARCHAR",
    # 2026-08-19: career history re-decoded (linked-list chains + the P-38 link), which also
    # yielded assists, average rating and the debut season. See fmparser/tables/history.py.
    "ALTER TABLE raw.player_history ADD COLUMN IF NOT EXISTS debut_season INTEGER",
    "ALTER TABLE raw.player_history ADD COLUMN IF NOT EXISTS debut_end_year INTEGER",
    "ALTER TABLE raw.player_history_seasons ADD COLUMN IF NOT EXISTS assists INTEGER",
    "ALTER TABLE raw.player_history_seasons ADD COLUMN IF NOT EXISTS rating DOUBLE",
    # 2026-09-29: yellow and red cards, verified against an in-game Player History screen.
    "ALTER TABLE raw.player_history_seasons ADD COLUMN IF NOT EXISTS yellows INTEGER",
    "ALTER TABLE raw.player_history_seasons ADD COLUMN IF NOT EXISTS reds INTEGER",
    # 2026-08-29: real on-pitch position per starter, decoded from the 11 slot pairs that
    # follow the formation string. See docs/agent-context/match-position-encoding.md.
    "ALTER TABLE raw.match_player_stats ADD COLUMN IF NOT EXISTS position VARCHAR",
    "ALTER TABLE raw.matches ADD COLUMN IF NOT EXISTS player_of_match INTEGER",
    # 2026-09: mistakes leading to a goal. Decoded all along (matches.FIELDS offset 23) but
    # dropped from _XI_FIELDS before serialisation, so it never reached the extract JSON.
    # Existing stores get the column as NULL: the value is missing from output/*.json, so a
    # backfill needs a full re-extract (scripts/rebuild.py), not --refresh-only.
    "ALTER TABLE raw.match_player_stats ADD COLUMN IF NOT EXISTS mistGoal INTEGER",
    # 2026-09-16: the global attribute record runs P-42..P+35, but we stopped reading at
    # P+22 — the last 13 bytes were never parsed. Field order confirmed against
    # nyongrand/fmm-editor; see docs/agent-context/fmm-editor-record-comparison.md. Same
    # caveat as mistGoal above: the values are absent from existing output/*.json, so
    # --refresh-only adds the columns as NULL and a backfill needs a full re-extract.
    "ALTER TABLE raw.players_raw ADD COLUMN IF NOT EXISTS current_reputation INTEGER",
    "ALTER TABLE raw.players_raw ADD COLUMN IF NOT EXISTS world_reputation INTEGER",
    """CREATE TABLE IF NOT EXISTS raw.world_fixtures (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        home_tid INTEGER NOT NULL, away_tid INTEGER NOT NULL,
        date DATE NOT NULL, year INTEGER NOT NULL,
        round INTEGER,
        home_goals INTEGER, away_goals INTEGER,
        home_pens INTEGER, away_pens INTEGER,
        stage_key INTEGER, seq_id INTEGER,
        season_year INTEGER,
        stage_index INTEGER, round_index INTEGER, subr INTEGER
    )""",

    # natural key: (season, phase, uid, stage_index, round_index). Each competition's
    # stage/round structure from its archive member comp_<uid>.dat; `uid` is
    # raw.competitions.uid, and stage_index/round_index are the numbers
    # world_fixtures carries. Name ids resolve through raw.round_names.
    """CREATE TABLE IF NOT EXISTS raw.competition_rounds (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL, uid BIGINT NOT NULL,
        stage_index INTEGER, stage_code VARCHAR, stage_type INTEGER, stage_teams INTEGER,
        stage_name_id BIGINT, n_groups INTEGER,
        round_index INTEGER, round_name_id BIGINT, round_teams INTEGER, legs INTEGER
    )""",

    # natural key: (season, phase, id). The game's stage/round/leg name catalog.
    """CREATE TABLE IF NOT EXISTS raw.round_names (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL, id BIGINT NOT NULL, name VARCHAR
    )""",
    "ALTER TABLE raw.players_raw ADD COLUMN IF NOT EXISTS international_retired BOOLEAN",
    "ALTER TABLE raw.players_raw ADD COLUMN IF NOT EXISTS squad_number INTEGER",
    "ALTER TABLE raw.players_raw ADD COLUMN IF NOT EXISTS preferred_squad_number INTEGER",
    "ALTER TABLE raw.players_raw ADD COLUMN IF NOT EXISTS height_cm INTEGER",
    "ALTER TABLE raw.players_raw ADD COLUMN IF NOT EXISTS weight_kg INTEGER",
    # 2026-09-16: competition LEVEL (0 = top flight) + parent cid, and the reputation read
    # moved from the trailer's p+8 to p+9 -- the old offset straddled the background colour
    # and returned roughly 256x the real value. See fmparser/clubs_comps.py.
    "ALTER TABLE raw.competitions ADD COLUMN IF NOT EXISTS level INTEGER",
    "ALTER TABLE raw.competitions ADD COLUMN IF NOT EXISTS parent_cid INTEGER",
    # history.player_snapshots is built with `CREATE TABLE ... AS SELECT p.*, a.*`, so its
    # columns froze when the store was first created. Mirror the raw.players additions
    # here too, otherwise the archive silently stops carrying them. _archive_snapshot names
    # its columns explicitly, so these can be appended in any order.
    "ALTER TABLE history.player_snapshots ADD COLUMN IF NOT EXISTS current_reputation INTEGER",
    "ALTER TABLE history.player_snapshots ADD COLUMN IF NOT EXISTS world_reputation INTEGER",
    "ALTER TABLE history.player_snapshots ADD COLUMN IF NOT EXISTS international_retired BOOLEAN",
    "ALTER TABLE history.player_snapshots ADD COLUMN IF NOT EXISTS squad_number INTEGER",
    "ALTER TABLE history.player_snapshots ADD COLUMN IF NOT EXISTS preferred_squad_number INTEGER",
    "ALTER TABLE history.player_snapshots ADD COLUMN IF NOT EXISTS height_cm INTEGER",
    "ALTER TABLE history.player_snapshots ADD COLUMN IF NOT EXISTS weight_kg INTEGER",
    # 2026-09-16: the national-team block on the nation record (world ranking, points, rival,
    # and the UEFA coefficients a European campaign is seeded from). Same trap as every other
    # addition here: raw.nations is CREATE TABLE IF NOT EXISTS, so a store built an hour
    # earlier keeps the narrower shape until these run.
    # 2026-09-16 (later): the staff record is 39 bytes, and +14 -- one of its seven HIDDEN
    # attribute bytes -- is the manager's attacking intent, which Style is banded from. See
    # fmparser/staff.py. Absent from existing output/*.json, so --refresh-only adds the
    # columns as NULL; a backfill needs a full re-extract.
    "ALTER TABLE raw.staff_attributes ADD COLUMN IF NOT EXISTS attacking_intent INTEGER",
    "ALTER TABLE raw.staff_attributes ADD COLUMN IF NOT EXISTS style VARCHAR",
    "ALTER TABLE raw.nations ADD COLUMN IF NOT EXISTS rival_nation_id INTEGER",
    "ALTER TABLE raw.nations ADD COLUMN IF NOT EXISTS is_ranked BOOLEAN",
    "ALTER TABLE raw.nations ADD COLUMN IF NOT EXISTS world_ranking INTEGER",
    "ALTER TABLE raw.nations ADD COLUMN IF NOT EXISTS ranking_points INTEGER",
    # 2026-09-16 (later still): the HIDDEN attributes. Both records carry 1-20 attribute bytes
    # we can identify as attributes but cannot name -- 9 on the player record, 6 on the staff
    # record. They were parsed and discarded, which is the record-tail failure with a
    # different excuse. Now carried, and named from fmm-editor's Player.cs. Same caveat:
    # absent from existing output/*.json, so --refresh-only adds them as NULL and a backfill
    # needs a full re-extract.
] + [f"ALTER TABLE raw.players_raw ADD COLUMN IF NOT EXISTS {c} INTEGER"
     for c in PLAYER_HIDDEN_COLS] + [
    # history.player_snapshots froze its columns at CREATE TABLE ... AS SELECT time, so it
    # needs the same additions or the archive silently stops carrying them.
] + [f"ALTER TABLE history.player_snapshots ADD COLUMN IF NOT EXISTS {c} INTEGER"
     for c in PLAYER_HIDDEN_COLS] + [
] + [f"ALTER TABLE raw.staff_attributes ADD COLUMN IF NOT EXISTS {c} INTEGER"
     for c in STAFF_HIDDEN_COLS] + [
    # 2026-09-16: the info record's personality block and international record. Decoded and
    # verified against screenshots back in BUGS #14, then never wired into the parser -- the
    # same identified-and-discarded failure as the record tail.
] + [f"ALTER TABLE raw.players_raw ADD COLUMN IF NOT EXISTS {c} INTEGER"
     for c in SRC_COLS] + [
] + [f"ALTER TABLE history.player_snapshots ADD COLUMN IF NOT EXISTS {c} INTEGER"
     for c in SRC_COLS] + [
] + [f"ALTER TABLE raw.players_raw ADD COLUMN IF NOT EXISTS {c} {t}"
     for c, t in _PERSON_SQL.items()] + [
] + [f"ALTER TABLE history.player_snapshots ADD COLUMN IF NOT EXISTS {c} {t}"
     for c, t in _PERSON_SQL.items()] + [
    # 2026-10-01: phase is the save's header date, so the label-derivation and match-date
    # columns carry nothing (data-layers plan, step 2).
] + [f"ALTER TABLE raw.extracts DROP COLUMN IF EXISTS {c}"
     for c in ("label_auto", "latest_match", "date_from", "date_to")] + [
    # 2026-10-01: extract writes the whole club and competition tables; the league tables
    # it used to assemble, and the league label on each player, are derived in the mart
    # (data-layers plan, step 4).
    "DROP TABLE IF EXISTS raw.leagues",
    "DROP TABLE IF EXISTS raw.league_members",
    "ALTER TABLE raw.competitions DROP COLUMN IF EXISTS num_teams",
    "ALTER TABLE raw.competitions DROP COLUMN IF EXISTS matches_in_save",
    "ALTER TABLE raw.competitions ADD COLUMN IF NOT EXISTS reputation INTEGER",
    "ALTER TABLE raw.players_raw DROP COLUMN IF EXISTS league_cid",
    "ALTER TABLE raw.players_raw DROP COLUMN IF EXISTS league",
    # 2026-10-01: extract hands over the contract grid and the training row's contract flag
    # and squad status as stored; the players' contract and status columns are int.players'
    # (data-layers plan, step 7).
    "ALTER TABLE raw.training ADD COLUMN IF NOT EXISTS contracted INTEGER",
    "ALTER TABLE raw.training ADD COLUMN IF NOT EXISTS squad_status INTEGER",
] + [f"ALTER TABLE raw.players_raw DROP COLUMN IF EXISTS {c}"
     for c in ("squad_status", "loaned_out", "wage_units", "wage_gbp", "contract_expiry",
               "contract_expiry_year")] + [
    # 2026-10-01: extract hands over each person's name ids and the name tables they index;
    # the display name is int.person_names' (data-layers plan, step 8). A store loaded before
    # keeps its resolved names in raw.players_raw.name, which int.person_names falls back to
    # for the snapshots that have no ids.
] + [f"ALTER TABLE raw.players_raw ADD COLUMN IF NOT EXISTS {c} BIGINT" for c in NAME_ID_COLS
] + [stmt for stmt in DDL
     if "raw.name_strings (" in stmt or "raw.name_ids (" in stmt]


def _backfill_contracts(con):
    """A store loaded before extract handed over the contract grid holds each player's current
    contract and squad status as columns of raw.players_raw. Move them to raw.contracts and
    raw.training, where int.players reads them, before the migration drops the columns; a
    snapshot already in raw.contracts is left alone. Idempotent: a no-op once the columns are
    gone. Lapsed contracts and start dates were never extracted, so they stay absent until the
    snapshot is re-extracted."""
    cols = {r[0] for r in con.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'raw' AND table_name = 'players_raw'").fetchall()}
    if "wage_units" not in cols or "squad_status" not in cols:
        return
    con.execute(_ddl_for("raw.contracts"))
    con.execute("ALTER TABLE raw.training ADD COLUMN IF NOT EXISTS contracted INTEGER")
    con.execute("ALTER TABLE raw.training ADD COLUMN IF NOT EXISTS squad_status INTEGER")
    con.execute("""
        INSERT INTO raw.contracts (season, phase, tid, marker, wage_units, expiry, start_date)
        SELECT p.season, p.phase, p.tid, 1, p.wage_units, p.contract_expiry, NULL
        FROM raw.players_raw p
        WHERE p.wage_units IS NOT NULL AND NOT p.is_staff
          AND NOT EXISTS (SELECT 1 FROM raw.contracts c
                          WHERE (c.season, c.phase) = (p.season, p.phase))""")
    con.execute(f"""
        UPDATE raw.training t SET contracted = {_CONTRACTED}, squad_status = p.squad_status
        FROM raw.players_raw p
        WHERE (t.season, t.phase, t.tid) = (p.season, p.phase, p.tid)
          AND p.squad_status IS NOT NULL AND t.contracted IS NULL""")


def _ddl_for(table):
    """The DDL statement that creates `table`."""
    return next(stmt for stmt in DDL if f"CREATE TABLE IF NOT EXISTS {table} (" in stmt)


def _migrate(con):
    _backfill_contracts(con)
    for stmt in _MIGRATIONS:
        try:
            con.execute(stmt)
        except Exception as e:            # older DuckDB without IF NOT EXISTS -> ignore dups
            msg = str(e).lower()
            if "already exists" in msg:
                continue
            # A PUBLISHED store (scripts/publish_duckdb.py) is run-length compacted: each
            # raw table becomes `_rle_<name>` with a decompressing VIEW in its place, and
            # a view has no columns of its own to add. Skipping is correct rather than
            # tolerant — the view's columns come from its definition. A mart edit that needs
            # a column the published data genuinely lacks still fails loudly downstream in
            # create_mart, which is the honest outcome: that store predates the field and
            # needs a rebuild + republish, not a migration.
            if "can only modify view" in msg:
                continue
            # _migrate now runs PARTWAY through create_schema (see _build_view), so a table
            # the DDL has not reached yet is not an error: it will be created complete, with
            # every column, by the statement that follows.
            if "does not exist" in msg or "not found" in msg:
                continue
            raise
    _drop_extracts_phase_check(con)


def _drop_extracts_phase_check(con):
    """Stores created before phase became a date have CHECK(phase IN ('start','mid','end'))
    on raw.extracts, which now rejects date-valued phases. DuckDB can't drop an unnamed
    CHECK in place, so rebuild the table (data + column types preserved) without it.
    Idempotent: a no-op once the constraint is gone."""
    has_check = con.execute(
        "SELECT COUNT(*) FROM duckdb_constraints() "
        "WHERE table_name = 'extracts' AND constraint_type = 'CHECK'").fetchone()[0]
    if not has_check:
        return
    con.execute("CREATE OR REPLACE TABLE raw._extracts_mig AS "
                "SELECT * FROM raw.extracts")
    con.execute("DROP TABLE raw.extracts")
    con.execute("ALTER TABLE raw._extracts_mig RENAME TO extracts")


# Weight-sets the seed no longer ships. Every player is rated in every role of every set, so
# each retired set is removed from an existing store too, not just left out of the seed.
RETIRED_METHODS = ("black_hawk", "personal", "frem_counter", "frem_gegenpress",
                   "frem_lowblock_overload", "frem_game_state", "frem_minmax_4411")


def seed_role_weights(con):
    """(Re)seed the tactic weight-sets from seeds/role_weights.csv, leaving any user-defined
    tactic untouched. Idempotent: deletes exactly the methods the CSV names, and the retired
    ones, then inserts it."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seeds",
                        "role_weights.csv")
    if not os.path.exists(path):
        print(f"  ! role_weights seed missing at {path}; skipping")
        return
    con.execute(
        "DELETE FROM raw.role_weights WHERE method IN "
        "(SELECT DISTINCT method FROM read_csv_auto(?))", [path])
    con.execute("DELETE FROM raw.role_weights WHERE method IN ("
                + ", ".join("?" * len(RETIRED_METHODS)) + ")", list(RETIRED_METHODS))
    con.execute(
        "INSERT INTO raw.role_weights (method, role, attribute, category, weight) "
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
    con.execute("DELETE FROM raw.eligible_origin_clubs")
    con.executemany("INSERT INTO raw.eligible_origin_clubs "
                    "(club_tid, club_name, region) VALUES (?,?,?)", rows)


def seed_reference(con):
    """Seed the static position->role map (replace) and app_config defaults (only for
    keys that don't yet exist, so Config-page edits survive reloads)."""
    con.execute("DELETE FROM raw.position_role_map")
    con.executemany("INSERT INTO raw.position_role_map VALUES (?,?)",
                    list(POSITION_ROLE.items()))
    for k, v in APP_CONFIG_DEFAULTS.items():
        con.execute(
            "INSERT INTO raw.app_config SELECT ?, ? "
            "WHERE NOT EXISTS (SELECT 1 FROM raw.app_config WHERE key=?)", [k, v, k])


def seed_event_types(con):
    """(Re)seed raw.event_types, the byte -> name map the mart labels match events with,
    from the parser's own table (fmparser.tables.matches.EVENT_TYPE). Replaced wholesale on
    every load and --refresh-only, so naming a byte reaches the store without a re-extract."""
    con.execute("CREATE TABLE IF NOT EXISTS raw.event_types "
                "(code INTEGER PRIMARY KEY, name VARCHAR NOT NULL)")
    con.execute("DELETE FROM raw.event_types")
    con.executemany("INSERT INTO raw.event_types VALUES (?, ?)",
                    sorted(EVENT_TYPE.items()))


def seed_career(con, key=None):
    """Record which career this store holds in raw.app_config: `career_key`,
    `career_rating_method` and `career_managed_tid`, the club we manage.

    fmstats reads the store, never fmparser, so the loader, which may read both, writes down
    the career facts the mart needs: the tactic we play (the save does not carry it) and our
    club (mart.our_clubs is it plus its reserve side). `key` is the career the loaded extracts
    name in their summary.json; without one (a --refresh-only) the store's own recorded key
    is kept. Runs before create_mart."""
    if key is None:
        row = con.execute("SELECT value FROM raw.app_config "
                          "WHERE key = 'career_key'").fetchone()
        key = row[0] if row else None
    car = careers.CAREERS.get(key) if key else None
    if car is None:
        print(f"  ! career {key!r} is not a registered career (fmparser/careers.py); "
              f"career keys left unset")
        return
    for k, v in (("career_key", car.key), ("career_rating_method", car.rating_method),
                 ("career_managed_tid", str(car.managed_tid))):
        con.execute("DELETE FROM raw.app_config WHERE key = ?", [k])
        if v is not None:
            con.execute("INSERT INTO raw.app_config VALUES (?, ?)", [k, v])


def _extract_career(dirs):
    """The career key the extracts' summary.json files name, or None. Every extract loaded
    into one store must name the same career."""
    keys = set()
    for d in dirs:
        sp = os.path.join(d, "summary.json")
        if os.path.exists(sp):
            k = (_load_json(sp).get("career") or {}).get("key")
            if k:
                keys.add(k)
    if len(keys) > 1:
        raise SystemExit(f"extracts from more than one career in one load: {sorted(keys)}")
    return keys.pop() if keys else None


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
        con.execute("DELETE FROM raw.app_config WHERE key=?", [k])
        con.execute("INSERT INTO raw.app_config VALUES (?, ?)", [k, str(v)])
    rows = b.get("role_weights") or []
    if rows:
        methods = sorted({r["method"] for r in rows})
        ph = ",".join("?" * len(methods))
        con.execute(f"DELETE FROM raw.role_weights WHERE method IN ({ph})", methods)
        con.executemany(
            "INSERT INTO raw.role_weights (method, role, attribute, category, weight) "
            "VALUES (?,?,?,?,?)",
            [(r["method"], r["role"], r["attribute"], r.get("category"), int(r["weight"]))
             for r in rows])
    prm = b.get("position_role_map") or {}
    if prm:
        con.execute("DELETE FROM raw.position_role_map")
        con.executemany("INSERT INTO raw.position_role_map VALUES (?,?)", list(prm.items()))
    print(f"  seeded config bundle from {os.path.basename(path)} "
          f"({len(b.get('app_config') or {})} settings, {len(rows)} weight rows)")


# person_id for a slice row; '?' when dob is unknown so the row still gets a stable key
# (28 tids appear in match stats but in no players slice at all — they keep tid-only identity).
def create_views(con):
    """The stg/int models (the dbt project in transform/) and the compatibility views over
    them. The attribute coefficients are seeded first: int.player_attributes is generated
    from them. Returns the models built."""
    con.execute(ATTR_MODEL_DDL)
    _seed_attribute_model(con)
    for name in RETIRED_VIEWS:
        con.execute(f"DROP VIEW IF EXISTS {name}")
    return build_models(con)


TRANSFORM_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "transform")


def build_models(con, select=None, test=True):
    """Build the dbt project (transform/) in the store `con` is open on -- every model, or the
    `select` expression -- then create the compatibility views over it. With `test`, this is
    `dbt build`: each model's data and unit tests run straight after it, a failure stops the
    models downstream of it, and this raises. dbt runs in this process, so it shares the open
    database rather than contending for the file's lock. Returns the models built."""
    from dbt.cli.main import dbtRunner
    path = con.execute("SELECT path FROM duckdb_databases() "
                       "WHERE database_name = current_database()").fetchone()[0]
    if not path:
        raise RuntimeError("the models are built by dbt, which needs the store as a file; "
                           "this connection is to an in-memory database")
    args = ["build" if test else "run", "--project-dir", TRANSFORM_DIR,
            "--profiles-dir", TRANSFORM_DIR, "--quiet"]
    if select:
        args += ["--select", select]
    before = os.environ.get("FM_DUCKDB")
    os.environ["FM_DUCKDB"] = os.path.abspath(path)
    try:
        res = dbtRunner().invoke(args)
    finally:
        if before is None:
            os.environ.pop("FM_DUCKDB", None)
        else:
            os.environ["FM_DUCKDB"] = before
    if not res.success:
        raise RuntimeError(f"dbt {args[0]} failed: {res.exception or 'see the errors above'}")
    built = [r.node.relation_name for r in res.result
             if r.node.resource_type == "model" and r.status == "success"]
    models_compat.create(con)
    return built


def report_persons(con):
    n, t = con.execute("SELECT COUNT(*), COUNT(DISTINCT tid) FROM int.persons").fetchone()
    if n > t:
        print(f"  identity bridge: {n} persons across {t} tids "
              f"({n - t} recycled slot(s) — see docs/IDS.md)")


def reset_schema(con):
    # mart first: its views depend on raw, so dropping raw out from under them
    # would leave dangling definitions behind.
    drop_mart(con)
    con.execute("DROP SCHEMA IF EXISTS raw CASCADE")
    con.execute("DROP SCHEMA IF EXISTS staging CASCADE")
    con.execute("DROP SCHEMA IF EXISTS history CASCADE")
    con.execute("DROP SCHEMA IF EXISTS int CASCADE")
    con.execute("DROP SCHEMA IF EXISTS stg CASCADE")
    for name in RETIRED_VIEWS:
        con.execute(f"DROP VIEW IF EXISTS {name}")
    for name in models_compat.VIEWS:
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
                    help="drop and recreate the raw schema + views first")
    ap.add_argument("--refresh-only", action="store_true",
                    help="rebuild the SQL views, the mart layer AND the role-weight seeds "
                         "against an existing store, loading nothing. All three are just "
                         "definitions, so a change to fmstats/mart.py, transform/ or "
                         "seeds/role_weights.csv does not reach a store until something "
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
            # Schema migrations first. A mart/view definition can depend on a raw COLUMN
            # that a store predating the change does not have, and --refresh-only is the
            # documented way to apply a definition edit (see CLAUDE.md) — so without this the
            # refresh dies in create_mart with a Binder Error naming the missing column, and
            # the only recovery is a full re-import. Every entry in _MIGRATIONS is idempotent,
            # so running it on an already-current store is a no-op.
            _rename_staging(con)
            _migrate(con)
            # seeds/role_weights.csv is a DEFINITION, exactly like a view: editing it has to
            # reach an existing store without a full re-import. seed_role_weights only replaces
            # the methods the CSV names, so a weight-set built in the Lab and promoted into
            # raw.role_weights survives this.
            seed_role_weights(con)
            seed_event_types(con)
            built = create_views(con)
            seed_career(con)
            mart_objects = create_mart(con)
            print(f"{args.db}: role-weight seeds + {len(built)} models + {len(mart_objects)} "
                  f"mart objects rebuilt (nothing loaded)")
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
            summ = _load_json(os.path.join(d, "summary.json"))
            if summ.get("season") is not None and summ.get("phase"):
                seen.setdefault((summ["season"], summ["phase"]), []).append(label)
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
        seed_event_types(con)
        create_views(con)
        report_persons(con)
        seed_career(con, _extract_career(dirs))
        mart_objects = create_mart(con)
        print(f"done: {ok} loaded, {fail} failed. views refreshed, "
              f"{len(mart_objects)} mart objects rebuilt.")
    finally:
        con.close()


if __name__ == "__main__":
    main()
