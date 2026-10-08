---
name: scout-opponent
description: Produce a technical-analyst opposition scouting report for a single upcoming opponent in the active FM career — expected style, threats with the numbers behind them, weaknesses, and a concrete game plan — our standing 4-2-3-1 plus any variation, settings and personnel calls this opponent justifies. Combines our data (head-to-head history, squad-attribute profile, ratings, and the opposing manager's own formation/Style record) with anything fresher the user can add from the in-game scout screens — optional, since the manager's preferences are in the save. Use when the user says "scout <team>", "how do we beat <team>", or "prep for <team> this week".
---

# Scout an opponent

Acts as the technical analyst briefing the manager on this week's opponent. **Career-aware** —
reads the active career's store (`fm-<key>.duckdb`; Frem is `fm-frem.duckdb`), not a hardcoded
club. Refresh via `import-fm-saves` first if stale. The opposing manager's own formation/Style
record (`mart.fact_staff_snapshot`) is the baseline for shape and intent — no user input required
to get a report started. Layer on anything fresher the user can add (this week's team news, an
in-game scout screen) as a refinement, not a prerequisite. Immersion rule: reason with ratings +
match stats + attributes, **never surface CA/PA** (the Level %ile is the one allowed CA-derived
exception). No store to hand? Attach the published one (see "No local store"), or use the
[`scout-from-site`](../scout-from-site/SKILL.md) skill — same job, the deployed site's JSON, works
from anywhere.

## The pulls — run these, then write the narrative

Everything this report needs is in the dbt models; the recipes below are the validated way to get
it. Each closes a trap that has already produced a wrong briefing: a raw `club_tid` filter that
keeps a player whose loan lapsed (membership comes from `mart.squad_membership`, the squad arrays),
`tid` recycling (everything keys on `person_id`), and rating an opponent by how well he would fit a
tactic he doesn't play (quality is Level %ile, `positions[].level_*`).

**Running them.** Open the store read-only and keep its file name: dbt bakes `fm-frem` into every
view, so a copy under another name fails with `Catalog "fm-frem" does not exist`. Save a recipe to
a file in the scratchpad and run it with the runner in
[`query-fm-data`](../query-fm-data/SKILL.md) ("Running a multi-statement recipe"). The full
scout takes ~35 s.

**Find the opponent first** — accent-insensitive, Danish clubs and first teams first. `ø`, `æ`
and `å` are letters, not accents: type them, or search a fragment (`'ndby'`). Initials do not
match (search "Odense", "København", "Aarhus", not OB / FCK / AGF); if several first teams in the
same league fit, list them and ask.
```sql
SELECT t.team_tid, t.name, t.team_type, n.name AS nation, c.name AS league
FROM mart.dim_team t
JOIN mart.dim_club cl USING (club_tid)
LEFT JOIN mart.dim_nation n ON n.nation_id = cl.nation_id
LEFT JOIN mart.fact_team_snapshot ts ON ts.team_tid = t.team_tid AND ts.is_current
LEFT JOIN mart.dim_competition c ON c.cid = ts.league_cid
WHERE strip_accents(t.name) ILIKE '%' || strip_accents('Brøndby') || '%'
ORDER BY n.name = 'Denmark' DESC, t.is_first_team DESC, length(t.name)
LIMIT 10;
```

**The manager — his formations and Style, read automatically:**
```sql
SELECT p.name AS manager, s.formation_preferred_name AS preferred,
       s.formation_attacking_name AS attacking, s.formation_defensive_name AS defensive,
       s.style, s.tactical_knowledge
FROM mart.fact_staff_spell sp
JOIN mart.fact_staff_snapshot s ON s.person_id = sp.person_id AND s.is_current
JOIN mart.dim_person p ON p.person_id = sp.person_id
WHERE sp.team_tid = 337 AND sp.role = 'manager' AND sp.is_current;
```

**The scout itself** — set `opp` (and `our_formation` if the manager has changed shape) and run the
lot. `opp_formation` defaults to his preferred formation; set it to the attacking or defensive one
to see how the face-offs move when he changes shape.
```sql
-- ── 0. who, and which shapes ──────────────────────────────────────────────
SET VARIABLE us  = (SELECT team_tid FROM site.our_teams WHERE is_managed);
SET VARIABLE opp = 337;                                   -- from the lookup above
SET VARIABLE our_formation = '4-2-3-1';
SET VARIABLE opp_formation = coalesce((
    SELECT s.formation_preferred_name
    FROM mart.fact_staff_spell sp
    JOIN mart.fact_staff_snapshot s ON s.person_id = sp.person_id AND s.is_current
    WHERE sp.team_tid = getvariable('opp') AND sp.role = 'manager' AND sp.is_current),
    '4-2-3-1');

-- ── 1. the frame: both current first-team squads, each player at his most familiar
--       position, with his Level %iles there and the attributes the duel reads use ──
CREATE OR REPLACE TEMP TABLE frame AS
WITH squad AS (
    SELECT person_id, team_tid, snapshot_date, is_loan_in
    FROM mart.squad_membership
    WHERE is_current AND team_tid IN (getvariable('us'), getvariable('opp'))
),
pos AS (
    SELECT s.team_tid, s.person_id, s.is_loan_in, f.age, f.attributes_are_estimated,
           p.position, p.familiarity, p.level_league, p.level_global,
           f.Pace, f.Movement, f.Positioning, f.Aerial, f.Strength, f.Tackling,
           f.Passing, f.Technique, f.Creativity, f.Decisions, f.Shooting, f.Stamina,
           f.Dribbling, f.Crossing,
           row_number() OVER (PARTITION BY s.team_tid, s.person_id
                              ORDER BY p.familiarity DESC, p.level_league DESC) AS rk
    FROM squad s
    JOIN mart.fact_player_snapshot f USING (person_id, snapshot_date)
    CROSS JOIN unnest(f.positions) AS u(p)
)
SELECT pos.* EXCLUDE (rk), dp.unit, dperson.name
FROM pos
JOIN mart.dim_position dp USING (position)
JOIN mart.dim_person dperson USING (person_id)
WHERE rk = 1;

-- coverage: below 11 rated, withhold every squad-derived call (see "Partial data")
SELECT sm.team_tid, count(*) AS in_squad, count(f.person_id) AS rated
FROM mart.squad_membership sm
LEFT JOIN frame f USING (team_tid, person_id)
WHERE sm.is_current AND sm.team_tid IN (getvariable('us'), getvariable('opp'))
GROUP BY sm.team_tid;

-- ── 2. each side's XI by unit: best N per unit, N = that unit's slots in its shape ──
CREATE OR REPLACE TEMP TABLE xi AS
WITH shape AS (
    SELECT t.team_tid, dp.unit, sum(fs.slots) AS slots
    FROM (VALUES (getvariable('us'), getvariable('our_formation')),
                 (getvariable('opp'), getvariable('opp_formation'))) AS t(team_tid, formation)
    JOIN site.formation_slots fs USING (formation)
    JOIN mart.dim_position dp USING (position)
    GROUP BY ALL
)
SELECT f.*, shape.slots
FROM frame f JOIN shape USING (team_tid, unit)
QUALIFY row_number() OVER (PARTITION BY f.team_tid, f.unit ORDER BY f.level_global DESC)
        <= shape.slots;

-- overall quality (Level %ile, tactic-agnostic) and each unit in isolation
SELECT team_tid, coalesce(unit, 'XI') AS unit, count(*) AS n,
       round(avg(level_league), 1) AS level_league, round(avg(level_global), 1) AS level_global
FROM xi GROUP BY GROUPING SETS ((team_tid), (team_tid, unit)) ORDER BY unit, team_tid;

-- ── 3. the face-offs that actually happen on the pitch (+ve edge = ours) ──
WITH u AS (SELECT team_tid, unit, avg(level_global) AS q FROM xi GROUP BY ALL)
SELECT m.contest, round(a.q, 1) AS us, round(b.q, 1) AS them, round(a.q - b.q, 1) AS edge
FROM (VALUES ('Our attack v their defence', 'attack', 'defence'),
             ('Their attack v our defence', 'defence', 'attack'),
             ('Midfield v midfield', 'midfield', 'midfield'),
             ('Goalkeeper v goalkeeper', 'goalkeeper', 'goalkeeper')) AS m(contest, our_unit, their_unit)
JOIN u a ON a.team_tid = getvariable('us') AND a.unit = m.our_unit
JOIN u b ON b.team_tid = getvariable('opp') AND b.unit = m.their_unit;

-- ── 4. the duels behind them, attacker's attribute v the defender's answer ──
WITH a AS (SELECT * FROM xi WHERE unit = 'attack'), d AS (SELECT * FROM xi WHERE unit = 'defence')
SELECT 'We attack' AS duel,
       round(avg(a.Movement), 1) AS att_movement, round(avg(a.Pace), 1) AS att_pace,
       round(avg(a.Aerial), 1) AS att_aerial,
       (SELECT round(avg(Positioning), 1) FROM d WHERE team_tid = getvariable('opp')) AS def_positioning,
       (SELECT round(avg(Pace), 1) FROM d WHERE team_tid = getvariable('opp')) AS def_pace,
       (SELECT round(avg(Aerial), 1) FROM d WHERE team_tid = getvariable('opp')) AS def_aerial
FROM a WHERE a.team_tid = getvariable('us')
UNION ALL
SELECT 'They attack',
       round(avg(a.Movement), 1), round(avg(a.Pace), 1), round(avg(a.Aerial), 1),
       (SELECT round(avg(Positioning), 1) FROM d WHERE team_tid = getvariable('us')),
       (SELECT round(avg(Pace), 1) FROM d WHERE team_tid = getvariable('us')),
       (SELECT round(avg(Aerial), 1) FROM d WHERE team_tid = getvariable('us'))
FROM a WHERE a.team_tid = getvariable('opp');

-- every defender by name: the unit mean hides the 8
SELECT team_tid, name, position, Positioning, Pace, Aerial, Strength, Tackling, Passing,
       Technique, level_global
FROM frame WHERE unit IN ('defence', 'goalkeeper') ORDER BY team_tid, position, level_global DESC;

-- ── 5. their key players, by Level %ile (quality, not output) ──
SELECT name, position, age, level_league, level_global, Pace, Movement, Positioning, Aerial,
       Strength, Tackling, Passing, Technique, Creativity, Shooting, Stamina
FROM frame WHERE team_tid = getvariable('opp') ORDER BY level_league DESC LIMIT 8;

-- ── 6. head-to-head, one row per match, from our side ──
SELECT match_date, season, competition, venue, gf || '-' || ga AS score, result,
       our_shots || '-' || opp_shots AS shots,
       our_shots_on_target || '-' || opp_shots_on_target AS on_target,
       round(100.0 * our_passes_completed / nullif(our_passes, 0)) || '-' ||
       round(100.0 * opp_passes_completed / nullif(opp_passes, 0)) AS pass_pct
FROM site.matches WHERE opp_tid = getvariable('opp') ORDER BY match_date;

SELECT coalesce(venue, 'all') AS venue, count(*) AS p,
       count(*) FILTER (WHERE result = 'W') AS w, count(*) FILTER (WHERE result = 'D') AS d,
       count(*) FILTER (WHERE result = 'L') AS l, sum(gf) AS gf, sum(ga) AS ga,
       round(avg(pts), 2) AS ppg
FROM site.matches WHERE opp_tid = getvariable('opp') AND stage_kind IS NOT NULL
GROUP BY ROLLUP (venue) ORDER BY venue;

-- ── 7. who has actually hurt us (output, not quality), and whether he is still there ──
WITH prod AS (
    SELECT f.person_id, mode(f.position) AS played_as,  -- his usual full-time position vs us
           count(*) FILTER (WHERE f.appeared) AS apps, sum(f.goals) AS goals,
           sum(f.assists) AS assists, sum(f.key_passes) AS key_passes, sum(f.shots) AS shots,
           sum(f.shots_on_target) AS on_target,
           round(avg(f.rating) FILTER (WHERE f.appeared), 2) AS avg_rating,
           count(*) FILTER (WHERE f.is_player_of_match) AS potm,
           max(m.match_date) AS last_played
    FROM mart.fact_player_match f
    JOIN mart.dim_match m USING (match_id)
    WHERE f.team_tid = getvariable('opp') AND f.opponent_tid = getvariable('us')
    GROUP BY f.person_id
)
SELECT p.name, prod.* EXCLUDE (person_id),
       prod.person_id IN (SELECT person_id FROM mart.squad_membership
                          WHERE is_current AND team_tid = getvariable('opp')) AS still_there
FROM prod JOIN mart.dim_person p USING (person_id)
WHERE prod.goals + prod.assists + prod.key_passes > 0
ORDER BY prod.goals + prod.assists DESC, prod.key_passes DESC LIMIT 12;

-- ── 8. their reserves: each one's best natural position, on level_global ──
SELECT d.name, p.position, p.familiarity, p.level_global, f.Pace, f.Movement, f.Positioning,
       f.Aerial, f.Tackling
FROM mart.squad_membership sm
JOIN mart.dim_team t ON t.team_tid = sm.team_tid
JOIN mart.fact_player_snapshot f USING (person_id, snapshot_date)
CROSS JOIN unnest(f.positions) AS u(p)
JOIN mart.dim_person d USING (person_id)
WHERE sm.is_current AND t.team_type = 'reserve' AND p.familiarity >= 15
  AND t.club_tid = (SELECT club_tid FROM mart.dim_team WHERE team_tid = getvariable('opp'))
QUALIFY row_number() OVER (PARTITION BY sm.person_id ORDER BY p.level_global DESC) = 1
ORDER BY p.level_global DESC LIMIT 6;
```

What each step is for, and how to read it:
- **Steps 1–2, the frame and the XI.** Each player is placed at his most familiar position (ties to
  the higher Level), and each side's XI is the best N per unit, where N is that unit's slots in the
  side's formation (`site.formation_slots` joined to `mart.dim_position.unit`). A unit, not a slot:
  a natural AMR can fill a 5-2-1-2's attack. Level %ile is a percentile among every player at that
  position — `level_league` within his own league, `level_global` world-wide. Quote `level_league`
  when both sides are in one league; compare across leagues (a reserve, a Cup draw from another
  division) on `level_global` only.
- **Step 3, the face-offs** — the pairing that actually meets on the pitch: our attack v their
  defence, their attack v our defence, midfield v midfield. A back line does not play a back line;
  the step-2 per-unit table answers "how strong is each line in isolation", step 3 answers "who
  wins this contest". The XI row of step 2 is the overall quality gap.
- **Step 4, the duels** — the attacker's attribute against the defender's answer (see "Reading
  attributes"), then every defender by name, because the unit mean hides the 8.
- **Step 5, key players** — QUALITY. **Step 7, who has hurt us** — OUTPUT, with `still_there`.
  **Read step 7 before the threat section, not after.** Level %ile ranks quality, not output:
  against OB it put Ely, Nørgaard and Weiss top while the men who had actually hurt us were
  Nielsen (5 goals, Level 53) and Þrándarson (11 key passes, Level 23) — a briefing built on the
  ranking alone called Nielsen the back-up striker. Flag anyone still there with 2+ goals and
  assists against us.
- **Step 6, head-to-head** — one row per match from `site.matches` (our first team, from our
  side), plus the per-venue record over competitive matches.
- **Step 8, their reserves** — see "Their squad is not their first-team list" below.

**Partial data — withhold, don't hedge.** When the coverage line shows fewer than 11 rated
players for either side, do not state the quality gap, the face-offs, danger men or defensive soft
spots at all; say the squad is not in our data and keep the H2H, which comes from match history,
not the frame. Emitting them with full confidence off however few players exist is worse than
nothing: scouting Hajduk Split off **two** rated players produced "We're stronger — team index 126
vs 116" and "Their defence: weak in the air (Aerial 5) — target it", where the Aerial 5 was ONE
full-back standing in for a back four. Acting on it means bombarding the box: 21 crosses, 17
headers won to 7, six corners to nil, one goal, lost 1-3.

If a report needs something the pulls don't return (a deeper individual-attribute cut), add that
one query rather than re-deriving what is already there.

## Reading attributes: check the role weights before calling anything a weakness

**An attribute is only a strength or a weakness against its counterpart.** `site.role_weights`
encodes which attributes a role is scored on (attribute names are **lowercase** there; a role with
no rows is flat), and a number the role does not score is noise. The pair that has bitten this
skill twice, in `frem_minmax_4231`:

| | CB | LB/RB | DM | CM | ST | AMC | AML/AMR |
|---|---|---|---|---|---|---|---|
| **movement** | baseline | baseline | baseline | 3 | **4** | baseline | flat |
| **positioning** | **3** | 2 | 3 | baseline | baseline | baseline | flat |

("baseline" = absent from that role's weight list, so it scores at weight 1 — the floor; "flat" =
the role has no weights at all. There is no way to weight an attribute *below* baseline, so an
unlisted attribute is not penalised; it is simply not what the role is judged on.) Re-read it
rather than trusting this table if the set changes:
```sql
SELECT role, attribute, weight FROM site.role_weights
WHERE method = 'frem_minmax_4231' AND attribute IN ('movement', 'positioning')
ORDER BY attribute, role;
```

**Movement is the attacker's side of the duel; Positioning is the defender's answer to it.** Two
consecutive briefings led with "their back line has Movement 7.1" as the headline exploit. A
centre-back with Movement 6 is not slow to react — Movement is not what he is judged on. Redone on
Positioning, one of those defences was *level* with ours, and the other's weak link turned out to be
a different player on the opposite flank. Same trap in reverse: "their striker has Positioning 7"
says nothing.

Before quoting any attribute, check it is weighted above baseline for that player's role:

| The question | Attacker column | Defender column |
|---|---|---|
| Can they track runners in behind? | Movement, Pace | **Positioning**, Pace |
| Can they win it back? | Dribbling, Technique | **Tackling** |
| Who wins the ball in the air? | Aerial, Strength | **Aerial, Strength** |
| Will they last 90? | Stamina | Stamina |

**A ball-playing centre-back is a threat, not just a press target.** The key-players pull (step 5) ranks by
Level %ile and a deep-lying creator can sit mid-table on it while running the game. If an opponent
defender's profile is Passing/Technique-led, check him as an attacking outlet too — one such
centre-back finished a scouted fixture on 53 passes, 45 completed, **4 key passes**, 11 tackles with
9 won and 7 interceptions, the best player on the pitch, having appeared in the briefing only as a
note about how they build from the back.

**Read the decoded numbers as exact.** Attributes for a player who was never ours are a frozen
decode, but held-out accuracy is ~63% exact / ~93% within ±1 (`fmparser/model.py`), so quote them
without hedging. Eight are exact outright (Pace, Strength, Stamina, Technique, Aggression,
Leadership, Agility, Teamwork) — a Pace or Strength comparison is the hardest claim available about
an opponent. Do **not** import the 8-24x "compression" figure from
[`player-analysis-methods`](../../../docs/agent-context/player-analysis-methods.md): that is about
year-over-year *growth* and belongs to forecasting, not to a point-in-time scouting read.

The two reads that do need care are about football, not decode error:

- **Check individual defenders, not just the unit duel means (step 4)** — a back four averaging 12 can contain
  an 8, and the unit mean hides exactly the player you want to attack.
- **One attribute does not decide a duel.** A full-back with Positioning 8 but Tackling 13 and Aerial
  15 can still have an excellent game (observed: 8 tackles, 6 won, 5 interceptions, rated 8). Name
  the weakness, then weigh it against the rest of that player's profile before building a flank plan
  on it. Seen again since: a right-back playing out of position at centre-back, flagged in a briefing
  as the aerial weak link, finished as his side's best player on 6 tackles from 6 and 6 interceptions.
- **A duel has two sides — check OURS before ruling a route out.** A briefing told the manager not to
  cross because the opponent centre-backs read Aerial 15 and Strength 14. It never looked up our own
  target man: Aerial 16, Strength 18, better than both. We crossed 19 times anyway, won the header
  count 18-14, and he won 5 of his 8 aerial duels on the way to a 2-0. Quoting only the defender's
  number is the same one-sided error as quoting an attribute the role isn't scored on — state both
  sides of the duel, or don't call the route off.

Full write-up: [`scouting-attribute-reads`](../../../docs/agent-context/scouting-attribute-reads.md).

## Resolve the career context first (do NOT hardcode)
Everything is parameterised off the active career:
- **Us** = `SELECT team_tid, name, is_managed FROM site.our_teams` — Frem 346 (first team, the one
  the scout rates) and 7296 (reserves).
- **Snapshot** — `SELECT snapshot_date, label FROM site.snapshots WHERE is_latest`. Every
  `is_current` in the pulls means this snapshot.
- **Our rating basis** — `SELECT value FROM site.config WHERE key = 'career_rating_method'`:
  **`frem_minmax_4231`**, matching the 4-2-3-1 we actually play. `default_method` reads
  `frem_attacking_ss`, the site's display default — not our tactic, so don't use it. The method
  only decides how players are RATED (Fit) — the game plan is a shape plus settings, see the
  game-plan section below.
- **Our identity** — read it off the step-2 unit table and the step-4 duels, don't recite a fixed
  line; the squad turns over heavily. **Check `n` per unit before quoting a unit mean** — a unit
  of two rated players makes both its quality figure and its attribute means a two-man sample. Say
  so rather than quoting a 40-point gap as if it were solid.

## Inputs to establish first
- **Opponent** — the lookup above.
- **Manager, formation & Style — read automatically, no ask required.** The manager pull names who
  is in charge and gives his **preferred / attacking / defensive formation** plus a derived
  **Style** (Attacking / Normal / Defensive, `attacking_intent` banded — confirmed 7/7 on a
  predict-then-check run spanning both edges, `docs/record-expansion.md` §F). This is the BASELINE
  for the report: open with the preferred shape and Style, and use the attacking/defensive variants
  for **what he changes to when the game state changes** — the shape he shifts into chasing a goal,
  and the one he shuts up shop in. Quote the Style label as read, not hedged. It is the manager's
  *standing* preference, not a guarantee of today's XI (a manager still departs from habit for a big
  occasion), so it is a starting point to state plainly, not a promise. Asking the user is optional
  refinement: don't block the report on it. No row means the club has no manager on record — fall
  back to the user's scout screen or say the shape is unknown.
- **If the user has it, an in-game scout screen still refines the above — ask for it, don't
  require it.** It answers something the manager record structurally cannot: this week's actual
  team news (injuries, suspensions, who's actually fit), not the manager's general habit.
  **Best artefact: their `Club Squad → Selection` screen (the `Pkd` column)** — the opposition
  manager's *actual* current selection with position badges, plus suspensions, injuries, condition %,
  form and season apps. On its first use it disagreed with the same fixture's Predicted XI in 2 of 11
  slots and revealed both first-choice full-backs unavailable, inverting the flank plan. Season apps
  also settle "is this name new?" outright. Failing that, **Next Match → Predicted XI** names eleven
  players and their slots.
  **Trust the Predicted XI for neither shape nor names, and COUNT SLOTS, NOT NAMES** — this is
  exactly why it is not a required input: across eleven
  checks names were wrong 2–7 of 11, and shape held for six, then broke on four straight. Lyngby away
  is the cleanest case: **8 of 11 names right, only 3 of 11 slots** — a 73% name accuracy concealing a
  completely different front four. Slot accuracy is volatile, not reliably bad (the same opponent went
  5/11 then 8/11 three weeks later), so a wrong sheet last time is no guide to this time. **What
  survives either way are the PROFILE reads, not the positional ones** — build the briefing so they do.
  - **Never let your single most specific recommendation depend on one predicted name.** The recurring,
    expensive error is naming a FLANK off a predicted full-back: three briefings running the named
    target was the wrong man (did not play / injured / replaced by the man who was the actual soft spot
    on the *opposite* flank). Name the weak **profile** and the zone, then say who fills it if the
    expected man is absent.
  - **The rule applies to the THREAT LIST too, and that is where it was missed.** Against Vejle the
    briefing led on Eiting ("press him and never take it off", 95.9 league Level) and Gyökeres (the
    stated reason the centre-back pair needed pace cover) — **both were benched**, and Remberg (39.3)
    and Ponce (35.7) started instead. The flank call was hedged; the threat section was not, so the
    most-emphasised half of the report aimed at men who never played. For the top two threats, always
    add the one-line fallback: *if X doesn't start, the threat becomes Y*.
  - **A thin H2H record is not a thin threat — profile the striker who actually STARTS.** FCK at home
    (2027-05-22): the briefing wrote "the striker is not the danger" off Babacar (Pace 6) and Fenger's
    2 apps / 0 goals against us. Fenger started as a pressing forward fed by their AMC and went 8 shots,
    5 on target, 2 goals, rated 10 in a 2-3. Step 7 ranks who HAS hurt us; it says nothing about
    a man who has barely played us. When the starting XI is known, read the starting No. 9's
    Shooting/Stamina and who supplies him before ruling the central route out.
  - **Ask for the `Club Squad → Selection` (`Pkd`) screen — this is now GRADED, not promising.** That
    screen would have shown Eiting at S5 and Gyökeres at S7 and inverted the threat section before
    kickoff. It is the single highest-value artefact to request.
  - **Read their BENCH for the counter-profile to whatever your plan depends on.** Twice the
    non-predicted names did the damage — a centre-back swap answering our aerial threat, and a winger
    who scored. Once the two men shown on the bench were their two best midfielders and both started;
    once the named goalkeeper was benched and the one who played was their best, which alone
    invalidated the briefing's route to goal.
  - **When a predicted man's best slot in our data differs from the slot the screen assigns him, say
    so** — cheap, checkable, and it has fired correctly (the `positions` list on `fact_player_snapshot` had Çorlu's best slot
    as ST against the screen's AMR; he played ST). Caveat: `level_*` is CA-derived, so for a very
    high-quality player it reads high at *every* slot and the ordering is mostly familiarity — only
    flag a difference that is large and football-plausible.
- **Their squad is not their first-team list — read the RESERVE club too** (step 8), and
  **compare reserves against the WEAKEST men in their XI, not the best** (`SELECT name, position,
  level_global FROM xi WHERE team_tid = getvariable('opp') ORDER BY level_global LIMIT 4`).
  Getting that backwards cost a briefing: it saw nobody near Horsens' top players, wrote "nobody who
  would walk into this XI", then watched a reserve start at centre-back (rated 7, 6 interceptions)
  with another off the bench — 79.9 and 83.0 against predicted starters at 71.7, 74.6 and 75.8. Done
  right it pays: at Lyngby the check named Datkovic (79.9) as beating predicted starter Maxsø
  (75.7), and he started. **Profile the reserve, don't just rank him** — Datkovic is Pace 7 /
  Movement 7, so his selection made their back line *slower* and the in-behind route better. Two
  traps: **`level_league` is a percentile against that player's OWN league**, so a reserve reads
  high against reserve peers and is not comparable to a first-teamer's Superliga number (compare on
  `level_global`); and a name in **no** club's squad is *often* a post-snapshot signing but
  **absence is weak evidence**
  ([`nickname-players-missing`](../../../docs/agent-context/nickname-players-missing.md)). Say
  **"our data has never seen him"**, not "he must be a new signing" — and the `Selection` screen's
  apps column settles it in one glance. Search for him world-wide by name (`mart.dim_person`, then
  his latest `mart.fact_player_snapshot` row) to rate him off his previous club.
- **OUR OWN tactics screens** — ASK FOR THESE TOO (Shape / Defence / Attack). A shape sets none of
  mentality, line, closing down, tempo, width or the final-third instructions. In particular check
  whether **`Work Into Box`** is already set before diagnosing poor shooting as a selection problem
  ([`scoring-and-shot-quality`](../../../docs/agent-context/scoring-and-shot-quality.md)). And **do
  not infer "sit deep" from a quality gap**: one briefing advised a deep line and "absorb and break"
  on a −39 gap; the manager ran Attacking / HIGH / All Over / Fast away at the division's best attack
  and won 6-0, having drawn 1-1 with the cautious version. State the settings you mean — see the
  game-plan section. Role labels (IW / PF / Poacher / AF / AP) belong to whichever club's screen you
  are reading — say whose, every time, or a briefing will attribute the opponent's roles to us.
- **Current league position / recent form (both sides).** The stored table is real but reflects the
  latest *imported* save, which can be behind where the user is — use it as the starting point and
  let the user's live position win where they differ:
  ```sql
  SELECT s.stage_index, s.position, t.name, s.played, s.won, s.drawn, s.lost,
         s.goal_difference, s.points, s.through_date
  FROM mart.standings s JOIN mart.dim_team t USING (team_tid)
  WHERE s.cid = 2 AND s.is_latest
    AND s.competition_season = (SELECT max(competition_season) FROM mart.standings WHERE cid = 2)
  ORDER BY s.stage_index, s.position;
  ```
  (cid 2 is the 3F Superliga; a later `stage_index` is the championship/relegation split.) The
  quality gap measures attributes, blind to results, form or depth holding up over a season. Don't
  let the Verdict assert "underdogs"/"favourites" from Level %ile alone — say what the gap
  suggests, then say where each side actually sits, and let table position win if the two disagree.
  This bit the first real scout run under this skill: Frem 1st, Brøndby 9th, but the quality read
  alone said "clear underdogs" — true for the attribute profile, false for the season.

## Check for a prior scout — this is calibration, not just prediction
The scout log is one JSON object per scout on R2,
`state/scouts/<opponent_tid>-<snapshot label>[-<fixture date>].json` (e.g.
`337-frem-2026-03-28-2026-05-29.json`), with `note` (what we thought before the game) and
`result_note` / `result` / `graded_at` (how it graded after). Pull this opponent's:
```bash
rclone copy r2:fmm-stats/state/scouts/ "$SCRATCH/scouts/" --include '337-*'
```
If a saved report exists, open the briefing with what it said (gap, plan, any note) and whether it
still holds — squad, tactic and our own personnel may have moved since. If nothing's saved, say so;
this scout will be the first entry once you save it.

**Save this one when the briefing is written** — nothing writes the log for you. Write a JSON
object with at least `saved_at` (ISO timestamp), `opponent_tid`, `opponent`, `snapshot_label`,
`method`, `venue`, `fixture` (the match date off the Next Match screen), `formation`, `style`,
`note` (the plan in a few lines), plus the numbers you relied on (`overall`, `matchups`,
`key_players`, `h2h`) so the grading can check them, and upload it under its key:
```bash
rclone copyto "$SCRATCH/scout.json" "r2:fmm-stats/state/scouts/337-frem-2028-05-09-2028-05-20.json"
```
**Always include the fixture in the key** — it is what separates the home and away meetings of the
same opponent between two imports; without it the second scout replaces the first. `rclone lsf` the
key first: if it exists, read it and carry its `result_note` / `result` / `graded_at` forward rather
than dropping them, and keep the superseded `note` in a `revisions` list. **Re-save a scout when its
reasoning changes, not just when the fixture does** — the log is what the next agent reads, and a
note carrying reasoning we already know to be wrong is worse than no note. If rclone or the remote
is missing, the scout reached nobody: tell the user. `season-outlook` and `scout-from-site` never
write to the log, so an absence there is not proof a team went unscouted.

## After the match — close the loop (do this when the user posts the FT stats)
The scout log only becomes calibration if someone checks it. When the user shares a full-time stat
screen for a fixture that was scouted, **grade the briefing explicitly**: which calls landed, which
did not, and which were right for the wrong reason. This is where the durable learning comes from,
and it is cheap — the FT screen already has everything needed.

- Anchor the match against the **season baseline**, not against feel (`stage_kind IS NULL` is a
  friendly):
  ```sql
  SELECT count(*) AS games, round(avg(our_shots), 1) AS shots,
         round(avg(our_shots_on_target), 1) AS on_target, round(avg(gf), 2) AS goals,
         round(100.0 * sum(gf) / sum(our_shots), 1) AS conversion_pct,
         round(avg(our_passes), 0) AS passes,
         round(100.0 * sum(our_passes_completed) / sum(our_passes), 1) AS pass_pct
  FROM site.matches WHERE season = 2028 AND stage_kind IS NOT NULL;
  ```
- **The FT stat screen lists starters and substitutes separately** — scroll before totalling, or a
  starters-only count gets compared against the store's full-match figures. That error manufactured a
  fake "shot collapse" across two briefings. Column key: `PaA/PaC` passes attempted/completed,
  `Key` key passes, `Ass` assists, `TaA/TaW` tackles, `Int` interceptions, `HeA/HeW` headers,
  `CrA/CrC` crosses, `Dri` dribbles, **`Mis` = mistakes** (not misplaced passes), `MiG` mistakes
  leading to a goal, `ShA/ShO` shots attempted/on target, `Con` condition.
- **Test a pattern before you write it down.** Four hypotheses from this skill's briefings looked
  compelling over 3–4 matches and died against the full history (see
  [`scoring-and-shot-quality`](../../../docs/agent-context/scoring-and-shot-quality.md)). A
  per-opponent record of "3 wins from 3" implies an effect several times larger than anything that
  survives a league-wide test. "11 shots and 3 goals" means nothing until it sits next to "7.1 shots and 0.82
  goals per game, 11.7% conversion".
- **A right conclusion off wrong reasoning still counts as a miss** — say so. It will not transfer to
  the next opponent otherwise.
- Read the **per-player** columns for the specific claim the briefing made: if the plan was "attack
  their weak aerial full-back", check the aerial-duel counts, not just the scoreline.
- **Write the grading into the scout's OWN record, never over its `note`.** Read the object for this
  opponent and fixture, set `result_note` / `result` (e.g. `"W 2-0 (H)"`) / `graded_at`, leave `note`
  exactly as it was, and `rclone copyto` it back under the same key. With more than one scout of this
  opponent, grade the one whose `fixture` is this match — never guess. If there is nothing saved to
  grade, say so rather than inventing a record. The pairing of `note` with `result_note` is the
  entire reason the log is calibration rather than a pile of old opinions: grading text written into
  `note` destroyed the Lyngby, Midtjylland, OB and FCK briefings, and R2 has no object versioning,
  so a bad write is gone.
- Feed anything durable back into this skill or `docs/agent-context/`. `docs/` is in git and
  versioned; the scout log is not.

Manager observations beat the model here. Three corrections from one session that no query would
have surfaced: that a defender's counter to Movement is Positioning (the model agreed — the briefing
had not checked); that both late goals arrived after the press was pulled back (see the game-plan
section on line vs press); and that a single poor performance is not evidence to move a player who
has been good all season. **Do not restructure a recommendation off one match's stat line** — that
is the same n=1 error the skill warns about elsewhere, applied to our own squad.

### Game plan — a 4-2-3-1 and the variations off it (THE career-specific value-add)

**Do NOT output a "recommended method + fallback switch".** A `role_weights` method is a **rating
weight-set**, not a game plan, and ranking several of them tells the manager nothing he can do on a
team screen. He runs a **4-2-3-1 with a back four** as the standing shape and varies it per
opponent. So the deliverable is **that baseline plus the specific variations this opponent
justifies**, each tied to the threat or weakness that triggers it.

**The method is only the RATING BASIS — pick it to match the shape, and say so once.** For a
4-2-3-1 rate with **`frem_minmax_4231`**, which is derived from this career's own match data rather
than from a tactic author's stated traits (`scripts/derive_weight_set.py` — read its docstring before
touching the set). Two things to know about it:
- **It has no AML/AMR block.** The wide attacking roles failed to beat a flat weighting and are left
  flat **on purpose**. Fit at AML/AMR is flat-weighted, so treat a wide Fit as a rough quality read,
  not a role-tuned one, and lean on `level_*` there instead.
