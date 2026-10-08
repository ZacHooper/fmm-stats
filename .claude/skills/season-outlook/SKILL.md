---
name: season-outlook
description: Produce a wider-than-one-game preparation briefing across a SET of opponents — a promotion stage, a run-in, or a full remaining fixture list — for the active FM career. Ranks the group by difficulty (squad-quality gap + H2H), maps the recurring threat pattern, recommends a tactic/press plan per game-type, and gives standings-aware rotation guidance (which fixtures are safe to rest/blood players in, plus a minutes-load view when games have been played). Distinct from scout-opponent (which is one team + one match + the full shape read); this needs no per-team formation input and hands off to scout-opponent for the games worth a full single-match scout. Use when the user says "season outlook", "how do we stack up against <group>", "prep for the run-in / promo stage", or asks for a minutes/fatigue/rotation view.
---

# Season / run-in outlook

The technical analyst zooming out from one match to the **whole run of games**. Answers: *how do we
stack up against this group, which fixtures actually bite, how should the tactic/press flex across
them, and — given where we sit in the table — who do we rest and who do we blood?* **Career-aware**
(reads the active career's store, not a hardcoded club). Immersion rule: reason with ratings,
percentiles, minutes, condition and attributes — **never surface CA/PA** (the Level %ile is the one
allowed CA-derived exception).


## What this is NOT
- Not a single-match game plan — that's `scout-opponent`, one team at a time, with the opposing
  manager's own formation/Style and anything fresher the user adds. This is a squad-quality + risk +
  workload map; it reads each manager's preferred formation only to size each XI.
- It **hands off** to `scout-opponent` for the one or two fixtures it flags as "circle this".
- It writes **nothing to the scout log**. A group outlook can profile a dozen opponents and leave no
  record of any of them, so an opponent covered here and nowhere else looks unscouted forever. Only
  the per-fixture hand-off to `scout-opponent` creates a record — say which teams you covered are
  going unlogged, and offer the hand-off for the ones that matter.

## Resolve context first (do NOT hardcode)
- **Us** = `SELECT team_tid FROM site.our_teams WHERE is_managed` (Frem 346; reserves 7296).
  Rating method, where Fit is needed for our own squad: `SELECT value FROM site.config WHERE key =
  'career_rating_method'` (`frem_minmax_4231`), not `default_method`, which reads the site's
  `frem_attacking_ss`.
- **Snapshot** — `SELECT snapshot_date FROM site.snapshots WHERE is_latest`; every `is_current` in
  the recipes means it.
- **The opponent set comes from the USER** (the stage/run-in list). Resolve each name → its
  **first-team** `team_tid` with `scout-opponent`'s club lookup (`mart.dim_team`, skip the
  `… Reserves` row).
- **Live table position** — ASK / take from the user (points, position, games left). The stored
  table (`mart.standings`, `is_latest`, the championship/relegation split as a later
  `stage_index` — query in `scout-opponent`) reflects the latest *imported* save, which can be
  behind where the user actually is. Use it as directional; **trust the user's stated live points
  when they differ.**

## Reading attributes: a duel, not a squad average
The rules are the same ones `scout-opponent` carries — read
[`scouting-attribute-reads`](../../../docs/agent-context/scouting-attribute-reads.md) for the full
write-up; the short version is below, because a six-team outlook repeats whatever error it makes
five more times than a single scout does.

**Never average attributes across a whole outfield squad.** That mixes attackers and defenders into
one number and compares it to the opponent's equally mixed number. Two failure modes, both observed
on the 2026-03-22 championship-group run:
- It reported "their strength is Tackling" for the two best sides — true of their *midfielders*,
  but the figure was dragged there by forwards who are not judged on Tackling at all.
- It reported "our edge is Movement +3.3" as if it applied everywhere, when Movement is only the
  **attacker's** side of a duel. Redone as *our attack's Movement vs their defence's Positioning*,
  the edge was +1.4 to +4.2 — same direction, different size, and for the first time comparable
  between opponents.

**Aggregate per UNIT and pair each unit against its counterpart**: our attack vs their defence,
their attack vs our defence, midfield vs midfield. A back line does not play a back line.

