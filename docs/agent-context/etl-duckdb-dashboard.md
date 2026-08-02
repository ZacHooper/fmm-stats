---
name: etl-duckdb-dashboard
description: fm-parser DuckDB ETL layer + Streamlit dashboard — how the data becomes usable
metadata: 
  node_type: memory
  type: project
  originSessionId: bd2c915a-239a-455d-8b4f-4109aabadc99
---

The fm-parser extract outputs (`output/<label>/` JSON/CSV) are loaded into a DuckDB store
and consumed by a Streamlit dashboard. Built 2026-07 on top of the existing extractors.

**Layers**
- `load_duckdb.py` (run via `uv run`) → `fm.duckdb`, `staging.*` schema (1:1 mirror of the
  extract files), every row stamped `season` (int end-year, 21/22→2022, Aus-FY style) +
  `phase` (start/mid/end). Idempotent per-label DELETE+INSERT. No enforced PKs (ART index made
  bulk reload hang — natural keys are documented in comments, enforced by the loader). Ledger in
  `staging.extracts`. Label math lives in `extract.parse_label` / `auto_label`.
- Transformed layer = views in `main` (v_match_results, v_league_table, v_top_scorers,
  v_ca_progression, v_transfers, v_player_attributes, **v_player_ratings**, **v_player_rating_ranks**).
- `fmq.py` = query CLI (`uv run python fmq.py league-table 2022 end 228`, etc).
- `dashboard/` = Streamlit app (`uv run streamlit run dashboard/Home.py`): Home, Development,
  Squad Tool (merged calculator+compare), Matches, Player Stats, Tactics, Config.
  Shared helpers in `dashboard/db.py` (config, effective_table, attr groups, primary_position).

