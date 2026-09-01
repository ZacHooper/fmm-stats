#!/usr/bin/env python3
"""The `mart` layer — the snapshot-shaped staging tables, restated as facts and spells.

`staging.*` mirrors the parser: one full row set per `(season, phase)` snapshot. That shape
is deliberate and worth keeping (it is what makes mid-season development trajectories
possible at all), but it forces four correctness rules onto every consumer:

  1. LATEST-PHASE-PER-SEASON. `match_player_stats` is a ring buffer, not a season log:
     every import re-scrapes whatever match history the save still holds, so later
     snapshots in a season are supersets of earlier ones. Summing across phases
     double-counts. Verified for this store: every 2024 phase starts at the same first
     match and the latest holds all 38.
  2. SNAPSHOT-SCOPED JOIN. `staging.players` is one row per SNAPSHOT, not per player. A
     bare `tid` join multiplies every fact row by the number of snapshots the player is in.
  3. PERSON IDENTITY. `tid` is a slot, not a person — FM recycles retired players' tids
     (1,908 recycled slots here). Any cross-snapshot per-player aggregate must key on
     `person_id`, not `tid`. See docs/IDS.md.
  4. APPEARANCE SEMANTICS. `pos_order <= 11` = started, `subOn <> 255` = appeared, and
     minutes need the 255-sentinel arithmetic on both ends.

Before this module those rules lived in prose (`site/AGENTS.md`), in a skill template, and
in ~10 copy-pasted CASE expressions across `load_duckdb.py`, `dashboard/db.py` and
`fmq.py`. Encoding them once here means every consumer — Streamlit, `fmq`, the JS site,
ad-hoc agent SQL over the published R2 copy — inherits them instead of re-deriving them.

The other half of the module is `mart.player_spells`, which replaces the state flags that
cannot be trusted. `staging.players.loaned_in` is SET-ONLY: nothing in the save clears it
when a loan lapses rather than being renewed, so it accumulates monotonically (0 -> 4 -> 7
-> 8 -> 9 across this store's 16 snapshots, never once decrementing). At the latest
snapshot 6 of the 9 flagged loan-ins last played for us in 2022 or 2023. The rows are not
stale — attributes keep updating — they are MISATTRIBUTED, so they look perfectly healthy
and silently pad the squad in every season.

A spell fixes that structurally: a loan that ended in 2022 simply does not overlap 2024, so
the ghosts cannot come back. Two domain rules from the manager make the derivation exact
rather than heuristic:

  * A LOAN LASTS AT MOST ONE SEASON and must then be re-loaned. So `valid_to` is never
    inferred — it is 30 June of the season the loan started. Only the OPENING needs
    evidence. This is also why a pre-season snapshot carries in ZERO loan-ins: every prior
    loan has, by rule, already expired.
  * TRANSFERS HAPPEN IN TWO WINDOWS, summer and winter, and the save stores no transfer
    date at all. See `_ARRIVAL_WINDOW_SQL` for how the window is inferred.

Deliberately NO confidence/uncertainty column. The rules above are stated as yes/no; if
they turn out to overfit, adjust the rule rather than hedge every row.

Spell overlap semantics:
  * ACROSS types, overlap is expected and required — a player can be injured *and* out on
    loan on the same date. `spell_type` is part of the grain, so this is free.
  * WITHIN one type, spells for one person must not overlap. `validate()` asserts this.
"""
from __future__ import annotations

from fmparser.attributes import ATTR_ORDER

# Which attributes are VESTIGIAL for which role. The UI swaps a block of attributes in and
# out by role; the engine still stores all 23 for everyone, but the ones the role does not
# use sit pinned in a 1-2 band and only jitter. Measured over our squad's REAL
# (non-estimated) rows, mean value by role:
#
#     attribute      outfield   GK        attribute      outfield   GK
#     Reflexes            1.5   12.8      Movement            8.3    1.3
#     Kicking             1.7   12.0      Tackling            8.5    1.6
#     Handling            1.5   11.1      Dribbling           7.5    2.2
#     Communication       1.0   10.2      Crossing            6.8    1.8
#     Throwing            1.5    7.6      Shooting            6.3    1.5
#
# Both blocks sit at 1.0-2.2 for the role that does not use them — the same inert band —
# so each role really uses 18 of the 23, not 23 and 18. Including a vestigial block in a
# growth total measures jitter: the keeper attributes change 68 times across outfielders'
# snapshots while never leaving the range 1-5.
#
# Passing is NOT vestigial for keepers even though the UI groups it with the technical
# block it swaps out: it averages 5.6 for our keepers against 8.2 for outfielders and
# reaches 13, well clear of the inert band Crossing (1.8) and Shooting (1.5) occupy. So
# the engine keeps a real passing value for a keeper and only the UI hides it. Aerial
# (12.7 vs 9.9) and Technique (7.0 vs 8.8) are likewise real for keepers.
#
# Given that, KEEPERS COUNT ALL 23 (manager's call, 2026-08). The outfield-only block adds
# roughly 8 points of near-constant value to a keeper's total, so it shifts the level but
# barely moves the delta, which is what growth reads. Known and accepted side effect: a
# young keeper can over-index slightly as "most improved" if that inert block drifts up.
# Outfielders still drop the keeper block, which is the asymmetry that actually matters —
# it is 5 attributes of pure jitter (they change 68 times across outfielders' snapshots
# without ever leaving the range 1-5).
GK_ONLY_ATTRS = ["Handling", "Kicking", "Reflexes", "Communication", "Throwing"]
OUTFIELD_ONLY_ATTRS = ["Crossing", "Dribbling", "Shooting", "Tackling", "Movement"]

OUTFIELD_ATTRS = [a for a in ATTR_ORDER if a not in GK_ONLY_ATTRS]
# NOT "the keeper attributes" — this is the keeper's TOTAL, which is all 23 (the manager's
# call: a keeper's outfield attributes still count toward his quality). Use it only for
# summing attr_total. If you want the five attributes only a keeper uses, that is GK_BLOCK
# below; reaching for GK_ATTRS there makes the predicate universally true, which is exactly
# the bug is_gk_attr shipped with.
GK_ATTRS = list(ATTR_ORDER)

# Kept for callers that want the raw blocks rather than the role-aware total.
GK_BLOCK = GK_ONLY_ATTRS


def _sum(attrs):
    return " + ".join(f'COALESCE(a."{a}", 0)' for a in attrs)


def _est_count(attrs):
    return " + ".join(f'CASE WHEN a."{a}_est" THEN 1 ELSE 0 END' for a in attrs)

# Every statement is formatted with {S} = the staging schema to read from. That is
# "staging" against a real store, and "fm.staging" when validating against a read-only
# ATTACHed copy (see scripts/validate_mart.py) — the mart objects are then built locally
# while the source stays untouched.

# Classic gaps-and-islands interval merge, applied per tid to a CTE named `raw`
# (person_id, tid, spell_start, spell_end). Spells that overlap or merely touch (<= 1 day
# apart) collapse into one; genuinely separate spells stay separate. Partitioned on tid
# rather than person_id because person_id can be NULL — a recycled tid's spells are years
# apart, so the gap test keeps them as distinct islands anyway.
_MERGE_SPELLS = """
    SELECT tid, any_value(person_id) AS person_id,
           MIN(spell_start) AS spell_start, MAX(spell_end) AS spell_end
    FROM (
        SELECT *, SUM(new_island) OVER (PARTITION BY tid ORDER BY spell_start,
                                        spell_end) AS island
        FROM (
            SELECT *, CASE WHEN prev_max_end IS NULL
                             OR spell_start > prev_max_end + INTERVAL 1 DAY
                           THEN 1 ELSE 0 END AS new_island
            FROM (
                SELECT raw.*, MAX(spell_end) OVER (
                           PARTITION BY tid ORDER BY spell_start, spell_end
                           ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                       ) AS prev_max_end
                FROM raw
            )
        )
    )
    GROUP BY tid, island
"""

MACROS = [
    # Orderable phase key. Date-phases ('YYYY-MM-DD') already sort correctly as strings;
    # the legacy words map to epoch sentinels so pre-existing stores keep their ordering.
    # This replaces the CASE expression copy-pasted ~10x across the codebase.
    """CREATE OR REPLACE MACRO phase_ord(p) AS
         CASE p WHEN 'start' THEN '0000-00-00' WHEN 'mid' THEN '0000-00-01'
                WHEN 'end'   THEN '0000-00-02' ELSE p END""",

    # Season of a calendar date. A campaign runs Jul Y-1 .. Jun Y and is named for its
    # END year (Aus-FY style), matching `staging.*.season`.
    """CREATE OR REPLACE MACRO season_of(d) AS
         CASE WHEN EXTRACT(MONTH FROM d) >= 7
              THEN EXTRACT(YEAR FROM d) + 1 ELSE EXTRACT(YEAR FROM d) END""",

    # Season boundaries. season_end is where loans expire, by the one-season rule.
    "CREATE OR REPLACE MACRO season_start(s) AS MAKE_DATE(CAST(s AS INT) - 1, 7, 1)",
    "CREATE OR REPLACE MACRO season_end(s)   AS MAKE_DATE(CAST(s AS INT), 6, 30)",

    # The summer/winter cut. Because a season is named for its end year, everything before
    # 1 Jan of that year is the autumn half (summer window) and everything on/after it is
    # the spring half (winter window). This needs no knowledge of the actual break dates —
    # which is the point: the competitive break MOVES (Nov 20 -> Feb 19, Nov 19 -> Feb 18,
    # Dec 3 -> Feb 18 across the three seasons here), so deriving it is fragile.
    "CREATE OR REPLACE MACRO winter_cut(s) AS MAKE_DATE(CAST(s AS INT), 1, 1)",
]


# --- foundation -------------------------------------------------------------------

SNAPSHOTS = """
CREATE OR REPLACE VIEW mart.snapshots AS
SELECT
    e.season,
    e.phase,
    e.label,
    phase_ord(e.phase)              AS phase_ord,
    TRY_CAST(e.phase AS DATE)       AS phase_date,
    e.latest_match,
    e.latest_match IS NULL          AS is_preseason,
    ROW_NUMBER() OVER (ORDER BY e.season, phase_ord(e.phase))   AS snap_ix,
    phase_ord(e.phase) = MAX(phase_ord(e.phase))
        OVER (PARTITION BY e.season)                            AS is_latest_in_season
FROM {S}.extracts e
"""

# Our club tids, derived from the data rather than from fmparser.careers, so the mart
# travels with the published store (where no career registry is available) and stays
# career-agnostic. `player_injuries` is scraped for the MANAGED SQUAD only, so the clubs
# its players belong to are exactly ours. The >= 3 floor guards against a single
# loaned-out player's row reading as his destination club.
OUR_CLUBS = """
CREATE OR REPLACE VIEW mart.our_clubs AS
SELECT p.club_tid
FROM {S}.player_injuries i
JOIN {S}.players p USING (season, phase, tid)
GROUP BY p.club_tid
HAVING COUNT(DISTINCT i.tid) >= 3
"""

# Our clubs split into the FIRST TEAM and the reserve side. `mart.our_clubs` holds both, which
# is right for squad membership (a player in the reserves is still ours) but wrong for results:
# a season review that filters on our_clubs silently folds 20 reserve fixtures into the first
# team's 38. The two are separable in the data because the reserve side's matches carry a NULL
# competition while the first team's are all in named competitions; squad size breaks the tie
# for a career whose save has no matches yet.
MANAGED_CLUB = """
CREATE OR REPLACE VIEW mart.managed_club AS
SELECT club_tid FROM (
    SELECT o.club_tid,
           COUNT(*) FILTER (WHERE m.competition IS NOT NULL) AS named_games,
           (SELECT COUNT(*) FROM {S}.players p
             WHERE p.club_tid = o.club_tid AND NOT p.is_staff)  AS player_rows
    FROM mart.our_clubs o
    LEFT JOIN mart.matches m
           ON m.home_tid = o.club_tid OR m.away_tid = o.club_tid
    GROUP BY o.club_tid
) ORDER BY named_games DESC, player_rows DESC LIMIT 1
"""

RESERVE_CLUBS = """
CREATE OR REPLACE VIEW mart.reserve_clubs AS
SELECT club_tid FROM mart.our_clubs
WHERE club_tid NOT IN (SELECT club_tid FROM mart.managed_club)
"""

# --- reference tables -------------------------------------------------------------
#
# These three are near-passthroughs, which normally would not earn a place here — the mart
# exists for the four snapshot-shape rules, and these tables are global, not snapshot-scoped,
# so there is no rule to apply. They are included for a functional reason instead: a rating is
# SUM(attribute x weight), so without the weight table and the position->role map the
# published artifact cannot answer "how good is he in this role" at all, and the familiarity
# curve is needed to discount it. scripts/publish_mart.py materialises mart.* and nothing else,
# so anything the artifact must be able to compute has to be reachable from this schema.
ROLE_WEIGHTS = """
CREATE OR REPLACE VIEW mart.role_weights AS
SELECT method, role, attribute, weight FROM {S}.role_weights
"""

POSITION_ROLES = """
CREATE OR REPLACE VIEW mart.position_roles AS
SELECT position, role FROM {S}.position_role_map
"""

APP_CONFIG = """
CREATE OR REPLACE VIEW mart.app_config AS
SELECT key, value FROM {S}.app_config
"""


# --- dimensions -------------------------------------------------------------------

