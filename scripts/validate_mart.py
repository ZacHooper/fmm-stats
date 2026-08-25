#!/usr/bin/env python3
"""Build the `mart` layer against a store and assert its invariants + ground truth.

Runs against either a local store or the published R2 copy (`--r2`). The R2 copy is
ATTACHed READ_ONLY and the mart objects are built in the local in-memory database on top
of it, so nothing is written to the published file.

    uv run python scripts/validate_mart.py --r2
    uv run python scripts/validate_mart.py --db fm-frem.duckdb

Checks, in order:
  1. Spell invariant — spells of the SAME type must not overlap for one person; spells of
     DIFFERENT types may (injured while out on loan).
  2. Ring-buffer dedup — the latest phase per season really is a superset.
  3. Loan-in ground truth — the derived spells must match the 9 known loan-ins, including
     that a pre-season snapshot carries ZERO loan-ins forward.
  4. Arrival windows — the three known winter arrivals must read winter, everyone else
     summer.
  5. Season totals — mart.player_seasons must reproduce the 2024 review numbers.
  6. Growth — totals, comparability flags, and the tenure/season rollups.
  7. Regression guards — the four bugs found in the 2026-08 site-refactor audit, each of
     which returned plausible-looking numbers while silently deleting real football.
  8. Site-facing objects — grain, percentile range, the as-at club->league pin, match
     mirroring, and a structural immersion check over information_schema.
"""
from __future__ import annotations

import argparse
import os
import sys

import duckdb

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fmparser.mart import create_mart  # noqa: E402

R2_KEY = "s3://fmm-stats/site-data/fm-frem.duckdb"

FAILURES: list[str] = []


def check(label, ok, detail=""):
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(label)


