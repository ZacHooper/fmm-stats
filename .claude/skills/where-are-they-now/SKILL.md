---
name: where-are-they-now
description: Nostalgia "where are they now" retrospective for a past Frem squad — filters down to the players who actually featured, tiers them by current status (still here / retired / thriving elsewhere / out on loan / faded to reserves), and pairs it with that season's own story (record, awards, a notable signing, cup run, any club records still standing). Produces a styled HTML artifact. Use when the user wants a walk down memory lane, asks what happened to an old squad, or wants a look-back retrospective on a past season.
---

# Where are they now

A once-a-season indulgence, not a data pipeline — the point is a good read, built on real
numbers. Produced once already for the 2021/22 debut squad (five seasons back); re-run it for
whichever squad the user names, most naturally "N years ago" or "the season we got promoted to
X". Ask which season if it isn't obvious from context — `site.snapshots` (below) gives the
range to pick from.

## Data access
Everything here reads the dbt models: `site.*` for our own matches and appearances,
`mart.*` for people, squads, careers and transfers, and `stg.club_records` /
`stg.player_records` for the in-game Club History screens. Locally, open `fm-frem.duckdb`
read-only under its own file name; with no local store, attach the published full copy — **as
`"fm-frem"`**, because dbt bakes that catalog name into every view — and `USE` it:
```sql
INSTALL httpfs; LOAD httpfs;
CREATE SECRET r2 (TYPE s3, KEY_ID '<R2_ACCESS_KEY>', SECRET '<R2_SECRET_ACCESS_KEY>',
                   ENDPOINT '<R2_ACCOUNT_ID>.r2.cloudflarestorage.com',
                   URL_STYLE 'path', REGION 'auto');
ATTACH 's3://fmm-stats/site-data/fm-frem.duckdb' AS "fm-frem" (READ_ONLY);
USE "fm-frem";
```
The slim `-mart` copy lacks `mart.squad_membership`, `site.*` and the records tables, so it
cannot run this. Multi-statement recipes run with the runner in
[`query-fm-data`](../query-fm-data/SKILL.md).

