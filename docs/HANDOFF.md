# Handoff — where the project is right now

**Last updated 2026-09-17**, after PR #51.

This file is **state**, not history, and it is deliberately short. Two companions:

- **[`TODO.md`](TODO.md)** — everything still outstanding. One register, nothing else.
- [`CLAUDE.md`](../CLAUDE.md) then [`agent-context/MEMORY.md`](agent-context/MEMORY.md) — the
  durable how-it-works notes.

Read this, then TODO. Anything not in TODO is not outstanding.

---

## The project in three lines

Reverse-engineering **Football Manager Mobile 2022** `.fms` saves into a DuckDB store, a static
web app and a Streamlit dashboard, to manage a career with real data. Active career is
**Boldklubben Frem** (Denmark, `--career frem`, managed tid 346, reserves 7296). Bucaspor
(Turkey) is archived — its saves are kept as the only cross-career parser regression test, and
PR #51 turned that into a real hold-out rather than a nice idea.

## Career state

| | |
|---|---|
| store | **25 snapshots**, `fm-frem.duckdb`, latest **2027 / 2026-07-02** |
| division | **3F Superliga — tier 1, `club_league` cid 2 — since season 2025** |
| how they got there | 3. Division → 2. Division → NordicBet Liga → Superliga, three straight promotions |
| tactic | `frem_attacking_ss` (strikerless SS), the dashboard default |

The squad was built to win the fourth tier. Expect the level gap to be the dominant story.

## Infrastructure — all of it done

- **Storage tiers** (git / R2 / local-only) settled and verified. The store is DISPOSABLE:
  `uv run python scripts/rebuild.py --career frem`.
- **The web app is LIVE** at <https://fmm-stats.zac-g-hooper.workers.dev>, deployed as a
  Worker. Seven sections; it ships data and computes ratings on the client, so switching tactic
  re-rates everyone with no rebuild. Streamlit stays for what writes to DuckDB.
- **Remote-agent SQL over R2** works — `ATTACH 's3://fmm-stats/site-data/fm-frem.duckdb'`.
  See [`agent-context/remote-duckdb-access.md`](agent-context/remote-duckdb-access.md).
- **Squad registration** (the Danish A/B lists, a house rule the save does not model) shipped.

## What PR #51 changed, and what it means for anyone reading data

**Records we were only half-reading are now read in full** — the player record's missing 13
bytes, the staff record (manager **formation triple** and **Style**, closing BUGS #14), the club
record, competition `Level`, and five new reference tables. Detail and the traps hit on the way:
[`PARSER_EXPANSION_HANDOFF.md`](PARSER_EXPANSION_HANDOFF.md).

**The attribute model moved out of the parser into the database.** The parser now scrapes raw
bytes; `staging.attribute_model` holds coefficients and `staging.player_attributes` is a VIEW.
A retrain is a query, not a 25-minute re-extract.

Numbers you should quote, and the two ways of getting them wrong:

| the 9 outfield entangled attributes | exact |
|---|---|
| frozen (2024) | 46.3% |
| **refit** | **59.4%** |
| **Bucaspor, not refitted** | **59.5%** |

- **Score each attribute on the population that HAS it.** A keeper attribute is pinned at the
  display floor for an outfielder, so pooling made Communication read 92.4% when it scores 3.0%
  on actual keepers.
- **The ceiling is 94.8%, not 100%** — measured on attributes read straight from a plain byte,
  where a disagreement is the two sources disagreeing rather than a decode error.
  [`ca-weighting.md`](ca-weighting.md).

**Aerial and Teamwork are closed forms, not fits** — and `docs/ca-weighting.md` also carries
**FM's per-position CA weight tables**, recovered from 155k snapshots, which say what the game
rewards in each slot. That is a scouting asset independent of the decoder.

## What the mart gained on 2026-09-17, after PR #51

PR #51 decoded a lot of records; several were then parsed and surfaced nowhere. Four new views
close that, and each one found a bug or an unknown on the way:

- **`mart.clubs` gained the club record** — facilities, academy, reputation, staff size,
  stadium and capacity, plus **last season's finishing position and the league it was finished
  in**. Frem read at a glance: 3rd in the Superliga on the 8th reputation, the worst-but-one
  training facilities, the biggest squad and staff. `last_league_pos` is NOT the current
  standing and the two columns are meaningless apart — twelve Superliga clubs read
  1,1,2,2,3,4..10 because two of them came up as NordicBet champions and runners-up.
- **`mart.club_attendance`** — real attendance, from the match records. FCK 32,875, Frem 10,924
  in 2026 (14% fill in 2022, 73% now). `staging.club_details.att_*` is NOT this: it correlates
  **−0.31** with what clubs actually draw while capacity correlates **+0.93**. Coverage is
  our-matches-only, so **read `n_games` before trusting `avg_att`** — every club but us has one
  or two home games a season.
- **`mart.match_events`** — goal timings, cards, injuries, penalties, with the scorer named and
  a side. Decoding it named `shootout_goal`/`shootout_miss` (bytes 0x07/0x08). The label is now
  derived from `type_byte` in SQL rather than read from the store, so **naming a future event
  byte needs a one-line edit and `--refresh-only`, not a re-extract**.
- **`mart.competitions`** — cups and friendlies had no dimension at all, so a goal total mixed
  them in silently (our 2026 goals are 67 league / 10 friendly / 1 cup / 1 reserve). It also
  identifies **the reserve league**, which holds 60 fixtures and has no name anywhere in the
  save; `kind = 'reserve'` is derived from `mart.our_clubs`, not hardcoded.

**Two traps worth carrying forward**, because both produced numbers that looked fine until they
did not: joining a per-(season, **phase**) dimension on (season, club_tid) **fans every fact
out by the snapshot count**, and `any_value(x ORDER BY y)` **does not order in DuckDB** —
`max_by(x, y)` is the one that works.

## Where to look

| you want | read |
|---|---|
| what is still open | **[`TODO.md`](TODO.md)** |
| the attribute decoder, and what is already ruled out | [`ATTRIBUTE_MODEL_HANDOFF.md`](ATTRIBUTE_MODEL_HANDOFF.md) |
| what CA is made of, per position | [`ca-weighting.md`](ca-weighting.md) |
| record layouts from the 2026-09 expansion | [`PARSER_EXPANSION_HANDOFF.md`](PARSER_EXPANSION_HANDOFF.md) |
| how to deploy the site | [`DEPLOY.md`](DEPLOY.md) |
| known parser bugs and their history | [`BUGS.md`](BUGS.md) |

## House rules that bite

- **Never surface raw CA/PA.** Percentiles and ranks only. `export_data.py`'s
  `check_immersion()` enforces it for published JSON. Level %ile is the sanctioned exception.
- **Never filter "our squad" on a bare `club_tid`** — a lapsed loan leaves a departed player
  pointing at us indefinitely. Use `mart.squad_current` / `mart.squad_on(d)`.
- **Opponent tactics are not in the save**, but the MANAGER's preferences now are. Ask for the
  in-game scout's formation and style anyway; use `mart.club_managers` as the prior.
- **The capital-province rule**: new signings need an origin club in
  `seeds/eligible_origin_clubs.csv` (the Copenhagen S-tog commuter belt; existing squad and
  academy products grandfathered). **See TODO #5 — 17% of origins do not resolve, and
  `eligible=False` currently cannot be told apart from "unknown".**