def connect(args):
    con = duckdb.connect()
    if args.r2:
        con.execute("LOAD httpfs")
        con.execute(
            f"""CREATE SECRET r2 (TYPE s3, KEY_ID '{os.environ["R2_ACCESS_KEY"]}',
                SECRET '{os.environ["R2_SECRET_ACCESS_KEY"]}',
                ENDPOINT '{os.environ["R2_ACCOUNT_ID"]}.r2.cloudflarestorage.com',
                URL_STYLE 'path', REGION 'auto')"""
        )
        con.execute(f"ATTACH '{R2_KEY}' AS fm (READ_ONLY)")
        return con, "fm.staging"
    con.execute(f"ATTACH '{args.db}' AS fm (READ_ONLY)")
    return con, "fm.staging"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--r2", action="store_true", help="validate against the published R2 copy")
    ap.add_argument("--db", default="fm-frem.duckdb")
    args = ap.parse_args()

    con, src = connect(args)
    created = create_mart(con, src=src)
    print(f"built {len(created)} mart objects on {src}\n")

    # -- 1. spell overlap invariant -----------------------------------------------
    print("1. spell invariants")
    same_type_overlap = con.execute("""
        WITH s AS (SELECT *, ROW_NUMBER() OVER () AS rid FROM mart.player_spells
                   WHERE person_id IS NOT NULL)
        SELECT COUNT(*) FROM s a JOIN s b
            ON a.person_id = b.person_id AND a.spell_type = b.spell_type
           AND a.rid < b.rid
           AND a.valid_from <= COALESCE(b.valid_to, DATE '9999-12-31')
           AND COALESCE(a.valid_to, DATE '9999-12-31') >= b.valid_from
    """).fetchone()[0]
    check("no same-type overlaps", same_type_overlap == 0, f"{same_type_overlap} overlapping pairs")

    cross = con.execute("""
        SELECT COUNT(*) FROM mart.player_spells a JOIN mart.player_spells b
          ON a.person_id = b.person_id AND a.spell_type <> b.spell_type
         AND a.valid_from <= COALESCE(b.valid_to, DATE '9999-12-31')
         AND COALESCE(a.valid_to, DATE '9999-12-31') >= b.valid_from
        WHERE a.spell_type = 'injured' AND b.spell_type = 'loan_out'
    """).fetchone()[0]
    check("cross-type overlap is permitted (injured while on loan)", cross > 0,
          f"{cross} injured/loan_out overlaps found")

    bad_range = con.execute("""
        SELECT COUNT(*) FROM mart.player_spells
        WHERE valid_to IS NOT NULL AND valid_to < valid_from
    """).fetchone()[0]
    check("no inverted date ranges", bad_range == 0, f"{bad_range} inverted")

    # -- 2. ring buffer ------------------------------------------------------------
    print("\n2. ring-buffer dedup")
    missed = con.execute(f"""
        WITH allm AS (
          SELECT season, date, home_tid, away_tid FROM {src}.matches
          WHERE home_tid IN (SELECT club_tid FROM mart.our_clubs)
             OR away_tid IN (SELECT club_tid FROM mart.our_clubs)),
        u AS (SELECT DISTINCT season, date, home_tid, away_tid FROM allm),
        kept AS (SELECT DISTINCT season, date, home_tid, away_tid FROM mart.matches
                 WHERE home_tid IN (SELECT club_tid FROM mart.our_clubs)
                    OR away_tid IN (SELECT club_tid FROM mart.our_clubs))
        SELECT COUNT(*) FROM (SELECT * FROM u EXCEPT SELECT * FROM kept)
    """).fetchone()[0]
    check("latest phase is a superset of all earlier phases", missed == 0,
          f"{missed} matches would be lost")

    # -- 3. loan-in ground truth ---------------------------------------------------
    print("\n3. loan-in spells vs ground truth")
    truth = {
        "Emil Hojlund": [2022], "Marcelo Randolf": [2022], "Daniel Bisgaard Haarbo": [2022],
        "Ernest Nuamah": [2022, 2023], "Jeppe Erenbjerg": [2023], "Nicklas Strunck": [2023],
        "Marc Nielsen": [2023, 2024], "Jeppe Corfitzen": [2023, 2024],
        "Jonas Jensen-Abbew": [2024],
    }
    got = con.execute("""
        SELECT name, LIST(DISTINCT season ORDER BY season) AS seasons
        FROM mart.loan_in_spells GROUP BY name ORDER BY name
    """).df()
    got_map = {r["name"]: sorted(r["seasons"]) for _, r in got.iterrows()}
    norm = lambda s: s.replace("ø", "o").replace("æ", "ae").replace("å", "a")
    got_norm = {norm(k): v for k, v in got_map.items()}
    for nm, seasons in truth.items():
        actual = got_norm.get(nm)
        check(f"{nm}: {seasons}", actual == seasons, f"got {actual}")
    check("no loan-in spells derived for 2025 (pre-season: all prior loans expired)",
          not any(2025 in v for v in got_map.values()),
          str({k: v for k, v in got_map.items() if 2025 in v}))
    check("exactly 9 distinct loan-in players", len(got_map) == 9, f"got {len(got_map)}")

    # loaned_in is SET-ONLY (never cleared in the save), so a loan-in's raw club_tid run
    # never ends on its own — at_club_spells must not let that leak through as open-ended
    # squad membership once the loan has lapsed (the actual bug this fixed: all 9 read as
    # permanent Frem players, ad infinitum, in mart.squad_on() before this check existed).
    still_open = con.execute("""
        SELECT s.name FROM mart.at_club_spells s
        JOIN mart.club_runs cr ON cr.tid = s.tid AND cr.person_id = s.person_id
                               AND cr.club_tid = s.club_tid AND cr.ever_loaned_in
        WHERE s.club_tid IN (SELECT club_tid FROM mart.our_clubs)
    """).fetchall()
    check("no loan-in ghosts in at_club_spells (loan presence comes from loan_in_spells only)",
          len(still_open) == 0, f"{[r[0] for r in still_open]}")

    # The day AFTER the season ends, not the latest phase itself: a loan's valid_to is 30
    # June, so a handful of these 9 (whoever's last evidenced season ran right up to the
    # snapshot date) are legitimately still "on loan" ON 2024-06-30 — that's correct, not a
    # ghost. 1 July is the first date no prior-season loan can still cover, so it isolates
    # true ghosting from a same-day boundary artifact.
    day_after = con.execute(
        "SELECT MAX(season_end(season)) + INTERVAL 1 DAY FROM mart.loan_in_spells").fetchone()[0]
    squad_ghosts = con.execute(f"""
        SELECT name FROM mart.squad_on('{day_after}')
        WHERE name IN {tuple(truth.keys())}
    """).fetchall()
    check(f"squad_on('{day_after}') carries none of the 9 known loan-ins forward "
          f"(none re-evidenced for the new season yet)", len(squad_ghosts) == 0,
          f"{[r[0] for r in squad_ghosts]}")

    # -- 4. arrival windows --------------------------------------------------------
    print("\n4. arrival windows")
    winter_truth = {"Marc Nielsen": 2023, "Anosike Ementa": 2024, "Lauge Sandgrav": 2024}
    win = con.execute("""
        SELECT name, season, arrival_window FROM mart.at_club_spells
        WHERE arrival_window IS NOT NULL
          AND club_tid IN (SELECT club_tid FROM mart.our_clubs)
    """).df()
    win_map = {(norm(r["name"]), int(r["season"])): r["arrival_window"] for _, r in win.iterrows()}
    for nm, sn in winter_truth.items():
        # Marc Nielsen arrives as a loan-in; check whichever spell type carries him.
        got_w = win_map.get((norm(nm), sn))
        if got_w is None:
            lw = con.execute(
                "SELECT arrival_window FROM mart.loan_in_spells WHERE name = ? AND season = ?",
                [nm, sn]).fetchall()
            got_w = lw[0][0] if lw else None
        check(f"{nm} ({sn}) = winter", got_w == "winter", f"got {got_w}")

    summer_truth = [("Anton Pedersen", 2024), ("Frederik Ellegaard", 2024),
                    ("Rasmus Moller", 2024), ("Adam Jakobsen", 2024)]
    for nm, sn in summer_truth:
        got_w = win_map.get((norm(nm), sn))
        check(f"{nm} ({sn}) = summer", got_w == "summer", f"got {got_w}")

    # -- 5. season totals ----------------------------------------------------------
    print("\n5. mart.player_seasons reproduces the 2024 review")
    # Team goals-for (73) and sum-of-player-goals (70) are DIFFERENT metrics, not a
    # discrepancy: match_events records exactly 3 own_goal events in 2024, and an
    # opposition own goal counts to our score without being attributed to any of our
    # players. Assert both so a future change to either can't silently conflate them.
    team_gf = con.execute("""
        SELECT SUM(CASE WHEN home_tid IN (SELECT club_tid FROM mart.our_clubs)
                        THEN score_home ELSE score_away END)
        FROM mart.matches
        WHERE season = 2024 AND competition = 'NordicBet Liga'
          AND (home_tid IN (SELECT club_tid FROM mart.our_clubs)
            OR away_tid IN (SELECT club_tid FROM mart.our_clubs))
    """).fetchone()[0]
    check("2024 league goals-for = 73 (team score)", team_gf == 73, f"got {team_gf}")

    player_goals = con.execute("""
        SELECT SUM(goals) FROM mart.player_seasons
        WHERE season = 2024 AND competition = 'NordicBet Liga'
          AND team_tid IN (SELECT club_tid FROM mart.our_clubs)
    """).fetchone()[0]
    check("2024 league player-attributed goals = 70 (= 73 less 3 own goals)",
          player_goals == 70, f"got {player_goals}")

    top = con.execute("""
        SELECT any_value(s.name) AS name, SUM(ps.goals) AS goals
        FROM mart.player_seasons ps
        JOIN (SELECT DISTINCT person_id, name FROM mart.player_spells) s USING (person_id)
        WHERE ps.season = 2024
          AND ps.team_tid IN (SELECT club_tid FROM mart.our_clubs)
        GROUP BY ps.person_id ORDER BY goals DESC LIMIT 1
    """).fetchone()
    # 30, not 34 — mart.player_seasons now excludes friendlies (is_competitive), and
    # Jakobsen scored 4 of his 34 total goals in friendlies in 2024.
    check("2024 golden boot = Adam Jakobsen, 30 (competitive only)",
          top[0] == "Adam Jakobsen" and top[1] == 30, f"got {top}")

    # -- 5b. first team vs reserves ---------------------------------------------------
    # our_clubs holds both sides. Filtering results on it folds the reserve fixtures into
    # the first team's, which is how a season review silently reports 58 games instead of
    # 38 — caught by running the rewritten fm-season-review template.
    print("\n5b. managed club vs reserves")
    split = con.execute("""
        SELECT
          (SELECT COUNT(*) FROM mart.matches
            WHERE season = 2024
              AND (home_tid IN (SELECT club_tid FROM mart.managed_club)
                OR away_tid IN (SELECT club_tid FROM mart.managed_club))) AS first_team,
          (SELECT COUNT(*) FROM mart.matches
            WHERE season = 2024
              AND (home_tid IN (SELECT club_tid FROM mart.our_clubs)
                OR away_tid IN (SELECT club_tid FROM mart.our_clubs)))    AS both
    """).fetchone()
    check("managed_club isolates the first team's 38 games", split[0] == 38,
          f"first team {split[0]}, both sides {split[1]}")
    check("our_clubs really does include more (the reserve fixtures)", split[1] == 58,
          f"got {split[1]}")
    check("managed_club resolves to exactly one club",
          con.execute("SELECT COUNT(*) FROM mart.managed_club").fetchone()[0] == 1)
    check("reserve_clubs is the complement",
          con.execute("SELECT COUNT(*) FROM mart.reserve_clubs").fetchone()[0] == 1)

    # -- 6. growth ------------------------------------------------------------------
    print("\n6. growth")
    # Garly's trajectory is the reference: 176 at his old club (estimated), 175-176 flat
    # through 2023, a +24 step at 2023-06-26, then +6 and +5 across 2024 to 211.
    g = con.execute("""
        SELECT phase, attr_total, delta, delta_comparable
        FROM mart.player_growth WHERE name = 'Andreas Garly' ORDER BY snap_ix
    """).df()
    check("Garly ends on 211", int(g.iloc[-1]["attr_total"]) == 211,
          f'got {g.iloc[-1]["attr_total"]}')
    check("Garly 2024 growth = +11", int(
        g[g.phase == "2024-06-03"].iloc[0]["attr_total"]
        - g[g.phase == "2023-07-02"].iloc[0]["attr_total"]) == 11)
    check("the estimated->real step is marked not-comparable",
          not bool(g[g.phase == "2022-03-19"].iloc[0]["delta_comparable"]),
          "the -1 when he joined us is an artifact, not a decline")

    # Each role sums the 18 attributes its role uses — outfielders drop the keeper block,
    # keepers drop the outfield-only block. Neither uses all 23.
    role = con.execute("""
        SELECT is_gk,
               BOOL_AND(attr_total = outfield_total) AS uses_outfield_set,
               BOOL_AND(attr_total = gk_total)       AS uses_gk_set
        FROM mart.player_growth
        WHERE season = 2024 AND phase = '2024-06-03'
          AND club_tid IN (SELECT club_tid FROM mart.our_clubs)
        GROUP BY is_gk ORDER BY is_gk
    """).df()
    check("outfielders' total drops the keeper block",
          bool(role[role.is_gk == 0].iloc[0]["uses_outfield_set"]))
    check("keepers' total counts all 23",
          bool(role[role.is_gk == 1].iloc[0]["uses_gk_set"]))

    # The vestigial blocks must be measurably inert for the role that doesn't use them,
    # which is the evidence the split rests on.
    inert = con.execute("""
        SELECT
          AVG(CASE WHEN is_gk = 0 THEN gk_block_total END) AS outfield_gk_block,
          AVG(CASE WHEN is_gk = 1 THEN gk_block_total END) AS keeper_gk_block
        FROM mart.player_growth
        WHERE season = 2024 AND phase = '2024-06-03' AND NOT is_estimated
          AND club_tid IN (SELECT club_tid FROM mart.our_clubs)
    """).fetchone()
    # 5 attributes: an inert block sums to well under 10, a live one to ~50+.
    check("keeper block is inert for outfielders, live for keepers",
          inert[0] < 10 and inert[1] > 40,
          f"outfield sum {inert[0]:.1f} vs keeper sum {inert[1]:.1f}")

    # Growth over a club spell must exceed the single-season figure for a long server.
    garly = con.execute("""
        SELECT growth, days_at_club, growth_comparable, age_on_arrival, age_now
        FROM mart.player_growth_at_club
        WHERE name = 'Andreas Garly'
          AND club_tid IN (SELECT club_tid FROM mart.our_clubs)
        ORDER BY days_at_club DESC LIMIT 1
    """).fetchone()
    check("Garly growth since joining = +36 (vs +11 in 2024 alone)", garly[0] == 36,
          f"got {garly[0]} over {garly[1]} days")
    check("that span is comparable end to end", bool(garly[2]))

    # Tenure must merge first-team/reserve stints into one row per player. Splitting on
    # club_tid gives Moller-Jensen four rows, none of them his real growth here.
    frag = con.execute("""
        SELECT COUNT(*) FROM (
          SELECT person_id FROM mart.player_growth_tenure t
          WHERE EXISTS (SELECT 1 FROM mart.squad_on('2024-06-30') s
                        WHERE s.person_id = t.person_id)
          GROUP BY person_id HAVING COUNT(*) > 1)
    """).fetchone()[0]
    check("tenure gives one row per current-squad player", frag == 0,
          f"{frag} players still fragmented")
    mj = con.execute("""
        SELECT growth FROM mart.player_growth_tenure WHERE name = 'Oliver Møller-Jensen'
        ORDER BY days_at_club DESC LIMIT 1
    """).fetchone()
    check("Møller-Jensen's tenure growth = +33 (4 fragments merged)", mj[0] == 33,
          f"got {mj[0]}")

    # Every player outside our squad is on model estimates, so growth must be filterable.
    est = con.execute("""
        SELECT
          COUNT(*) FILTER (WHERE is_estimated)     AS estimated,
          COUNT(*) FILTER (WHERE NOT is_estimated) AS real
        FROM mart.player_growth WHERE season = 2024 AND phase = '2024-06-03'
    """).fetchone()
    check("outside players are flagged as estimated", est[0] > 20000, f"{est[0]} estimated")
    check("our squad reads as real", est[1] >= 30, f"{est[1]} real")

    # The season rollup must agree with the per-snapshot view.
    agree = con.execute("""
        SELECT COUNT(*) FROM mart.player_growth_season s
        WHERE s.season = 2024
          AND s.growth <> (SELECT MAX(attr_total) - MIN(attr_total) FROM (
                SELECT attr_total FROM mart.player_growth g
                WHERE g.person_id = s.person_id AND g.season = 2024
                  AND g.snap_ix IN (
                    (SELECT MIN(snap_ix) FROM mart.player_growth WHERE person_id = s.person_id AND season = 2024),
                    (SELECT MAX(snap_ix) FROM mart.player_growth WHERE person_id = s.person_id AND season = 2024))))
          AND s.growth >= 0
    """).fetchone()[0]
    check("season rollup agrees with per-snapshot totals", agree == 0, f"{agree} disagreements")

    # -- 7. regression guards for the bugs found in the 2026-08 site-refactor audit ----
    # Each of these shipped once. They are cheap to assert and expensive to rediscover:
    # every one of them looked like a working query returning plausible numbers.
    print("\n7. regression guards")

    # is_gk_attr once rendered from GK_ATTRS (all 23) instead of GK_BLOCK (the 5 keeper
    # attributes), so the predicate was universally true and the filter we DOCUMENT for
    # agents — NOT (is_gk_attr AND NOT is_gk) — silently discarded every outfielder.
    gk = con.execute("""
        SELECT COUNT(DISTINCT attribute) FILTER (WHERE is_gk_attr),
               COUNT(DISTINCT attribute) FILTER (WHERE NOT is_gk_attr)
        FROM mart.player_attribute_growth
    """).fetchone()
    check("is_gk_attr marks exactly the 5 keeper attributes", gk == (5, 18),
          f"{gk[0]} gk / {gk[1]} outfield")
    kept = con.execute("""
        SELECT COUNT(*) FROM mart.player_attribute_growth g
        JOIN mart.player_growth pg USING (person_id, season, phase)
        WHERE NOT (g.is_gk_attr AND NOT pg.is_gk) AND pg.is_gk = 0
    """).fetchone()[0]
    check("the documented is_gk_attr filter keeps outfielder rows", kept > 0,
          f"{kept} outfielder rows survive the filter")

    # player_seasons dropped rows with a NULL person_id, and person_slices only covers tids
    # that appear in staging.players — so 42 of OUR tids with match rows but no roster row
    # were deleted, taking 25 of our 2024 goals (22% of the season) with them. It also
    # any_value()'d team_tid while callers filtered on it. Assert exact parity against the
    # fact table, for EVERY season: any future regression of either kind shows up here.
    # Both sides filter to competitive matches — player_seasons excludes friendlies now, so
    # the fact-table side has to match that scope or every season would show phantom drift.
    drift = con.execute("""
        WITH ps AS (
            SELECT season, SUM(apps) AS apps, SUM(goals) AS goals
            FROM mart.player_seasons
            WHERE team_tid IN (SELECT club_tid FROM mart.our_clubs)
            GROUP BY season),
        f AS (
            SELECT season, COUNT(*) FILTER (WHERE appeared) AS apps, SUM(goals) AS goals
            FROM mart.match_player_facts
            WHERE team_tid IN (SELECT club_tid FROM mart.our_clubs) AND is_competitive
            GROUP BY season)
        SELECT f.season, f.apps, ps.apps, f.goals, ps.goals
        FROM f LEFT JOIN ps USING (season)
        WHERE f.apps IS DISTINCT FROM ps.apps OR f.goals IS DISTINCT FROM ps.goals
    """).fetchall()
    check("player_seasons reproduces match_player_facts exactly, every season (competitive)",
          not drift, f"{len(drift)} season(s) drift: {drift}" if drift else "0 drift")

    # squad_on had a ghost and a hole at once, which is why the HEADCOUNT looked right:
    #   ghost — club_runs filters NOT is_staff, so a player who retires into the coaching
    #           staff stops producing runs, LEAD() is NULL, and his spell never closes.
    #   hole  — a run first seen in late June belongs to the NEXT season, so the inferred
    #           season_start landed one day AFTER the snapshot that observed him.
    # Compare the SETS, not the counts.
    season, phase = con.execute("""
        SELECT season, phase FROM mart.snapshots ORDER BY snap_ix DESC LIMIT 1
    """).fetchone()
    sym = con.execute(f"""
        WITH roster AS (
            SELECT tid FROM {src}.players
            WHERE season = ? AND phase = ? AND NOT is_staff
              AND club_tid IN (SELECT club_tid FROM mart.our_clubs)),
        spells AS (SELECT DISTINCT tid FROM mart.squad_on(?))
        SELECT
            (SELECT COUNT(*) FROM spells WHERE tid NOT IN (SELECT tid FROM roster)),
            (SELECT COUNT(*) FROM roster WHERE tid NOT IN (SELECT tid FROM spells))
    """, [season, phase, phase]).fetchone()
    check(f"squad_on('{phase}') matches the roster set exactly", sym == (0, 0),
          f"{sym[0]} ghost(s), {sym[1]} missing")

    # A spell may only claim valid_to IS NULL — "still here" — if the newest snapshot really
    # does still show him there. Stated against the roster rather than against club_runs.to_ix
    # on purpose: a player can have several runs at one club (left and came back), so joining
    # spells to runs on (tid, person_id, club_tid) fans out and matches an earlier run's end
    # against a later run's open spell. The roster is unambiguous.
    stale = con.execute(f"""
        SELECT COUNT(*) FROM mart.at_club_spells s
        WHERE s.valid_to IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM {src}.players p, mart.snapshots n
              WHERE n.snap_ix = (SELECT MAX(snap_ix) FROM mart.snapshots)
                AND (p.season, p.phase) = (n.season, n.phase)
                AND p.tid = s.tid AND p.club_tid = s.club_tid AND NOT p.is_staff)
    """).fetchone()[0]
    check("every open-ended spell is still on the newest snapshot's roster",
          stale == 0, f"{stale} stale-open spell(s)")

    # -- 8. the dimension / level / match objects the site is built on -----------------
    # These replaced hand-rolled SQL in scripts/export_data.py and dashboard/db.py. Each was
    # verified row-for-row against the code it replaced at the time (see the commit), but that
    # code is gone now, so what is asserted here are the invariants that survive it.
    print("\n8. site-facing objects")

    # Grain. A duplicate here silently multiplies whatever joins to it.
    for obj, key in [("club_leagues", "season, phase, club_tid"),
                     ("clubs", "season, phase, club_tid"),
                     ("leagues", "season, phase, cid"),
                     ("player_snapshots", "season, phase, tid"),
                     ("player_position_levels", "season, phase, tid, position"),
                     ("player_origin", "season, phase, tid"),
                     ("club_matches", "season, phase, anchor, club_tid")]:
        dup = con.execute(f"""
            SELECT COUNT(*) FROM (SELECT {key} FROM mart.{obj}
                                  GROUP BY {key} HAVING COUNT(*) > 1)
        """).fetchone()[0]
        check(f"mart.{obj} is unique on ({key})", dup == 0, f"{dup} duplicate key(s)")

    # THE as-at regression pin. Two of the five club->league CTEs this object replaced left
    # off the `ord <=` bound, so every historical snapshot resolved a club to the division it
    # ENDED UP in. Frem climbed 3.Division -> 2.Division -> NordicBet -> Superliga across this
    # store, so if the bound is ever dropped again our own league stops varying by season.
    ladder = con.execute("""
        SELECT DISTINCT s.season, cl.league_cid
        FROM mart.club_leagues cl JOIN mart.snapshots s USING (season, phase)
        WHERE cl.club_tid IN (SELECT club_tid FROM mart.managed_club)
        ORDER BY s.season
    """).fetchall()
    cids = [c for _s, c in ladder]
    check("our own division is resolved AS AT each snapshot, not store-wide",
          len(set(cids)) > 1, f"{len(set(cids))} distinct division(s) across seasons: {ladder}")

    # Levels are percentiles, so they must be in range and total. A NULL here means a player
    # with no ability got ranked; a value outside [0,100] means the window is wrong.
    bad = con.execute("""
        SELECT COUNT(*) FROM mart.player_position_levels
        WHERE level_global IS NULL OR level_global NOT BETWEEN 0 AND 100
           OR level_league IS NULL OR level_league NOT BETWEEN 0 AND 100
    """).fetchone()[0]
    check("every level_* percentile is present and in [0, 100]", bad == 0, f"{bad} bad row(s)")

    # IMMERSION, enforced structurally rather than by remembering to write EXCLUDE (ca).
    leak = con.execute("""
        SELECT list(table_name || '.' || column_name)
        FROM information_schema.columns
        WHERE table_schema = 'mart'
          AND LOWER(column_name) IN ('ca','pa','aca','current_ability','potential_ability')
    """).fetchone()[0]
    check("no raw-ability column anywhere in the mart", not leak, str(leak))

    # club_matches is mart.matches seen from each side; the two views of one match must mirror.
    mirror = con.execute("""
        SELECT COUNT(*) FROM mart.club_matches a
        JOIN mart.club_matches b USING (season, phase, anchor)
        WHERE a.club_tid < b.club_tid
          AND (a.gf IS DISTINCT FROM b.ga OR a.ga IS DISTINCT FROM b.gf
               OR a.venue = b.venue
               OR a.opp_tid IS DISTINCT FROM b.club_tid)
    """).fetchone()[0]
    check("club_matches mirrors correctly between the two sides of a match",
          mirror == 0, f"{mirror} inconsistent pair(s)")
    pts = con.execute("""
        SELECT COUNT(*) FROM mart.club_matches
        WHERE pts IS DISTINCT FROM CASE result WHEN 'W' THEN 3 WHEN 'D' THEN 1 ELSE 0 END
           OR result IS DISTINCT FROM CASE WHEN gf > ga THEN 'W'
                                           WHEN gf = ga THEN 'D' ELSE 'L' END
    """).fetchone()[0]
    check("club_matches result/pts agree with the score", pts == 0, f"{pts} bad row(s)")

    # The fit layer is method-dependent and the level layer is not; they must still cover the
    # same (tid, position) set, or the join that rebuilds effective_table loses rows.
    S, P = con.execute("""SELECT season, phase FROM mart.snapshots
                          ORDER BY snap_ix DESC LIMIT 1""").fetchone()
    lv = con.execute("SELECT COUNT(*) FROM mart.player_position_levels "
                     "WHERE season=? AND phase=?", [S, P]).fetchone()[0]
    holes = []
    for (m,) in con.execute(f"SELECT DISTINCT method FROM {src}.role_weights ORDER BY 1").fetchall():
        n = con.execute("""SELECT COUNT(*) FROM mart.player_position_fit
                           WHERE season=? AND phase=? AND method=?""", [S, P, m]).fetchone()[0]
        if n != lv:
            holes.append((m, n))
    check(f"player_position_fit covers the level set for every method ({lv} rows)",
          not holes, f"{holes}" if holes else "all methods agree")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} CHECK(S) FAILED:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