| The question | Attacker side | Defender's answer |
|---|---|---|
| Can they be run in behind? | **Movement**, Pace | **Positioning**, Pace |
| Who wins it back? | Dribbling, Technique | **Tackling** |
| Who wins the air? | Aerial, Strength | Aerial, Strength |
| Will they last 90? | Stamina | Stamina |

In `frem_minmax_4231`, Movement is weighted **baseline** for a CB and **3–4** for a CM/ST;
Positioning is **3** for a CB and **baseline** for a ST/AMC (`site.role_weights`, lowercase
attribute names; the wide AMs are flat). Quoting an attribute a role is not scored on is quoting
noise.

**Check individual defenders, never only the unit mean.** Confirmed again on Brøndby: back-line
Positioning averaged 12.7, and their first-choice left-back sat on **8** — the flank the whole plan
ended up pointing at. Then weigh it against the rest of that player's profile (the same left-back
has Tackling 15, so he can win a tackle, he just cannot track a runner off the ball).

**Level %ile, not Fit %ile, for every opponent in the group.** Fit (role-weighted rating ×
familiarity) answers "how well would these players suit OUR tactic" — only a fair question about
our own squad. Rank group difficulty on Level %ile (`level_global`, so sides from different
divisions compare).

**Read the decoded numbers as exact** — ~63% exact / ~93% within ±1, and Pace, Strength, Stamina,
Technique, Aggression, Leadership, Agility and Teamwork are exact outright. No hedging.

> **Level %ile can understate a defence badly, and it is worth saying so in the report.** On
> 2026-03-22 our back line read 19 on Level while containing a centre-back with **Positioning 19,
> Tackling 18, Aerial 16** (Pace 10 — hence the low CA). The manager's own read, "our defence has
> been great", agreed with the attributes and not with the percentile. Use Level to rank *opponents*
> against each other; use the duel read to say what will actually happen.

