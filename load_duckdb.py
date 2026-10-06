#!/usr/bin/env python3
"""
Load fm-parser extract bundles into a DuckDB store.

    uv run python load_duckdb.py output/frem-2023-07-02 --db fm-frem.duckdb [--career frem]
    uv run python load_duckdb.py output --all --db fm-frem.duckdb --career frem
    uv run python load_duckdb.py output/frem-2023-07-02 --include core,world
    uv run python load_duckdb.py output --all --reset --career frem

The tables in the `raw` schema are a 1:1 mirror of the JSON that the extractors
write to output/<label>/ (same grain, minimal reshaping) — every row stamped with
season (int end-year, 21/22 -> 2022) and phase (the save's in-game date). The extract is
career-agnostic; the career (`--career`, else the one the store records, careers.py) places
each snapshot in its campaign and names our clubs for the match-table check. The
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
import careers
from fmparser.tables.matches import EVENT_TYPE, check_against_fixtures

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
from fmparser.core import DATE as _DATE, HEX4 as _HEX4, U32 as _U32     # noqa: E402
from fmparser.tables.player_attributes import HIDDEN_OFFSETS as _PLAYER_HIDDEN  # noqa: E402
from fmparser.tables.player_attributes import SRC_OFFSETS as _SRC              # noqa: E402
from fmparser.tables.player_attributes import PLAIN_OFFSETS as _PLAIN            # noqa: E402
from fmparser.tables.person_info import PERSON_FIELDS as _PERSON        # noqa: E402
from fmparser.tables.person_info import PERSON_INFO as _PERSON_INFO     # noqa: E402
from fmparser.tables.staff import STAFF as _STAFF                       # noqa: E402
SRC_COLS = list(_SRC.values()) + list(_PLAIN.values())
PERSON_COLS = list(_PERSON)
# Everything off the info record is a small integer except the one date.
PERSON_DATE_COLS = {"joined_date"}
_PERSON_SQL = {c: ("DATE" if c in PERSON_DATE_COLS else "INTEGER") for c in PERSON_COLS}
PLAYER_HIDDEN_COLS = list(_PLAYER_HIDDEN.values())
NAME_TABLES = ("first_names", "surnames", "nicknames")


def _record_columns(record):
    """[(column, SQL type)] for every field a parser Record emits, in layout order: a date
    is DATE, a hex id VARCHAR, a u32 BIGINT, anything narrower INTEGER."""
    sql = {_DATE: "DATE", _HEX4: "VARCHAR", _U32: "BIGINT"}
    return [(f.name, sql.get(f.kind, "INTEGER")) for f in record.fields if f.emits]


# The three person tables as extract dumps them (persons.json, attribute_records.json,
# staff_records.json): each column list is the parser's own record layout, so the loader
# cannot fall out of step with it.
PERSON_RECORD_COLS = _record_columns(_PERSON_INFO)
ATTRIBUTE_RECORD_COLS = (
    [("sid", "VARCHAR"), ("history_head", "BIGINT"), ("positions", "JSON"), ("foot_left", "INTEGER"),
     ("foot_right", "INTEGER"), ("ca", "INTEGER"), ("pa", "INTEGER"), ("reputation", "INTEGER"),
     ("current_reputation", "INTEGER"), ("world_reputation", "INTEGER"),
     ("international_retired", "BOOLEAN"), ("squad_number", "INTEGER"),
     ("preferred_squad_number", "INTEGER"), ("height_cm", "INTEGER"), ("weight_kg", "INTEGER")]
    + [(c, "INTEGER") for c in PLAYER_HIDDEN_COLS + SRC_COLS])
STAFF_RECORD_COLS = _record_columns(_STAFF)


def _cols_ddl(cols):
    return ",\n        ".join(f"{c} {t}" for c, t in cols)


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
    # Danish 100, English 70, Swedish 50). A nation can list a language more than once
    # (Iceland: English at 50, 70 and 95), so there is no natural key.
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

    # The person table as the save stores it, one record per person (players and staff):
    # identity, club, personality, and the links to a player's attribute record (`sid`,
    # 'ffffffff' for staff) and a staff member's staff record (`id2`). The stg/int models
    # join the three; raw.players is the old mart's view over them.
    # natural key: (season, phase, tid)
    f"""CREATE TABLE IF NOT EXISTS raw.person_records (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        {_cols_ddl(PERSON_RECORD_COLS)}
    )""",

    # The player attribute table as stored, one record per player who has one, keyed by
    # `sid`: the 34 attribute bytes (the 16 entangled *_src bytes raw, the nine plain ones,
    # the nine hidden ones), positions, feet, CA/PA and the record's tail. The entangled
    # bytes are kept undecoded so the attribute model can be refitted against the store.
    # natural key: (season, phase, sid)
    f"""CREATE TABLE IF NOT EXISTS raw.attribute_records (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        {_cols_ddl(ATTRIBUTE_RECORD_COLS)}
    )""",

    # The staff attribute table as stored, keyed by `id2`: coaching ability, reputation and
    # the manager's formation triple (indices into raw.formations).
    # natural key: (season, phase, id2)
    f"""CREATE TABLE IF NOT EXISTS raw.staff_records (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        {_cols_ddl(STAFF_RECORD_COLS)}
    )""",

    # The formation catalog the staff records index, in declaration order.
    # natural key: (season, phase, formation_id)
    """CREATE TABLE IF NOT EXISTS raw.formations (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL, formation_id INTEGER NOT NULL,
        name VARCHAR
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
        tid INTEGER, type VARCHAR, type_byte INTEGER, b0 INTEGER,
        side VARCHAR CHECK (side IN ('home','away'))
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

    # natural key: (season, phase, home_tid, away_tid, date). home_goals / away_goals are the
    # score after 90 minutes, home_extra_goals / away_extra_goals the score after extra time
    # (NULL when there was none), home_pens / away_pens the shoot-out.
    """CREATE TABLE IF NOT EXISTS raw.world_fixtures (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        home_tid INTEGER NOT NULL, away_tid INTEGER NOT NULL,
        date DATE NOT NULL, year INTEGER NOT NULL,
        round INTEGER,
        home_goals INTEGER, away_goals INTEGER,
        home_pens INTEGER, away_pens INTEGER,
        stage_key INTEGER, seq_id INTEGER,
        season_year INTEGER,
        stage_index INTEGER, round_index INTEGER, subr INTEGER,
        home_extra_goals INTEGER, away_extra_goals INTEGER
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


    # career-history summary, one row per player, read from the raw pool in history.json by
    # `load_history`. origin_club_tid = youth/debut club = the Athletic-Bilbao eligibility
    # key; debut_season = the season on the chain's first record, the debut line. The player
    # -> history link is a stored pointer (the attribute record's `history_head`), so every
    # row is exact; the mart names the clubs. natural key: (season, phase, tid).
    """CREATE TABLE IF NOT EXISTS raw.player_history (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL, tid INTEGER NOT NULL,
        origin_club_tid INTEGER,
        last_season_club_tid INTEGER, record_offset BIGINT,
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
GROUPS = ("core", "world")


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
# 16-byte record as stored), each player's chain starting at his attribute record's
# `history_head`. One record is one line of the in-game Player History screen: a season,
# its club, its fee and its numbers.
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
SELECT ?, ?, e.tid, head.club, last.club, ? + 16 * h.row,
       head.season, {HISTORY_SEASON_BASE} + head.season
FROM ends e
JOIN _hist_chain h ON (h.tid, h.seq) = (e.tid, 0)
JOIN _hist_rows head ON head.row = h.row
JOIN _hist_chain l ON (l.tid, l.seq) = (e.tid, e.last_seq)
JOIN _hist_rows last ON last.row = l.row
"""


def load_history(con, season, phase, hist, heads):
    """raw.player_history (one row per player) and raw.player_history_seasons (one
    per season line), read from the raw history pool, each player's chain from his head
    row (`heads`, {tid: his attribute record's `history_head`}). The pool itself is not
    stored."""
    rows = hist["rows"]
    df = pd.DataFrame({"row": range(hist["count"]),
                       **{k: rows[k] for k in ("club", "fee", "next", "season", "apps",
                                               "goals", "assists", "rating", "yellows",
                                               "reds")}})
    heads = pd.DataFrame({"tid": list(heads), "head": list(heads.values())}, dtype="int64")
    con.register("_hist_rows", df)
    con.register("_hist_heads", heads)
    try:
        con.execute(f"CREATE OR REPLACE TEMP TABLE _hist_chain AS {_HISTORY_CHAIN_SQL}")
        on_chains = con.execute("SELECT count(*) FROM _hist_chain").fetchone()[0]
        con.execute("INSERT INTO raw.player_history (season, phase, tid, origin_club_tid, "
                    "last_season_club_tid, record_offset, debut_season, debut_end_year) "
                    + _HISTORY_SUMMARY_SQL,
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

    # --- the person table and the two attribute tables it links, as stored ----
    def rows(path, cols):
        """Each record of a person-table dump as a row of `cols`, in the dump's order."""
        out = []
        for v in _load_json(path):
            row = [season, phase]
            for c, t in cols:
                x = v.get(c)
                if t == "DATE":
                    x = _date(x)
                elif t == "JSON":
                    x = json.dumps(x or {})
                row.append(x)
            out.append(tuple(row))
        return out

    for name, table, cols in (("persons.json", "person_records", PERSON_RECORD_COLS),
                              ("attribute_records.json", "attribute_records",
                               ATTRIBUTE_RECORD_COLS),
                              ("staff_records.json", "staff_records", STAFF_RECORD_COLS)):
        # every u32 column is stored on every record, so it can be typed (see _insert)
        counts[table] = _insert(con, table, ["season", "phase"] + [c for c, _ in cols],
                                rows(os.path.join(d, name), cols),
                                dtypes={c: "int64" for c, t in cols if t == "BIGINT"})
    formations_path = os.path.join(d, "formations.json")
    if os.path.exists(formations_path):
        counts["formations"] = _insert(
            con, "formations", ["season", "phase", "formation_id", "name"],
            [(season, phase, i, n) for i, n in enumerate(_load_json(formations_path))])

    # the name tables the name ids above index: the browse strings and the three id-tables
    strings_path = os.path.join(d, "browse_names.json")
    if os.path.exists(strings_path):
        counts["name_strings"] = _insert(con, "name_strings",
                                         ["season", "phase", "ordinal", "name"],
                                         [(season, phase, i, s)
                                          for i, s in enumerate(_load_json(strings_path))])
    ids_path = os.path.join(d, "name_ids.json")
    if os.path.exists(ids_path):
        nt = _load_json(ids_path)
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

    # --- career history (origin club + season-by-season) ---------------------
    # each player's chain starts at his attribute record's history_head
    hist_path = os.path.join(d, "history.json")
    if os.path.exists(hist_path):
        heads = dict(con.execute(
            "SELECT p.tid, a.history_head FROM raw.person_records p "
            "JOIN raw.attribute_records a USING (season, phase, sid) "
            "WHERE p.season = ? AND p.phase = ?", [season, phase]).fetchall())
        counts.update(load_history(con, season, phase, _load_json(hist_path), heads))

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
               "tid", "type", "type_byte", "b0", "side"]
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
                            _int(e.get("type_byte")), _int(e.get("b0")),
                            ("home", "away")[e["side"]]))
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
            "stage_key", "seq_id", "season_year", "stage_index", "round_index", "subr",
            "home_extra_goals", "away_extra_goals"]
    rows = []
    for r in data:
        rows.append((
            season, phase,
            _int(r["home_tid"]), _int(r["away_tid"]), _date(r["date"]), _int(r["year"]), _int(r.get("round")),
            _int(r.get("home_goals")), _int(r.get("away_goals")),
            _int(r.get("home_pens")), _int(r.get("away_pens")),
            _int(r.get("stage_key")), _int(r.get("seq_id")), _int(r.get("season_year")),
            _int(r.get("stage_index")), _int(r.get("round_index")), _int(r.get("subr")),
            _int(r.get("home_extra_goals")), _int(r.get("away_extra_goals"))
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
        for t in ("person_records", "attribute_records", "staff_records", "formations",
                  "name_strings", "name_ids", "player_scrapbook",
                  "player_history", "player_history_seasons", "player_progress",
                  "clubs", "club_details", "club_squad", "club_staff", "stadiums", "cities", "languages", "currencies", "nations", "nation_ranking_history",
                  "nation_coefficients", "nation_languages",
                  "club_affiliates", "competitions", "competition_team_counts", "matches",
                  "match_events", "match_player_stats", "club_records", "player_records",
                  "club_league_history", "training", "contracts"):
            _delete(con, t, season, phase)
    elif group == "world":
        for tbl in ("world_fixtures", "competition_rounds", "round_names"):
            _delete(con, tbl, season, phase)


_GROUP_FN = {"core": load_core, "world": load_world}


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
    if os.path.exists(os.path.join(d, "persons.json")):
        present.append("core")
    if os.path.exists(os.path.join(d, "world_fixtures.json")):
        present.append("world")
    return present


# ---------------------------------------------------------------------------
# per-label orchestration
# ---------------------------------------------------------------------------

def _matches(d):
    path = os.path.join(d, "matches.json")
    return _load_json(path) if os.path.exists(path) else []


def save_date(d):
    """The save's in-game date, from its header (summary.json `save_date`), or None."""
    path = os.path.join(d, "summary.json")
    return (_load_json(path) if os.path.exists(path) else {}).get("save_date")


def resolve_season_phase(label, d, career, override=(None, None)):
    """(season, phase): the --season/--phase override, else the save's header date as phase
    and, as season, the campaign that date falls in by the career's rollover
    (`careers.campaign`). An extract with no header date cannot be placed and is refused."""
    phase = override[1] or save_date(d)
    if phase is None:
        raise SystemExit(f"{label}: summary.json carries no save_date (an extract from "
                         f"before header dates?); re-extract it or pass --season and --phase")
    season = override[0]
    if season is None:
        season = career.campaign(phase, any(m["date"] for m in _matches(d)))
    return int(season), phase


def check_matches(d, career):
    """The match table against the world fixture list: the same games, our two clubs'
    fixtures played since the career's last rollover on or before the save date (the game
    empties the table that day). This is what tells an empty table after the rollover from a
    table the locator missed. Raises `MatchTableError`; no fixture list, no check."""
    path = os.path.join(d, "world_fixtures.json")
    world = _load_json(path) if os.path.exists(path) else []
    until = save_date(d)
    if not world or until is None:
        return
    since = f"{until[:4]}-{career.rollover[0]:02d}-{career.rollover[1]:02d}"
    if since > until:
        since = f"{int(until[:4]) - 1}{since[4:]}"
    check_against_fixtures(_matches(d), world, (career.managed_tid, career.reserve_tid),
                           since, until)


def load_label(con, d, include, career, override=(None, None)):
    label = os.path.basename(os.path.normpath(d))
    season, phase = resolve_season_phase(label, d, career, override)
    check_matches(d, career)
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

    _rename_staging(con)
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
    """CREATE TABLE IF NOT EXISTS raw.world_fixtures (
        season INTEGER NOT NULL, phase VARCHAR NOT NULL,
        home_tid INTEGER NOT NULL, away_tid INTEGER NOT NULL,
        date DATE NOT NULL, year INTEGER NOT NULL,
        round INTEGER,
        home_goals INTEGER, away_goals INTEGER,
        home_pens INTEGER, away_pens INTEGER,
        stage_key INTEGER, seq_id INTEGER,
        season_year INTEGER,
        stage_index INTEGER, round_index INTEGER, subr INTEGER,
        home_extra_goals INTEGER, away_extra_goals INTEGER
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
    # 2026-09-16: competition LEVEL (0 = top flight) + parent cid, and the reputation read
    # moved from the trailer's p+8 to p+9 -- the old offset straddled the background colour
    # and returned roughly 256x the real value. See fmparser/tables/competitions.py.
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
    "ALTER TABLE raw.nations ADD COLUMN IF NOT EXISTS rival_nation_id INTEGER",
    "ALTER TABLE raw.nations ADD COLUMN IF NOT EXISTS is_ranked BOOLEAN",
    "ALTER TABLE raw.nations ADD COLUMN IF NOT EXISTS world_ranking INTEGER",
    "ALTER TABLE raw.nations ADD COLUMN IF NOT EXISTS ranking_points INTEGER",
    # history.player_snapshots froze its columns at CREATE TABLE ... AS SELECT time, so it
    # needs the hidden attributes, the attribute bytes and the person block added too, or
    # the archive silently stops carrying them.
] + [f"ALTER TABLE history.player_snapshots ADD COLUMN IF NOT EXISTS {c} INTEGER"
     for c in PLAYER_HIDDEN_COLS + SRC_COLS] + [
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
    # 2026-10-01: extract hands over the contract grid and the training row's contract flag
    # and squad status as stored; the players' contract columns are int.player_snapshots'
    # (data-layers plan, step 7).
    "ALTER TABLE raw.training ADD COLUMN IF NOT EXISTS contracted INTEGER",
    "ALTER TABLE raw.training ADD COLUMN IF NOT EXISTS squad_status INTEGER",
    # 2026-10-01: extract hands over each person's name ids and the name tables they index;
    # the display name is int.person_names' (data-layers plan, step 8).
] + [stmt for stmt in DDL
     if "raw.name_strings (" in stmt or "raw.name_ids (" in stmt] + [
    # 2026-10-02: the history summary's `confidence` was always 'exact' and `origin_club`
    # always NULL (data-layers plan, step 10).
] + [f"ALTER TABLE raw.player_history DROP COLUMN IF EXISTS {c}"
     for c in ("confidence", "origin_club")] + [
    # 2026-10-02: extract dumps the person, attribute and staff tables as stored, and the
    # stg/int models join them (data-layers plan, step 9). The tables extract used to
    # assemble go; a snapshot loaded before has no person records until it is re-extracted.
    "DROP TABLE IF EXISTS raw.players_raw",
    "DROP TABLE IF EXISTS raw.player_attributes_exact_raw",
    # 2026-10-02: a player's history head is his attribute record's own field, not a
    # second map in history.json (data-layers plan, step 11).
    "ALTER TABLE raw.attribute_records ADD COLUMN IF NOT EXISTS history_head BIGINT",
    # 2026-10-02: extract writes no light results, so raw.results was always empty
    # (data-layers plan, step 12).
    "DROP TABLE IF EXISTS raw.results",
    # 2026-10-02: the fixture list's score after extra time (data-layers step 14).
    "ALTER TABLE raw.world_fixtures ADD COLUMN IF NOT EXISTS home_extra_goals INTEGER",
    "ALTER TABLE raw.world_fixtures ADD COLUMN IF NOT EXISTS away_extra_goals INTEGER",
    # 2026-10-02: the event player's side, always extracted (data-layers step 14b).
    "ALTER TABLE raw.match_events ADD COLUMN IF NOT EXISTS side VARCHAR",
]


def _ddl_for(table):
    """The DDL statement that creates `table`."""
    return next(stmt for stmt in DDL if f"CREATE TABLE IF NOT EXISTS {table} (" in stmt)


def _migrate(con):
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


# The game's codes, named, and the value model's coefficients: seeds/<file> -> raw.<table>, replaced on every load and
# --refresh-only, so naming a code reaches a store with no re-extract. fmstats/mart.py
# renders mart.roles and mart.training_attributes from the same files.
CODE_SEEDS = (("roles", "roles.csv", "id INTEGER, name VARCHAR, inferred BOOLEAN"),
              ("training_attributes", "training_attributes.csv",
               "code INTEGER, abbrev VARCHAR"),
              ("positions", "positions.csv",
               "code VARCHAR, unit VARCHAR, display_order INTEGER"),
              ("value_model", "value_model.csv", "term VARCHAR, coefficient DOUBLE"))


def seed_codes(con):
    """(Re)seed raw.roles, raw.training_attributes, raw.positions and raw.value_model from
    seeds/."""
    seeds = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seeds")
    for table, name, cols in CODE_SEEDS:
        types = ", ".join(f"'{c.split()[0]}': '{c.split()[1]}'" for c in cols.split(", "))
        con.execute(f"CREATE OR REPLACE TABLE raw.{table} AS SELECT * FROM "
                    f"read_csv(?, header = true, columns = {{{types}}})",
                    [os.path.join(seeds, name)])


def store_career(con):
    """The career key the store records (raw.app_config `career_key`), or None."""
    try:
        row = con.execute("SELECT value FROM raw.app_config "
                          "WHERE key = 'career_key'").fetchone()
    except duckdb.CatalogException:
        return None
    return row[0] if row else None


def seed_career(con, key=None):
    """Record which career this store holds in raw.app_config: `career_key`,
    `career_rating_method`, `career_managed_tid`, the club we manage, and
    `career_rollover`, the day ('MM-DD') its new season starts.

    fmstats reads the store, never fmparser, so the loader, which may read both, writes down
    the career facts the mart needs: the tactic we play (the save does not carry it) and our
    club (mart.our_clubs is it plus its reserve side). `key` is the career being loaded;
    without one (a --refresh-only) the store's own recorded key is kept. Runs before
    the models (stg.career reads these keys) and create_mart."""
    if key is None:
        key = store_career(con)
    car = careers.CAREERS.get(key) if key else None
    if car is None:
        print(f"  ! career {key!r} is not a registered career (careers.py); "
              f"career keys left unset")
        return
    for k, v in (("career_key", car.key), ("career_rating_method", car.rating_method),
                 ("career_managed_tid", str(car.managed_tid)),
                 ("career_rollover", "{:02d}-{:02d}".format(*car.rollover))):
        con.execute("DELETE FROM raw.app_config WHERE key = ?", [k])
        if v is not None:
            con.execute("INSERT INTO raw.app_config VALUES (?, ?)", [k, v])


def seed_config_bundle(con):
    """Apply a committed config bundle (seeds/config_bundle.json) as the baked default —
    the same shape the dashboard exports (db.export_config_bundle). Runs AFTER
    seed_role_weights/seed_reference so it wins for overlapping methods.
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
    them. The attribute coefficients are seeded first: int.player_attribute_estimates is generated
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
    if not select:
        _drop_unbuilt(con, res.result)
    return built


MODEL_SCHEMAS = ("stg", "int", "site")


def _drop_unbuilt(con, results):
    """Drop the views in the model schemas, and the dim_ / fact_ tables in mart, that the
    project no longer defines (a renamed or removed model), so a store refreshed across a
    rename holds only what dbt built."""
    built = {(r.node.schema, r.node.alias) for r in results
             if r.node.resource_type == "model"}
    for schema, name in con.execute(
            "SELECT schema_name, view_name FROM duckdb_views() WHERE NOT internal "
            "AND database_name = current_database() AND schema_name IN "
            f"{MODEL_SCHEMAS}").fetchall():
        if (schema, name) not in built:
            con.execute(f'DROP VIEW "{schema}"."{name}"')
    # dbt's mart tables and consumer views share the schema with fmstats/mart.py's views; only
    # the dim_ / fact_ / mart_ names (and the retired unprefixed consumer views) are dbt's.
    for (name,) in con.execute(
            "SELECT view_name FROM duckdb_views() WHERE database_name = current_database() "
            "AND schema_name = 'mart' "
            "AND (regexp_matches(view_name, '^mart_') "
            "     OR view_name IN ('standings', 'tie_results', 'squad_membership'))").fetchall():
        if ("mart", name) not in built:
            con.execute(f'DROP VIEW mart."{name}"')
    for (name,) in con.execute(
            "SELECT table_name FROM duckdb_tables() WHERE database_name = current_database() "
            "AND schema_name = 'mart' "
            "AND regexp_matches(table_name, '^(dim|fact|mart)_')").fetchall():
        if ("mart", name) not in built:
            con.execute(f'DROP TABLE mart."{name}"')


def report_persons(con):
    n, t = con.execute("SELECT COUNT(*), COUNT(DISTINCT tid) FROM int.persons").fetchone()
    if n > t:
        print(f"  identity bridge: {n} persons across {t} tids "
              f"({n - t} recycled slot(s) — see docs/IDS.md)")


def reset_schema(con):
    con.execute("DROP SCHEMA IF EXISTS raw CASCADE")
    con.execute("DROP SCHEMA IF EXISTS staging CASCADE")
    con.execute("DROP SCHEMA IF EXISTS history CASCADE")
    con.execute("DROP SCHEMA IF EXISTS int CASCADE")
    con.execute("DROP SCHEMA IF EXISTS stg CASCADE")
    con.execute("DROP SCHEMA IF EXISTS site CASCADE")
    con.execute("DROP SCHEMA IF EXISTS mart CASCADE")
    for name in RETIRED_VIEWS:
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
    ap.add_argument("--career", help="the career these saves belong to (careers.py): "
                    "places each snapshot in its campaign and checks its matches against "
                    "the fixture list (default: the career the store records)")
    ap.add_argument("--season", type=int)
    ap.add_argument("--phase", help="snapshot phase; normally the in-game date "
                    "'YYYY-MM-DD' (the save's header date, from summary.json — rarely "
                    "needed). "
                    "Legacy words start/mid/end still accepted.")
    ap.add_argument("--reset", action="store_true",
                    help="drop and recreate the raw schema + views first")
    ap.add_argument("--skip-views", action="store_true",
                    help="load raw tables only; skip dbt build, mart views, and person reporting")
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
            seed_codes(con)
            seed_career(con, args.career)
            built = create_views(con)
            report_persons(con)
            print(f"{args.db}: role-weight seeds + {len(built)} models rebuilt (nothing loaded)")
        finally:
            con.close()
        return

    dirs = discover_labels(args.path) if args.all else [args.path.rstrip("/")]
    if not dirs:
        raise SystemExit(f"no labels found under {args.path}")

    # collision pre-flight: two on-disk labels -> the same save date, so the same snapshot
    if args.all:
        seen = {}
        for d in dirs:
            if save_date(d):
                seen.setdefault(save_date(d), []).append(os.path.basename(os.path.normpath(d)))
        for date, labels in seen.items():
            if len(labels) > 1:
                print(f"! WARNING: labels {labels} are all saves of {date}; loaded in "
                      f"order, last wins ({labels[-1]}).")

    con = duckdb.connect(args.db)
    try:
        recorded = store_career(con)
        if args.career and recorded and args.career != recorded:
            raise SystemExit(f"{args.db} holds the {recorded!r} career, not {args.career!r}")
        key = args.career or recorded
        if key is None:
            raise SystemExit(f"{args.db} records no career: pass --career "
                             f"({', '.join(sorted(careers.CAREERS))})")
        career = careers.resolve_career(key)
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
                load_label(con, d, include, career, (args.season, args.phase))
                ok += 1
            except Exception as e:  # one bad label must not abort a batch
                fail += 1
                print(f"  ! FAILED {os.path.basename(os.path.normpath(d))}: {e}")
        seed_event_types(con)
        seed_codes(con)
        seed_career(con, career.key)
        if not args.skip_views:
            built = create_views(con)
            report_persons(con)
            print(f"done: {ok} loaded, {fail} failed. {len(built)} models rebuilt.")
        else:
            print(f"done: {ok} loaded, {fail} failed (raw only; views skipped).")
    finally:
        con.close()


if __name__ == "__main__":
    main()
