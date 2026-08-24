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

# The whole season review as one table. Note it aggregates on person_id (rule 3) but keeps
# tid for convenience; `apps` counts only matches the player actually appeared in.
PLAYER_SEASONS = """
CREATE OR REPLACE VIEW mart.player_seasons AS
SELECT
    f.season, f.person_id, any_value(f.tid) AS tid, any_value(f.team_tid) AS team_tid,
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
WHERE f.person_id IS NOT NULL
GROUP BY f.season, f.person_id, f.competition
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
        fm.first_match
    FROM lagged l
    LEFT JOIN mart.snapshots prev_s ON prev_s.snap_ix = l.prev_to_ix
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
dated AS (
    SELECT w.*,
           CASE
             WHEN is_transition AND arrival_window = 'winter'
               THEN GREATEST(winter_cut(season),
                             COALESCE(prev_phase_date + INTERVAL 1 DAY, winter_cut(season)))
             WHEN is_transition
               THEN GREATEST(season_start(season),
                             COALESCE(prev_phase_date + INTERVAL 1 DAY, season_start(season)))
             ELSE from_phase_date
           END AS valid_from
    FROM w
)
-- valid_to is derived from the NEXT spell's valid_from, never from a snapshot date, so the
-- spells of one person tile without gaps or overlaps by construction. NULL = still current.
SELECT
    person_id, tid, name, 'at_club' AS spell_type, club_tid, club, season,
    valid_from,
    LEAD(valid_from) OVER (PARTITION BY tid, person_id ORDER BY from_ix)
        - INTERVAL 1 DAY                              AS valid_to,
    CASE WHEN is_transition THEN arrival_window END   AS arrival_window
FROM dated
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
           l.attribute IN ({", ".join(f"'{a}'" for a in GK_ATTRS)}) AS is_gk_attr
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
PLAYER_GROWTH_TENURE = """
CREATE OR REPLACE VIEW mart.player_growth_tenure AS
WITH pc AS (
    SELECT g.person_id, g.tid, g.name, g.snap_ix, g.phase, g.phase_date, g.age,
           g.attr_total, g.is_estimated, g.is_gk,
           g.club_tid IN (SELECT club_tid FROM mart.our_clubs) AS ours
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


ORDER = [
    ("mart.snapshots", SNAPSHOTS),
    ("mart.our_clubs", OUR_CLUBS),
    ("mart.chosen_match_phase", CHOSEN_MATCH_PHASE),
    ("mart.match_player_facts", MATCH_PLAYER_FACTS),
    ("mart.matches", MATCHES),
    ("mart.player_seasons", PLAYER_SEASONS),
    ("mart.club_runs", CLUB_RUNS),
    ("mart.at_club_spells", AT_CLUB),
    ("mart.loan_in_spells", LOAN_IN),
    ("mart.loan_out_spells", LOAN_OUT),
    ("mart.injury_spells", INJURED),
    ("mart.player_spells", PLAYER_SPELLS),
    ("mart.squad_on", SQUAD_ON),
    ("mart.player_growth", PLAYER_GROWTH),
    ("mart.player_attribute_growth", PLAYER_ATTRIBUTE_GROWTH),
    ("mart.player_growth_season", PLAYER_GROWTH_SEASON),
    ("mart.player_growth_at_club", PLAYER_GROWTH_AT_CLUB),
    ("mart.player_growth_tenure", PLAYER_GROWTH_TENURE),
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