## Step 1 — Group comparison (the core engine)
For each opponent pull, vs us: **Level-%ile quality gap**, **per-unit quality**, **H2H**,
**top threats by Level %ile**, and the **duel edges** above. Rank by quality (difficulty). The
recipe builds the same frame `scout-opponent` does — each current squad player (from
`mart.squad_membership`, never a `club_tid` filter, which keeps lapsed loans) at his most familiar
position (or the one he has actually started in against us), each side's XI the best N per unit
for its manager's preferred formation — for the whole group at once (~20 s). `lined_up` is the
shape each opponent started in the last time it played us: where it differs from the preferred
formation, say so in the group table and set that team's row in `shapes` to it before the XI. Run it with the runner in [`query-fm-data`](../query-fm-data/SKILL.md);
set the `grp` tids to the user's set.
```sql
-- the user's set, by first-team tid (look each up with scout-opponent's club lookup)
CREATE OR REPLACE TEMP TABLE grp AS
SELECT * FROM (VALUES (2465), (360), (337), (364), (326)) AS g(team_tid);
SET VARIABLE us = (SELECT team_tid FROM site.our_teams WHERE is_managed);

-- each side's shape: ours, and each opponent manager's preferred formation; lined_up is the
-- shape that opponent started in the last time it played us (NULL if never, 'unlisted' if
-- its eleven match no listed formation)
CREATE OR REPLACE TEMP TABLE shapes AS
WITH met AS (
    SELECT f.team_tid, m.match_date, list_sort(list(f.position)) AS xi
    FROM mart.fact_player_match f JOIN mart.dim_match m USING (match_id)
    WHERE f.started AND f.team_tid IN (SELECT team_tid FROM grp)
    GROUP BY f.team_tid, m.match_date
    QUALIFY row_number() OVER (PARTITION BY f.team_tid ORDER BY m.match_date DESC) = 1
),
listed AS (
    SELECT formation, list_sort(list(position)) AS xi
    FROM site.formation_slots, range(slots) GROUP BY formation
)
SELECT getvariable('us') AS team_tid, '4-2-3-1' AS formation,
       NULL AS lined_up, NULL::DATE AS lined_up_on
UNION ALL
SELECT g.team_tid, coalesce(s.formation_preferred_name, '4-2-3-1'),
       CASE WHEN met.xi IS NOT NULL THEN coalesce(listed.formation, 'unlisted') END,
       met.match_date
FROM grp g
LEFT JOIN mart.fact_staff_spell sp
       ON sp.team_tid = g.team_tid AND sp.role = 'manager' AND sp.is_current
LEFT JOIN mart.fact_staff_snapshot s ON s.person_id = sp.person_id AND s.is_current
LEFT JOIN met ON met.team_tid = g.team_tid
LEFT JOIN listed ON listed.xi = met.xi;

-- the frame: every current squad player at the position he has started most in the last year
-- of our matches (for an opponent: against us), else his most familiar
CREATE OR REPLACE TEMP TABLE frame AS
WITH played AS (
    SELECT f.team_tid, f.person_id, mode(f.position) AS played_as
    FROM mart.fact_player_match f JOIN mart.dim_match m USING (match_id)
    WHERE f.started AND f.team_tid IN (SELECT team_tid FROM shapes)
      AND m.match_date > (SELECT max(match_date) FROM mart.dim_match WHERE has_detail)
                         - INTERVAL 1 YEAR
    GROUP BY ALL
),
pos AS (
    SELECT sm.team_tid, sm.person_id, f.age, p.position, p.familiarity,
           p.level_league, p.level_global,
           f.Pace, f.Movement, f.Positioning, f.Aerial, f.Strength, f.Tackling,
           f.Passing, f.Decisions, f.Creativity, f.Shooting, f.Stamina,
           row_number() OVER (PARTITION BY sm.team_tid, sm.person_id
                              ORDER BY coalesce(p.position = pl.played_as, false) DESC,
                                       p.familiarity DESC, p.level_league DESC) AS rk
    FROM mart.squad_membership sm
    JOIN mart.fact_player_snapshot f USING (person_id, snapshot_date)
    CROSS JOIN unnest(f.positions) AS u(p)
    LEFT JOIN played pl ON pl.team_tid = sm.team_tid AND pl.person_id = sm.person_id
    WHERE sm.is_current AND sm.team_tid IN (SELECT team_tid FROM shapes)
)
SELECT pos.* EXCLUDE (rk), dp.unit, d.name
FROM pos JOIN mart.dim_position dp USING (position) JOIN mart.dim_person d USING (person_id)
WHERE rk = 1;

-- each side's XI: best N per unit, N = the unit's slots in its shape
CREATE OR REPLACE TEMP TABLE xi AS
WITH slots AS (
    SELECT sh.team_tid, dp.unit, sum(fs.slots) AS slots
    FROM shapes sh
    JOIN site.formation_slots fs USING (formation)
    JOIN mart.dim_position dp USING (position)
    GROUP BY ALL
)
SELECT f.* FROM frame f JOIN slots USING (team_tid, unit)
QUALIFY row_number() OVER (PARTITION BY f.team_tid, f.unit ORDER BY f.level_global DESC)
        <= slots.slots;

-- the group table: quality (Level %ile), per unit, H2H, and the face-offs against us
CREATE OR REPLACE TEMP TABLE units AS
SELECT team_tid, unit, count(*) AS n, avg(level_global) AS q,
       avg(Movement) AS movement, avg(Pace) AS pace, avg(Positioning) AS positioning,
       avg(Aerial) AS aerial, avg(Tackling) AS tackling, avg(Passing) AS passing,
       avg(Stamina) AS stamina
FROM xi GROUP BY ALL;

WITH team AS (SELECT team_tid, avg(level_global) AS q, count(*) AS n FROM xi GROUP BY 1),
h2h AS (
    SELECT opp_tid AS team_tid, count(*) AS p, count(*) FILTER (WHERE result = 'W') AS w,
           count(*) FILTER (WHERE result = 'D') AS d, count(*) FILTER (WHERE result = 'L') AS l,
           sum(gf) AS gf, sum(ga) AS ga
    FROM site.matches WHERE stage_kind IS NOT NULL GROUP BY 1
),
u AS (SELECT * FROM units)
SELECT t.name, sh.formation, sh.lined_up, sh.lined_up_on, team.n AS rated, round(team.q, 1) AS level,
       round((SELECT q FROM team WHERE team_tid = getvariable('us')) - team.q, 1) AS gap,
       round(d.q, 1) AS def, round(m.q, 1) AS mid, round(a.q, 1) AS att, round(g.q, 1) AS gk,
       round(ua.q - d.q, 1) AS we_attack_edge, round(ud.q - a.q, 1) AS they_attack_edge,
       round(um.q - m.q, 1) AS midfield_edge,
       h2h.p || '·' || h2h.w || '-' || h2h.d || '-' || h2h.l AS h2h, h2h.gf || '-' || h2h.ga AS gf_ga
FROM grp
JOIN mart.dim_team t USING (team_tid)
JOIN shapes sh USING (team_tid)
JOIN team USING (team_tid)
LEFT JOIN u d  ON d.team_tid = grp.team_tid AND d.unit = 'defence'
LEFT JOIN u m  ON m.team_tid = grp.team_tid AND m.unit = 'midfield'
LEFT JOIN u a  ON a.team_tid = grp.team_tid AND a.unit = 'attack'
LEFT JOIN u g  ON g.team_tid = grp.team_tid AND g.unit = 'goalkeeper'
LEFT JOIN u ua ON ua.team_tid = getvariable('us') AND ua.unit = 'attack'
LEFT JOIN u ud ON ud.team_tid = getvariable('us') AND ud.unit = 'defence'
LEFT JOIN u um ON um.team_tid = getvariable('us') AND um.unit = 'midfield'
LEFT JOIN h2h USING (team_tid)
ORDER BY team.q DESC;

-- the duels, per unit against its counterpart (+ve = our advantage)
SELECT t.name,
       round(ua.movement - d.positioning, 1) AS our_movement_v_their_positioning,
       round(ua.pace - d.pace, 1) AS our_pace_v_their_def_pace,
       round(ud.positioning - a.movement, 1) AS our_positioning_v_their_movement,
       round(ud.pace - a.pace, 1) AS our_def_pace_v_their_pace,
       round(um.tackling - m.tackling, 1) AS mid_tackling, round(um.passing - m.passing, 1) AS mid_passing,
       round(um.stamina - m.stamina, 1) AS mid_stamina
FROM grp
JOIN mart.dim_team t USING (team_tid)
JOIN units d ON d.team_tid = grp.team_tid AND d.unit = 'defence'
JOIN units a ON a.team_tid = grp.team_tid AND a.unit = 'attack'
JOIN units m ON m.team_tid = grp.team_tid AND m.unit = 'midfield'
JOIN units ua ON ua.team_tid = getvariable('us') AND ua.unit = 'attack'
JOIN units ud ON ud.team_tid = getvariable('us') AND ud.unit = 'defence'
JOIN units um ON um.team_tid = getvariable('us') AND um.unit = 'midfield'
ORDER BY t.name;

-- each opponent's two best players (Level) and its weakest defender on Positioning
SELECT t.name AS team, x.name, x.position, x.level_league, x.Pace, x.Positioning, x.Movement
FROM xi x JOIN mart.dim_team t USING (team_tid)
WHERE x.team_tid IN (SELECT team_tid FROM grp)
QUALIFY row_number() OVER (PARTITION BY x.team_tid ORDER BY x.level_league DESC) <= 2
     OR (x.unit = 'defence'
         AND row_number() OVER (PARTITION BY x.team_tid, x.unit ORDER BY x.Positioning) = 1)
ORDER BY team, x.level_league DESC;
```
Read out per opponent: quality gap, per-unit quality (**a lone elite unit matters more than the
mean** — a group-best keeper or one 95-100 %ile attacker decides a fixture), H2H with GF-GA (**a
prior defeat flags the danger side even when the quality table does not**), the duel edges, and the
named threats. Check the **goalkeeper** explicitly: a 100 %ile keeper is the single most common
reason a favourable outlook produces no goals. A `rated` below 11 means the side is not in our data
(newly promoted, a lower division): say so and leave its row out of the ranking rather than rank it
off a handful of players. For who has produced against us per opponent, run `scout-opponent`'s
step 7 with that `opp`.