# Club -> league, AS AT each snapshot. This one object replaces FIVE hand-rolled copies of
# the same arg_max CTE (dashboard/db.py had three, scripts/export_data.py two), and two of
# those copies were wrong in the same two ways: they built the sort key from the raw `phase`
# column instead of phase_ord() — so a legacy start/mid/end store sorted 'mid' after 'end' —
# and they left off the `ord <= snapshot` bound, which resolves a club to whatever division
# it ended up in rather than the one it was in at the time. Harmless when exporting the
# newest snapshot, silently wrong for any older one, and Frem climbed three divisions in
# three seasons, so it is exactly the kind of wrong that reads as plausible.
#
# `nation` is resolved by cid across ALL snapshots, not per-snapshot, deliberately matching
# the existing `lgn` CTE — a league's country does not change, and per-snapshot resolution
# would drop it for any snapshot where the row happens to carry NULL.
CLUB_LEAGUES = """
CREATE OR REPLACE VIEW mart.club_leagues AS
WITH lm AS (
    SELECT club_tid, league_cid,
           LPAD(CAST(season AS VARCHAR), 4, '0') || phase_ord(phase) AS ord
    FROM {S}.league_members
    WHERE source = 'club_league' AND league_cid IS NOT NULL
),
asat AS (
    SELECT s.season, s.phase, s.snap_ix, lm.club_tid,
           arg_max(lm.league_cid, lm.ord) AS league_cid
    FROM mart.snapshots s
    JOIN lm ON lm.ord <= LPAD(CAST(s.season AS VARCHAR), 4, '0') || s.phase_ord
    GROUP BY s.season, s.phase, s.snap_ix, lm.club_tid
),
lg AS (
    SELECT season, phase, cid, any_value(name) AS league_name,
           max(reputation) AS league_reputation, max(type) AS league_type
    FROM {S}.leagues GROUP BY season, phase, cid
),
nat AS (
    SELECT cid, any_value(nation) AS nation
    FROM {S}.leagues WHERE nation IS NOT NULL GROUP BY cid
)
SELECT a.season, a.phase, a.snap_ix, a.club_tid, a.league_cid,
       lg.league_name, nat.nation, lg.league_reputation, lg.league_type
FROM asat a
LEFT JOIN lg  ON (lg.season, lg.phase, lg.cid) = (a.season, a.phase, a.league_cid)
LEFT JOIN nat ON nat.cid = a.league_cid
"""

# The club dimension. squad_size counts the clubs whose squads actually parsed, which is why
# it is here rather than left to each caller: a club with zero players is a club we could not
# scrape, not a club with no players, and the site reports that count separately. Keep the
# zero rows.
CLUBS = """
CREATE OR REPLACE VIEW mart.clubs AS
SELECT
    c.season, c.phase, c.tid AS club_tid,
    any_value(c.name)                       AS name,
    any_value(cl.league_cid)                AS league_cid,
    any_value(cl.league_name)               AS league_name,
    any_value(cl.nation)                    AS nation,
    any_value(cl.league_reputation)         AS league_reputation,
    COUNT(DISTINCT p.tid)                   AS squad_size,
    c.tid IN (SELECT club_tid FROM mart.our_clubs)     AS is_ours,
    c.tid IN (SELECT club_tid FROM mart.managed_club)  AS is_managed
FROM {S}.clubs c
LEFT JOIN mart.club_leagues cl
       ON (cl.season, cl.phase, cl.club_tid) = (c.season, c.phase, c.tid)
LEFT JOIN {S}.players p
       ON (p.season, p.phase) = (c.season, c.phase)
      AND p.club_tid = c.tid AND p.tid IS NOT NULL AND NOT p.is_staff
GROUP BY c.season, c.phase, c.tid
"""

# The league dimension, including the division-strength index.
#
# IMMERSION: skill_idx is the average player ability per league, normalised 0-100 across the
# leagues that have enough rated players to mean anything. It is a CA-DERIVED INDEX, in the
# same sanctioned category as the Level percentile — the raw average must never become a
# column, so the normalisation happens inside this view rather than in a caller. Doing it
# outside would put an `aca` column in the mart, which publish_mart.verify() rejects on
# sight, and renaming it to slip past that check would break the house rule for real.
LEAGUES = """
CREATE OR REPLACE VIEW mart.leagues AS
WITH lg AS (
    SELECT season, phase, cid,
           any_value(name) AS name, any_value(nation) AS nation,
           max(type) AS type, max(reputation) AS reputation,
           max(member_count) AS member_count
    FROM {S}.leagues WHERE name IS NOT NULL
    GROUP BY season, phase, cid
),
counted AS (
    SELECT season, phase, league_cid AS cid, COUNT(*) AS club_count
    FROM mart.club_leagues GROUP BY season, phase, league_cid
),
rated AS (
    SELECT cl.season, cl.phase, cl.league_cid AS cid,
           AVG(p.ca) AS aca, COUNT(*) AS rated
    FROM {S}.players p
    JOIN mart.club_leagues cl
      ON (cl.season, cl.phase, cl.club_tid) = (p.season, p.phase, p.club_tid)
    WHERE NOT p.is_staff AND p.ca IS NOT NULL
    GROUP BY cl.season, cl.phase, cl.league_cid
    HAVING COUNT(*) >= 20
),
scaled AS (
    SELECT season, phase, cid, rated,
           ROUND(100.0 * (aca - MIN(aca) OVER w)
                 / NULLIF(MAX(aca) OVER w - MIN(aca) OVER w, 0), 1) AS skill_idx
    FROM rated
    WINDOW w AS (PARTITION BY season, phase)
)
SELECT lg.season, lg.phase, lg.cid, lg.name, lg.nation, lg.type, lg.reputation,
       lg.member_count, counted.club_count, scaled.skill_idx, scaled.rated
FROM lg
LEFT JOIN counted USING (season, phase, cid)
LEFT JOIN scaled  USING (season, phase, cid)
"""

# Our own division, then the next lower-reputation divisions in the same nation — the ladder
# a squad player is judged against (his league, then the ones he could be loaned into).
# ladder_rank 0 is always ours. `type IS NOT NULL` drops cups, which have a reputation but no
# table to be placed in.
COMPARISON_LADDER = """
CREATE OR REPLACE VIEW mart.comparison_ladder AS
WITH ours AS (
    SELECT l.season, l.phase, l.cid, l.nation, l.reputation
    FROM mart.leagues l
    JOIN mart.club_leagues cl
      ON (cl.season, cl.phase) = (l.season, l.phase) AND cl.league_cid = l.cid
    WHERE cl.club_tid IN (SELECT club_tid FROM mart.managed_club)
),
below AS (
    SELECT o.season, o.phase, l.cid, l.name, l.reputation
    FROM ours o
    JOIN mart.leagues l ON (l.season, l.phase) = (o.season, o.phase)
    WHERE l.nation IS NOT DISTINCT FROM o.nation
      AND l.type IS NOT NULL AND l.reputation < o.reputation
)
SELECT season, phase, cid, name, is_ours,
       ROW_NUMBER() OVER (PARTITION BY season, phase
                          ORDER BY is_ours DESC, reputation DESC, cid) - 1 AS ladder_rank
FROM (
    SELECT o.season, o.phase, o.cid,
           (SELECT name FROM mart.leagues l
             WHERE (l.season, l.phase, l.cid) = (o.season, o.phase, o.cid)) AS name,
           o.reputation, TRUE AS is_ours
    FROM ours o
    UNION ALL
    SELECT season, phase, cid, name, reputation, FALSE FROM below
)
"""


# --- deliberately NOT in the mart: ability ranks against an arbitrary pool ----------
#
# dashboard/db.py's ability_rank_leagues / ability_rank_clubs answer "how many bodies would be
# ahead of him at that club, or in that division" — and they need the raw ability number to do
# it. They stay in db.py, reading staging.players.ca directly, for two reasons:
#
#   1. There is nothing to materialise. The pool is an arbitrary club's squad at an arbitrary
#      familiarity floor (`--min-fam` is a live knob), so the only precomputable form is a
#      TOTAL ABILITY ORDINAL over every player. A dense rank over 23k players is an
#      order-isomorphism of `ca` with finer resolution than `ca` itself: it would pass
#      publish_mart.verify(), which matches on column NAMES, while being a plain immersion
#      leak. Baking min_fam into a two-valued column instead would narrow a real feature to
#      dodge that, which is worse than leaving the helpers where they are.
#   2. The published MART-ONLY artifact (fm-<career>-mart.duckdb) never carries `ca` at all —
#      not scrubbed, just never selected by any mart view — so these helpers still can't run
#      against it; ATTACH the full store (fm-<career>.duckdb, published unscrubbed since
#      2026-09-01) instead. This is exactly why positions.json ships a RENDERED ANSWER (ranks
#      and verdicts) rather than data: the mart-only artifact everything else reads from can't
#      answer this one.
#
# What those helpers DO take from the mart is mart.club_leagues, so the club->league rule has
# one definition. The ranking itself is theirs.

# --- role ratings and tactic fit ---------------------------------------------------
#
# NEITHER OF THE NEXT TWO OBJECTS IS EVER PUBLISHED. player_role_ratings is 27M rows and
# player_position_fit is ~9.4M; materialising either would dwarf the ~11 MB analysis
# artifact many times over. They are views so the exporter has a single schema to read from
# while it runs against a real local store; scripts/publish_mart.py skips them by name. If
# you are tempted to "fix" that omission, read the size numbers again.

# The role-rating formula: SUM(attribute x weight), with an unlisted attribute defaulting to
# weight 1. This is a verbatim restatement of load_duckdb.py's v_player_ratings so that
# nothing outside the mart has to be read to build the site — NOT a second definition of the
# formula. There are already three deliberate implementations (the loader view, this, and
# site/js/data.js's rating(), which is verified equal over 36,920 combinations); keep them
# equal or the app and the dashboard start disagreeing.
PLAYER_ROLE_RATINGS = f"""
CREATE OR REPLACE VIEW mart.player_role_ratings AS
WITH long AS (
    UNPIVOT {{S}}.player_attributes
    ON {", ".join(f'"{a}"' for a in ATTR_ORDER)}
    INTO NAME attribute VALUE value
),
combos AS (SELECT DISTINCT method, role FROM {{S}}.role_weights)
SELECT l.season, l.phase, l.tid, c.method, c.role,
       SUM(l.value * COALESCE(w.weight, 1)) AS rating
FROM long l
CROSS JOIN combos c
LEFT JOIN {{S}}.role_weights w
       ON w.method = c.method AND w.role = c.role AND w.attribute = LOWER(l.attribute)
GROUP BY l.season, l.phase, l.tid, c.method, c.role
"""

# Tactic fit: the role rating discounted by how familiar the player is with the position, then
# ranked against everyone who plays that position, globally / in his nation / in his division.
#
# The familiarity curve is read from staging.app_config INSIDE the view rather than baked in
# by the caller. dashboard/db.py generates the same expression in Python (_mult_sql), which
# means the mart definition would otherwise depend on whatever config the process that built
# it happened to see — and publish_mart rebuilds the mart from a source store, so the two
# could silently disagree. A scalar subquery keeps the view self-describing.
#
# The ability levels are NOT here: they are method-independent and live in
# mart.player_position_levels. Join the two on (season, phase, tid, position).
PLAYER_POSITION_FIT = """
CREATE OR REPLACE VIEW mart.player_position_fit AS
WITH cfg AS (
    SELECT
        COALESCE(any_value(CASE WHEN key = 'familiarity_curve' THEN value END),
                 'linear_floor')                                       AS curve,
        COALESCE(TRY_CAST(any_value(CASE WHEN key = 'familiarity_floor' THEN value END)
                          AS DOUBLE), 0.5)                             AS floor
    FROM {S}.app_config
),
base AS (
    SELECT
        l.season, l.phase, l.tid, l.person_id, l.position, l.role, l.familiarity,
        l.name, l.club, l.club_tid, l.league_cid, l.nation,
        r.method,
        r.rating AS base_rating,
        r.rating * CASE cfg.curve
            WHEN 'proportional' THEN l.familiarity / 20.0
            WHEN 'tiers' THEN CASE WHEN l.familiarity >= 18 THEN 1.0
                                   WHEN l.familiarity >= 15 THEN 0.95
                                   WHEN l.familiarity >= 10 THEN 0.85
                                   WHEN l.familiarity >= 5  THEN 0.70
                                   ELSE 0.50 END
            ELSE cfg.floor + (1 - cfg.floor) * (l.familiarity / 20.0)
        END                                                            AS eff
    FROM mart.player_position_levels l
    JOIN mart.player_role_ratings r
      ON (r.season, r.phase, r.tid) = (l.season, l.phase, l.tid) AND r.role = l.role
    CROSS JOIN cfg
)
SELECT
    b.*,
    ROUND(100 * PERCENT_RANK() OVER (PARTITION BY season, phase, method, position
                                     ORDER BY eff), 1)                 AS pctile_global,
    ROUND(100 * PERCENT_RANK() OVER (PARTITION BY season, phase, method, position, nation
                                     ORDER BY eff), 1)                 AS pctile_nation,
    ROUND(100 * PERCENT_RANK() OVER (PARTITION BY season, phase, method, position, league_cid
                                     ORDER BY eff), 1)                 AS pctile_league,
    RANK() OVER (PARTITION BY season, phase, method, position
                 ORDER BY eff DESC)                                    AS rank_global,
    RANK() OVER (PARTITION BY season, phase, method, position, nation
                 ORDER BY eff DESC)                                    AS rank_nation,
    RANK() OVER (PARTITION BY season, phase, method, position, league_cid
                 ORDER BY eff DESC)                                    AS rank_league
FROM base b
"""


# --- matches, from one club's point of view ----------------------------------------