- **`default_method` reads `frem_attacking_ss`** (`seeds/config_bundle.json`), which is not what we
  play; don't describe it as "our tactic".

**Rate the slot, not the player.** The same winger can be a 92 at MR and an 85 at AMR, and a deep
left slot has flipped which of two candidates was correct by 25 percentile points. If the manager
shares a formation screen, rate that XI at the slots each player really occupies — Fit is the
role-weighted rating (`int.player_ratings`: attributes × `site.role_weights`, unlisted attributes
at weight 1) scaled by familiarity (`linear_floor`, floor 0.5, per `site.config`):
```sql
SELECT d.name, p.position, pr.role, p.familiarity, r.rating AS base,
       round(r.rating * (0.5 + 0.5 * p.familiarity / 20.0)) AS eff, p.level_league
FROM mart.squad_membership sm
JOIN mart.fact_player_snapshot f USING (person_id, snapshot_date)
CROSS JOIN unnest(f.positions) AS u(p)
JOIN site.position_roles pr ON pr.position = p.position
JOIN int.player_ratings r
  ON r.snapshot_date = f.snapshot_date AND r.tid = f.tid
 AND r.method = 'frem_minmax_4231' AND r.role = pr.role
JOIN mart.dim_person d USING (person_id)
WHERE sm.is_current AND sm.team_tid = 346 AND p.familiarity >= 15
ORDER BY pr.role, eff DESC;
```
Fit is a question about OUR squad in OUR system (or a signing target). Never rate an opponent on it.