## Step 2 — Cross-group pattern read → run-in tactic plan
Don't just list five matchups — find what **repeats**, because it dictates the whole run:
- **What kind of threat recurs?** (e.g. "danger is almost always central MCs; only two sides carry
  elite wide pace"). Central-only threats → win midfield and most have no plan B.
- **Our universal edges** (e.g. "we beat all five on Stamina") — these justify the base approach
  (fittest side → a high press is low-risk here).
- **Where the base plan must flex** — the sides with **pace in behind** (high `Pace` / a 95-100 %ile
  winger/striker) are the ONLY ones that punish an attacking high line. Those are the "drop the line /
  go the deeper-line variant" games. Key it to `docs/fmm-tactic-blueprints.md` "when to use each":
  default proactive method for the field; the counter/deeper-line variant for the pace threats; the
  break-them-down variant for anyone who'll bunker (likely, if we're clear favourites forcing them to
  chase late).
Output a **base method + the 1-2 named games to flex**, not a wall of per-game plans.

### A quality gap is NOT a reason to plan a cautious game — the trap this step is most prone to
A season outlook often sizes up a group where **we are the underdog in most of it**, and the
temptation is to write four counter-attacking game plans. That was tested and it failed. Away at
Midtjylland with a 45-v-84 quality gap, the cautious plan (counter method, deep line, absorb and
break) drew 1-1 **from 3 shots**. The same fixture replayed with the proactive default —
**Attacking / High / All Over / Fast / Work Into Box / Short through the Centre** — finished **6-0**
on 15 shots, 7 on target. Being out-rated on Level %ile is not the trigger for sitting deep.

