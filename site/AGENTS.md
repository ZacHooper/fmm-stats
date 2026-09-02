# Querying this site as an agent

This is a **Football Manager Mobile 2022 career**, exported from parsed save files. Everything
here is static JSON plus two endpoints. You need no credentials to read.

Fetch **`api/index.json` first, always.** It names the career, the snapshot, the division ladder,
every other file, and the caveats that change what an honest answer looks like. Nothing below is
worth trusting if it contradicts that file — this document describes the shape, `index.json`
describes the current contents.

## The one thing to understand before anything else

**Ratings are not in the data. You compute them.**

A role rating is a weighted sum of a player's 23 attributes:

```
rating(player, role) = Σ over attributes of  value × weight(role, attribute)
```

Weights live in `core.json` → `tactics[method][role][attribute_lowercase]`. **An attribute the
role doesn't list weighs 1.** Attribute keys in `tactics` are lowercase; the names in
`core.attrs` are capitalised — lowercase before you look up.

Then familiarity discounts it, because a player out of position is worse there:

```
famMult(fam) = floor + (1 − floor) × (fam / 20)     // curve "linear_floor", floor from core.familiarity
effective    = rating × famMult(fam)
```

Other curves exist (`proportional` = fam/20; `tiers` = 1.0/0.95/0.85/0.70/0.50 at 18/15/10/5/else).
Read `core.familiarity` rather than assuming.

### Worked example — check your arithmetic against this

Adam Jakobsen (tid 9858), role `ST`, method `frem_attacking_ss`. Weighted attributes:
Aerial 12×3, Shooting 12×3, Passing 10×2, Aggression 14×4, Decisions 10×2, Movement 11×4,
Teamwork 14×3, Pace 12×3, Stamina 14×4, Strength 13×2 — every other attribute ×1.

**rating = 453** at the current snapshot (`2025 / 2024-06-30`). Familiarity at ST is 20, so
`famMult = 1.0` and **effective = 453**. If you get a different number, you have the weight lookup
or the default-of-1 wrong.

His attributes move with every import, so this figure is only a self-check against the snapshot
named above — it read 449 one snapshot earlier and 448 in 2022. The method is what matters. To
re-derive it from the published mart object rather than from the JSON:

```sql
WITH long AS (
  UNPIVOT (SELECT * EXCLUDE (season, phase, snap_ix, phase_date, tid, person_id, name, club_tid,
                             club, league_cid, league_name, nation, dob, age, is_gk,
                             has_attributes, squad_status, reputation, foot_left, foot_right,
                             nationality_id, player_value, wage_units, wage_gbp, contract_expiry,
                             contract_expiry_year, loaned_in, loaned_out, parent_club_tid,
                             parent_club, est_attrs, is_estimated)
           FROM m.mart.player_snapshots WHERE tid = 9858)
  ON COLUMNS(*) INTO NAME attribute VALUE value)
SELECT SUM(l.value * COALESCE(w.weight, 1)) AS rating
FROM long l
LEFT JOIN m.mart.role_weights w
       ON w.method = 'frem_attacking_ss' AND w.role = 'ST'
      AND w.attribute = LOWER(l.attribute);
```

Ratings are only comparable **within a position**. A keeper scores ~324 and a striker ~404 purely
from weight scale. To compare across positions, standardise within position (100 = pool mean,
15 = one standard deviation) or use percentiles.

## The immersion rule — read this before you write anything

The game's underlying ability number ("CA") is **deliberately absent** from every file, and the
manager does not want it surfaced. It is not withheld from you as a trick; it is withheld because
naming it spoils the game they are playing.

What you may use, and should:
- **`lvl_league` / `lvl_global`** — ability *percentiles* per player-position, the sanctioned form.
- **Ability ranks** in `positions.json` — "21 of 40", never the number behind it.
- **`skill_idx`** per league — average ability normalised 0–100.

So: talk about percentiles, ranks and attributes. Never reconstruct or estimate a single ability
score for a player, and never present one.

## Files

All URLs below are absolute and independently followable — you don't need to construct a path
from the base URL of this doc.

