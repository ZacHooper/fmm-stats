---
name: query-fm-data
description: Answer a football question about the active FM career (top scorers, head-to-head, tables, transfers, squad, finances, injuries, development) from the published R2 mart via fmq.py or direct DuckDB SQL, without a local rebuild. Use for any quick data question or before writing ad-hoc SQL against the store — it lists the mart views and the ATTACH/club_tid traps.
---

# Answering a quick football question — don't default to a local rebuild
A question like "who was our top scorer last season" does NOT need
`scripts/rebuild.py` (~1 min/snapshot, dozens of minutes total) if a local `fm-<career>.duckdb`
isn't already sitting there. **`fmq.py` reads the already-published R2 copy by default** —
same data, cached locally on first use (~5 s for 101 MB), so the common questions are one line:
```bash
uv run python fmq.py output --season 2024 --include-departed   # top scorers/assists/key passes
uv run python fmq.py output --club OB --vs Frem                # who from OB produces against us
uv run python fmq.py matches --opp OB                          # head-to-head, one row per match
uv run python fmq.py table --season 2026                       # final table, from the fixture list
uv run python fmq.py sql "SELECT ..."                          # anything else, against the same copy
```
For arbitrary SQL without the CLI, `ATTACH` the R2 copy directly instead:
```sql
INSTALL httpfs; LOAD httpfs;
CREATE SECRET r2 (TYPE s3, KEY_ID '<R2_ACCESS_KEY>', SECRET '<R2_SECRET_ACCESS_KEY>',
                   ENDPOINT '<R2_ACCOUNT_ID>.r2.cloudflarestorage.com',
                   URL_STYLE 'path', REGION 'auto');
ATTACH 's3://fmm-stats/site-data/fm-frem-mart.duckdb' AS m (READ_ONLY);

-- "who was our top scorer" — AGGREGATE FIRST, NAME SECOND. Both halves matter:
--   * mart.player_seasons is one row per (player, season, CLUB, COMPETITION), so a league
--     campaign and a cup run are separate rows and have to be summed.
--   * at_club_spells has one row PER SPELL, so joining it before aggregating multiplies
--     every stat by the number of spells that player has — Jakobsen has 5, and his 34 goals
--     come back as 170. Resolve the name in a scalar subquery, after the aggregate.
WITH tot AS (
  SELECT ps.person_id,
         SUM(ps.goals) AS goals,
         SUM(ps.apps)  AS apps,
         ROUND(SUM(ps.avg_rating * ps.apps) / NULLIF(SUM(ps.apps), 0), 2) AS avg_rating
  FROM m.mart.player_seasons ps
  WHERE ps.season = 2024 AND ps.team_tid IN (SELECT club_tid FROM m.mart.managed_club)
  GROUP BY ps.person_id)
SELECT (SELECT any_value(name) FROM m.mart.at_club_spells s
         WHERE s.person_id = tot.person_id) AS name,
       goals, apps, avg_rating
FROM tot ORDER BY goals DESC LIMIT 5;
-- -> Adam Jakobsen 34, Anosike Ementa 12, Anton Pedersen 9 ...
```
`avg_rating` is re-weighted by appearances rather than re-averaged: averaging a 33-game league
average with a 1-game cup average would give the cup 33x the weight it earned.
**Attach the mart object (~87 MB), not the full store (~101 MB)** — it holds the `mart` schema
as real tables with the correctness rules already applied, so a top-scorer query is one
`SELECT` rather than a re-derivation of latest-phase/person_id/minutes logic. Since the
2026-08-25 refactor the mart is also what GENERATES the web app, so it covers the dimensions
too (`mart.clubs`, `mart.leagues`, `mart.player_snapshots` with the 23 attributes wide,
`mart.player_position_levels` for Level %ile, `mart.club_matches` already oriented per club,
`mart.role_weights` so ratings are computable), and the common questions each have a view:
`mart.league_tables` (tables rebuilt from the fixture list; verified for Denmark only),
`mart.head_to_head`, `mart.player_vs_club` (each player's output against each opponent),
`mart.transfers` (every club move with its fee, from the career history; `season` = the campaign
the player moves for),
`mart.squad_finances` (our squad value + wage bill on every snapshot date — owned players only, loanees out of both, the modelled share counted),
`mart.player_primary_position` (the one primary-position rule), `mart.match_stages` (every fixture of a competition we play,
labelled in the game's own words — 'League Path · Third Qualifying Round', 'Group D',
'Championship Group' — with the leg, the tie aggregate and whether the club went through;
from each competition's rules member in the save archive), `mart.match_ratings` / `mart.player_role_seasons` (the game's match rating next to a **position-adjusted** `rating_adj` — compare across positions only on the adjusted one; see `docs/plans/2026-09-23-match-rating-normalisation.md`) and `mart.club_squad_latest`
(every club's genuine squad now), `mart.injury_spells` / `mart.loan_out_spells` (drawn from the
weekly Player Progress rows the parser hands over as stored, `raw.player_progress`, via
`mart.progress_weeks`), `mart.training_focus` (the Training page for every player on every snapshot: focus
position and role, attribute focus, intensity -- a Scrapbook Profile's role is this focus role
on its date; role and attribute names come from `mart.roles` / `mart.training_attributes`,
rendered from `seeds/roles.csv` / `seeds/training_attributes.csv` -- the parser hands over ids only), and `mart.player_development` (a
**development** word per player: 'Lots to come' / 'Developing' / 'Nearly there' / 'At his
ceiling' — the only form potential ever leaves the mart in; there are deliberately no stars). Use the full `site-data/fm-frem.duckdb` only
when you need the `raw` tables or per-snapshot history for a player who was never ours. (The published copies name that schema `staging` until they are next republished, data-layers step 18; `fmq` reads them as published.)

Two gotchas worth knowing before you query it: **macros do not resolve across an `ATTACH`, and
that breaks ORDINARY VIEWS too, not just the obvious macro calls** — `mart.clubs` fails with
`Scalar Function with name phase_ord does not exist` purely because its own SQL calls
`phase_ord`, which lives in `main` and resolves to your LOCAL database. The error names a
missing function, so it does not look like an ATTACH problem at all. **`USE m` first and
qualify nothing**, which fixes every case including `mart.squad_on(d)`; and
**a raw `club_tid` filter for "our squad" is NOT SAFE, on ANY table** — `player_snapshots`,
`player_position_levels`, `players`, all of them — because a loan that lapsed without being
renewed can leave a departed player's `club_tid` still pointing at our club indefinitely (this
is real save data, confirmed against the raw bytes, not an extraction bug). **Use
`mart.squad_current` (current squad) or `mart.squad_on('<date>')` (as of any date) for "who's
ours" — never a bare `club_tid = <our tid>` filter.** Confirmed live, not theoretical: Ernest
Nuamah's loan ended 2023-06-30, but his row a season later still read `club_tid=346,
loaned_in=True`, and turned up as one of "our" attacking outlets in a scout report built on a
raw filter. `mart.squad_current` is scoped to `mart.our_clubs`, so it only answers this for OUR
squad — `fmstats/scout.py`'s `club_attributes()` (and everything built on it: `squad_frame`,
`scout_report`) reads `mart.snapshot_squad`, the same spell-based check for an ARBITRARY club,
since a scout report needs "who's really on the opponent's books" too, not just ours.
`.claude/hooks/session-start.sh` sets up everything this needs (`rclone`, the `r2:` remote, the
`httpfs` extension) automatically on a Claude Code web session — see
[`docs/agent-context/remote-duckdb-access.md`](docs/agent-context/remote-duckdb-access.md) for
the full story and [`site/AGENTS.md`](site/AGENTS.md)'s "Query cookbook" for the three traps
in `match_player_stats`/`players`/`club_tid` that make a naive query wrong, not just imprecise. The R2 copy
carries raw `ca`/`pa` unscrubbed (as of 2026-09-01) — immersion is enforced by never *surfacing*
the number, not by hiding it from SQL, so `mart.player_position_fit`/`player_position_levels`
(Level %ile, Fit ratings — both need `ca` to compute) work against it same as a local store. The
one remaining reason to fall back to a real local rebuild is data more recent than the last
`publish_duckdb.py --upload` (re-run after every import — not automatic); the mart-ONLY object
(`fm-<career>-mart.duckdb`) still omits the rating layer regardless (too big to materialise —
ATTACH the full store for that, not a scrub issue).