**The one genuine trigger is pace in behind against slow centre-backs** — and check it as a *duel*
(their attack's Pace vs our defenders' Pace, plus the individual pacy threat), not as "they're
better than us". On the 2026-03 group, four of the five out-rated us and only one had a real pace
edge over our back line.

**Line and press are two levers.** "Drop the line" reads as "drop the press" and that is the more
expensive half: a 3-0 became 3-2 immediately after the press came off, their deep playmaker
finishing on 32 passes / 28 completed, by ten the most on the pitch. When a game needs protecting,
drop the line and **keep the press on**.

### Carry the shot-quality lever into the plan
If the group contains sides that will bunker, or a top-tier goalkeeper, the binding constraint is
chance *quality*, not chance volume. Shots on target predicts our goals at **r=+0.72** while shot
volume is flat across every accuracy quartile, and crossing correlates **+0.50 with shots but only
+0.23 with goals** — it buys more attempts, not better ones
([`scoring-and-shot-quality`](../../../docs/agent-context/scoring-and-shot-quality.md)). Crossing is
*not* harmful in general: bucketed over 184 matches, goals rise with crosses (1.43 / 1.72 / 1.89 /
1.83 by quartile) and merely plateau at the top. It becomes the wrong delivery only against a
specific profile — aerially strong centre-backs and a high-Handling keeper — so argue it per
opponent, never as a league-wide law.
**`Work Into Box` is the lever** — with it set, the squad's worst shooters simply stop shooting and
team SOT rate went from a 36.2% season average to 47-67%. It is a team instruction, not a selection
problem; say so before recommending a different XI.

### Check who actually scores before recommending anything
A run-in plan that ignores where the goals come from is decoration. Pull goals and assists by
position and by player for the season, and compare each contributor's **share of output** to his
**share of minutes** — on the 2026-03 group this surfaced the whole answer: two players held 73% of
our goals while playing 59% and 46% of available minutes. Under-playing the top scorer is a bigger
lever than any setting in the briefing, and it only shows up if you look. (`site.match_players` is
the managed first team's appearances, `season` our campaign; `position` here is the one he started
in most.)
```sql
-- where the goals come from: share of output against share of minutes, this season
WITH tot AS (
    SELECT person_id, sum(goals) AS g, sum(assists) AS a, sum(minutes) AS mins,
           mode(position) AS position
    FROM site.match_players WHERE season = 2028 AND competition <> 'Friendly'
    GROUP BY person_id
)
SELECT p.name, tot.position, tot.g, tot.a, tot.mins,
       round(100.0 * tot.g / sum(tot.g) OVER (), 1) AS goal_share,
       round(100.0 * tot.mins / (SELECT 90 * count(*) FROM site.matches
                                 WHERE season = 2028 AND stage_kind IS NOT NULL), 1) AS min_pct
FROM tot JOIN mart.dim_person p USING (person_id)
WHERE tot.g + tot.a > 0 ORDER BY tot.g DESC, tot.a DESC;
```

## Step 3 — Rotation guidance
Only meaningful with a **table cushion** (rotation licence) — tie the advice to the user's live
position. This has TWO parts; **lead with the fixture-level one** (it's the reliable signal and it
works on any save):

