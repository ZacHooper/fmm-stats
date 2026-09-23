---
name: where-are-they-now
description: Nostalgia "where are they now" retrospective for a past Frem squad — filters down to the players who actually featured, tiers them by current status (still here / retired / thriving elsewhere / out on loan / faded to reserves), and pairs it with that season's own story (record, awards, a notable signing, cup run, any club records still standing). Produces a styled HTML artifact. Use when the user wants a walk down memory lane, asks what happened to an old squad, or wants a look-back retrospective on a past season.
---

# Where are they now

A once-a-season indulgence, not a data pipeline — the point is a good read, built on real
numbers. Produced once already for the 2021/22 debut squad (five seasons back); re-run it for
whichever squad the user names, most naturally "N years ago" or "the season we got promoted to
X". Ask which season if it isn't obvious from context — `mart.snapshots` (below) gives the
range to pick from.

## Data access
Same as any quick-question job (see `CLAUDE.md`'s "don't default to a local rebuild"): `ATTACH`
the published R2 copies directly, no local store needed.

```sql
INSTALL httpfs; LOAD httpfs;
CREATE SECRET r2 (TYPE s3, KEY_ID '<R2_ACCESS_KEY>', SECRET '<R2_SECRET_ACCESS_KEY>',
                   ENDPOINT '<R2_ACCOUNT_ID>.r2.cloudflarestorage.com',
                   URL_STYLE 'path', REGION 'auto');
ATTACH 's3://fmm-stats/site-data/fm-frem-mart.duckdb' AS m (READ_ONLY);   -- squad, seasons, spells
ATTACH 's3://fmm-stats/site-data/fm-frem.duckdb'      AS f (READ_ONLY);   -- staging.club_records / player_records only
```
You need the **full store** (`f`), not just the mart, for `staging.club_records` and
`staging.player_records` — the "is this still a club record" check isn't in the mart schema.
Everything else (squad, spells, career history, match facts) comes from the mart object; it's
smaller and already has the correctness rules applied.

## 1. Pick the season and the squad
`SELECT season, phase FROM mart.snapshots ORDER BY phase` gives the full range. "N years ago"
means the season whose END-YEAR is N less than the newest snapshot's season — Frem's debut
season is `season=2022` (phase `2021-07-01`), so five years back *is* the debut season, not a
guess.

**Filter down — don't do the whole squad.** Rank by apps and cut at a threshold that leaves a
manageable, meaningful list (10+ apps in the target season worked well for a ~30-man squad,
leaving 22):
```sql
SELECT ps.person_id, ps.tid, SUM(ps.apps) apps, SUM(ps.goals) goals, SUM(ps.assists) assists,
       ROUND(SUM(ps.avg_rating*ps.apps)/NULLIF(SUM(ps.apps),0),2) avg_rating
FROM mart.player_seasons ps
WHERE ps.season = <season> AND ps.team_tid IN (SELECT club_tid FROM mart.managed_club)
GROUP BY ps.person_id, ps.tid
HAVING SUM(ps.apps) >= 10
ORDER BY apps DESC
```

## 2. Name resolution — use `player_spells`, not `player_snapshots`
`mart.player_snapshots` is **newest-snapshot-only, world-wide** — it drops anyone who has since
retired, and (see gotcha below) anyone with no career-history chain at all. `mart.player_spells`
carries a `name` column on every row for every person who's ever passed through the club, so pull
the name from there instead:
```sql
SELECT * FROM mart.player_spells WHERE person_id='<pid>' ORDER BY valid_from
```

## 3. Determine current status — the retirement trap
Naively: "their last `at_club` spell has `club_tid=346`, so they're still here." **This is
wrong and it will bite you.** A contract renewal can close out one `at_club` row and (if the
mart's spell-builder doesn't stitch it back together) leave no successor row, even though the
player never left. Two Class-of-2021/22 players (a GK and a squad midfielder) looked "still at
Frem" this way and had actually retired a year earlier.

**Cross-check every "still here" and every "just left" against actual recent minutes**, not
just the spell table:
```sql
SELECT ps.season, ps.competition, ps.apps
FROM mart.player_seasons ps WHERE ps.tid=<tid> AND ps.team_tid IN (SELECT club_tid FROM mart.managed_club)
ORDER BY ps.season
```
If a player has no real minutes (or no `mart.match_player_facts` rows with `minutes>0`) in the
one or two seasons before "now", and doesn't appear in `mart.squad_current` or `mart.staff`,
treat them as **retired**, not "still here" — and pull their actual last appearance for a
send-off line:
```sql
SELECT cm.date, cm.competition, cm.opponent, mpf.rating, mpf.minutes
FROM mart.match_player_facts mpf
JOIN mart.club_matches cm ON cm.club_tid IN (SELECT club_tid FROM mart.managed_club)
  AND cm.season=mpf.season AND cm.phase=mpf.phase AND cm.anchor=mpf.anchor
WHERE mpf.tid=<tid> AND mpf.minutes>0
ORDER BY cm.date DESC LIMIT 1
```
A genuinely current player has recent `mart.squad_current` rows or a still-open (`valid_to`
`NULL`) `at_club` spell corroborated by recent minutes — check both.

## 4. Post-departure story — `mart.player_career_seasons`
This is the section that makes the retrospective worth reading (the user's own steer: "this
kind of is the crux of this artifact"). It's a season-by-season club/fee/apps/goals/assists/
rating table, **worldwide**, not scoped to our club:
```sql
SELECT hist_season, end_year, club, fee, apps, goals, assists, rating
FROM mart.player_career_seasons WHERE tid=<tid> ORDER BY seq
```
- **`fee` decoding**: `'stay'` = contracted there, no move that year; `'free'` = free transfer;
  `'loan'` = a loan move; a plain number is the fee **in £000s** (`37` = £37,000) — quote these,
  they read well ("signed for £37,000", "Nordsjælland actually got £216,000 for him"). Treat a
  value near `65532`–`65535` as a decode sentinel (released/free, not a real fee in the
  hundred-million range) and don't quote it as money.
- **Always name the league/country** next to an unfamiliar club (`(Spain)`, `(Germany)`, a
  three-letter tag) — confirmed this is what makes the "moved on" tier readable rather than a
  wall of club names nobody recognises.
- Use the post-move rows to say whether they're **actually doing well** — apps, goal
  involvements, and rating with enough of a sample to mean something. That's the whole point of
  this tier, more than the tiers either side of it.
- **Known gap**: a player who started the save as an unattached free agent (their very first
  `player_spells` row is `club_tid=65535`, "Free agent") has **no history chain at all** —
  `player_career_seasons` comes back empty for them, before Frem and after. This isn't a "club
  not loaded" issue; per `fmparser/history.py`, the chain head pointer (`P-38`) is only valid
  for players who were slotted onto a real club roster at world creation — a free agent dumped
  into the pool at save-gen seemingly never gets one written, the same "no history yet" state a
  newgen has. Say so in the write-up rather than inventing pre/post-Frem stats for these
  players — it'll usually be one or two per squad (a keeper, a squad player signed same week).

## 5. Loan-only players — treat separately
Anyone whose *only* connection to the club is a `loan_in` row (never an `at_club` row with our
`club_tid`) was never really "ours" — a raw squad list can't tell you that, `player_spells`
can. Give them their own tier and read their post-loan trail the same way as §4 (parent club's
`player_career_seasons` chain covers loans out from them too). Worth flagging if they were
loaned to us **more than once** (`spell_type='loan_in'` rows in more than one season) — it's a
nice detail and it's easy to miss if you only look at the season in question.

## 6. That season's own story (the summary section)
- **Record & attendance**: `mart.club_matches` for the target season, `club_tid IN
  managed_club`. `WHERE competition NOT ILIKE '%Pokalen%' AND is_competitive` isolates the
  league campaign from cup/friendlies; sum W/D/L, gf/ga, and `MIN`/`MAX(attendance)` for the
  crowd-growth line.
- **Player of the Season / Golden Boot**: highest `avg_rating` and highest `goals` from the §1
  query (with an apps floor) — call out explicitly if it's the same player, it usually is.
- **A notable signing**: scan `mart.player_career_seasons` for `fee` = a real number in that
  season for anyone in the squad — a low fee for a teenager who went on to rack up appearances
  is the good story, not the outlay.
- **Cup run**: which round they went out in and the standout result — don't list every
  fixture, just the headline scoreline and the exit.
- **League progression since**: `SELECT season, competition FROM mart.club_matches WHERE
  club_tid IN (managed_club) AND is_competitive AND competition NOT ILIKE '%Pokalen%' GROUP BY
  1,2` — read down the seasons for the promotion trail. **Don't infer this from
  `mart.club_leagues`**, which is latest-snapshot-only and will make a multi-year climb look
  like it happened in one step.
- **Still-standing records** (needs the full store, `f`, not the mart):
  ```sql
  SELECT * FROM f.staging.club_records
  WHERE club_tid IN (SELECT club_tid FROM m.mart.managed_club)
    AND phase = (SELECT MAX(phase) FROM f.staging.club_records WHERE club_tid IN (SELECT club_tid FROM m.mart.managed_club))
  ORDER BY category, slot
  ```
  and the equivalent on `f.staging.player_records` for individual season records. Cross-check
  the `record_season`/score against the target season's own `club_matches` rows (same
  opponent, same score, date within a few days — `day` is a day-of-year, roughly ±1 vs the
  real date) before claiming a record is "from that year" — several of these tables' records
  belong to *later* seasons, not the one you're writing about. A club-level record (biggest
  win, highest-scoring match) surviving is a great callback if the target season set it; an
  individual season record (most goals/assists/apps in a season) usually gets broken by a
  later squad, which is itself worth a line ("no individual season record from that year still
  stands").
- **Hat-tricks / standout individual performances that season**, for cross-referencing into a
  player's own card:
  ```sql
  SELECT mpf.tid, cm.date, cm.opponent, cm.competition, mpf.goals, mpf.assists, mpf.rating
  FROM mart.match_player_facts mpf
  JOIN mart.club_matches cm ON cm.club_tid IN (SELECT club_tid FROM mart.managed_club)
    AND cm.season=mpf.season AND cm.phase=mpf.phase AND cm.anchor=mpf.anchor
  WHERE mpf.tid IN (<the filtered squad's tids>) AND mpf.goals >= 3
  ```
  (`mpf.rating` is already 0–10, not ×10.)

## 7. Build the artifact
This is an editorial page, not a dashboard — load `artifact-design` (via the `Artifact` tool's
`quickstart`) and give it real design attention: a season-summary hero (record, awards, notable
signing, records-that-survive, promotion trail), then tiers as cards. Tiers that worked well:
**Still here** → **Retired** → **Out in the world** (the crux — give it the most text) →
**Loan-only** → **Faded to reserves** (kept brief, one standout fact each). Note the filter
threshold and any data gaps (§4's free-agent-origin caveat) in a short footer, not the intro —
it reads better as a footnote than as a hedge up front.

## Gotchas, summarised
- Retirement isn't "no more `at_club` rows for us" — verify against recent minutes, don't trust
  a bare spell-table read (§3).
- `player_snapshots` silently drops retired players AND free-agent-origin players — use
  `player_spells` for names, always.
- `fee` is in **£000s**, and `~65532` is a sentinel, not a windfall.
- Always tag the league/country next to an unfamiliar club name.
- Don't infer a multi-season promotion trail from `club_leagues` (latest-only) — read it off
  `club_matches`'s per-season competition names instead.
- A club record and an individual-season record are different tables (`club_records` vs
  `player_records`) with different lifespans — check both, and check the actual date/score
  against your target season before attributing a record to it.