# Every match twice, once per participating club, already oriented: venue, opponent, goals
# for and against, result, points, and each team stat split into our_/opp_.
#
# dashboard/db.py's our_match_history did this in Python — a query per season in a loop, then
# seventeen lines of pandas .where(home, ...) flips — and only ever for the managed club. In
# SQL it costs nothing (mart.matches is 139 rows, so doubling it is ~278) and it generalises:
# an opposition head-to-head becomes a WHERE clause instead of a rewrite.
#
# The opponent's name is resolved in the SAME snapshot as the match. The Python version keyed
# its name map on (season, tid) only, so within a season it kept whichever phase's row landed
# last — harmless while names are stable, but a tid is a recycled slot and the snapshot-scoped
# join is the rule the rest of the mart follows.
CLUB_MATCHES = """
CREATE OR REPLACE VIEW mart.club_matches AS
WITH sides AS (
    SELECT m.season, m.phase, m.anchor, m.home_tid AS club_tid FROM mart.matches m
    UNION ALL
    SELECT m.season, m.phase, m.anchor, m.away_tid AS club_tid FROM mart.matches m
)
SELECT
    c.season, c.phase, c.anchor, c.club_tid,
    m.date, m.competition, m.is_competitive, m.comp_id, m.formation, m.attendance,
    CASE WHEN c.club_tid = m.home_tid THEN 'H' ELSE 'A' END               AS venue,
    CASE WHEN c.club_tid = m.home_tid THEN m.away_tid ELSE m.home_tid END AS opp_tid,
    COALESCE(oc.name, '#' || CASE WHEN c.club_tid = m.home_tid
                                  THEN m.away_tid ELSE m.home_tid END)    AS opponent,
    CASE WHEN c.club_tid = m.home_tid THEN m.score_home ELSE m.score_away END AS gf,
    CASE WHEN c.club_tid = m.home_tid THEN m.score_away ELSE m.score_home END AS ga,
    CASE WHEN (CASE WHEN c.club_tid = m.home_tid THEN m.score_home ELSE m.score_away END)
            > (CASE WHEN c.club_tid = m.home_tid THEN m.score_away ELSE m.score_home END)
         THEN 'W'
         WHEN (CASE WHEN c.club_tid = m.home_tid THEN m.score_home ELSE m.score_away END)
            = (CASE WHEN c.club_tid = m.home_tid THEN m.score_away ELSE m.score_home END)
         THEN 'D' ELSE 'L' END                                            AS result,
    CASE WHEN (CASE WHEN c.club_tid = m.home_tid THEN m.score_home ELSE m.score_away END)
            > (CASE WHEN c.club_tid = m.home_tid THEN m.score_away ELSE m.score_home END)
         THEN 3
         WHEN (CASE WHEN c.club_tid = m.home_tid THEN m.score_home ELSE m.score_away END)
            = (CASE WHEN c.club_tid = m.home_tid THEN m.score_away ELSE m.score_home END)
         THEN 1 ELSE 0 END                                                AS pts,
    CASE WHEN c.club_tid = m.home_tid THEN m.home_shots ELSE m.away_shots END  AS our_shots,
    CASE WHEN c.club_tid = m.home_tid THEN m.away_shots ELSE m.home_shots END  AS opp_shots,
    CASE WHEN c.club_tid = m.home_tid THEN m.home_shots_on_target ELSE m.away_shots_on_target END  AS our_shots_on_target,
    CASE WHEN c.club_tid = m.home_tid THEN m.away_shots_on_target ELSE m.home_shots_on_target END  AS opp_shots_on_target,
    CASE WHEN c.club_tid = m.home_tid THEN m.home_passes ELSE m.away_passes END  AS our_passes,
    CASE WHEN c.club_tid = m.home_tid THEN m.away_passes ELSE m.home_passes END  AS opp_passes,
    CASE WHEN c.club_tid = m.home_tid THEN m.home_passes_completed ELSE m.away_passes_completed END  AS our_passes_completed,
    CASE WHEN c.club_tid = m.home_tid THEN m.away_passes_completed ELSE m.home_passes_completed END  AS opp_passes_completed,
    CASE WHEN c.club_tid = m.home_tid THEN m.home_tackles ELSE m.away_tackles END  AS our_tackles,
    CASE WHEN c.club_tid = m.home_tid THEN m.away_tackles ELSE m.home_tackles END  AS opp_tackles,
    CASE WHEN c.club_tid = m.home_tid THEN m.home_tackles_won ELSE m.away_tackles_won END  AS our_tackles_won,
    CASE WHEN c.club_tid = m.home_tid THEN m.away_tackles_won ELSE m.home_tackles_won END  AS opp_tackles_won,
    CASE WHEN c.club_tid = m.home_tid THEN m.home_crosses ELSE m.away_crosses END  AS our_crosses,
    CASE WHEN c.club_tid = m.home_tid THEN m.away_crosses ELSE m.home_crosses END  AS opp_crosses,
    CASE WHEN c.club_tid = m.home_tid THEN m.home_interceptions ELSE m.away_interceptions END  AS our_interceptions,
    CASE WHEN c.club_tid = m.home_tid THEN m.away_interceptions ELSE m.home_interceptions END  AS opp_interceptions
FROM sides c
JOIN mart.matches m USING (season, phase, anchor)
LEFT JOIN {S}.clubs oc
       ON (oc.season, oc.phase) = (m.season, m.phase)
      AND oc.tid = CASE WHEN c.club_tid = m.home_tid THEN m.away_tid ELSE m.home_tid END
"""


# --- the player dimension ---------------------------------------------------------

# One row per player per snapshot: bio, club, contract, and the 23 attributes wide. This is
# the object the site's player payload is built from, so it deliberately ships RAW
# ATTRIBUTES rather than ratings — the app computes role ratings in the browser from
# attributes x weights, which is what lets you switch tactic and re-rate everyone with no
# rebuild. Turning attributes into ratings here would break that by design.
#
# NO ca/pa. Ability reaches the site only as the Level percentile
# (mart.player_position_levels), never as a number.
#
# `age` is birthday-adjusted against the snapshot date rather than a plain year subtraction,
# matching dashboard/db.py's player_bio.
PLAYER_SNAPSHOTS = f"""
CREATE OR REPLACE VIEW mart.player_snapshots AS
SELECT
    s.season, s.phase, s.snap_ix, s.phase_date,
    p.tid, ps.person_id, p.name,
    p.club_tid, p.club, cl.league_cid, cl.league_name, cl.nation,
    p.dob,
    CASE WHEN p.dob IS NULL THEN NULL
         ELSE DATE_DIFF('year', p.dob, s.phase_date)
              - CASE WHEN (MONTH(s.phase_date), DAY(s.phase_date))
                        < (MONTH(p.dob), DAY(p.dob)) THEN 1 ELSE 0 END
    END                                                       AS age,
    p.is_gk, p.has_attributes, p.squad_status, p.reputation,
    p.foot_left, p.foot_right, p.nationality_id,
    p.player_value, p.wage_units, p.wage_gbp,
    p.contract_expiry, p.contract_expiry_year,
    -- The raw loan flags, carried but NOT to be trusted for "is he ours right now": both are
    -- set-only and never cleared by the save. mart.squad_on(d) is the answer to that
    -- question; these are here for provenance and for the parent-club name.
    p.loaned_in, p.loaned_out, p.parent_club_tid, p.parent_club,
    ({_est_count(ATTR_ORDER)})                                AS est_attrs,
    ({_est_count(ATTR_ORDER)}) > 0                            AS is_estimated,
    {", ".join(f'a."{col}"' for col in ATTR_ORDER)}
FROM {{S}}.players p
JOIN mart.snapshots s USING (season, phase)
LEFT JOIN {{S}}.player_attributes a USING (season, phase, tid)
LEFT JOIN {{S}}.person_slices ps USING (season, phase, tid)
LEFT JOIN mart.club_leagues cl
       ON (cl.season, cl.phase, cl.club_tid) = (p.season, p.phase, p.club_tid)
WHERE NOT p.is_staff
"""

# Career history as the game reports it: one row per prior season per player, per snapshot.
# The club name is resolved WITHIN THE SAME SNAPSHOT on purpose — a tid is a recycled slot,
# so resolving it against a different snapshot can name the wrong club entirely.
PLAYER_CAREER_SEASONS = """
CREATE OR REPLACE VIEW mart.player_career_seasons AS
SELECT
    h.season, h.phase, h.tid, ps.person_id, h.seq,
    h.hist_season, h.end_year, h.club_tid,
    COALESCE(c.name, '#' || h.club_tid) AS club,
    h.fee, h.apps, h.goals, h.assists, h.rating
FROM {S}.player_history_seasons h
LEFT JOIN {S}.clubs c
       ON (c.season, c.phase, c.tid) = (h.season, h.phase, h.club_tid)
LEFT JOIN {S}.person_slices ps
       ON (ps.season, ps.phase, ps.tid) = (h.season, h.phase, h.tid)
"""

# Where a player came from, and whether that makes him eligible under the capital rule.
#
# confidence='low' blanks the origin rather than dropping the row: an unreliable origin must
# not read as a known one, but the player still exists. Since the career-history chain head
# became a STORED POINTER (u32 @ P-38 in the attribute record) rather than a positional
# guess, every row here is 'exact' in practice and the blanking is a guard, not a filter.
PLAYER_ORIGIN = """
CREATE OR REPLACE VIEW mart.player_origin AS
SELECT
    h.season, h.phase, h.tid, ps.person_id,
    CASE WHEN h.confidence = 'low' THEN NULL ELSE h.origin_club_tid END AS origin_club_tid,
    CASE WHEN h.confidence = 'low' THEN NULL
         ELSE COALESCE(oc.name, '#' || h.origin_club_tid) END           AS origin_club,
    CASE WHEN h.confidence = 'low' THEN NULL
         ELSE COALESCE(lc.name, '#' || h.last_season_club_tid) END      AS last_season_club,
    h.confidence,
    (e.club_tid IS NOT NULL AND h.confidence <> 'low')                 AS eligible
FROM {S}.player_history h
LEFT JOIN {S}.clubs oc ON (oc.season, oc.phase, oc.tid) = (h.season, h.phase, h.origin_club_tid)
LEFT JOIN {S}.clubs lc ON (lc.season, lc.phase, lc.tid) = (h.season, h.phase, h.last_season_club_tid)
LEFT JOIN {S}.eligible_origin_clubs e ON e.club_tid = h.origin_club_tid
LEFT JOIN {S}.person_slices ps
       ON (ps.season, ps.phase, ps.tid) = (h.season, h.phase, h.tid)
"""


# --- ability levels ---------------------------------------------------------------

# The immersion-safe ability layer: where a player sits among everyone who plays his
# position, as a percentile, globally / in his nation / in his division.
#
# THIS OBJECT CARRIES NO `method` COLUMN, AND THAT IS THE POINT. dashboard/db.py's
# effective_table joins the 27M-row v_player_ratings into its base CTE and then computes
# these three columns as PERCENT_RANK() ... ORDER BY ca. The ratings appear nowhere in that
# expression; they only shape row membership, and membership is identical for every method
# because v_player_ratings CROSS JOINs `SELECT DISTINCT method, role` onto every player.
# Verified directly: the same query with the ratings join deleted returns byte-identical
# level columns over 80,627 rows, for four different methods. So the level layer is a
# narrow, tactic-free 1.34M-row object, and the fit layer (which genuinely does depend on
# method) is a separate concern — see PLAYER_POSITION_FIT.
#
# IMMERSION: `ca` is the ORDER BY and is never projected. This is the sanctioned Level
# percentile (CLAUDE.md's house rule), not the ability number. Adding ca as a column here
# would ship raw ability into the published artifact and publish_mart.verify() would — and
# should — refuse the upload.
#
# Two guards that are no-ops on this store and deliberate anyway:
#   - `p.ca IS NOT NULL`: DuckDB orders NULLs LAST by default, so a NULL-ability player would
#     silently receive level_global = 100.0, i.e. read as the best in the world at his
#     position. Zero rows are affected today; the day one is, the guard is what stops a
#     nonsense number reaching the site.
#   - LEFT JOIN to position_role_map rather than INNER: all 14 position codes are mapped
#     today, but an unmapped one should lose its ROLE, not vanish from the level pool
#     entirely. Because PERCENT_RANK partitions by position, an extra position creates its
#     own partition and cannot perturb any existing one.
PLAYER_POSITION_LEVELS = """
CREATE OR REPLACE VIEW mart.player_position_levels AS
WITH base AS (
    SELECT s.season, s.phase, s.snap_ix, pp.tid, ps.person_id,
           pp.position, prm.role, pp.familiarity,
           p.name, p.club, p.club_tid, cl.league_cid, cl.nation, p.ca
    FROM {S}.player_positions pp
    JOIN mart.snapshots s          USING (season, phase)
    JOIN {S}.players p             USING (season, phase, tid)
    LEFT JOIN {S}.position_role_map prm ON prm.position = pp.position
    LEFT JOIN {S}.person_slices ps USING (season, phase, tid)
    LEFT JOIN mart.club_leagues cl
           ON (cl.season, cl.phase, cl.club_tid) = (pp.season, pp.phase, p.club_tid)
    WHERE NOT p.is_staff AND p.ca IS NOT NULL
)
SELECT
    season, phase, snap_ix, tid, person_id, position, role, familiarity,
    name, club, club_tid, league_cid, nation,
    ROUND(100 * PERCENT_RANK() OVER (PARTITION BY season, phase, position
                                     ORDER BY ca), 1)             AS level_global,
    ROUND(100 * PERCENT_RANK() OVER (PARTITION BY season, phase, position, nation
                                     ORDER BY ca), 1)             AS level_nation,
    ROUND(100 * PERCENT_RANK() OVER (PARTITION BY season, phase, position, league_cid
                                     ORDER BY ca), 1)             AS level_league,
    -- No rank_* here. effective_table's rank_global/nation/league order by `eff`, the
    -- FAMILIARITY-ADJUSTED TACTIC FIT, so they belong with pctile_* in the method-dependent
    -- fit layer, not with the ability levels. n_* are just partition sizes and are shared by
    -- both, so they live here where they cost nothing.
    COUNT(*) OVER (PARTITION BY season, phase, position)              AS n_global,
    COUNT(*) OVER (PARTITION BY season, phase, position, nation)      AS n_nation,
    COUNT(*) OVER (PARTITION BY season, phase, position, league_cid)  AS n_league
FROM base
"""


# Rule 1 in one place: the single phase per season that match facts should be read from.
CHOSEN_MATCH_PHASE = """
CREATE OR REPLACE VIEW mart.chosen_match_phase AS
SELECT season, arg_max(phase, phase_ord(phase)) AS phase
FROM (SELECT DISTINCT season, phase FROM {S}.match_player_stats)
GROUP BY season
"""