**3a — Which FIXTURES are safe to rotate into (PRIMARY — always available).** Straight from the
Step 1 difficulty ranking: the **comfortable games** (big Level %ile gap, strong H2H, no elite threat) are
where you rest key men / start youngsters; the **danger side(s)** get full strength. This needs NO
minutes data, so it's the whole rotation answer on a **season-start save**. This is usually the more
useful output — surface it even when the player-load view below is empty.


**3b — Player minutes load (SECONDARY — only if games have been played).** A season-start save has
**zero minutes**, so skip this entirely then (say "no minutes logged yet — early-season save").
When minutes exist, rank by **minutes + age + Stamina** — the durable signals for who can/can't
handle a congested run.

> **Do NOT use `condition` as a fatigue signal.** It's the end-of-last-match reading and **recovers
> to ~100 by the next kickoff** — it tracks how gassed a player got in *one* game, not durable
> tiredness, so it's noise for rotation. (Kept in schema notes only as "what the column is.")


Minutes come from **`site.match_players`** (one row per appearance for the first team — an unused
substitute has no row, so nothing drags the averages toward a flat 6.00) and the team's game count
from `site.matches` (`stage_kind IS NULL` is a friendly). Guard for the 0-games case first —
`SELECT count(*) FROM site.matches WHERE season = <S> AND stage_kind IS NOT NULL`; at 0, skip 3b
and give the fixture-rotation flags (3a) only. Otherwise:
```sql
-- minutes load: every current first-team player, with age and Stamina
WITH games AS (
    SELECT count(*) AS n FROM site.matches WHERE season = 2028 AND stage_kind IS NOT NULL
),
load AS (
    SELECT person_id, count(*) AS apps, count(*) FILTER (WHERE started) AS starts,
           sum(minutes) AS mins, round(avg(rating), 2) AS avg_rating
    FROM site.match_players WHERE season = 2028 AND competition <> 'Friendly'
    GROUP BY person_id
)
SELECT p.name, f.age, f.Stamina, coalesce(l.apps, 0) AS apps, coalesce(l.starts, 0) AS starts,
       coalesce(l.mins, 0) AS mins, round(100.0 * coalesce(l.mins, 0) / (games.n * 90), 1) AS min_pct,
       l.avg_rating
FROM mart.squad_membership sm
JOIN mart.fact_player_snapshot f USING (person_id, snapshot_date)
JOIN mart.dim_person p USING (person_id)
LEFT JOIN load l USING (person_id)
CROSS JOIN games
WHERE sm.is_current AND sm.team_tid = (SELECT team_tid FROM site.our_teams WHERE is_managed)
ORDER BY mins DESC;
```
(Condition is deliberately NOT pulled — see the note above.)

Two player buckets (only when 3b ran):
- **🔴 Heavy load — rotate to rest:** highest minutes, esp. **older** players (age ≥ ~30) and your
  **best performers by rating** (protect the talisman for the games that matter + next season);
  low-`Stamina` + high-minutes is the one to cap.
- **🟢 Fresh & underused — blood them:** low minutes, esp. **young** players — the cushion is licence
  to develop them for the division above. Flag anyone with 0 apps.
Caveats to state: `min_pct` uses games × 90, so genuine mid-season arrivals read artificially
low; 90-min model ignores ET.

## After the fixtures — close the loop
This skill predicts a whole group, which makes it cheap to grade and therefore inexcusable not to.
When the user reports results from the run, revisit the briefing and say plainly which calls held:
the difficulty ranking (did the circled side actually bite?), the duel edges (did we out-move them?),
the recommended base plan, and the rotation calls. `site.matches` has the results and
`site.match_players` the per-player minutes, so the grade is a pull, not a memory exercise.
Record anything that *changed* our understanding in `docs/fmm-tactic-blueprints.md` (dated), not just
in the chat — an undated finding gets quoted forever, and a finding left in a transcript is lost.

## Report template — KEEP THIS LAYOUT
Technical-analyst tone, to the manager. Prose + small tables. Base every claim on the pulls.

