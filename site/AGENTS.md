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

**rating = 449.** Familiarity at ST is 20, so `famMult = 1.0` and **effective = 449**. If you get
a different number, you have the weight lookup or the default-of-1 wrong. (Values change when the
career is re-exported; the method is what matters.)

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
CREATE SECRET r2 (TYPE r2, KEY_ID '<R2_ACCESS_KEY>', SECRET '<R2_SECRET_ACCESS_KEY>',
                   ACCOUNT_ID '<R2_ACCOUNT_ID>');
ATTACH 's3://fmm-stats/site-data/fm-frem.duckdb' AS fm (READ_ONLY);
SELECT * FROM fm.staging.players LIMIT 5;
```

Deliberately not a `workers.dev` URL: a network-restricted agent sandbox often can't reach that
host, but the R2 endpoint above (`<account-id>.r2.cloudflarestorage.com`) usually can, since
it's the same host the data pipeline already uploads through. If `INSTALL httpfs` itself 403s,
the sandbox's network policy needs `extensions.duckdb.org` added — that's the one other host
this needs.

This is a *scrubbed* copy — `staging.players.ca`/`.pa` (raw ability) are already NULLed before
publish, so the immersion rule above still holds; there is no extra care needed on your part.
Everything else in the store (attributes, matches, history, contracts, …) is queryable, which
covers questions the JSON files above don't shape an answer for.

## Task guides

For a structured job, fetch the guide and follow it:

- [`guides/scout.md`](https://fmm-stats.zac-g-hooper.workers.dev/guides/scout.md) — scout an opponent for an upcoming match.

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