**The variation vocabulary — these are the manager's own levers, so propose in these terms:**

| Variation | Trigger to look for in the pulls |
|---|---|
| **Drop one forward wing AM → M** (e.g. AML → ML) | their strongest attacking outlet is on that flank, or their full-back on that side is their best attacking contributor — buys cover without changing the back four |
| **Drop the 10 to a 6** (second pivot beside the DM) | their AMC is a genuine threat (high Level %ile, Technique/Creativity-led) and would otherwise play between our lines |
| **Turn a WB into an IWB** | their winger on that side is a dribbler who comes inside, or we need an extra body in central midfield without losing a defender |
| **Back 3, or a single anchor + two strikers** | **reserved for the very top sides (FCK)** — do not propose it for mid-table opposition |

Almost always a back four. A variation is worth naming only when something in the data triggers it;
**listing all four as a menu is noise.** Usually the honest answer is "standard 4-2-3-1, no
variation needed" plus the settings — say that rather than manufacturing a tweak.

**The decision inputs are in the pulls:**
- **Favourite vs underdog** — the XI row of step 2 (Level %ile), read beside the table position.
  This sets mentality and how much cover the shape needs, **not** which weight-set to quote.
- **Their style** (the manager pull, refined by the user's scout if they have one) → a deep block
  is a width-and-patience problem; a side that tries to play out is a pressing opportunity keyed to
  their weakest build-up player.
- **The face-offs** (step 3) → "Our attack v their defence" says whether to expect chances; "Their
  attack v our defence" says what to protect, and is the row that justifies a wing dropping to M.
  If they edge that second row on Strength/Aerial (step 4) and play direct to a target man,
  **don't** open in a high-press duel game that plays to their one advantage.

**Check the weights against the opponent before trusting a shape or a route.** A weight-set is
selected for a duel, and a situational mapping can point at the wrong one: against a side with a
slow but dominant aerial centre-back, the "break down a low block" set weighted **aerial highest and
pace lowest**, rewarding the duel we lose and ignoring the one we win. Read `site.role_weights`
(**attribute names are lowercase there** — a capitalised filter returns nothing) when a route
recommendation hinges on it.

**Line and press are two levers, not one.** It is easy to write "drop the line" and have it read as
"drop the press". Against a side whose creativity funnels through one deep passer, pulling the
*press* hands that player time on the ball and is the more expensive of the two. Observed: a 3-0
became 3-2 immediately after the press was pulled, with their deep playmaker finishing on 32 passes
/ 28 completed, by ten the most on the pitch. When protecting a lead against a technical build-up
(check the opponent Defense unit's Passing/Technique in step 4's per-defender list), **drop the line and
keep the press on**. Say which lever you mean, every time.

**Settings and personnel are the valuable half — spell them out.** A shape sets none of Mentality,
Line, Tempo, Width, Press, Final third or Passing; those live on the manager's Shape / Defence /
Attack screens and the presets are in
[`docs/fmm-tactic-blueprints.md`](../../../docs/fmm-tactic-blueprints.md) → **"In-game SETTING
presets per scenario"** (read it live). Two that repeatedly matter:
- **`Work Into Box` vs `Shoot On Sight` is the shot-quality lever** — a team instruction, not a
  selection problem (see
  [`scoring-and-shot-quality`](../../../docs/agent-context/scoring-and-shot-quality.md)). Check it is
  set before proposing a different XI.
- **Justify Line and Width from the duel, not the preset.** "vs pace in behind → drop deep" does not
  apply when our Defense unit Pace beats their Attack unit Pace; narrow does not apply when their
  wide men don't track back. Quote both sides of the comparison.

Personnel calls are what the manager actually acts on: name the centre-back pairing and why (a
high line behind a Positioning-19/Pace-10 defender needs a quick partner), the flank to load and the
pace gap that justifies it, the in-behind runner, and who man-marks the aerial threat at set pieces.

**Before proposing a personnel change, split that player's OWN record BY POSITION.** Attributes say
what a player could do; the match record says what he actually does in a given slot, and the two
disagree often enough to flip a recommendation:
```sql
SELECT mp.season, mp.position, count(*) AS starts,
       round(avg(mp.rating), 2) AS avg_rating, round(avg(mp.rating_adj), 2) AS avg_rating_adj,
       sum(mp.goals) AS goals, sum(mp.assists) AS assists,
       round(avg(mp.shots), 2) AS shots_pg, round(avg(mp.shots_on_target), 2) AS on_target_pg,
       round(avg(mp.mistakes), 2) AS mistakes_pg
FROM site.match_players mp
JOIN mart.dim_person p USING (person_id)
WHERE p.name = 'Tochi Chukwuani' AND mp.started
GROUP BY ALL HAVING count(*) >= 5
ORDER BY mp.season, starts DESC;
```
**Compare a player across positions on `rating_adj`, never raw** — the game rates a DM ~0.47 below
a central midfielder for the same game — and compare two players in the same position on either.
Read a position only on 5+ starts. Two live findings it produced in one sitting:
- **Chukwuani**: at MC in 2025, 27 apps, rating 7.33, 6 goals, 5 assists. At AMC in 2026, 8 apps,
  rating 6.75, **2.25 shots a game at 0.38 on target, zero goals, zero assists**. The manager's read
  — "he liked being the main creator" — was exactly right, and the split also identified him as one
  of the wasteful shooters behind a bad shots-to-goals night.
- **Larsen**: 2.78 mistakes per game at DR over 9 apps, against 2.00 at DC and 1.00 at DMC. A
  4-mistake match was not an outlier but the top of his normal distribution there.
**And check the position before blaming the player** (the same query without the name filter, grouped by position). Across 194 matches our right backs average
**2.38** mistakes a game to the left backs' **1.55** — stable in ALL FIVE seasons, across four
divisions and ~18 players, and **2.36 with the current incumbent removed**. So "our right back is
error-prone" is a fact about the slot, and swapping the man does not fix it (his replacement reads
2.44). Swap for quality; do not promise an error reduction the data does not support.
**One bad game is not a pattern** — the same sitting had a player rated 4 immediately after an 8 with
2 assists. Move on a split, not on a scoreline.
**But a position split answers "how does he rate there", not "can he do THIS job".** Against FCK
(2027-05-22) the briefing withdrew "Tjørnelund screens their 10" because his DMC rating split was poor
(6.20 over 5 starts). He started at MC, Mensah ran the first half (39 passes, 1 assist, Fenger fed
twice) and we were 0-2 down; Tjørnelund moved to DMC at half-time and the game turned. Against a
creative AMC behind a striker, guarantee a screen in front of the back four from kick-off, and do not
talk a matchup assignment away with a small rating split.
**A DM's rating is not comparable to anyone else's.** DMs average 6.58 to a central midfielder's
7.07 for the same performance (within-player gap +0.48), and the rating rewards a DM's key passes,
not his screening. A DM averaging 6.5 is par, 6.7+ is playing well — see
[`match-rating-position-bias`](../../../docs/agent-context/match-rating-position-bias.md).
Note whose screen a role label belongs to (IW / PF / Poacher / AF / AP) every time, or a briefing
will attribute the opponent's roles to us.