**Identity is `person_id`** (the game's slot id plus the date of birth). A tid is a recycled slot:
when a retired player's slot is handed to a new, younger person, the newcomer gets a different
`person_id`, so nothing below can blend two people's stories — as long as you join on
`person_id`, never on a bare `tid`. The only place a bare tid appears is the player-records
table (§6), and that join needs checking.

## 1. Pick the season and the squad
`SELECT season, min(snapshot_date), max(snapshot_date) FROM site.snapshots GROUP BY 1 ORDER BY 1`
gives the full range. "N years ago" means the season whose END-YEAR is N less than the newest
snapshot's season — Frem's debut season is `season=2022` (21/22), so five years back from 2027 *is*
the debut season, not a guess.

**Filter down — don't do the whole squad.** Rank by apps and cut at a threshold that leaves a
manageable, meaningful list (10+ competitive apps in the target season worked well for a ~30-man
squad, leaving 22):
```sql
SET VARIABLE season = 2022;
-- §1 the players who featured: 10+ competitive appearances for the first team
CREATE OR REPLACE TEMP TABLE sq AS
SELECT mp.person_id, p.name, p.dob, count(*) AS apps, sum(mp.goals) AS goals,
       sum(mp.assists) AS assists, round(avg(mp.rating), 2) AS avg_rating
FROM site.match_players mp JOIN mart.dim_person p USING (person_id)
WHERE mp.season = getvariable('season') AND mp.competition <> 'Friendly'
GROUP BY ALL HAVING count(*) >= 10;
SELECT * FROM sq ORDER BY apps DESC;
```

## 2. Names
`mart.dim_person` holds every person any snapshot has seen, retired or not, with `name`, `dob`,
`first_seen_date` and `last_seen_date` — the recipes join it on `person_id`.

## 3. Determine current status
One pull places every player: still in our first team, faded to our reserves, out on loan from
us, on a club's staff, playing elsewhere (a player record on the newest snapshot), or no longer a
player anywhere in the save.
```sql
-- §3 where each one is now
WITH latest AS (SELECT max(snapshot_date) AS d FROM site.snapshots),
ours_now AS (
    SELECT sm.person_id, sm.team_tid, sm.is_loan_in FROM mart.squad_membership sm
    WHERE sm.is_current AND sm.is_managed_club),
last_player AS (
    SELECT person_id, max(snapshot_date) AS last_as_player,
           arg_max(team_tid, snapshot_date) AS last_team_tid
    FROM mart.fact_player_snapshot WHERE person_id IN (SELECT person_id FROM sq) GROUP BY 1),
staff AS (
    SELECT person_id, arg_max(team_tid, first_seen_date) AS staff_team_tid,
           arg_max(role, first_seen_date) AS staff_role, bool_or(is_current) AS staff_now
    FROM mart.fact_staff_spell WHERE person_id IN (SELECT person_id FROM sq) GROUP BY 1),
loans_out AS (
    SELECT person_id, arg_max(borrowing_team_tid, season) AS on_loan_at
    FROM mart.fact_loan_spell
    WHERE parent_club_tid = (SELECT club_tid FROM site.our_teams WHERE is_managed)
      AND season = (SELECT season FROM site.snapshots WHERE is_latest)
    GROUP BY 1)
SELECT sq.name, sq.apps,
       CASE WHEN o.team_tid IS NOT NULL AND lo.on_loan_at IS NOT NULL THEN 'out on loan'
            WHEN o.team_tid = (SELECT team_tid FROM site.our_teams WHERE is_managed) THEN 'still here'
            WHEN o.team_tid IS NOT NULL THEN 'faded to reserves'
            WHEN st.staff_now THEN 'now staff'
            WHEN lp.last_as_player = latest.d THEN 'playing elsewhere'
            ELSE 'no longer a player in the save' END AS status,
       t.name AS last_team, n.name AS nation, lp.last_as_player, dp.last_seen_date,
       ts.name AS staff_team, st.staff_role, lt.name AS loaned_to
FROM sq CROSS JOIN latest
JOIN mart.dim_person dp USING (person_id)
LEFT JOIN ours_now o USING (person_id)
LEFT JOIN last_player lp USING (person_id)
LEFT JOIN staff st USING (person_id)
LEFT JOIN loans_out lo USING (person_id)
LEFT JOIN mart.dim_team t ON t.team_tid = lp.last_team_tid
LEFT JOIN mart.dim_club c ON c.club_tid = t.club_tid
LEFT JOIN mart.dim_nation n ON n.nation_id = c.nation_id
LEFT JOIN mart.dim_team ts ON ts.team_tid = st.staff_team_tid
LEFT JOIN mart.dim_team lt ON lt.team_tid = lo.on_loan_at
ORDER BY status, sq.apps DESC;
```
Read the last two buckets with care:
- **"playing elsewhere"** — `last_team` is his club on the newest snapshot. Name the
  league/country beside an unfamiliar club (`nation`).
- **"no longer a player in the save"** — his player record stops at `last_as_player`. If
  `last_seen_date` runs past it, the game still held him as a person after he stopped playing;
  if he has no staff spell either, he **retired**. Don't invent a coaching move without a
  `fact_staff_spell` row — and don't call a man "retired" when `status` says "now staff": that is
  a backroom move, not leaving the game; name the club (`staff_team`).

**Cross-check every "still here" against recent minutes** — a squad-array row with no minutes in
two seasons is a reserve-list fixture, not a first-teamer:
```sql
SELECT season, count(*) AS apps, sum(minutes) AS minutes
FROM site.match_players
WHERE person_id = (SELECT person_id FROM mart.dim_person WHERE name = 'Andreas Garly')
GROUP BY season ORDER BY season;
```

## 4. Post-departure story — `mart.fact_player_season`
This is the section that makes the retrospective worth reading (the user's own steer: "this
kind of is the crux of this artifact"). It's a season-by-season club/fee/apps/goals/assists/
rating table, **worldwide**, not scoped to our club:
```sql
SELECT f.season, t.name AS team, n.name AS nation, f.fee_kind, f.fee_gbp,
       f.apps, f.goals, f.assists, f.rating
FROM mart.fact_player_season f
JOIN mart.dim_person p USING (person_id)
LEFT JOIN mart.dim_team t USING (team_tid)
LEFT JOIN mart.dim_club c ON c.club_tid = t.club_tid
LEFT JOIN mart.dim_nation n ON n.nation_id = c.nation_id
WHERE p.name = 'Andreas Garly'
ORDER BY f.line_index;
```
- **The fee is on the SELLING club's line**: a `fee` row's `fee_gbp` is what the buyer paid when
  he left that club (Nordsjælland's 2022 line reads £37,000 — what Frem paid for Garly). `stay`
  = contracted there, no move; `free` = free transfer; `loan` = a loan move; `contract_ended` = he
  left when it ran out. Quote fees in £ — they read well ("signed for £37,000").
- **Always name the league/country** next to an unfamiliar club — confirmed this is what makes the
  "moved on" tier readable rather than a wall of club names nobody recognises.
- Use the post-move rows to say whether they're **actually doing well** — apps, goal
  involvements, and rating with enough of a sample to mean something. That's the whole point of
  this tier, more than the tiers either side of it.
- A goalkeeper's `goals` are goals CONCEDED.
- **A suspiciously thin history is worth one more look** — a signing with a named origin club but
  no rows before his first Frem season. `mart.dim_person.origin_club_tid` names where he started;
  if the two disagree, say "our data has no record of his earlier career" rather than inventing
  one.

## 5. Loan-only players — treat separately
Anyone whose *only* connection to the club is a loan was never really "ours". Give them their own
tier and read their post-loan trail the same way as §4. Worth flagging if they were loaned to us
**more than once** — it's a nice detail and it's easy to miss if you only look at the season in
question:
```sql
-- §5 who was only ever here on loan, and how many seasons he was loaned to us
SELECT p.name, bool_and(sm.is_loan_in) AS loan_only,
       (SELECT count(DISTINCT l.season) FROM mart.fact_loan_spell l
        WHERE l.person_id = sm.person_id
          AND l.borrowing_club_tid = (SELECT club_tid FROM site.our_teams WHERE is_managed)) AS loan_seasons
FROM mart.squad_membership sm JOIN mart.dim_person p USING (person_id)
WHERE sm.is_managed_club AND sm.person_id IN (SELECT person_id FROM site.match_players
                                              WHERE season = getvariable('season'))
GROUP BY sm.person_id, p.name HAVING bool_and(sm.is_loan_in);
```

## 6. That season's own story (the summary section)
- **Record & attendance, cup run, the promotion trail, a notable signing, standout games** — one
  recipe (cup-match counts across every season gauge the depth of a run: a two-legged tie near the
  end inflates the count, so 7–8 cup matches against 2–3 in a normal year is very likely a run to
  the final rounds — worth naming, and worth checking whether it's the deepest in the club's
  history; `went_through` says how each tie ended). Run it in the same session as §1, which sets
  `season`. Read the trail off the per-season league
  names, which is what shows a multi-year climb one step at a time:
  ```sql
  -- §6 the league campaign, and the crowd
  SELECT competition, count(*) AS p, count(*) FILTER (WHERE result = 'W') AS w,
         count(*) FILTER (WHERE result = 'D') AS d, count(*) FILTER (WHERE result = 'L') AS l,
         sum(gf) AS gf, sum(ga) AS ga
  FROM site.matches WHERE season = getvariable('season') AND stage_kind = 'League' GROUP BY 1;
  SELECT * FROM site.attendance ORDER BY season;
  -- cup run: every cup match of the season, and cup-match counts across every season
  SELECT match_date, competition, stage, venue, opponent, gf || '-' || ga AS score, result, went_through
  FROM site.matches
  WHERE season = getvariable('season') AND stage_kind IN ('Knockout', 'Qualifying', 'Group')
  ORDER BY match_date;
  SELECT season, competition, count(*) AS matches FROM site.matches
  WHERE stage_kind IN ('Knockout', 'Qualifying', 'Group') GROUP BY ALL ORDER BY competition, season;
  -- the promotion trail: our league, season by season
  SELECT season, any_value(competition) AS league, count(*) AS p, sum(pts) AS pts
  FROM site.matches WHERE stage_kind = 'League' GROUP BY season ORDER BY season;
  -- notable signings that season
  SELECT p.name, extract(year FROM age(coalesce(t.move_date, make_date(t.season::INT - 1, 7, 1)), p.dob)) AS age,
         c.name AS from_club, t.fee_gbp, t.fee_kind, t.move_date
  FROM mart.fact_transfer t JOIN mart.dim_person p USING (person_id)
  LEFT JOIN mart.dim_club c ON c.club_tid = t.from_club_tid
  WHERE t.to_club_tid = (SELECT club_tid FROM site.our_teams WHERE is_managed)
    AND t.season = getvariable('season') AND t.transfer_type IS NOT NULL
  ORDER BY t.fee_gbp DESC NULLS LAST;
  -- hat-tricks and standout games
  SELECT p.name, mp.match_date, m.opponent, mp.competition, mp.goals, mp.assists, mp.rating
  FROM site.match_players mp JOIN mart.dim_person p USING (person_id) JOIN site.matches m USING (match_id)
  WHERE mp.season = getvariable('season') AND (mp.goals >= 3 OR mp.goals + mp.assists >= 4)
  ORDER BY mp.match_date;
  ```
  **The notable signing** is usually not the outlay: a low fee for a teenager who went on to rack
  up appearances is the good story (Garly, £37,000 at 18, six seasons and counting).
- **Player of the Season / Golden Boot**: highest `avg_rating` and highest `goals` from the §1
  query (with an apps floor) — call out explicitly if it's the same player, it usually is.
- **Still-standing records** — the in-game Club History screens:
  ```sql
  -- club records still standing (the in-game Club History 'overall' screen, latest snapshot)
  SELECT r.category, r.value, r.record_season, o.name AS opponent, r.score_for, r.score_against
  FROM stg.club_records r LEFT JOIN mart.dim_team o ON o.team_tid = r.opponent_tid
  WHERE r.club_tid = (SELECT club_tid FROM site.our_teams WHERE is_managed)
    AND r.record_table = 'overall'
    AND r.snapshot_date = (SELECT max(snapshot_date) FROM stg.club_records)
  ORDER BY r.slot;
  SELECT r.category, r.value, r.unit, r.record_season, d.name AS holder
  FROM stg.player_records r
  LEFT JOIN mart.fact_player_snapshot f
         ON f.tid = r.player_tid AND f.snapshot_date = r.snapshot_date
  LEFT JOIN mart.dim_person d ON d.person_id = f.person_id
  WHERE r.club_tid = (SELECT club_tid FROM site.our_teams WHERE is_managed)
    AND r.record_table = 'overall'
    AND r.snapshot_date = (SELECT max(snapshot_date) FROM stg.player_records)
  ORDER BY r.slot;
  ```
  `record_table = 'overall'` is the all-time screen (`'season'` is the current season's, where
  `record_season` means nothing). **`record_season` is the season's START year** (2021 = 21/22,
  our season 2022): Frem's 8-0 at Brønshøj on 2021-09-02 is a 2021 record. Cross-check the
  score/opponent against the target season's own `site.matches` row before claiming a record is
  "from that year" — several records belong to *later* seasons. A club-level record (biggest win,
  highest-scoring match) surviving is a great callback if the target season set it; an individual
  season record usually gets broken by a later squad, which is itself worth a line ("no individual
  season record from that year still stands"). The player-records holder is matched on the slot id
  at the newest snapshot, so for an old record check the holder actually played for us that
  season (§4) before naming him — a recycled slot names its new occupant.

## 7. Build the artifact
This is an editorial page, not a dashboard — load `artifact-design` (via the `Artifact` tool's
`quickstart`) and give it real design attention: a season-summary hero (record, awards, notable
signing, records-that-survive, promotion trail), then tiers as cards. Tiers that worked well:
**Still here** → **Retired** → **Out in the world** (the crux — give it the most text) →
**Loan-only** → **Faded to reserves** (kept brief, one standout fact each). Note the filter
threshold and any data gaps (§4's chain-gap caveats) in a short footer, not the intro — it reads
better as a footnote than as a hedge up front.

**The filter is by apps, not by fame — say so if it surfaces someone forgettable.** A squad
player who crossed the 10-apps line and is still technically on the books will get a card next
to the players everyone actually remembers, purely because the query has no way to weigh
"memorable" against "met the threshold." That's fine and honest, but don't invent a bigger story
for them than the data supports — a plain one- or two-line entry is the right length when
someone's whole footprint is a modest run of appearances, and it's worth flagging in the
write-up that inclusion here means "featured that season," not "notable."

## Gotchas, summarised
- **Join on `person_id`, never a bare `tid`.** A tid is a recycled slot; `person_id` carries the
  date of birth, so two occupants of one slot are two people. The one exception is the player
  records table's holder (§6) — check it.
- "Not at Frem now" is not "retired": §3's buckets separate retired, staff, and still playing
  somewhere.
- A loan-only player (§5) was never really ours — his own tier.
- The fee sits on the selling club's career line, in £.
- Always tag the league/country next to an unfamiliar club name.
- Read a multi-season promotion trail off `site.matches`' per-season league names, not one
  snapshot's league.
- A club record and an individual-season record are different tables (`stg.club_records` vs
  `stg.player_records`) — check both, and check the actual date/score against your target season
  before attributing a record to it.
- Gauge cup-run depth by match count across every season, not just the target one — see §6.