# --- match facts ------------------------------------------------------------------

# Rules 1, 3 and 4 applied. Every consumer that used to hand-roll the dedup + the
# started/appeared/minutes arithmetic reads this instead.
MATCH_PLAYER_FACTS = """
CREATE OR REPLACE VIEW mart.match_player_facts AS
SELECT
    m.season, m.phase, m.anchor, m.side, m.tid,
    ps.person_id,
    m.team_tid, m.opponent_tid, m.date, m.competition,
    m.competition NOT ILIKE '%%friend%%'        AS is_competitive,
    m.pos_order, m.rating, m.goals, m.assists,
    m.passA, m.passC, m.keyPass, m.tackA, m.tackW, m.intercept,
    m.headA, m.headW, m.crossA, m.crossC, m.dribbles, m.mistakes,
    m.shotA, m.shotO, m.condition, m.yellow,
    -- Real on-pitch position for OUR starters ('DR','DMC','AML',...); NULL for the
    -- opposition (the save stores no shape for them) and for substitutes. PREFER THIS
    -- over bucketing pos_order: slot order is depth order and shifts with the shape, so
    -- a fixed pos_order->unit map ("2,3 = fullbacks") is wrong for every back-3 game.
    m.position,
    CASE
        WHEN m.position IS NULL                                   THEN NULL
        WHEN m.position = 'GK'                                    THEN 'GK'
        WHEN m.position LIKE 'DM%%'                               THEN 'Defensive midfield'
        WHEN m.position LIKE 'AM%%'                               THEN 'Attacking midfield'
        WHEN m.position LIKE 'D%%'                                THEN 'Defenders'
        WHEN m.position LIKE 'M%%'                                THEN 'Midfield'
        WHEN m.position = 'FC'                                    THEN 'Forwards'
    END                                          AS unit,
    m.pos_order <= 11                            AS started,
    m.pos_order <= 11 OR m.subOn <> 255          AS appeared,
    CASE WHEN m.pos_order <= 11 OR m.subOn <> 255
         THEN (CASE WHEN m.subOff = 255 THEN 90 ELSE m.subOff END)
            - (CASE WHEN m.subOn  = 255 THEN 0  ELSE m.subOn  END)
         ELSE 0 END                              AS minutes
FROM {S}.match_player_stats m
JOIN mart.chosen_match_phase USING (season, phase)
LEFT JOIN {S}.person_slices ps USING (season, phase, tid)
"""

MATCHES = """
CREATE OR REPLACE VIEW mart.matches AS
SELECT
    m.*,
    m.competition NOT ILIKE '%%friend%%' AS is_competitive
FROM {S}.matches m
JOIN (SELECT season, arg_max(phase, phase_ord(phase)) AS phase
      FROM (SELECT DISTINCT season, phase FROM {S}.matches) GROUP BY season)
  USING (season, phase)
"""

# The whole season review as one table. `apps` counts only matches the player actually
# appeared in. Friendlies are excluded (is_competitive) — a season total is a
# competitive-season total. `mart.match_player_facts` still has friendlies for anyone who
# wants them explicitly.
#
# GRAIN NOTE, and it is the whole reason this view is shaped the way it is. Two earlier
# choices each silently deleted real football:
#
#   1. Aggregating on person_id and dropping the rows where it is NULL. person_slices is
#      derived purely from staging.players (load_duckdb.rebuild_persons), so a player with
#      match rows but no roster row in ANY snapshot never gets an identity — 76 tids here,
#      42 of them ours. Filtering them out cost 196 of our appearances and 25 of our 2024
#      goals, 22% of the season. So the aggregation key is `player_key`, which falls back to
#      the tid when identity is unknown. Rule 3 still holds where it can: a recycled slot
#      whose two occupants ARE both known stays split, because their person_ids differ.
#
#      `person_id` is still projected, as any_value, and is still NULL for those rows. Do
#      NOT replace it with player_key: mart.player_growth_season's `mins` CTE,
#      publish_mart's OURS predicate and CLAUDE.md's cookbook example all JOIN person_id to
#      the spell tables, and a synthetic 'tid-1234' would match nothing while looking right.
#
#   2. any_value(team_tid) with team_tid outside the GROUP BY. 23 person-seasons here span
#      more than one club, so the club a row claimed was arbitrary and filtering on it was
#      unsound. team_tid is part of the grain now: a mid-season transfer becomes two rows,
#      one per club, which is what "his season at THIS club" means. Callers wanting the
#      whole season sum across clubs and competitions.
PLAYER_SEASONS = """
CREATE OR REPLACE VIEW mart.player_seasons AS
SELECT
    f.season,
    COALESCE(f.person_id, 'tid-' || f.tid)          AS player_key,
    any_value(f.person_id)                          AS person_id,
    any_value(f.tid) AS tid, f.team_tid,
    f.competition,
    COUNT(*) FILTER (WHERE f.appeared)              AS apps,
    COUNT(*) FILTER (WHERE f.started)               AS starts,
    SUM(f.minutes)                                  AS minutes,
    ROUND(AVG(f.rating) FILTER (WHERE f.appeared), 2) AS avg_rating,
    SUM(f.goals) AS goals, SUM(f.assists) AS assists, SUM(f.keyPass) AS key_passes,
    SUM(f.passA) AS passA, SUM(f.passC) AS passC,
    SUM(f.tackA) AS tackA, SUM(f.tackW) AS tackW, SUM(f.intercept) AS intercept,
    SUM(f.headA) AS headA, SUM(f.headW) AS headW,
    SUM(f.crossA) AS crossA, SUM(f.crossC) AS crossC,
    SUM(f.shotA) AS shotA, SUM(f.shotO) AS shotO,
    SUM(f.dribbles) AS dribbles, SUM(f.mistakes) AS mistakes, SUM(f.yellow) AS yellows
FROM mart.match_player_facts f
WHERE f.is_competitive
GROUP BY f.season, COALESCE(f.person_id, 'tid-' || f.tid), f.team_tid, f.competition
"""


# --- spells -----------------------------------------------------------------------

# Arrival-window inference, in evidence order. The save carries NO transfer date, so the
# window is inferred; the snapshot bracket ALONE is not enough, because five players in
# this store share the identical bracket 2023-07-02 -> 2024-01-05 and split across both
# windows (Pedersen/Ellegaard/Moller summer, Ementa/Sandgrav winter). Only the first match
# date separates them.
#
#   1. FIRST MATCH for the new club, if any. A match played before 1 Jan of the end-year
#      means he was already at the club in the autumn half => summer.
#   2. SNAPSHOT OVERRIDE (upward only). If he already reads as ours in a snapshot dated
#      before the winter cut, he is a summer arrival regardless of when he debuted — this
#      is the guard for a summer signing who is injured until February.
#   3. FIRST MATCH on/after the cut, with no earlier snapshot evidence => winter.
#   4. Last seen elsewhere on/after the cut => winter.
#   5. Otherwise SUMMER. A player first seen at a pre-season snapshot with no match data is
#      a summer transfer or a youth-intake graduation; both are summer.
#
# Friendlies are deliberately NOT filtered here: a mid-break friendly is the earliest proof
# of presence (Ementa and Sandgrav are dated by the 2024-01-17 friendly). Filter friendlies
# for competitive analysis, never for arrival evidence.
_ARRIVAL_WINDOW_SQL = """
        CASE
            WHEN r.first_match IS NOT NULL AND r.first_match <  winter_cut(r.season) THEN 'summer'
            WHEN r.from_phase_date IS NOT NULL AND r.from_phase_date < winter_cut(r.season) THEN 'summer'
            WHEN r.first_match IS NOT NULL                                           THEN 'winter'
            WHEN r.prev_phase_date IS NOT NULL
                 AND r.prev_phase_date >= winter_cut(r.season)                       THEN 'winter'
            ELSE 'summer'
        END"""

# Contiguous club runs per person. Partitioning by person_id as well as tid means a
# recycled tid starts a fresh run instead of splicing two careers into one (rule 3).
CLUB_RUNS = """
CREATE OR REPLACE VIEW mart.club_runs AS
WITH pc AS (
    SELECT p.tid, ps.person_id, p.name, p.club_tid, p.club, p.loaned_in,
           s.season, s.phase, s.snap_ix, s.phase_date
    FROM {S}.players p
    JOIN mart.snapshots s USING (season, phase)
    LEFT JOIN {S}.person_slices ps USING (season, phase, tid)
    WHERE NOT p.is_staff
),
marked AS (
    SELECT *, CASE WHEN club_tid IS DISTINCT FROM
                LAG(club_tid) OVER (PARTITION BY tid, person_id ORDER BY snap_ix)
              THEN 1 ELSE 0 END AS chg
    FROM pc
),
grouped AS (
    SELECT *, SUM(chg) OVER (PARTITION BY tid, person_id ORDER BY snap_ix) AS run_id
    FROM marked
)
SELECT
    tid, person_id, any_value(name) AS name, club_tid, any_value(club) AS club, run_id,
    MIN(snap_ix)    AS from_ix,
    MAX(snap_ix)    AS to_ix,
    MIN(season)     AS season,
    MIN(phase_date) AS from_phase_date,
    bool_or(loaned_in) AS ever_loaned_in
FROM grouped
GROUP BY tid, person_id, club_tid, run_id
"""

# at_club spells. valid_from is the START OF THE INFERRED WINDOW, not a guessed exact day —
# the save has no transfer date, so claiming one would be false precision. valid_to is the
# day before the next run begins, or NULL while the run is still current.
AT_CLUB = """
CREATE OR REPLACE VIEW mart.at_club_spells AS
WITH lagged AS (
    SELECT
        cr.*,
        LAG(cr.to_ix)    OVER (PARTITION BY cr.tid, cr.person_id ORDER BY cr.from_ix) AS prev_to_ix,
        LEAD(cr.from_ix) OVER (PARTITION BY cr.tid, cr.person_id ORDER BY cr.from_ix) AS next_from_ix
    FROM mart.club_runs cr
),
firstmatch AS (
    SELECT tid, team_tid, season, MIN(date) AS first_match
    FROM mart.match_player_facts WHERE appeared
    GROUP BY tid, team_tid, season
),
r AS (
    SELECT
        l.*,
        prev_s.phase_date                       AS prev_phase_date,
        -- The snapshot AFTER the one that last showed him in this run. NULL means the run
        -- reaches the newest snapshot, i.e. he is genuinely still here. Anything else means
        -- the run ended and this is the first date on which he was gone — see the ghost
        -- note on valid_to below.
        after_s.phase_date                      AS after_phase_date,
        fm.first_match
    FROM lagged l
    LEFT JOIN mart.snapshots prev_s  ON prev_s.snap_ix  = l.prev_to_ix
    LEFT JOIN mart.snapshots after_s ON after_s.snap_ix = l.to_ix + 1
    LEFT JOIN firstmatch fm
           ON fm.tid = l.tid AND fm.team_tid = l.club_tid AND fm.season = l.season
),
w AS (SELECT r.*, {window} AS arrival_window, r.prev_to_ix IS NOT NULL AS is_transition
      FROM r),
-- valid_from is the start of the INFERRED WINDOW, clamped to the day after the snapshot
-- that last showed him elsewhere (he cannot have arrived before we observed him at another
-- club). Without the clamp two club changes inside one season both resolve to the same
-- season_start and collide. The clamp uses prev_phase_date + 1 day rather than
-- prev_phase_date because prev_phase_date is strictly increasing across a person's runs,
-- which makes valid_from strictly increasing too — and that is what guarantees the
-- LEAD-derived valid_to below can neither overlap nor invert.
--
-- The whole inferred window is then capped at from_phase_date by LEAST, because a window
-- must not open AFTER the observation that created it. Without the cap, a run first seen in
-- a snapshot that falls in the last days of June belongs to the NEXT season (phase 2024-06-30
-- is season 2025), so season_start(2025) = 2024-07-01 lands one day after the snapshot and
-- squad_on('2024-06-30') cannot see a player who demonstrably signed. LEAST only ever moves
-- valid_from earlier, and never earlier than prev_phase_date + 1 (which is <= from_phase_date
-- by construction), so the strict-increase property above survives intact.
dated AS (
    SELECT w.*,
           CASE
             WHEN is_transition AND arrival_window = 'winter'
               THEN LEAST(GREATEST(winter_cut(season),
                             COALESCE(prev_phase_date + INTERVAL 1 DAY, winter_cut(season))),
                          from_phase_date)
             WHEN is_transition
               THEN LEAST(GREATEST(season_start(season),
                             COALESCE(prev_phase_date + INTERVAL 1 DAY, season_start(season))),
                          from_phase_date)
             ELSE from_phase_date
           END AS valid_from
    FROM w
)
-- valid_to is derived from the NEXT spell's valid_from, never from a snapshot date, so the
-- spells of one person tile without gaps or overlaps by construction. NULL = still current.
--
-- GHOST NOTE. "No next spell" does not imply "still here". club_runs filters
-- WHERE NOT p.is_staff, so a player who retires into the coaching staff (his players row
-- flips is_staff and club_tid to the 65535 sentinel) simply stops producing runs — LEAD
-- returns NULL and he stayed in every squad_on() forever. Same for anyone who leaves the
-- scraped world entirely. So an open-ended spell is only honoured when the run actually
-- reaches the newest snapshot; otherwise it closes the day before the first snapshot that
-- no longer showed him. after_phase_date is NULL exactly when to_ix is the newest snap_ix,
-- which is what makes that the only case yielding a genuine NULL valid_to.
--
-- SECOND GHOST, same symptom, different cause: ever_loaned_in runs are EXCLUDED entirely
-- below, not just closed by the note above. `loaned_in` is a SET-ONLY flag (see module
-- docstring) — nothing in the save clears it when a loan lapses without being renewed, so
-- the byte marker keeps re-finding a lapsed loanee in OUR squad-list region every later
-- save. His run genuinely reaches the newest snapshot, so after_phase_date can't help here.
-- `mart.loan_in_spells` already derives his presence correctly — one spell per SEASON he
-- actually appeared for us, capped at that season's end — so at_club_spells drops these
-- runs and leaves loan_in_spells as the SOLE source of loan-in presence; mart.squad_on()'s
-- UNION of ('at_club', 'loan_in') stays correct either way. club_runs itself is untouched,
-- so growth-at-club tracking for loan spells is unaffected.
SELECT
    person_id, tid, name, 'at_club' AS spell_type, club_tid, club, season,
    valid_from,
    COALESCE(
        LEAD(valid_from) OVER (PARTITION BY tid, person_id ORDER BY from_ix),
        after_phase_date
    ) - INTERVAL 1 DAY                                AS valid_to,
    CASE WHEN is_transition THEN arrival_window END   AS arrival_window
FROM dated
WHERE NOT ever_loaned_in
"""