## Gotchas if you write your own query
- **Attribute columns are Capitalised** on `mart.fact_player_snapshot` (`Pace`, `Positioning`);
  **lowercase** in `site.role_weights`.
- **Membership is `mart.squad_membership`, never `club_tid`.** A player's record can keep our club
  long after a loan lapsed (Ernest Nuamah's loan ended 2023-06-30 and his record still named us 16
  months later). The squad arrays don't have that fault. Loans out are `mart.fact_loan_spell`.
- **Reconcile a squad pull against the coverage line.** `in_squad` is the squad array; `rated` is
  how many have positions (and so a Level). A large gap means players our data has no attributes
  for, and the frame is thinner than it looks.
- Cross-snapshot per-player work keys on `person_id`, not `tid` — FM recycles retired players'
  slots, and `person_id` carries the date of birth that tells two occupants apart.
- Opponent `name` **resolves for every club** (`mart.dim_person`).
- `positions` lists only the positions a player has some familiarity at (1–20; 15+ is natural).

## No local store
Attach the published full store over R2 — **as `"fm-frem"`**, since the views carry that catalog
name — then `USE "fm-frem";` and run the same recipes (the ATTACH secret is in
[`query-fm-data`](../query-fm-data/SKILL.md)). The slim `-mart` copy has no
`mart.squad_membership` and no `site.*`, so it cannot run this scout. Without R2 credentials, hand
off to [`scout-from-site`](../scout-from-site/SKILL.md), which is built for exactly that (the
deployed site's JSON). It carries its own, narrower set of caveats (no per-match H2H beyond
`matches.json`, no manager record) — don't quietly deliver that thinner report under this skill's
name.

