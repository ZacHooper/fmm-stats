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
Frem" this way and had actually left the club a year earlier.

**Cross-check every "still here" and every "just left" against actual recent minutes**, not
just the spell table:
```sql
SELECT ps.season, ps.competition, ps.apps
FROM mart.player_seasons ps WHERE ps.tid=<tid> AND ps.team_tid IN (SELECT club_tid FROM mart.managed_club)
ORDER BY ps.season
```
But **don't jump straight to "retired" either** — that was wrong the first time this skill ran.
When someone has no recent minutes anywhere in the mart, check the RAW status directly before
writing them off:
```sql
SELECT season, phase, tid, name, club_tid, is_staff
FROM f.staging.players WHERE tid=<tid> ORDER BY phase
```
(needs the full store, `f` — `mart.squad_current`/`mart.staff` are our-club-scoped and won't
show a player who moved to an untracked club). Three real outcomes turned up doing this, not
two:
1. **Genuinely retired** — no more rows at all, or the last rows fade out with no destination.
2. **Became club staff** — `is_staff` flips to `True`, with a real (if obscure) `club_tid`.
   This is a coaching/backroom move, not retirement from football — say so, and name the club
   if `f.staging.clubs`/`mart.staff` resolves one (see §4's gotcha for why their playing
   history stops here even though they haven't left the game).
3. **Kept playing somewhere the mart doesn't reach** — `is_staff` stays `False` and `club_tid`
   changes to something `mart.clubs`/`f.staging.clubs` *can* still name, just not a club we've
   ever played or that's in our tracked leagues.

A genuinely current *Frem* player has recent `mart.squad_current` rows or a still-open
(`valid_to` `NULL`) `at_club` spell corroborated by recent minutes — check both. But "not
current at Frem" is not the same claim as "retired," and the raw `staging.players` check above
is the only way to tell which one it actually is.

**Before trusting outcome 3, or ANY row that reappears after a staff spell or an unexplained
gap, check `dob` too, not just `name` and `club_tid`.** The first pass of this skill got exactly
this wrong on two players: both went `is_staff=True` (unattached) for roughly a year, then
`is_staff=False` again at a small foreign club — read, without checking further, as "took a
staff detour, came back to playing." The real story, caught by the user asking why two players
neither of them could place were still showing up: `dob` for both changed the moment they
reappeared as players — the tid had been handed to a completely different, much younger person,
and the raw data simply carried the OLD display name forward onto the new occupant. **A tid is
a recycled slot** (this is documented in `fmparser/mart.py`'s own comments on
`player_career_seasons`), and nothing about `staging.players.name` guarantees it gets refreshed
when that happens. The only reliable check:
```sql
SELECT DISTINCT dob FROM f.staging.players WHERE tid=<tid>
```
More than one distinct `dob` for a tid means at least two different real people are being read
as one — find the transition point (`SELECT season, phase, name, dob, club_tid, is_staff FROM
f.staging.players WHERE tid=<tid> ORDER BY phase`) and treat everything from that point on as a
different person. A retired player whose ID was later recycled is still just retired — write
them up that way, and don't invent a second act for someone else's story.

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
- **Known gap, corrected**: the published mart object's `player_career_seasons` came back
  *empty* for a few players even though the raw chain clearly exists. The first write-up of
  this skill guessed it was a free-agent-origin thing ("no backstory for a player minted
  unattached at world creation") — **that guess was wrong**, caught by checking the raw
  `f.staging.player_history_seasons` table directly across every snapshot instead of trusting
  the published mart:
  ```sql
  SELECT season, phase, seq, hist_season, end_year, club_tid, apps
  FROM f.staging.player_history_seasons WHERE tid=<tid> ORDER BY season, phase, seq
  ```
  The real mechanism: **the chain is walked from the PLAYER attribute record, and it stops
  being populated the moment `is_staff` flips to `True` for that tid** — confirmed on two
  players whose full, real history (including the move that took them away from Frem) is
  sitting right there in earlier snapshots and just stops appearing once they became coaching
  staff, even though nothing else about the row (name, dob) changed. It isn't tid recycling and
  it isn't a missing backstory; the player-history walk simply doesn't run against a staff
  record, so once someone crosses that line their whole player-side chain — past AND future —
  drops out of every snapshot from then on, not just the ones after the switch. **The published
  mart-only object makes this worse**: `player_career_seasons` there is latest-snapshot-only
  (see the R2-access doc), so if the very last snapshot happens to catch someone mid-retirement
  as staff, the mart shows nothing for them at all even though five prior snapshots had their
  complete history. **Always fall back to the raw query above against the full store (`f`)
  before declaring "no data exists"** — it will usually still be there.
- **A second pattern, now CONFIRMED, not just theorised**: a player whose `player_spells` shows
  a normal-looking prior club (not the `65535` free-agent sentinel) but whose
  `player_career_seasons`/raw history has **nothing before their first Frem season at all** — no
  youth rows, no prior-club stats, ever, in any snapshot. Caught on a Class-of-2022/23 player
  ("Thomas De Clercq," supposedly signed from Belgium's KSV Bornem): `SELECT DISTINCT dob FROM
  f.staging.players WHERE tid=<tid>` returned **two** birth dates. The full timeline showed the
  real De Clercq (b. 1983) at Frem only through early 2022, becoming staff shortly after — and a
  brand new tid occupant (b. 2005, a completely different person, "Johan Nordberg") from
  2022-07-01 onward, with zero history of his own, who is who actually played all 22 apps that
  season and everything since. **The Belgian transfer story belonged entirely to the old
  occupant** — `player_spells`/raw `player_history_seasons`, queried by bare `tid` with no `dob`
  filter, silently blends both identities into what looks like one continuous player. This is
  the same `fmparser/mart.py`-documented "a tid is a recycled slot" behaviour as the staff-detour
  gotcha above, just discovered from the other direction (no gap in OUR data to notice — the
  join across two people is seamless unless you check `dob`). **Whenever a player's history is
  suspiciously thin, or a transfer origin doesn't ring true, run the `DISTINCT dob` check before
  writing up the story** — a real signing with unusually few displayed prior seasons is common
  and fine; a signing with a named origin club but literally zero backing history anywhere is
  the tell.

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
  fixture, just the headline scoreline and the exit. **Gauge depth by match count, not
  vibes**: `SELECT season, COUNT(*) FROM mart.club_matches WHERE club_tid IN (managed_club) AND
  competition ILIKE '%Pokalen%' GROUP BY season` across every season, not just the target one —
  a two-legged tie near the end inflates the count, so a season with 7-8 cup matches against 2-3
  in a normal year is very likely a run to the final rounds (semi-final or later), worth naming
  as such and worth checking whether it's the deepest run in the club's history so far.
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
- Retirement isn't "no more `at_club` rows for us" — but it also isn't the automatic fallback
  once "still here" is ruled out. Check raw `staging.players.is_staff` and `club_tid` for
  anyone who drops off before calling them retired (§3) — the real options are retired, moved
  into coaching/staff, or still playing somewhere the mart just doesn't resolve a name for.
- **A tid is a recycled slot, and `name` does not reliably change when the occupant does.**
  Before writing up ANYONE whose story involves a gap, a staff detour, or an origin that doesn't
  quite add up, run `SELECT DISTINCT dob FROM f.staging.players WHERE tid=<tid>` (§3, §4). More
  than one `dob` means you're reading two different people as one. This produced two confirmed,
  wrong storylines in earlier drafts of this skill's own output: two "retired" players who
  looked like they'd come back to play at small foreign clubs (they hadn't — different, younger
  people inherited their IDs) and one active squad player written up under a completely wrong
  name and transfer history for two published pages running (the real player has no prior club
  at all; a different, already-retired person's Belgian signing had leaked into his card).
- `player_snapshots` silently drops retired/staff/departed-to-untracked-club players — use
  `player_spells` for names, always, but see the recycled-tid caution above before trusting a
  name from any source blindly.
- `player_career_seasons` on the **published mart object** is latest-snapshot-only and goes
  empty the moment a tid becomes staff — even if their full real history exists in earlier
  snapshots. Before writing "no data survives" for anyone, check the raw
  `f.staging.player_history_seasons` across every snapshot, not just the mart (§4).
- `fee` is in **£000s**, and `~65532` is a sentinel, not a windfall.
- Always tag the league/country next to an unfamiliar club name.
- Don't infer a multi-season promotion trail from `club_leagues` (latest-only) — read it off
  `club_matches`'s per-season competition names instead.
- A club record and an individual-season record are different tables (`club_records` vs
  `player_records`) with different lifespans — check both, and check the actual date/score
  against your target season before attributing a record to it.
- Gauge cup-run depth by match count across every season, not just the target one — see §6.