# loan_in spells. The flag is set-only and never cleared, so it is used ONLY to identify
# who was ever loaned in; liveness comes from appearance evidence, and expiry from the
# one-season rule. A loan is live in season S iff the player actually appeared for us in S.
# A renewal is therefore a SECOND spell in S+1, not one long spell — which is exactly how
# the game models it. A pre-season snapshot has no matches in S, so it yields no loan-in:
# correct, since by rule every prior-season loan has already expired.
LOAN_IN = """
CREATE OR REPLACE VIEW mart.loan_in_spells AS
WITH flagged AS (
    SELECT DISTINCT ps.person_id, p.tid
    FROM {S}.players p
    JOIN {S}.person_slices ps USING (season, phase, tid)
    WHERE p.loaned_in AND p.club_tid IN (SELECT club_tid FROM mart.our_clubs)
      AND NOT p.is_staff
),
seasons_played AS (
    SELECT f.person_id, f.tid, f.season, f.team_tid,
           MIN(f.date) AS first_match, MAX(f.date) AS last_match
    FROM mart.match_player_facts f
    WHERE f.appeared AND f.team_tid IN (SELECT club_tid FROM mart.our_clubs)
    GROUP BY f.person_id, f.tid, f.season, f.team_tid
),
r AS (
    SELECT sp.person_id, sp.tid, sp.season, sp.team_tid AS club_tid,
           sp.first_match, sp.first_match AS from_phase_date,
           CAST(NULL AS DATE) AS prev_phase_date
    FROM seasons_played sp
    JOIN flagged fl ON fl.person_id = sp.person_id
)
SELECT
    r.person_id, r.tid,
    (SELECT any_value(p.name) FROM {S}.players p WHERE p.tid = r.tid)  AS name,
    'loan_in' AS spell_type, r.club_tid,
    CAST(NULL AS VARCHAR) AS club, r.season,
    CASE WHEN {window} = 'winter' THEN winter_cut(r.season)
         ELSE season_start(r.season) END       AS valid_from,
    season_end(r.season)                       AS valid_to,
    {window}                                   AS arrival_window
FROM r
"""

# loan_out spells, lifted from the parsed weekly Player-Progress flag — these carry REAL
# dates, unlike loan-ins. One normalisation is needed: `_merge_ranges(gap_days=8)` glues a
# loan to its renewal when the weekly flag never drops for more than 8 days across the
# summer, producing 75-77 week spells that span two seasons (5 of 10 at the latest
# snapshot). The one-season rule says those are two loans, so the interval is clipped to
# each season it touches.
LOAN_OUT = """
CREATE OR REPLACE VIEW mart.loan_out_spells AS
-- `player_loans` is re-scraped every snapshot, and the weekly Player-Progress table has a
-- limited visibility window, so ONE real loan comes back with DIFFERENT spell_start values
-- from different snapshots (an early snapshot sees it starting 2023-01-06; a later one
-- sees the same loan from 2022-07-14). Deduping on (tid, spell_start) therefore keeps
-- several partial copies of the same loan, which then overlap. The fix is a proper
-- interval merge — union every observation of a player's loan state, then split.
WITH raw AS (
    SELECT ps.person_id, l.tid, l.spell_start, l.spell_end
    FROM {S}.player_loans l
    LEFT JOIN {S}.person_slices ps USING (season, phase, tid)
),
merged AS ({merge}),
-- Only NOW split at the season line: a merged 75-77 week block is a loan plus its
-- renewal (`_merge_ranges(gap_days=8)` glues them when the weekly flag never drops across
-- the summer), and the one-season-max rule says those are two loans.
split AS (
    SELECT merged.*, UNNEST(range(CAST(season_of(merged.spell_start) AS INT),
                                  CAST(season_of(merged.spell_end) AS INT) + 1)) AS s
    FROM merged
)
SELECT
    person_id, tid,
    (SELECT any_value(p.name) FROM {S}.players p WHERE p.tid = split.tid) AS name,
    'loan_out' AS spell_type,
    CAST(NULL AS INTEGER) AS club_tid,   -- destination club is not in the save
    CAST(NULL AS VARCHAR) AS club,
    s AS season,
    GREATEST(spell_start, season_start(s)) AS valid_from,
    LEAST(spell_end,   season_end(s))      AS valid_to,
    CAST(NULL AS VARCHAR) AS arrival_window
FROM split
WHERE GREATEST(spell_start, season_start(s)) <= LEAST(spell_end, season_end(s))
"""

# Injury spells, lifted as parsed. Deliberately NOT split at the season boundary: the
# one-season rule is about loans, and a long-term injury genuinely does run continuously
# across a summer.
INJURED = """
CREATE OR REPLACE VIEW mart.injury_spells AS
-- Same interval merge as loan_out (the same re-scrape/visibility-window effect applies),
-- but deliberately NOT split at the season line: the one-season rule is about loans, and a
-- long-term injury genuinely does run continuously across a summer.
WITH raw AS (
    SELECT ps.person_id, i.tid, i.spell_start, i.spell_end
    FROM {S}.player_injuries i
    LEFT JOIN {S}.person_slices ps USING (season, phase, tid)
),
merged AS ({merge})
SELECT
    merged.person_id, merged.tid,
    (SELECT any_value(p.name) FROM {S}.players p WHERE p.tid = merged.tid) AS name,
    'injured' AS spell_type,
    CAST(NULL AS INTEGER) AS club_tid,
    CAST(NULL AS VARCHAR) AS club,
    season_of(merged.spell_start) AS season,
    merged.spell_start AS valid_from,
    merged.spell_end   AS valid_to,
    CAST(NULL AS VARCHAR) AS arrival_window
FROM merged
"""

# The union. Different spell types MAY overlap for one person (injured while out on loan);
# spells of the SAME type may not — validate() asserts that.
PLAYER_SPELLS = """
CREATE OR REPLACE VIEW mart.player_spells AS
SELECT person_id, tid, name, spell_type, club_tid, club, season,
       valid_from, valid_to, arrival_window FROM mart.at_club_spells
UNION ALL
SELECT person_id, tid, name, spell_type, club_tid, club, season,
       valid_from, valid_to, arrival_window FROM mart.loan_in_spells
UNION ALL
SELECT person_id, tid, name, spell_type, club_tid, club, season,
       valid_from, valid_to, arrival_window FROM mart.loan_out_spells
UNION ALL
SELECT person_id, tid, name, spell_type, club_tid, club, season,
       valid_from, valid_to, arrival_window FROM mart.injury_spells
"""

# The squad question the loaned_in flag gets wrong, asked correctly: who was actually ours
# on a given date. Usage:
#   SELECT * FROM mart.squad_on('2024-03-01');
SQUAD_ON = """
CREATE OR REPLACE MACRO mart.squad_on(d) AS TABLE
SELECT s.person_id, s.tid, s.name, s.club_tid, s.spell_type, s.valid_from, s.valid_to
FROM mart.player_spells s
WHERE s.spell_type IN ('at_club', 'loan_in')
  AND s.club_tid IN (SELECT club_tid FROM mart.our_clubs)
  AND CAST(d AS DATE) >= s.valid_from
  AND (s.valid_to IS NULL OR CAST(d AS DATE) <= s.valid_to)
"""

# The general form of the same question: genuine squad membership at EVERY snapshot, for
# EVERY club, not just ours. A plain VIEW (not a macro — see squad_current's note below), so
# it's the primitive a remote agent querying the published store over ATTACH should reach
# for directly: `SELECT * FROM m.mart.snapshot_squad WHERE club_tid = <opp> AND season = ...
# AND phase = '...'` needs no macro, no USE, no per-caller reimplementation of the spell-date
# join. This replaces what dashboard/db.py's club_attributes() used to do inline (an EXISTS
# against mart.player_spells written fresh in Python) — that was itself a smaller instance of
# exactly the bug it was fixing: correctness logic re-derived outside the mart instead of
# defined once inside it. squad_current (below) is now just a filtered read of this.
SNAPSHOT_SQUAD = """
CREATE OR REPLACE VIEW mart.snapshot_squad AS
SELECT
    sn.season, sn.phase, sn.snap_ix, sn.phase_date,
    s.person_id,
    any_value(s.tid)                      AS tid,
    any_value(s.name)                     AS name,
    max(s.club_tid)                       AS club_tid,
    bool_or(s.spell_type = 'loan_in')     AS is_loan_in,
    min(s.valid_from)                     AS valid_from
FROM mart.snapshots sn
JOIN mart.player_spells s
     ON s.spell_type IN ('at_club', 'loan_in')
    AND sn.phase_date >= s.valid_from
    AND (s.valid_to IS NULL OR sn.phase_date <= s.valid_to)
GROUP BY sn.season, sn.phase, sn.snap_ix, sn.phase_date, s.person_id
"""

# The same question for "now, our clubs", as a VIEW rather than a macro — because a macro's
# body resolves unqualified names against the CURRENT catalog, so `m.mart.squad_on('...')` on
# an ATTACHed published artefact fails with "schema mart does not exist" (it looks for
# mart.player_spells in the caller's database, not in m). That is the documented way to read
# the artefact, so the most common question needs an object that survives it. `USE m` first
# also works, and is what you need for any other date or any other club (`snapshot_squad`,
# above).
SQUAD_CURRENT = """
CREATE OR REPLACE VIEW mart.squad_current AS
SELECT
    ss.person_id, ss.tid, ss.name, ss.club_tid, ss.is_loan_in,
    ss.club_tid IN (SELECT club_tid FROM mart.reserve_clubs) AS is_reserve,
    ss.valid_from,
    ss.phase_date AS as_of
FROM mart.snapshot_squad ss
JOIN (SELECT season, phase FROM mart.snapshots ORDER BY snap_ix DESC LIMIT 1) latest
  USING (season, phase)
WHERE ss.club_tid IN (SELECT club_tid FROM mart.our_clubs)
"""


# --- growth -----------------------------------------------------------------------

# Per player per snapshot, with the delta since that player's PREVIOUS snapshot.
#
# Three things make a naive "sum the 23 attributes and diff it" wrong here, and each is
# handled by a column rather than by dropping rows — the caller decides what to filter:
#
#  1. ESTIMATED ATTRIBUTES. Every player outside our squad carries model estimates
#     (24,472 of 24,472 at 2024-06-03 have Passing_est), and so do a few inside it. Diffing
#     an estimate measures the model re-estimating, not the player developing. `est_attrs`
#     counts how many of the 23 are estimated; `is_estimated` is the yes/no. Growth
#     analysis should filter to is_estimated = false.
#     (Corroboration for the loan-in ghosts: all 9 of them carry estimated attributes,
#     because the game is modelling them as outside players — which is what they are.)
#  2. KEEPER ATTRIBUTES ON OUTFIELDERS — see GK_ATTRS above. `attr_total` is role-aware.
#  3. IRREGULAR SNAPSHOT SPACING. Gaps here run from 1 day to 261, so raw deltas are not
#     comparable between players or periods. `days_elapsed` and `delta_per_365` make them
#     so. Consecutive snapshots 1-3 days apart legitimately produce a zero delta.
PLAYER_GROWTH = f"""
CREATE OR REPLACE VIEW mart.player_growth AS
WITH base AS (
    SELECT
        ps.person_id, p.tid, p.name, s.season, s.phase, s.snap_ix, s.phase_date,
        p.club_tid, p.club, p.is_gk, p.dob,
        CASE WHEN p.dob IS NULL THEN NULL
             ELSE DATE_DIFF('year', p.dob, s.phase_date)
                  - CASE WHEN (MONTH(s.phase_date), DAY(s.phase_date))
                            < (MONTH(p.dob), DAY(p.dob)) THEN 1 ELSE 0 END
        END                                                   AS age,
        ({_sum(OUTFIELD_ATTRS)})                              AS outfield_total,
        ({_sum(GK_ATTRS)})                                    AS gk_total,
        ({_sum(GK_BLOCK)})                                    AS gk_block_total,
        -- role-aware: each role sums the 18 attributes its role actually uses
        CASE WHEN p.is_gk = 1 THEN ({_sum(GK_ATTRS)})
             ELSE ({_sum(OUTFIELD_ATTRS)}) END                AS attr_total,
        ({_est_count(ATTR_ORDER)})                            AS est_attrs
    FROM {{S}}.players p
    JOIN {{S}}.player_attributes a USING (season, phase, tid)
    JOIN mart.snapshots s USING (season, phase)
    LEFT JOIN {{S}}.person_slices ps USING (season, phase, tid)
    WHERE NOT p.is_staff AND p.has_attributes
)
SELECT
    b.*,
    b.est_attrs > 0                                           AS is_estimated,
    -- LAG partitioned on person_id, never on tid alone: a recycled slot would otherwise
    -- diff a newgen against the retired player whose tid he inherited (rule 3).
    LAG(b.attr_total) OVER w                                  AS prev_attr_total,
    LAG(b.phase)      OVER w                                  AS prev_phase,
    LAG(b.est_attrs) OVER w > 0                               AS prev_is_estimated,
    b.attr_total - LAG(b.attr_total) OVER w                   AS delta,
    DATE_DIFF('day', LAG(b.phase_date) OVER w, b.phase_date)   AS days_elapsed,
    ROUND(365.0 * (b.attr_total - LAG(b.attr_total) OVER w)
          / NULLIF(DATE_DIFF('day', LAG(b.phase_date) OVER w, b.phase_date), 0), 1)
                                                              AS delta_per_365,
    -- A delta is only meaningful when BOTH endpoints are real reads. The step where a
    -- player joins us flips his attributes from model estimate to exact, so it produces a
    -- spurious delta of a point or two in either direction that has nothing to do with
    -- development (Garly reads -1 across exactly that step). Filter on this, not on
    -- is_estimated alone, whenever you are measuring growth.
    LAG(b.attr_total) OVER w IS NOT NULL
        AND b.est_attrs = 0
        AND LAG(b.est_attrs) OVER w = 0                       AS delta_comparable
FROM base b
WINDOW w AS (PARTITION BY b.person_id ORDER BY b.snap_ix)
"""