## Hard limitations — state them in the report
- **The exact XI on the day is NOT in the save** — the manager record gives his standing
  preferred/attacking/defensive formation and Style, which is the baseline, but it is a preference,
  not a guarantee. A fresher in-game scout screen from the user narrows this further (this week's
  team news) but is optional, not required.
- **Opponent player names ARE resolved** for every club → **use real names** alongside position +
  percentile.
- **Opponent attributes are model estimates (±1)** for technical/mental (Pace/physicals are exact;
  `attributes_are_estimated` on `fact_player_snapshot` says which rows are modelled). Treat as
  directional, not precise.
- **Don't assert loan status in prose from a flag alone** — check `mart.fact_loan_spell`.
- **Check how stale the snapshot is against the fixture date, and say so.** The latest snapshot is
  the last *imported* save, not today's game. Scouting a February fixture off a November snapshot
  means the entire January window is invisible: on one real briefing **six of the opponent's
  starting eleven had arrived since the snapshot**, including the man who ran the game, and on the
  next opponent it was both first-choice full-backs. Sanity-check the user's predicted-XI
  screenshot against step 5 and the frame — **a name in their XI that is absent from the frame is
  probably a new signing**, and one you can often still rate off his previous club (search
  `mart.dim_person` by name with no club filter). State the gap in the caveat line and prompt for an
  import.