| Fetch | Size | Holds |
|---|---|---|
| [`api/index.json`](https://fmm-stats.zac-g-hooper.workers.dev/api/index.json) | 2 KB | manifest: career, snapshot, ladder, files, caveats. **Start here.** |
| [`api/core.json`](https://fmm-stats.zac-g-hooper.workers.dev/api/core.json) | 277 KB (95 KB gz) | our clubs + every club in the division ladder, full attributes; all clubs; all leagues; all 7 tactics. **Schema/reference keys come before the `players` array**, so a truncated fetch still yields a usable schema — only the tail of the player list is lost. |
| [`api/clubs.json`](https://fmm-stats.zac-g-hooper.workers.dev/api/clubs.json) | 207 KB (66 KB gz) | name/tid/league for **every** club in the save (not just the ladder). Fetch this instead of `/api/all` when you only need to resolve a club name. |
| [`api/squad.json`](https://fmm-stats.zac-g-hooper.workers.dev/api/squad.json) | 83 KB | our squad's attributes at **every** snapshot (growth) + career history |
| [`api/forecast.json`](https://fmm-stats.zac-g-hooper.workers.dev/api/forecast.json) | small | the attribute-forecast lookup: given a player's current value of an attribute and his age, what players like him actually had at 21/24. A LEVEL model, not a growth-rate one — a starting attribute like Technique does not predict how fast another attribute grows (+0.000 R² beyond current value), so don't use one attribute to forecast a different one |
| [`api/positions.json`](https://fmm-stats.zac-g-hooper.workers.dev/api/positions.json) | 47 KB | the position review: depth charts, ability ranks, keep/loan/sell reads |
| [`api/matches.json`](https://fmm-stats.zac-g-hooper.workers.dev/api/matches.json) | 115 KB | every parsed match + every per-player-per-match row |
| [`/api/all`](https://fmm-stats.zac-g-hooper.workers.dev/api/all) | 1.3 MB gz (full); a few KB filtered | **every player in the save** (~23,800), full attributes. Add `?club=<tid>[,<tid>...]` and/or `?tid=<tid>[,<tid>...]` to get back only those players instead of the whole file — the response keeps the same shape (`attrs`/`fields`/`players`/`note`) plus `count` and `filtered_by`. Use `clubs.json` first to find the tid, then `/api/all?club=<tid>` for that club's full attributes. |

## Columnar format — the main gotcha

Player, club, league, match and match-player rows are **positional arrays**, not objects, with a
sibling `*_fields` array naming the slots. Zip them; don't index by guesswork.

```
core.fields  = ["tid","name","club_tid","dob","value","wage","expiry","attrs","positions"]
core.players[0] = [8834,"Samuel Clemmensen",343,"2006-04-30",null,3640,"2025-06-29",
                   [13,6,5,...],                       // 23 values, ordered by core.attrs
                   [["ST",20,12,18]]]                  // see below
```

`attrs` is ordered by **`core.attrs`** — a fixed 23-element list. Position entries are
`[code, familiarity, lvl_league, lvl_global]`: familiarity 0–20, then the two ability
percentiles. A player has one entry per position he has any familiarity in, so an unfiltered
list of "left backs" includes centre-halves who could shuffle across — **filter on familiarity
(≥15 is the house floor) before treating a position as real.**

```
core.club_fields   = ["tid","name","league_cid","players"]
core.league_fields = ["cid","name","nation","reputation","clubs","skill_idx","rated"]
```

`core.pos_role` maps a position code to the role whose weights apply (`DL`→`LB`, `DMC`→`DM`,
`MC`→`CM`, `ML`→`AML` …). `core.ours` carries our club tids, per-player squad status, loaned-in
tids, career-origin clubs and capital-region eligibility.

## Caveats that change the answer

Read `index.json` → `caveats` for the live list. The ones that bite hardest:

1. **Opponent tactics and formation are NOT in the save.** There is no way to derive them.
   If you are asked to prepare for a match, **ask the manager for the in-game scout's formation
   and style.** Guessing produces a confident, useless briefing.
2. **Opponent attribute values are model estimates (±1)** except pace and physicals. Fine for
   shape and comparison; don't hang an argument on a single point.
3. **Squad status and loan flags are unreliable.** Rank by minutes played (`matches.json`).
4. **League standings do not parse for this career** — a 22-game division reads back with max
   `played` 12. There is no league table. Rank clubs by squad strength instead.
5. **`clubs` in `league_fields` is the competition record's member count and is wrong** (5 for a
   12-team division). Count clubs in `core.clubs` by `league_cid` instead — that's exact.
6. **Match detail lives in a ring buffer the game overwrites.** A save late in a season no longer
   holds its opening games, so a short season means *missing* games, not lost ones. Only the
   managed club's matches are richly parsed — these are our records, not the league's.
7. **One snapshot.** Everything except `squad.json` trajectories and `matches.json` describes the
   single snapshot in `index.snapshot`. You cannot see the current in-game state, only that save.

## Prefer SQL? Attach the database directly

Everything above is a fixed export. If you can run DuckDB and want an arbitrary query instead —
grouping, joins, anything not already shaped into one of these files — attach the store itself
straight from R2 over DuckDB's native S3 protocol, using the R2 credentials a Claude Code
session in this project already carries (`R2_ACCESS_KEY`/`R2_SECRET_ACCESS_KEY`/`R2_ACCOUNT_ID`
env vars):

```sql
INSTALL httpfs; LOAD httpfs;
CREATE SECRET r2 (TYPE s3, KEY_ID '<R2_ACCESS_KEY>', SECRET '<R2_SECRET_ACCESS_KEY>',
                   ENDPOINT '<R2_ACCOUNT_ID>.r2.cloudflarestorage.com',
                   URL_STYLE 'path', REGION 'auto');
ATTACH 's3://fmm-stats/site-data/fm-frem-mart.duckdb' AS m (READ_ONLY);
SELECT * FROM m.mart.player_growth_season WHERE season = 2024 ORDER BY growth DESC;
```

**Attach the mart object (~24 MB), not the full store (~34 MB), unless you need raw
`staging`.** `site-data/fm-frem-mart.duckdb` holds the `mart` schema as real tables, with the
four correctness rules already applied — latest-phase-per-season (match stats are a ring
buffer; summing across phases double-counts), snapshot-scoped joins (`staging.players` is one
row per SNAPSHOT), `person_id` not `tid` (FM recycles retired slots), and the 255-sentinel
minutes arithmetic. Querying raw `staging` means re-deriving all four correctly yourself.

Since 2026-08-25 the mart is what GENERATES the files above, so anything in this document is
answerable from it: `mart.player_snapshots` (bio, contract, the 23 attributes wide),
`mart.player_position_levels` (Level percentiles + familiarity), `mart.clubs`, `mart.leagues`
(incl. `skill_idx`), `mart.club_leagues` (club→league **as at** a snapshot), `mart.club_matches`
(every match already oriented per club — venue, opponent, gf/ga, result, pts, `our_`/`opp_`
stats), `mart.player_career_seasons`, `mart.player_origin`, and `mart.role_weights` /
`mart.position_roles` / `mart.app_config` so ratings are computable without the JSON.

Reach for the full store — `ATTACH 's3://fmm-stats/site-data/fm-frem.duckdb' AS fm` — only when
you need raw `staging`, or per-snapshot history for a player who was never ours. It carries the
`mart` views too.

**Scoping in the published mart object.** The growth family is scoped to our clubs (first team +
reserves), since `player_attribute_growth` unscoped is 8.88M rows / 108 MB and ours are 0.24% of
it. The world-wide dimensions — `player_snapshots`, `player_position_levels`, `player_origin`,
`player_career_seasons` — carry the **newest snapshot only**; every snapshot cost 17 MB for
near-duplicates, and our players' history is the growth family. Opponent data is NOT scoped:
`mart.match_player_facts` keeps every opponent appearance and `mart.at_club_spells` all ~3,330
clubs. The method-dependent rating layer (`player_role_ratings`, `player_position_fit`) is absent
— 27M and 9.4M rows, and it needs the ability number the published copy does not have.

Player names come from the spell tables — `match_player_facts` is keyed by `person_id`, so join
`mart.at_club_spells USING (person_id)` for a name.

**Aggregate before you join a name on.** `mart.at_club_spells` is one row per SPELL, so
joining it to a fact table before the `GROUP BY` multiplies every stat by that player's spell
count. Adam Jakobsen has five spells, so his 34 goals come back as 170. Aggregate on
`person_id` first, then resolve the name in a scalar subquery:

```sql
WITH tot AS (SELECT person_id, SUM(goals) AS goals FROM m.mart.player_seasons
             WHERE season = 2024 GROUP BY person_id)
SELECT (SELECT any_value(name) FROM m.mart.at_club_spells s
         WHERE s.person_id = tot.person_id) AS name, goals
FROM tot ORDER BY goals DESC;
```

Related: `mart.player_seasons` is one row per (player, season, **club**, **competition**), so a
league campaign and a cup run are separate rows. Sum them, and re-weight `avg_rating` by apps
rather than averaging the averages.

**`mart.squad_on(d)` is a macro and macros do not cross an `ATTACH`** — its body looks for
`mart.player_spells` in YOUR catalog, not in `m`. Either `USE m` first, or use
`m.mart.squad_current` (a plain view, newest snapshot, one row per person with `is_loan_in` and
`is_reserve`). `squad_on` returns one row per SPELL, so a borrowed player appears twice.

**Do not trust `staging.players.loaned_in` / `.loaned_out`.** The save sets them and never
clears them, so they accumulate: at the newest snapshot the flag claimed nine loanees where
three loans were live. The spell tables are the answer — that is what they exist for.

`mart.squad_on('YYYY-MM-DD')` is a table macro — call it, don't select from it.

Use `TYPE s3` with an explicit `ENDPOINT`, not the `TYPE r2`/`ACCOUNT_ID` shorthand — in
testing, the shorthand silently fell through to public AWS S3 instead of R2 from a
network-proxied sandbox.

Deliberately not a `workers.dev` URL: a network-restricted agent sandbox often can't reach that
host, but the R2 endpoint above (`<account-id>.r2.cloudflarestorage.com`) usually can, since
it's the same host the data pipeline already uploads through. If `INSTALL httpfs` itself 403s,
the sandbox's network policy needs `extensions.duckdb.org` added. One more wrinkle: DuckDB's
installer defaults to a *plain HTTP* URL, which can still 403 even once the HTTPS host is
allowed (a network policy commonly allowlists by host **and scheme**) — if so, fetch the `.gz`
over HTTPS yourself and drop it in `~/.duckdb/extensions/v<version>/<platform>/` (see
`scripts/publish_duckdb.py`'s docstring for the exact commands), then `LOAD httpfs` picks it up
from the local cache with no `INSTALL` needed. **A Claude Code session working in this repo
doesn't need to do any of this by hand** — `.claude/hooks/session-start.sh` installs `rclone`,
configures the `r2:` remote, and pre-places the `httpfs` extension from our own R2-vendored copy
automatically on startup.

### Query cookbook — three traps this schema has that a fixed export doesn't

Raw SQL gets you the underlying tables directly, which means you also own the two dedup rules
`dashboard/db.py`'s helper functions (`player_match_totals`, `squad`, …) apply for you in the
Python app. Skip either one and the numbers are wrong, not just imprecise — e.g. a naive query
for a player's season goals can come back **10-20× too high**.

1. **`staging.match_player_stats` is a ring buffer, not a season table.** Every import snapshot
   re-scrapes however much match history the save still holds, so **later snapshots in the same
   season are supersets of earlier ones** — summing `goals` across every `(season, phase)` row
   double- (or 10×-) counts every match that appears in more than one snapshot. Always restrict
   to **one `phase` per `season`** — the latest one, since later fully contains earlier:
   ```sql
   WITH chosen AS (
     SELECT season, MAX(phase) AS phase FROM staging.match_player_stats GROUP BY season
   )
   SELECT m.tid, SUM(m.goals) AS goals
   FROM staging.match_player_stats m JOIN chosen USING (season, phase)
   WHERE m.team_tid = <club tid> AND m.competition = '<competition name>'
   GROUP BY m.tid;
   ```
   (`MAX(phase)` works because phases are `YYYY-MM-DD` strings within a season here; the
   dashboard's own helper uses an `arg_max` that also tolerates the legacy `start/mid/end`
   words — see `dashboard/db.py::player_match_totals` for that fuller form.)
2. **`staging.players` is ALSO one row per snapshot, not one row per player.** A naive
   `JOIN staging.players p ON p.tid = m.tid` multiplies every stat row by however many snapshots
   that player appears in (16+ across this store's history) — the same 10-20× inflation as #1,
   from a completely different cause. Either join on the **same** `(season, phase)` as the stats
   row (`JOIN staging.players p ON p.tid = m.tid AND p.season = m.season AND p.phase = m.phase`),
   or look the name up once from a single fixed snapshot (`db.latest_snapshot()`'s `(season,
   phase)` pair, or any one row via `WHERE tid = ... ORDER BY season DESC, phase DESC LIMIT 1`).
3. **`club_tid` at the latest snapshot can still show a loan-in whose loan lapsed years ago —
   this is real save data, not a bug you can filter around.** A loan is renewed by the game
   every season, but the byte marker that records "who's on this club's squad list" apparently
   does not always get cleared when a renewal doesn't happen, so `staging.players`/
   `mart.player_snapshots`/`mart.player_position_levels` can keep listing a departed loanee at
   `club_tid = <our club>` indefinitely — confirmed against the raw `.fms` bytes, not an
   extraction glitch. **For "who is on our books right now" (or as of any date), use
   `mart.squad_current`** (current squad, one row per person, `is_loan_in` correct) or
   **`mart.squad_on('<date>')`** (same question for an arbitrary date — call it after `USE m`
   or via the `m.mart.squad_current`/`squad_on` forms, since a macro's body does not resolve
   across an `ATTACH`). Both are built from `mart.loan_in_spells`, which requires match
   appearance evidence before it will call someone loaned-in for a season — a lapsed loan
   cannot come back. **Never** infer "current squad" from a raw `club_tid` filter on
   `player_snapshots`/`players`/`player_position_levels` — it will include names who left the
   club, sometimes years ago (Haarbo, Nuamah and 4 others in this store, as of writing).

**This copy is NOT scrubbed** — `staging.players.ca`/`.pa` (raw ability) are present and
queryable, same as a local store, since Level %ile / Fit ratings (`mart.player_position_fit`,
`mart.player_position_levels`) both need `ca` to compute and came back completely empty when
this copy used to NULL it out. That means the immersion rule above is now YOUR responsibility
here, not something the export already handled for you: `SELECT ca FROM staging.players` will
return a real number, and the house rule says don't put it in front of the manager. Compute with
it (ratings, percentiles, ranks) freely; never print the raw value itself — same as everywhere
else in this project. Everything else in the store (attributes, matches, history, contracts, …)
is queryable, which covers questions the JSON files above don't shape an answer for.

## Task guides

For a structured job, fetch the guide and follow it:

- [`guides/scout.md`](https://fmm-stats.zac-g-hooper.workers.dev/guides/scout.md) — scout an opponent for an upcoming match.
- [`guides/registration.md`](https://fmm-stats.zac-g-hooper.workers.dev/guides/registration.md) — the squad-registration house rule (A/B lists, home grown). FMM models none of it; every
  field is derived, so report it as "home grown on our reading of the save".

## Deriving the common things

- **Fit percentile** at a position: compute `effective` for every player at that position in the
  scope (usually our division), then the share below your player. Needs ≥8 comparators to mean
  anything.
- **Per-player match aggregates**: group `matches.player_rows` by `tid`, sum the counting stats,
  average `rating`. Rates: `Pass % = passC/passA`, `Tackle % = tackW/tackA`,
  `Header % = headW/headA`, `Cross % = crossC/crossA`, `Shot acc % = shotO/shotA`,
  `Conversion % = goals/shotA`. Per-90 = `90 × stat / minutes`.
- **Head-to-head**: filter `matches.matches` on `opp_tid`, and exclude competitions matching
  /friend/i — friendlies say nothing about a bogey side.
- **Growth**: `squad.trajectories[tid]` is `[[season, phase, attrs], …]` oldest first. Re-run the
  rating formula at each snapshot to get a trajectory under whichever tactic you care about.