# Long form: one row per player per snapshot per attribute, with its own delta. This is
# the "WHICH attributes moved" view — a +11 total is a different story if it is all Pace
# than if it is spread across the mental attributes.
PLAYER_ATTRIBUTE_GROWTH = f"""
CREATE OR REPLACE VIEW mart.player_attribute_growth AS
WITH long AS (
    UNPIVOT (SELECT season, phase, tid, {", ".join(f'"{a}"' for a in ATTR_ORDER)}
             FROM {{S}}.player_attributes)
    ON {", ".join(f'"{a}"' for a in ATTR_ORDER)}
    INTO NAME attribute VALUE value
),
joined AS (
    SELECT ps.person_id, l.tid, p.name, s.season, s.phase, s.snap_ix, s.phase_date,
           l.attribute, l.value,
           l.attribute IN ({", ".join(f"'{a}'" for a in GK_BLOCK)}) AS is_gk_attr
    FROM long l
    JOIN {{S}}.players p USING (season, phase, tid)
    JOIN mart.snapshots s USING (season, phase)
    LEFT JOIN {{S}}.person_slices ps USING (season, phase, tid)
    WHERE NOT p.is_staff AND p.has_attributes
)
SELECT
    j.*,
    LAG(j.value) OVER w                     AS prev_value,
    j.value - LAG(j.value) OVER w           AS delta
FROM joined j
WINDOW w AS (PARTITION BY j.person_id, j.attribute ORDER BY j.snap_ix)
"""

# The season rollup — the shape the "who is still improving, who has stalled" question
# actually wants. First and last snapshot IN the season, so the near-duplicate snapshots
# a few days apart collapse harmlessly.
#
# NOTE it deliberately does NOT bake in a "stalled" verdict. Whether +2 is stalling
# depends on age, position and what you paid him; that is a judgement for the caller (or
# the dashboard), not a column. `growth`, `age` and `minutes` are what it needs to decide.
PLAYER_GROWTH_SEASON = """
CREATE OR REPLACE VIEW mart.player_growth_season AS
WITH ranked AS (
    SELECT g.*,
           ROW_NUMBER() OVER (PARTITION BY g.person_id, g.season ORDER BY g.snap_ix)      AS rn_first,
           ROW_NUMBER() OVER (PARTITION BY g.person_id, g.season ORDER BY g.snap_ix DESC) AS rn_last
    FROM mart.player_growth g
),
bounds AS (
    SELECT
        person_id, season,
        MAX(CASE WHEN rn_first = 1 THEN tid END)            AS tid,
        MAX(CASE WHEN rn_last  = 1 THEN name END)           AS name,
        MAX(CASE WHEN rn_last  = 1 THEN club_tid END)       AS club_tid,
        MAX(CASE WHEN rn_last  = 1 THEN is_gk END)          AS is_gk,
        MAX(CASE WHEN rn_last  = 1 THEN age END)            AS age,
        MAX(CASE WHEN rn_first = 1 THEN phase END)          AS first_phase,
        MAX(CASE WHEN rn_last  = 1 THEN phase END)          AS last_phase,
        MAX(CASE WHEN rn_first = 1 THEN phase_date END)     AS first_date,
        MAX(CASE WHEN rn_last  = 1 THEN phase_date END)     AS last_date,
        MAX(CASE WHEN rn_first = 1 THEN attr_total END)     AS start_total,
        MAX(CASE WHEN rn_last  = 1 THEN attr_total END)     AS end_total,
        BOOL_OR(CASE WHEN rn_first = 1 THEN is_estimated END) AS start_estimated,
        BOOL_OR(CASE WHEN rn_last  = 1 THEN is_estimated END) AS end_estimated,
        BOOL_OR(is_estimated)                               AS any_estimated,
        COUNT(*)                                            AS snapshots
    FROM ranked GROUP BY person_id, season
),
mins AS (
    SELECT person_id, season, SUM(minutes) AS minutes, SUM(apps) AS apps
    FROM mart.player_seasons GROUP BY person_id, season
)
SELECT
    b.*,
    b.end_total - b.start_total                                     AS growth,
    -- Same rule as delta_comparable: both endpoints must be real reads, or the "growth"
    -- is partly the model handing over to exact data. A season in which the player joined
    -- us is exactly the case this catches.
    NOT b.start_estimated AND NOT b.end_estimated                   AS growth_comparable,
    DATE_DIFF('day', b.first_date, b.last_date)                     AS days_observed,
    ROUND(365.0 * (b.end_total - b.start_total)
          / NULLIF(DATE_DIFF('day', b.first_date, b.last_date), 0), 1) AS growth_per_365,
    COALESCE(m.minutes, 0)                                          AS minutes,
    COALESCE(m.apps, 0)                                             AS apps
FROM bounds b
LEFT JOIN mins m USING (person_id, season)
"""


# Growth bounded by a CLUB SPELL rather than by a season — "how much has he grown since we
# bought him". A season rollup understates a long-serving player badly: Garly reads +11 for
# 2024 alone but +36 across his whole time here, because his big step (+24) landed in 2023.
# Keyed on mart.club_runs so each stint at a club is its own row; a player who left and
# came back gets two.
#
# KNOWN, NOT FIXED HERE: unlike player_growth_tenure (fixed 2026-09-01 to gate `ours` on
# mart.player_spells), this still keys off mart.club_runs directly, which is raw
# staging.players.club_tid — exposed to the same lapsed-loan ghost (see the GHOST NOTE on
# mart.at_club_spells: "club_runs itself is untouched, so growth-at-club tracking for loan
# spells is unaffected" — a deliberate call at the time, not an oversight, but the same class
# of bug player_growth_tenure just got fixed for). A lapsed loanee's run here still spans
# from his real loan to the newest snapshot, same fabricated-tenure shape. Not fixed in this
# pass because it needs a real redesign, not a one-line EXISTS swap: club_runs is keyed by
# run_id derived from raw club_tid continuity, and player_growth_at_club's whole grouping
# (`joined AS ... JOIN mart.club_runs cr`) would need to key on spell windows instead. Lower
# priority than player_growth_tenure was: not read by export_data.py or dashboard/db.py
# today (grep confirms only fmparser/mart.py and scripts/publish_mart.py reference it), so
# nothing user-facing is currently corrupted by it — but a remote agent querying this mart
# object directly would be.
PLAYER_GROWTH_AT_CLUB = """
CREATE OR REPLACE VIEW mart.player_growth_at_club AS
WITH joined AS (
    SELECT
        cr.person_id, cr.club_tid, cr.club, cr.run_id,
        g.snap_ix, g.tid, g.name, g.phase, g.phase_date, g.age, g.attr_total, g.is_estimated,
        ROW_NUMBER() OVER (PARTITION BY cr.person_id, cr.run_id ORDER BY g.snap_ix)      AS rn_first,
        ROW_NUMBER() OVER (PARTITION BY cr.person_id, cr.run_id ORDER BY g.snap_ix DESC) AS rn_last
    FROM mart.club_runs cr
    JOIN mart.player_growth g
      ON g.person_id = cr.person_id AND g.snap_ix BETWEEN cr.from_ix AND cr.to_ix
),
bounds AS (
    SELECT
        person_id, club_tid, run_id,
        MAX(CASE WHEN rn_last  = 1 THEN tid END)          AS tid,
        MAX(CASE WHEN rn_last  = 1 THEN name END)         AS name,
        MAX(CASE WHEN rn_last  = 1 THEN club END)         AS club,
        MAX(CASE WHEN rn_first = 1 THEN phase END)        AS joined_phase,
        MAX(CASE WHEN rn_last  = 1 THEN phase END)        AS last_phase,
        MAX(CASE WHEN rn_first = 1 THEN phase_date END)   AS joined_date,
        MAX(CASE WHEN rn_last  = 1 THEN phase_date END)   AS last_date,
        MAX(CASE WHEN rn_first = 1 THEN age END)          AS age_on_arrival,
        MAX(CASE WHEN rn_last  = 1 THEN age END)          AS age_now,
        MAX(CASE WHEN rn_first = 1 THEN attr_total END)   AS start_total,
        MAX(CASE WHEN rn_last  = 1 THEN attr_total END)   AS end_total,
        BOOL_OR(CASE WHEN rn_first = 1 THEN is_estimated END) AS start_estimated,
        BOOL_OR(CASE WHEN rn_last  = 1 THEN is_estimated END) AS end_estimated,
        COUNT(*)                                          AS snapshots
    FROM joined GROUP BY person_id, club_tid, run_id
)
SELECT
    b.*,
    b.end_total - b.start_total                                          AS growth,
    NOT b.start_estimated AND NOT b.end_estimated                        AS growth_comparable,
    DATE_DIFF('day', b.joined_date, b.last_date)                         AS days_at_club,
    ROUND(365.0 * (b.end_total - b.start_total)
          / NULLIF(DATE_DIFF('day', b.joined_date, b.last_date), 0), 1)  AS growth_per_365
FROM bounds b
"""


# Growth over a contiguous TENURE at our clubs, treating the first team and the reserves as
# one place. mart.player_growth_at_club splits on club_tid, which is right for the spells
# model (a drop to the reserves IS a club change in the data) but fragments the "since we
# signed him" question: a player who bounces 346 <-> 7296 gets a row per stint, so
# Moller-Jensen shows up four times and none of the rows is his real growth here.
#
# `ours` is spell-based (EXISTS against mart.player_spells), not a raw `g.club_tid` check —
# see the GHOST NOTE on mart.at_club_spells above for why the raw column can't be trusted:
# `staging.players.club_tid` is a per-snapshot fact, but a lapsed loan leaves it pointing at
# us indefinitely (the squad-list record is written once and never cleared). A raw check
# here fabricated a 967-day, +24-attribute "tenure" for Ernest Nuamah (2022-03-19 through the
# newest snapshot) out of a loan that actually ended 2023-06-30 — confirmed against the raw
# save bytes, not a hypothetical. `mart.player_spells` already answers "was he genuinely
# here on this date" correctly (that's what `mart.squad_on`/`squad_current` are built from);
# this reuses the identical check per growth row instead of re-deriving it from club_tid.
PLAYER_GROWTH_TENURE = """
CREATE OR REPLACE VIEW mart.player_growth_tenure AS
WITH pc AS (
    SELECT g.person_id, g.tid, g.name, g.snap_ix, g.phase, g.phase_date, g.age,
           g.attr_total, g.is_estimated, g.is_gk,
           EXISTS (
               SELECT 1 FROM mart.player_spells sp
               WHERE sp.person_id = g.person_id
                 AND sp.spell_type IN ('at_club', 'loan_in')
                 AND sp.club_tid IN (SELECT club_tid FROM mart.our_clubs)
                 AND g.phase_date >= sp.valid_from
                 AND (sp.valid_to IS NULL OR g.phase_date <= sp.valid_to)
           )                                                        AS ours
    FROM mart.player_growth g
),
marked AS (
    SELECT *, CASE WHEN ours IS DISTINCT FROM
                     LAG(ours) OVER (PARTITION BY person_id ORDER BY snap_ix)
                   THEN 1 ELSE 0 END AS chg
    FROM pc
),
stints AS (
    SELECT *, SUM(chg) OVER (PARTITION BY person_id ORDER BY snap_ix) AS stint
    FROM marked
),
ranked AS (
    SELECT *,
        ROW_NUMBER() OVER (PARTITION BY person_id, stint ORDER BY snap_ix)      AS rn_first,
        ROW_NUMBER() OVER (PARTITION BY person_id, stint ORDER BY snap_ix DESC) AS rn_last
    FROM stints WHERE ours
),
bounds AS (
    SELECT
        person_id, stint,
        MAX(CASE WHEN rn_last  = 1 THEN tid END)              AS tid,
        MAX(CASE WHEN rn_last  = 1 THEN name END)             AS name,
        MAX(CASE WHEN rn_last  = 1 THEN is_gk END)            AS is_gk,
        MAX(CASE WHEN rn_first = 1 THEN phase END)            AS joined_phase,
        MAX(CASE WHEN rn_last  = 1 THEN phase END)            AS last_phase,
        MAX(CASE WHEN rn_first = 1 THEN phase_date END)       AS joined_date,
        MAX(CASE WHEN rn_last  = 1 THEN phase_date END)       AS last_date,
        MAX(CASE WHEN rn_first = 1 THEN age END)              AS age_on_arrival,
        MAX(CASE WHEN rn_last  = 1 THEN age END)              AS age_now,
        MAX(CASE WHEN rn_first = 1 THEN attr_total END)       AS start_total,
        MAX(CASE WHEN rn_last  = 1 THEN attr_total END)       AS end_total,
        BOOL_OR(CASE WHEN rn_first = 1 THEN is_estimated END) AS start_estimated,
        BOOL_OR(CASE WHEN rn_last  = 1 THEN is_estimated END) AS end_estimated,
        COUNT(*)                                              AS snapshots
    FROM ranked GROUP BY person_id, stint
)
SELECT
    b.*,
    b.end_total - b.start_total                                          AS growth,
    NOT b.start_estimated AND NOT b.end_estimated                        AS growth_comparable,
    DATE_DIFF('day', b.joined_date, b.last_date)                         AS days_at_club,
    ROUND(365.0 * (b.end_total - b.start_total)
          / NULLIF(DATE_DIFF('day', b.joined_date, b.last_date), 0), 1)  AS growth_per_365
FROM bounds b
"""