- **In-game news items name players from BOTH squads.** An "opposition report on <Club>" screen
  mixes their scout's read with our own players' morale notes. Three names in one such report were
  all ours. Resolve every name against the squads before attributing it.
- **No-data opponents:** the coverage line shows fewer than 11 rated — a **newly-promoted side** we
  haven't parsed in a prior save, or a **lower-division Cup draw** FMM doesn't fully model. A
  **day-1 start save** (0 matches) also has no H2H or league yet. Don't fake tables when the pulls
  come back thin — say plainly they're not in our data yet, that we're strong favourites
  (promoted/lower side), and give a **formation/style-only** briefing (interpret their shape, the
  structural threats — counter + set pieces — and how we break it down, tying to our identity),
  keeping the same template but noting "none available / not in our data" in the data sections.

## Report template — KEEP THIS LAYOUT for every scout (consistency matters)
Technical-analyst tone, to the manager. Prose + small tables. Fill the skeleton below verbatim
(same headings, order, emoji, the italic caveat line, and the closing gaffer line + footer). Base
every claim on the pulls; don't invent numbers.

**Two sections are load-bearing and are never dropped for brevity, even when thin:**
- **The prior-scout line in the Verdict.** Check the log (see "calibration" above) and say what we
  said last time and whether it still holds — or that this is the first scout of them. That pairing
  is the only thing that makes the log calibration rather than a pile of old opinions.