```markdown
# 🏆 <Stage/run-in> outlook — <Us> (<N> matches, <k> opponents)
*Squad-quality + risk + workload map across the run. No per-team formations (that's the single-opponent
scout). <Live standing: leaders on X, 2nd on Y — an N-point cushion with M to play.>*

## Verdict
<favourite/underdog for the group + the single game that can actually bite + what the prep is really for.>

## The group (Level %ile — quality, not Fit; +ve gap = we're stronger)
| Team | Level %ile | Gap vs us | D / Mf / A / GK | H2H (P·W-D-L) | GF-GA | Read |
|---|---|---|---|---|---|---|
| ... sorted by Level %ile; mark the ⚠️ danger side (a prior defeat / a 95-100 %ile attacker / a
  top-tier keeper). Per-unit quality earns its column: a group-best GK or one elite unit decides a
  fixture that the squad mean says is even. ... |

## The duels (per unit, against its counterpart — never a squad average)
| Team | We attack: our Movement v their Positioning | their def Pace | They attack: their Movement v our Positioning | their Pace | Midfield edge |
|---|---|---|---|---|---|
| ... +ve = our advantage. Name the individual outlier too — the back-line mean hides the 8. ... |

## ⚠️ The one(s) to circle — <Team>
<why: the only side to beat us / their elite man at N-th %ile / they out-<attr> us; recommend a full
single-opponent scout when it comes up, and the likely tactic flex.>

## The pattern across the group
<the 2-3 things that repeat: recurring threat type, our universal edge(s), the exposure that flexes the plan.>

## Where our goals come from
<goals + assists by position, then the share-of-output vs share-of-minutes comparison. If a top
contributor is under-played, say it here — it outranks every setting below.>

## Plan for the run-in
- **Default:** `<method>` + <press/approach> for <the field / named routine games>.
- **Flex:** <drop the line / `<counter variant>` for the pace-threat game(s); `<lowblock variant>` vs anyone who bunkers.>

## Rotation
**Safe to rotate into:** <the comfortable fixtures from the group table — big quality gap + good H2H +
no elite threat — rest key men / start kids here>. **Full strength:** <the danger side(s)>.
<Player-load — only if games have been played; on an early-season save write "no minutes logged yet":>
🔴 Heavy load — rotate to rest: <players + mins% + age/Stamina why (talisman, veteran, low-stamina)>
🟢 Fresh & underused — blood: <players + why; flag 0-app squad members>
*Caveats: min% denom = G×90 (mid-season arrivals read low); minutes model ignores ET. Condition is
NOT used (it resets to ~100 each game).*

**One-line to the gaffer:** *<punchy summary: it's won bar X — press the field, cup-tie the danger side, rest legs + blood kids in the soft games.>*


---
Eyeball it on the site's **Squad** and **Matches** pages. Run `scout-opponent <danger side>` for
the full single-match plan when that fixture lands.
```

## Gotchas (shared with scout-opponent)
- **Positions come from `fact_player_snapshot.positions`** (a list: `position`, `familiarity`,
  `level_league`, `level_global` — `CROSS JOIN unnest(f.positions) AS u(p)`); the frame keeps each
  player's most familiar one. **Membership is `mart.squad_membership`** (`is_current`, `team_tid`),
  never a raw `club_tid`, which can linger after a loan.
- **A `role_weights` method is a rating weight-set, NOT a tactic.** Rating players with
  `frem_minmax_4231` sets no mentality, line, press, tempo or final-third instruction — name the
  in-game settings too. The full menu surface is
  [`fmm-tactic-options`](../../../docs/agent-context/fmm-tactic-options.md).
- **Any Fit number quoted from a doc must carry the date and squad it was computed on** — a mid-22
  Fit table was quoted at a 2026 squad and put a wrong claim into `scout-opponent`.
- **Attribute columns are Capitalised** (`Pace`, `Stamina`…) on `mart.fact_player_snapshot`, one
  column each; **lowercase** in `site.role_weights`.
- **Level %ile across divisions: `level_global`.** `level_league` is within a player's own league.
- **Reserves rows** share a club's name — take the first-team tid.
- **Standings can lag the live game** — take live points/position from the user.
- The store's views carry the catalog name `fm-frem`: open `fm-frem.duckdb` (or a copy under that
  same file name) read-only, or attach the published copy `AS "fm-frem"` (see `query-fm-data`).
- Opponent attribute limitations from `scout-opponent` apply (opponent attrs are ±1 estimates
  except pace/physicals). Opponent names resolve for every club.

Offer at the end to run a full `scout-opponent` on the circled fixture(s), or a deeper rotation plan.