# --- squad registration: homegrown status and the A/B lists -------------------------
#
# FMM22 does not model squad registration at all, so none of this is read out of the save:
# it is the Danish Herre-DM rulebook (docs/danish-registration-rules.md) applied to save
# data, as a SELF-IMPOSED house rule. The A-list is capped at 25 and, in the top two tiers,
# must contain 8 "Home Grown" players of whom at least 4 were trained at the club itself;
# the B-list is unlimited but only takes players who were under 21 at the last new year.
#
# The rulebook's Home Grown test is "eligible to play at the club for 36 months in total
# between the start of the season he turns 15 and the end of the season he turns 21" — we run
# one season longer, to the end of the season he turns 22; see PLAYER_TRAINING. Three
# things in the save carry that:
#
#   1. `player_history.origin_club_tid` — the head of the career-history chain, i.e. the club
#      he came out of. For most players this is a real club tid; for an academy product it is
#      a YOUTH-TEAM tid that appears in no club table (see mart.youth_clubs).
#   2. `mart.player_career_seasons` — one row per season per club, which is a dated timeline
#      once you map a season to Jul-Jun and split a multi-club season across its legs.
#   3. `mart.at_club_spells` — what WE observed across the snapshots, which fills the gap
#      where the career history has not written the in-progress season yet (real case: Johan
#      Nordberg, at the club since 2022 with no 24/25 history row at the 2024-11-10 snapshot).
#
# Sources 2 and 3 overlap, so they are unioned as dated intervals and merged (gaps-and-
# islands) before any month is counted — adding two months figures would double-count every
# season we watched happen.

# Nation for every club, with a fallback for the ones whose league carries none.
#
# `mart.clubs.nation` comes from the club's league, and the save parks its unplayable clubs
# in league buckets that have no name and no nation (cid 245 holds 82 obviously-Danish clubs
# — Dragor BK, Nexo BK Bornholm, Silkeborg BK). Three of our own squad's origin clubs sit
# there, so "was he trained at a Danish club" would be unanswerable for them.
#
# The fallback is a two-step vote and needs no hardcoded nation table: first learn what each
# `nationality_id` MEANS by asking which nation's leagues its players actually play in
# (nationality 138 -> Denmark, 139 -> England, ...), then give a nation-less league the modal
# nation of its own players. Confidence is reported rather than hidden, because a league of
# 46 players voting 138 is a much better bet than one of 3.
CLUB_NATIONS = """
CREATE OR REPLACE VIEW mart.club_nations AS
WITH nat_votes AS (
    SELECT p.season, p.phase, p.nationality_id, cl.nation, COUNT(*) AS n
    FROM {S}.players p
    JOIN mart.club_leagues cl
      ON (cl.season, cl.phase, cl.club_tid) = (p.season, p.phase, p.club_tid)
    WHERE NOT p.is_staff AND cl.nation IS NOT NULL AND p.nationality_id IS NOT NULL
    GROUP BY ALL),
nat_nation AS (
    SELECT season, phase, nationality_id, ARG_MAX(nation, n) AS nation
    FROM nat_votes GROUP BY season, phase, nationality_id),
league_votes AS (
    SELECT cl.season, cl.phase, cl.league_cid, nn.nation, COUNT(*) AS n
    FROM {S}.players p
    JOIN mart.club_leagues cl
      ON (cl.season, cl.phase, cl.club_tid) = (p.season, p.phase, p.club_tid)
    JOIN nat_nation nn
      ON (nn.season, nn.phase, nn.nationality_id) = (p.season, p.phase, p.nationality_id)
    WHERE NOT p.is_staff AND cl.nation IS NULL AND cl.league_cid IS NOT NULL
    GROUP BY ALL),
league_nation AS (
    SELECT season, phase, league_cid, ARG_MAX(nation, n) AS nation,
           ROUND(MAX(n) * 1.0 / SUM(n), 2) AS share, SUM(n) AS voters
    FROM league_votes GROUP BY season, phase, league_cid)
SELECT
    c.season, c.phase, c.club_tid, c.name, c.league_cid,
    COALESCE(c.nation, ln.nation)                                       AS nation,
    CASE WHEN c.nation IS NOT NULL THEN 'league'
         WHEN ln.nation IS NOT NULL THEN 'inferred' END                 AS nation_source,
    CASE WHEN c.nation IS NOT NULL THEN 1.0 ELSE ln.share END           AS nation_confidence,
    ln.voters                                                           AS nation_voters
FROM mart.clubs c
LEFT JOIN league_nation ln
       ON (ln.season, ln.phase, ln.league_cid) = (c.season, c.phase, c.league_cid)
"""

# Youth/academy team tids -> the senior club they belong to.
#
# An academy product's origin club is a tid in the ~64000-65534 band that exists in no club
# table, so it renders as '#65189' and resolves to nothing. It is not garbage: the players
# sharing one of these tids are overwhelmingly at ONE club (65064 -> Liverpool, 65104 ->
# Chelsea, 64896 -> Bayern, 65189 -> us), with the strays being academy graduates who moved
# on — exactly the shape of a youth side. So the mapping is recoverable by asking where each
# cohort actually ended up.
#
# 65535 is excluded: it is 0xFFFF, the u16 "none" sentinel, not a club.
#
# Reserve sides vote for their first team, otherwise our own academy would map to Boldklubben
# Frem Reserves half the time. Only OUR reserve side is known to be a reserve side, which is
# fine — for a foreign academy the answer only has to be good enough to carry a nation, and
# "Liverpool Reserves" is as English as "Liverpool".
#
# `share` and `alumni` ship so a caller can refuse a weak mapping: cohorts average 2.8 players
# and 143 of the 388 are singletons, where the "majority" is one player.
YOUTH_CLUBS = """
CREATE OR REPLACE VIEW mart.youth_clubs AS
WITH alumni AS (
    SELECT o.season, o.phase, o.origin_club_tid AS youth_tid,
           CASE WHEN ps.club_tid IN (SELECT club_tid FROM mart.our_clubs)
                THEN (SELECT club_tid FROM mart.managed_club)
                ELSE ps.club_tid END                                    AS club_tid,
           COUNT(*)                                                     AS n
    FROM mart.player_origin o
    JOIN mart.player_snapshots ps USING (season, phase, tid)
    WHERE o.origin_club_tid IS NOT NULL
      AND o.origin_club_tid <> 65535
      AND ps.club_tid IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM mart.clubs c
                      WHERE (c.season, c.phase, c.club_tid)
                          = (o.season, o.phase, o.origin_club_tid))
    GROUP BY ALL)
SELECT season, phase, youth_tid,
       ARG_MAX(club_tid, n)                     AS club_tid,
       ROUND(MAX(n) * 1.0 / SUM(n), 2)          AS share,
       SUM(n)                                   AS alumni
FROM alumni GROUP BY season, phase, youth_tid
"""

# Months a player was registered at each club INSIDE his home-grown window, as evidence.
#
# The window runs from the start of the season in which he turns 15 to the end of the LAST
# SEASON IN WHICH HE IS STILL 21 — i.e. the season he turns 22. `season_of` already knows a
# campaign runs Jul-Jun and is named for its end year, so both bounds are one macro call.
#
# THAT UPPER BOUND IS ONE SEASON LATER THAN A LITERAL READING of TR 14.1, which says "the end
# of the season in which he turns 21", and the departure is deliberate (manager's call,
# 2026-08). Under the literal text a March-born player's window shuts the June he is 21 and
# three months old, while an autumn-born player in the same position keeps accruing for another
# nine months purely on his birthday. Andreas Garly — four seasons at the club and still 21 on
# the day of this snapshot — closed out on 35.9 months and missed club-trained status
# permanently by a tenth of a month, which is well inside the error of the even-leg split below.
# Running to the end of the season he turns 22 gives every player his full seventh season and
# takes the birthday lottery out of the borderline cases.
#
# Career history is turned into dated intervals rather than counted as seasons, so that it can
# be merged with what we observed. A season with several legs (a mid-season loan) splits the
# Jul-Jun span evenly across its legs in `seq` order — an approximation, because the save
# stores no transfer date, and a deliberately visible one: the alternative of crediting each
# leg a full season would hand a player 24 months for one year of football.
#
# A LOAN LEG CREDITS THE HOST, NOT THE PARENT. That follows TR 15.2 (a loaned player is a
# member of the club he plays for) and is flagged as an inference in
# docs/danish-registration-rules.md, not as a sourced rule. It is also the reading that costs
# us something — Adelgaard's 23/24 loan to Frederiksberg is six months he does not accrue
# with us — so it is the conservative one.
PLAYER_TRAINING = """
CREATE OR REPLACE VIEW mart.player_training AS
WITH at_date AS (
    SELECT season, phase, COALESCE(phase_date, season_end(season)) AS as_of
    FROM mart.snapshots),
win AS (
    SELECT ps.season, ps.phase, ps.tid, ps.person_id, ps.dob,
           season_start(season_of(ps.dob + INTERVAL 15 YEAR)) AS window_from,
           season_end(season_of(ps.dob + INTERVAL 22 YEAR))   AS window_to
    FROM mart.player_snapshots ps
    WHERE ps.dob IS NOT NULL),
-- one interval per career-history leg
legs AS (
    SELECT h.season, h.phase, h.tid, h.club_tid, h.end_year, h.fee,
           ROW_NUMBER() OVER (PARTITION BY h.season, h.phase, h.tid, h.end_year
                              ORDER BY h.seq)                          AS leg,
           COUNT(*)     OVER (PARTITION BY h.season, h.phase, h.tid, h.end_year) AS legs
    FROM mart.player_career_seasons h
    WHERE h.club_tid IS NOT NULL AND h.end_year IS NOT NULL),
hist AS (
    SELECT season, phase, tid, club_tid, 'history' AS src,
           season_start(end_year)
             + CAST((leg - 1) * 364 / legs AS INTEGER)     AS d_from,
           season_start(end_year)
             + CAST(leg * 364 / legs AS INTEGER)           AS d_to
    FROM legs),
-- and one per spell we watched happen, keyed on person_id because a tid is a recycled slot
-- (tid 3505 was Mark Reynolds at Vejgaard before it was Johan Maarup here)
obs AS (
    SELECT w.season, w.phase, w.tid, s.club_tid, 'observed' AS src,
           CAST(s.valid_from AS DATE)                                   AS d_from,
           LEAST(CAST(COALESCE(s.valid_to, a.as_of) AS DATE), a.as_of)  AS d_to
    FROM mart.at_club_spells s
    JOIN win w ON w.person_id = s.person_id
    JOIN at_date a ON (a.season, a.phase) = (w.season, w.phase)
    WHERE s.club_tid IS NOT NULL AND CAST(s.valid_from AS DATE) <= a.as_of),
clipped AS (
    SELECT i.season, i.phase, i.tid,
           CASE WHEN i.club_tid IN (SELECT club_tid FROM mart.our_clubs)
                THEN (SELECT club_tid FROM mart.managed_club)
                ELSE i.club_tid END                                     AS club_tid,
           GREATEST(i.d_from, w.window_from)                            AS d_from,
           LEAST(i.d_to, w.window_to, a.as_of)                          AS d_to
    FROM (SELECT * FROM hist UNION ALL SELECT * FROM obs) i
    JOIN win  w USING (season, phase, tid)
    JOIN at_date a USING (season, phase)),
-- merge overlapping intervals per club before counting, or the two sources double-count
-- every season we watched happen
marked AS (
    SELECT *, CASE WHEN prev_end IS NULL OR d_from > prev_end + 1 THEN 1 ELSE 0 END AS new_island
    FROM (SELECT c.*, MAX(d_to) OVER (PARTITION BY season, phase, tid, club_tid
                                      ORDER BY d_from, d_to
                                      ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)
                      AS prev_end
          FROM clipped c WHERE d_to > d_from)),
islands AS (
    SELECT *, SUM(new_island) OVER (PARTITION BY season, phase, tid, club_tid
                                    ORDER BY d_from, d_to) AS island
    FROM marked)
SELECT season, phase, tid, club_tid,
       ROUND(SUM(days) / 30.44, 1)  AS months,
       SUM(days)                    AS days,
       MIN(d_from)                  AS first_from,
       MAX(d_to)                    AS last_to
FROM (SELECT season, phase, tid, club_tid, island,
             MIN(d_from) AS d_from, MAX(d_to) AS d_to,
             DATE_DIFF('day', MIN(d_from), MAX(d_to)) AS days
      FROM islands GROUP BY season, phase, tid, club_tid, island)
GROUP BY season, phase, tid, club_tid
"""