- **The Head-to-head table.** Keep it even when it is two old fixtures; the manager reads it. Say
  plainly how much weight it carries (a two-season-old meeting after both squads turned over is
  near-worthless as evidence, and a promotion or relegation in between is worth naming), and still
  pull the one pattern that survives — home vs away, clinical vs wasteful, out-shot or not.

```markdown
# 📋 Opposition briefing — <Club> (<H or A> this week)
*<Manager name> — preferred **<formation>**, **<Style>** (shifts to <attacking formation> chasing
a goal, <defensive formation> protecting one). <If the user supplied a fresher in-game scout read
that differs, say so and which one this briefing follows.> Caveats: opponent attributes are model
estimates (±1) except pace/physicals; key players are named (names resolve for every club) and
profiled by position + league percentile. <If the snapshot predates the fixture by a window, say so
here and name the players in their XI that our data has never seen.>*

## Verdict
<one line: favourites/underdogs + our H2H record + the single biggest threat + our single biggest
edge. If a prior scout of this opponent exists, one more line: what we said last time and whether
it still holds.>

## Head-to-head (<competitions>)
| Date | V | Score | Res | Shots (us–them) | On target (us–them) | Pass% (us–them) |
|---|---|---|---|---|---|---|
| <yyyy-mm-dd> | H/A | x–y | W/D/L | a–b | c–d | e%–f% |
<one/two-line pattern read: do they out-shoot / out-possess us? did we control but not create
(shots-on-target)? are we clinical? home vs away?>

## Expected shape & where their space is
<interpret their formation + style positionally; name the exploitable space, e.g. the AMC pocket a
flat 4-4-2 leaves, the channels behind weak fullbacks, either side of a lone pivot.>

## Their threats
<ONE section — named player, the numbers behind the threat, and what it means for us. Do NOT also
write a separate "key men" list: that duplicated this section almost line for line in every
briefing, which is why it was removed. Four or five bullets, each in the form
**Name (POS)** — the stat that makes him a threat + the tactical consequence:>
- **<Name> (<POS>)** — <pick the men from BOTH lists: step 7 (`still_there`, with
  goals/assists/key passes against us — lead with that record when he has one) and
  step 5 (Level %ile + the attribute profile beside it). A proven producer against us outranks a
  higher-rated player who has never hurt us. Level %ile, not Fit — see "The pulls"
  above. Then the consequence: who picks him up, which lever contains him, what he punishes if
  ignored.>
- <plus the non-player threats, still with their numbers: the "Their attack vs our defense" row of
  step 3, the direct/set-piece route and the aerial group that delivers it, shot volume
  from the H2H, and anything the partial-data rule withholds.>
- <their BENCH, when it holds a counter-profile to our plan or a player stronger than a predicted
  starter — this is where the briefing has been caught out most often.>

## Game plan
<This section carries WHERE WE WIN inside it — there is no separate "Where we win" heading. That
split made the report state an edge in one section and the instruction acting on it three sections
later; folding them ties the why to the what, which is how the manager reads it. So **every bullet
below names the number or duel that justifies it**, and the edges to work from are the "Our attack
vs their defense" row of step 3 (do we have the quality edge going forward?), their
Defense unit's weak attributes in step 4, and the space their shape concedes.
**Go per-player, not per-unit** — name the individual defender who is the soft spot and say which
KIND he is: a **Positioning** weakness is a run-at-him weakness, an **Aerial/Strength** weakness is
a duel-and-deliver one, and they are usually different players on opposite flanks, so a unit mean
hides both. Read only the columns the role is actually scored on — see "Reading attributes" above.>
- **Shape: standard 4-2-3-1.** <How it sits against theirs — who screens whom, and which flank or
  channel we attack, with the edge that makes it the right one. Prefer our real edges
  (width/pace/creativity) over their strengths (aerial/duels).>
- **Variation:** <ONLY if the data triggers one, in the manager's own vocabulary — a forward wing
  dropping AM→M for cover, the 10 dropping to a 6 against a dangerous opposing AMC, a WB becoming an
  IWB, back four almost always. Name the trigger with its number. If nothing triggers one, write
  "none needed — standard 4-2-3-1" and move on; do not list the menu. A variation you argued AGAINST
  is worth one line when the reason is a finding (e.g. their AMC is their weakest starter, so the
  second pivot buys nothing) — that is analysis, not a menu item.>
- **Settings:** <Mentality / Line / Tempo / Width / Press / Final third / Passing — each justified
  from a duel or a number, not from the preset. Say which of Line and Press you mean, every time.>
- **Personnel:** <the centre-back pairing and why, the flank to load with the gap that justifies it
  (name the pace/positioning numbers on both sides), the in-behind runner, who takes the danger man.>
- **Defend:** <funnel wide/deny centre; screen the direct ball; man-mark aerial threats on set pieces.>
- **Cutting edge / set pieces:** <if the H2H shows control-without-chances, stress chance quality;
  our aerial edge if any — checking BOTH sides of the duel before recommending OR ruling out a
  route, and saying where to deliver rather than just whether to; who to track after our set pieces.>

**One-line to the gaffer:** *<punchy, quotable summary of the plan.>*

---
Saved to the scout log as `state/scouts/<opp_tid>-<snapshot label>-<fixture>.json` (or: NOT saved
— <why>). Grade it after the match by filling `result_note` / `result` in that record.
```

Keep it decision-useful and honest about the estimate limitations (attributes ±1; tactics not in
the save). One opponent at a time — see [`season-outlook`](../season-outlook/SKILL.md) for the
group-level version, which hands off to this skill per fixture. Offer at the end to scout the next
opponent.