**Opposition scouting is codified (added 2026-07-31) — USE IT instead of ad-hoc pulls.**
`db.scout_report(opp_tid, season=None, phase=None, method='buca_433')` returns the full report as
dicts/DataFrames: coverage (partial-squad warning), overall eff, unit edges (us−them per
Def/Mid/Att), key_players (their squad by eff + `pctile_league`), standouts (max per key attr),
h2h (competitive only, friendlies dropped), and rule-based `flags` (squad strength / 🚩 bogey vs
✅ own-them / per-unit edge / danger men / their defensive soft-spots). Helpers: `db.resolve_club`
(name→tid, Turkish/diacritic-insensitive via `_fold`), `db.latest_snapshot`. CLI: `uv run python
fmq.py scout <team|tid>` prints the whole briefing — and it copies the DB to a temp file if the
live one is locked by a running dashboard (`FM_DUCKDB_READONLY=1` env makes `db._connect` attach
read-only). Dashboard Team page → "🔎 Scout a team" tab now shows the auto-read + key-players +
standouts on top of the existing interactive unit comparison + H2H. Still supply opponent
formation/style yourself (tactics aren't parsed). The `scout-opponent` skill can lean on this now.

**Cross-position rating normalisation (added 2026-07-31).** Raw `eff` is NOT comparable across
positions — role weights don't sum to a common total, so mean raw eff runs GK~324 → ST~404 by
scale alone. Fixed: `db._add_position_index(eff)` adds `pos_index` = eff standardised within
position vs the GLOBAL position pool, rescaled to 100=avg / 15=1σ. `db.team_strength(frame,
club_tid)` aggregates the **best XI** (`_best_xi`, canonical 4-3-3 = GK+4+3+3, top-N per unit by
pos_index) → per-unit + TEAM index and mean `pctile_league` (both cross-position fair). scout_report
now uses this: `overall`/`strength` are index+percentile (not raw-eff means), and `key_players`
is ranked by `pos_index` — which correctly surfaces e.g. a 99%ile full-back that raw-eff ranking
buried under mid-tier midfielders. `db.squad_frame(season,phase,method,club_tids)` is the single enriched per-player frame (eff +
pos_index + pctile_league + unit + 23 attrs) and `db.squad_key_players(frame,club_tid,method)`
ranks a club's players by pos_index with `top_attrs` inline — both PUBLIC and shared by the scout
tab AND the **Vs-league tab** (7_Team.py now leads with our best-XI `team_strength` index+%ile per
unit + a TEAM row, plus an "our standouts" table with names/attrs; the drill-down "Overall" is
mean pos_index, not raw eff). Use `pos_index`/`team_strength`/`squad_key_players` for any future
best-XI / squad-review / unit-rating work instead of averaging raw eff.
Each key player also carries `top_attrs` (`_player_top_attrs`): his most threat-defining
attributes shown inline on his row = value + 0.6×role_weight (role-relevant strengths lead but
an elite off-role attr like a striker's Strength 16 still shows), value floor 9, with
Leadership/Teamwork/Aggression (`_LOW_SIGNAL`) and pure-GK attrs (outfield) denied. Note: pure
position-relative z-score was TRIED and rejected — it put Crossing on every DMC (low-variance
inflation) and dropped high-value attrs; value+role-relevance is the shipped approach.

**Positional / effective rating** (added in 2nd feedback round): `staging.player_positions`
(long: every position a player can play + familiarity 1-20; 14 FM codes) + `staging.position_role_map`
(14 codes→10 rating roles) + `staging.app_config` (key/value, editable via Config page). Effective
rating = base role rating × familiarity multiplier (config-driven curve: linear_floor default
floor 0.5 / tiers / proportional). `db.effective_table()` gives per-player-per-position eff +
percentile/rank scoped to league / nation / global (via club→club_league→leagues.nation). Home &
Squad Tool never show CA/PA — only rating + scoped rank. Match/Player-stats pages dedupe cumulative
snapshots by taking the latest phase per season (end ⊇ mid). Attribute groups Technical/Mental/
Physical/Goalkeeping; radar + development charts highlight role-weighted attrs (★key ▲imp △useful).

**Weighted role rating** (immersion-safe alt to CA/PA — user does NOT want CA/PA surfaced ever):
`staging.role_weights(method, role, attribute, category, weight)` is a GLOBAL table seeded from
`seeds/role_weights.csv` (ported from fm-data-entry's `black_hawk`+`personal` dicts; key=4,
important=3, useful=2, else=1). rating = Σ attr×weight per (method=tactic, role); unlisted attrs
×1. Verified EXACT match to fm-data-entry `get_weighted_df`. New tactics = new `method` rows,
added via the Tactics page and preserved across reloads (only built-ins re-seeded). See
[[squad-comparison-bridge]].

**Known data gaps for viz**: non-managed standings are approximate (lightresults-computed) until
the exact-standings parser (Task: fmparser/standings.py) lands; opponent formation is NOT parsed
(formation analysis is our-shape-only); matches exist only for managed club. Own-squad attributes
are exact; other clubs' 14/23 attributes are model-estimated (so league-wide ratings approximate).

Squad definition (db.squad/squad_tids): OUR_CLUBS = (6567 first team, 11320 reserves).
Loaned-out players sit in reserves (club_tid=11320, loaned_out=True), so club_tid IN OUR_CLUBS
captures first team + reserves + loans; status flag = First team/Reserve/Loan. Team-level
(Team page) stays club_tid=6567 (league entity). League/nation ranking resolves club→league
across ALL labels (arg_max latest) so season-start labels borrow the club's prior league.
Nation pool is already just playable mapped leagues; residual optimism is the estimation
caveat (rivals' attrs are model-estimated/compressed, our squad exact → floats up).

Match-appearance decoding (match_player_stats): **pos_order 1–11 = starters** (subOn=255),
**12–20 = bench**. subOff: 255=played to end else minute subbed off. subOn: 255=never came on.
So started = pos_order<=11; appeared = pos_order<=11 OR subOn<>255; unused sub = bench &
subOn=255&subOff=255 (excluded from Apps). minutes = (subOff or 90) − (subOn or 0), gated on
appeared (verified: GK Apps×90 = minutes exactly). Enables Starts/Sub split + per-90.
No injury time (ET matches undercounted). Player-name pick-lists sort by surname (db.surname_key).
team_tid separates first-team (6567) vs reserve (11320) matches — Match Stats page has a
First team/Reserve/Both filter. **buca_433** is the user's tactic + dashboard default_method:
cloned from `personal` for all roles except ST, which uses an Advanced-Forward skew (key:
shooting/movement/pace/technique). Note: attribute rating predicts striker goals poorly here —
Seyhun overperforms his profile (Movement 6/Decisions 5 but 26 goals); select strikers on
goals/90, use rating to scout. Reserve top scorer Bartu Gökçen (9 res goals) is promotion/loan
material. Youth-only save: no transfers, aging CB (only 17yo Binici young) + no young DM.

Deps (root pyproject.toml, uv): duckdb, streamlit, plotly, pandas. Extractors stay pure-stdlib.