# One row per player: is he Home Grown, at us or at another club of our association?
#
# HG-AT-CLUB IS ACADEMY-OR-CLOCK, and the academy half is a deliberate departure from a
# literal reading of the save. FMM only brings an intake player into existence at ~16, so a
# strict 36-month clock would call a player our own academy produced NOT home grown until he
# is 19 — backwards from the rule, where his youth registration already counts. Origin =
# our academy is therefore taken as club-trained outright (manager's call, 2026-08), and the
# clock is what SIGNED players earn it on. `hg_club_basis` says which of the two fired, and
# `months_club` ships regardless, so the strict reading is one predicate away.
#
# HG-AT-ASSOCIATION (the "trained at another Danish club" half of the 8) accepts a Danish
# ORIGIN club as well as 36 clocked months, because the history slab only reaches back so
# far: a 34-year-old's eligibility window predates every row he has, so the clock can only
# ever read zero for him. Origin is the sole surviving evidence there.
#
# THE ORIGIN CLUB IS THE YOUTH CLUB, whenever it resolves at all — so origin = us is
# club-trained outright, with no age test on top. An earlier version gated it behind "his
# first recorded season starts at 18 or younger", on the theory that a first Frem season at
# 19 says where he SIGNED rather than where he trained. That theory is wrong, and the data
# says so plainly: Mikkel Bruhn (34) and Daniel S. Jørgensen (33) both have their first
# recorded season at 21, yet their origin clubs read Espergærde IF and Næstved BK — their
# real youth clubs, not whoever they played for at 21. The chain head is stored
# independently of where the recorded seasons begin, which is exactly why a player signed
# from elsewhere at 19 gets THAT club as his origin, not us. So an origin of us can only
# mean he came out of us. (The gate had been marking Christian Bramsborg and Oliver
# Møller-Jensen, both origin: Boldklubben Frem, as not club-trained.)
#
# `age_at_first_season` is still carried, as evidence for a human reading a borderline case,
# but nothing branches on it.
PLAYER_HOMEGROWN = """
CREATE OR REPLACE VIEW mart.player_homegrown AS
WITH us AS (SELECT club_tid FROM mart.managed_club),
our_nation AS (
    SELECT ANY_VALUE(nation) AS nation FROM mart.club_nations
    WHERE club_tid IN (SELECT club_tid FROM us) AND nation IS NOT NULL),
at_date AS (
    SELECT season, phase, COALESCE(phase_date, season_end(season)) AS as_of
    FROM mart.snapshots),
first_season AS (
    SELECT season, phase, tid, MIN(end_year) AS first_end_year
    FROM mart.player_career_seasons WHERE end_year IS NOT NULL
    GROUP BY ALL),
origin AS (
    SELECT o.season, o.phase, o.tid, o.origin_club_tid,
           COALESCE(y.club_tid, o.origin_club_tid)  AS origin_parent_tid,
           y.youth_tid IS NOT NULL                  AS via_academy,
           y.share                                  AS academy_share,
           f.first_end_year,
           -- Carried as EVIDENCE only, never as a test. Completed age, not the difference of
           -- year parts: DATE_DIFF('year', ...) alone reads 18 for an autumn-born 17-year-old.
           DATE_DIFF('year', ps.dob, season_start(f.first_end_year))
             - CASE WHEN (MONTH(season_start(f.first_end_year)),
                          DAY(season_start(f.first_end_year)))
                        < (MONTH(ps.dob), DAY(ps.dob)) THEN 1 ELSE 0 END
                                                    AS age_at_first_season
    FROM mart.player_origin o
    JOIN mart.player_snapshots ps USING (season, phase, tid)
    LEFT JOIN mart.youth_clubs y
           ON (y.season, y.phase, y.youth_tid) = (o.season, o.phase, o.origin_club_tid)
    LEFT JOIN first_season f USING (season, phase, tid)
    WHERE o.origin_club_tid IS NOT NULL AND o.origin_club_tid <> 65535
      AND ps.dob IS NOT NULL),
mine AS (
    SELECT season, phase, tid, months, last_to FROM mart.player_training
    WHERE club_tid IN (SELECT club_tid FROM us)),
domestic AS (
    SELECT t.season, t.phase, t.tid,
           MAX(t.months)                    AS months,
           ARG_MAX(t.club_tid, t.months)    AS club_tid
    FROM mart.player_training t
    JOIN mart.club_nations cn
      ON (cn.season, cn.phase, cn.club_tid) = (t.season, t.phase, t.club_tid)
    WHERE cn.nation = (SELECT nation FROM our_nation)
      AND t.club_tid NOT IN (SELECT club_tid FROM us)
    GROUP BY ALL)
SELECT
    ps.season, ps.phase, ps.tid, ps.person_id, ps.name, ps.dob, ps.age, ps.club_tid,
    season_start(season_of(ps.dob + INTERVAL 15 YEAR))          AS window_from,
    season_end(season_of(ps.dob + INTERVAL 22 YEAR))            AS window_to,
    a.as_of <= season_end(season_of(ps.dob + INTERVAL 22 YEAR)) AS window_open,
    o.origin_club_tid, o.origin_parent_tid, o.via_academy, o.academy_share,
    o.age_at_first_season,
    oc.name                                                     AS origin_club,
    oc.nation                                                   AS origin_nation,
    oc.nation_source                                            AS origin_nation_source,
    COALESCE(m.months, 0)                                       AS months_club,
    COALESCE(d.months, 0)                                       AS months_domestic,
    d.club_tid                                                  AS domestic_club_tid,
    dc.name                                                     AS domestic_club,
    -- club-trained: he came out of our club, or he clocked 36 months with us in the window
    COALESCE(o.origin_parent_tid IN (SELECT club_tid FROM us), FALSE)
      OR COALESCE(m.months, 0) >= 36                            AS hg_club,
    CASE WHEN o.origin_parent_tid IN (SELECT club_tid FROM us)
              THEN CASE WHEN o.via_academy THEN 'academy' ELSE 'youth-origin' END
         WHEN COALESCE(m.months, 0) >= 36 THEN 'clock' END      AS hg_club_basis,
    -- Association-trained: the same test, at any club of our nation (us included), so it is
    -- satisfied by every club-trained player plus everyone whose origin club is domestic.
    -- Nearly free for this career, where the capital-region signing rule already means the
    -- whole squad came out of a Danish club — the quota that actually binds is the club half.
    COALESCE(o.origin_parent_tid IN (SELECT club_tid FROM us), FALSE)
      OR COALESCE(m.months, 0) >= 36
      OR COALESCE(oc.nation = (SELECT nation FROM our_nation), FALSE)
      OR COALESCE(d.months, 0) >= 36                            AS hg_association,
    -- how much further he has to go, and when he gets there if he stays. The ETA is NULL
    -- once the arithmetic runs past his window: he cannot get there any more, and a date
    -- pinned to the window's last day would read as a deadline he still meets.
    CASE WHEN COALESCE(m.months, 0) < 36
         THEN ROUND(36 - COALESCE(m.months, 0), 1) END          AS months_to_hg_club,
    CASE WHEN COALESCE(m.months, 0) < 36
              AND ps.club_tid IN (SELECT club_tid FROM mart.our_clubs)
              AND a.as_of + CAST((36 - COALESCE(m.months, 0)) * 30.44 AS INTEGER)
                  <= season_end(season_of(ps.dob + INTERVAL 22 YEAR))
         THEN a.as_of + CAST((36 - COALESCE(m.months, 0)) * 30.44 AS INTEGER)
         END                                                    AS hg_club_eta
FROM mart.player_snapshots ps
JOIN at_date a USING (season, phase)
LEFT JOIN origin o USING (season, phase, tid)
LEFT JOIN mart.club_nations oc
       ON (oc.season, oc.phase, oc.club_tid) = (ps.season, ps.phase, o.origin_parent_tid)
LEFT JOIN mine     m USING (season, phase, tid)
LEFT JOIN domestic d USING (season, phase, tid)
LEFT JOIN mart.club_nations dc
       ON (dc.season, dc.phase, dc.club_tid) = (ps.season, ps.phase, d.club_tid)
WHERE ps.dob IS NOT NULL
"""

# The registration rules that apply to US this season, as data rather than as constants in
# the app. The homegrown minimums bind only in the top two tiers (TR 14.1 vs 14.2) and we
# have been promoted three times in three seasons, so which set applies is a moving target —
# derived from where our division sits in its nation's reputation order, not hardcoded.
REGISTRATION_RULES = """
CREATE OR REPLACE VIEW mart.registration_rules AS
WITH ours AS (
    SELECT cl.season, cl.phase, cl.league_cid, cl.nation
    FROM mart.club_leagues cl
    WHERE cl.club_tid IN (SELECT club_tid FROM mart.managed_club)),
tier AS (
    SELECT o.season, o.phase, o.league_cid, o.nation,
           (SELECT COUNT(*) FROM mart.leagues l
             WHERE l.season = o.season AND l.phase = o.phase
               AND l.nation IS NOT DISTINCT FROM o.nation
               AND l.type = 'league' AND l.reputation IS NOT NULL
               AND l.reputation > (SELECT ANY_VALUE(l2.reputation) FROM mart.leagues l2
                                    WHERE (l2.season, l2.phase, l2.cid)
                                        = (o.season, o.phase, o.league_cid))) + 1 AS tier
    FROM ours o)
SELECT t.season, t.phase, t.league_cid, t.nation, t.tier,
       (SELECT ANY_VALUE(name) FROM mart.leagues l
         WHERE (l.season, l.phase, l.cid) = (t.season, t.phase, t.league_cid)) AS league_name,
       25                                        AS a_list_max,
       CASE WHEN t.tier <= 2 THEN 8 ELSE 0 END   AS hg_min,
       CASE WHEN t.tier <= 2 THEN 4 ELSE 0 END   AS hg_club_min,
       21                                        AS b_list_under_age,
       16                                        AS min_matchday_age
FROM tier t
"""

# Our squad, ready to be registered: who is A-list material, who rides free on the B-list,
# and what each of them contributes to the homegrown quotas.
#
# B-LIST ELIGIBILITY IS A FIXED DATE, NOT AN AGE. "Under 21 at the last new year before the
# tournament year" (TR 14.1) means 1 January of the season's first calendar half, so a player
# born 7 January 2003 is B-list for all of 24/25 while a 21-year-old born in November is not.
# Using `age` instead would drop players out of the B-list mid-season, which the rule never
# does.
SQUAD_REGISTRATION = """
CREATE OR REPLACE VIEW mart.squad_registration AS
WITH sq AS (
    SELECT person_id, tid, ANY_VALUE(name) AS name, MAX(club_tid) AS club_tid,
           BOOL_OR(is_loan_in) AS is_loan_in, BOOL_OR(is_reserve) AS is_reserve,
           ANY_VALUE(as_of) AS as_of
    FROM mart.squad_current GROUP BY person_id, tid),
snap AS (SELECT season, phase FROM mart.snapshots
         ORDER BY season DESC, phase_ord DESC LIMIT 1),
r AS (SELECT * FROM mart.registration_rules
      WHERE (season, phase) IN (SELECT season, phase FROM snap))
SELECT
    s.season, s.phase, sq.person_id, sq.tid, sq.name, sq.club_tid,
    sq.is_loan_in, sq.is_reserve, h.age, h.dob,
    MAKE_DATE(s.season - 1, 1, 1)                               AS u21_on,
    h.dob > MAKE_DATE(s.season - 1 - 21, 1, 1)                  AS b_list_eligible,
    h.hg_club, h.hg_club_basis, h.hg_association,
    h.months_club, h.months_to_hg_club, h.hg_club_eta, h.window_open,
    h.origin_club, h.origin_nation, h.via_academy,
    r.a_list_max, r.hg_min, r.hg_club_min, r.tier, r.league_name
FROM snap s
CROSS JOIN sq
LEFT JOIN mart.player_homegrown h
       ON (h.season, h.phase, h.tid) = (s.season, s.phase, sq.tid)
LEFT JOIN r ON TRUE
"""


ORDER = [
    ("mart.snapshots", SNAPSHOTS),
    ("mart.role_weights", ROLE_WEIGHTS),
    ("mart.position_roles", POSITION_ROLES),
    ("mart.app_config", APP_CONFIG),
    ("mart.our_clubs", OUR_CLUBS),
    ("mart.chosen_match_phase", CHOSEN_MATCH_PHASE),
    ("mart.match_player_facts", MATCH_PLAYER_FACTS),
    ("mart.matches", MATCHES),
    ("mart.club_matches", CLUB_MATCHES),
    ("mart.managed_club", MANAGED_CLUB),
    ("mart.reserve_clubs", RESERVE_CLUBS),
    ("mart.club_leagues", CLUB_LEAGUES),
    ("mart.clubs", CLUBS),
    ("mart.leagues", LEAGUES),
    ("mart.comparison_ladder", COMPARISON_LADDER),
    ("mart.player_snapshots", PLAYER_SNAPSHOTS),
    ("mart.player_position_levels", PLAYER_POSITION_LEVELS),
    ("mart.player_career_seasons", PLAYER_CAREER_SEASONS),
    ("mart.player_origin", PLAYER_ORIGIN),
    ("mart.player_role_ratings", PLAYER_ROLE_RATINGS),
    ("mart.player_position_fit", PLAYER_POSITION_FIT),
    ("mart.player_seasons", PLAYER_SEASONS),
    ("mart.club_runs", CLUB_RUNS),
    ("mart.at_club_spells", AT_CLUB),
    ("mart.loan_in_spells", LOAN_IN),
    ("mart.loan_out_spells", LOAN_OUT),
    ("mart.injury_spells", INJURED),
    ("mart.player_spells", PLAYER_SPELLS),
    ("mart.squad_on", SQUAD_ON),
    ("mart.snapshot_squad", SNAPSHOT_SQUAD),
    ("mart.squad_current", SQUAD_CURRENT),
    ("mart.player_growth", PLAYER_GROWTH),
    ("mart.player_attribute_growth", PLAYER_ATTRIBUTE_GROWTH),
    ("mart.player_growth_season", PLAYER_GROWTH_SEASON),
    ("mart.player_growth_at_club", PLAYER_GROWTH_AT_CLUB),
    ("mart.player_growth_tenure", PLAYER_GROWTH_TENURE),
    ("mart.club_nations", CLUB_NATIONS),
    ("mart.youth_clubs", YOUTH_CLUBS),
    ("mart.player_training", PLAYER_TRAINING),
    ("mart.player_homegrown", PLAYER_HOMEGROWN),
    ("mart.registration_rules", REGISTRATION_RULES),
    ("mart.squad_registration", SQUAD_REGISTRATION),
]


def create_mart(con, src="staging"):
    """(Re)create the macros and the `mart` schema against `src` staging tables."""
    con.execute("CREATE SCHEMA IF NOT EXISTS mart")
    for stmt in MACROS:
        con.execute(stmt)
    for name, sql in ORDER:
        con.execute(sql.format(S=src, window=_ARRIVAL_WINDOW_SQL, merge=_MERGE_SPELLS))
    return [n for n, _ in ORDER]


def drop_mart(con):
    con.execute("DROP SCHEMA IF EXISTS mart CASCADE")
