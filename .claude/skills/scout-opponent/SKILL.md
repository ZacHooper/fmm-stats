---
name: scout-opponent
description: Produce a technical-analyst opposition scouting report for a single upcoming opponent in the active FM career — expected style, threats, weaknesses, key players/positions, a concrete game plan, and a recommendation of WHICH of our tactic methods to run. Combines our data (head-to-head history, squad-attribute profile, ratings) with the in-game scout's report (formation + style), which the user must supply because opponent tactics are NOT in the save. Use when the user says "scout <team>", "how do we beat <team>", or "prep for <team> this week".
---

# Scout an opponent

Acts as the technical analyst briefing the manager on this week's opponent. **Career-aware** —
reads the active career's store (`FM_CAREER` / newest `fm-<key>.duckdb`), not a hardcoded club.
Refresh via `import-fm-saves` first if stale. Combine **our data** with the **in-game scout's
report** — neither is enough alone. Immersion rule: reason with ratings + match stats + attributes,
**never surface CA/PA** (the Level %ile is the one allowed CA-derived exception). No local store
to hand? Use the [`scout-from-site`](../scout-from-site/SKILL.md) skill instead — same job, the
deployed site's JSON, works from anywhere.

## The engine already exists — call it, don't re-derive it

`db.scout_report(opp_tid, season, phase, method)` (`dashboard/db.py`) is the shared engine behind
`fmq.py scout <team>` and the Streamlit **Team scout** tab. It already does every
correctness-sensitive pull this report needs, so **this skill's job is to call it once and write
the narrative, not to hand-roll SQL that re-derives what it already gets right**:

- **H2H** via `our_match_history()` — latest phase per season already picked (the match table is a
  ring buffer; a naive scan across every snapshot double-counts).
- **Squad strength** via `squad_frame()`/`team_strength()` — position-normalised best-XI index,
  both clubs, one coherent frame so unit and attribute reads use the same players.
- **Matchups** via `matchup_table()` (new) — the pairing that actually meets on the pitch: our
  attack vs their defense, their attack vs our defense, midfield vs midfield. `strength` compares
  each unit to itself (Defense-us vs Defense-them), which is the wrong axis for a game plan — their
  defense never plays our defense. Use `rep["matchups"]` for "who wins this contest", `rep["strength"]`
  only for "how strong is each line in isolation".
- **Key players** via `squad_key_players(..., rank_by="level_league")` — ranked by **Level %ile**
  (tactic-agnostic quality), not our tactic's Fit rating. `pos_index`/`pctile_league` are OUR role
  weights applied to their attributes — a fair "how would this player suit OUR system" question,
  and the right ranking for our own squad (`squad_key_players` defaults to it there), but the wrong
  one for judging an opponent, who almost certainly doesn't run our tactic. Level %ile is
  CA-derived and immersion-safe already (it's the one sanctioned CA export) and it's what
  `scout_report` now ranks their `key_players`/danger men by.
- **Auto-read** via `_scout_flags()` — bogey-side / we-own-them H2H calls, the same face-off
  matchup edges, danger men (Level %ile), and their defensive soft spots (a fixed threshold list),
  plus a `⚠️ PARTIAL DATA` flag when the frame doesn't reach 11 rated players. **This already covers
  the old "no-data opponent" detection** — check `rep["coverage"]["partial"]` and read `rep["flags"]`
  instead of eyeballing empty DataFrames yourself.

Writing your own query for any of this reopens exactly the traps these helpers exist to close —
ring-buffer double counts, `tid` recycling across snapshots, a raw `club_tid` filter that still
matches a player whose loan lapsed without clearing, and (new) rating an opponent by how well they'd
fit a tactic they don't play. If a report needs something `scout_report` doesn't return (e.g. a
deeper individual-attribute cut), pull that one extra thing with `db.q(...)` — don't re-derive what's
already there.

**`fmq.py scout <team> [--venue H|A --formation "..." --style "..." --note "..."]`** is the CLI
form of the same call and — unless `--no-save` — writes the result into the R2-synced scout log
(`state/scouts/`, via `db.save_scout`). That log is new since this skill was last written and is
worth using: it's a season's worth of "what we thought going in," so a scout for a team you've
faced before can open by saying what the last read was and whether it still holds. Call
`db.scout_report()` directly for the briefing (you need the DataFrames, not printed text) but still
call `db.save_scout(rep, venue=..., formation=..., style=..., note=...)` yourself afterward so this
report lands in the same log the CLI would write.

## Resolve the career context first (do NOT hardcode)
Everything below is parameterised off the active career — pull these from `db`, don't assume Bucaspor:
- **Us** = `db.MANAGED_CLUB_TID` (first team) + `db.OUR_CLUBS` (adds the reserve tid). e.g. Frem =
  346 (+7296 reserves); Bucaspor = 6567 (+11320).
- **Snapshot** — `S, P = db.latest_snapshot()` (backed by `mart.snapshots.snap_ix`, already
  chronological across seasons/phases — don't hand-roll a `max(phase)` or a `phase_key` sort).
- **Our default method** = `db.config().get("default_method")` (Frem → `frem_attacking_ss`;
  Bucaspor → `buca_433`). This is the *base* for the game plan; the tactic step below may recommend
  switching to a situational variant. `scout_report(method=None)` already resolves this same
  fallback internally, so passing `None` explicitly is fine too.
- **Our identity** — read it off `rep["strength"]`/the unit means, don't recite a fixed line.
  (Frem: strong Creativity/Movement/Shooting/Pace, physically lighter → suits proactive control +
  width + pace, not an aerial/physical scrap.)

## Inputs to establish first
- **Opponent** — `matches = db.resolve_club(name_or_tid)`. Diacritic/Turkish-insensitive
  substring match, sorted by squad size descending, so a same-named **Reserves** side (smaller
  squad) already sorts below the first team — take `matches.iloc[0]` unless it's genuinely
  ambiguous (`len(matches) > 1` with comparable squad sizes), in which case list the candidates and
  ask.
- **Formation** — ASK THE USER (from the in-game scout). Opponent shape is NOT parsed.
- **Style** — ASK THE USER (balanced / possession / counter / high-press / direct …).
- **Current league position / recent form (both sides)** — ASK THE USER. `v_league_table`
  genuinely does not parse for this career (match history is a ring buffer — a season's table
  never fully reconstructs), so `rep["overall"]`'s squad-quality read is the ONLY signal this
  report has for "who's favoured", and it can be flatly wrong: it measures attribute quality,
  blind to results, table position, current form, or squad depth actually holding up over a
  season. Don't let the Verdict assert "underdogs"/"favourites" from `us_quality`/`them_quality`
  alone — say what the quality gap suggests, then explicitly ask (or use what the user already
  told you) where each side actually sits, and let table position win if the two disagree. This
  bit the first real scout run under this skill: Frem 1st, Brøndby 9th, but the quality read
  alone said "clear underdogs" — true for the attribute profile, false for the season.

## Check for a prior scout — this is calibration now, not just prediction
Before pulling fresh data: `s = db.load_scouts(); s = s[s.opponent_tid == OPP]` (or
`uv run python fmq.py scouts`). If a saved report exists for this opponent, open the briefing with
what it said (index gap, method planned, any note) and whether it still holds — squad, tactic and
even our own personnel may have moved since. If nothing's saved, say so and proceed; this scout
will be the first entry once you save it.

### Tactic recommendation — consult our playbook (THE career-specific value-add)
After profiling, **recommend which of our methods to run**, keyed to
[`docs/fmm-tactic-blueprints.md`](../../docs/fmm-tactic-blueprints.md) → **"When to use each —
cheatsheet"**. Read that table live (methods evolve); don't hardcode the mapping. The decision
inputs are already in `rep`:
- **Favourite vs underdog** (`rep["overall"]["us_quality"]` vs `["them_quality"]` — Level %ile, not
  the Fit-based `us`/`them`, since the latter judges them under a tactic they don't run) →
  proactive default (`frem_attacking_ss`) when we're better/equal; the counter variant
  (`frem_counter`) when they're stronger / carry pace to hit in behind.
- **Their style** (user's scout) → if they'll **park a deep block**, the break-them-down variant
  (`frem_lowblock_overload`); if they'll **try to play out**, pressing their weak build-up
  (`frem_gegenpress`).
- **The actual on-pitch matchups** (`rep["matchups"]` — see above) → "Our attack vs their defense"
  tells you whether to expect chances created; "Their attack vs our defense" tells you what to
  protect. If they edge that second row and it's built on Strength/Aerial (check `rep["unit_attrs"]`
  for the Defense-unit attribute detail) and they play direct to a target man, **don't** open in a
  high-press/duel game that plays to their one advantage; control instead.
- **Game state** → protecting a lead late = the close-out variant (`frem_game_state`).

Output a **"Recommended method + why + fallback switch"** call: a base method to start, and the
in-game lever to pull if the game turns (e.g. "start `frem_attacking_ss`; if they bunker like the
0-0, switch to `frem_lowblock_overload`"). Fold this into the game-plan section of the report (see
template).

### Validated pull snippet + gotchas
This whole path is `duckdb` + `pandas` — `uv sync` (no extras) is enough; you do NOT need
`uv sync --extra dashboard` (streamlit + plotly) to run a scout. `dashboard/db.py` only uses
streamlit for its Streamlit-page sidebar widgets and a cache decorator, and falls back to a plain
`functools.lru_cache` when it isn't installed, so `import db` works either way.

Query a **copy** of the db if the live one is locked — mirror what `fmq.py scout` itself does
(try a read-only connect first; only copy on failure), rather than always paying for a full copy.
Run via a **heredoc / script file**, not `python -c` (the escaping bites).

```python
import os, sys, shutil, tempfile, duckdb
os.environ["FM_CAREER"] = "frem"                                             # active career
repo = os.getcwd()
src = os.path.join(repo, "fm-frem.duckdb")                                   # or db.py's resolved path
path = src
try:
    duckdb.connect(src, read_only=True).close()
except duckdb.Error:
    path = os.path.join(tempfile.gettempdir(), "scout.duckdb")
    shutil.copy2(src, path)                                                  # live DB is locked — scout a copy
os.environ["FM_DUCKDB"] = path
os.environ["FM_DUCKDB_READONLY"] = "1"
sys.path.insert(0, "dashboard"); import db

matches = db.resolve_club("Slagelse")
OPP = int(matches.iloc[0]["tid"])
S, P = db.latest_snapshot()
M = db.config().get("default_method")

rep = db.scout_report(OPP, season=S, phase=P, method=M)
# rep = {opp, season, phase, method, coverage, overall, strength, matchups, units,
#        unit_attrs, key_players, h2h, flags} — DataFrames for strength/matchups/units/
#        unit_attrs/key_players.
#   overall/strength carry BOTH ratings: us/them (+ us_pctile/them_pctile) is our tactic's
#     Fit; us_quality/them_quality is tactic-agnostic Level %ile. Use *_quality for "how
#     good are they", *_pctile for "how would this suit OUR system".
#   matchups is the face-off pairing (see matchup_table docstring): rows "Our attack vs
#     their defense" / "Their attack vs our defense" / "Midfield (contested)", each with
#     us_quality/them_quality/edge (Level %ile) and us_fit/them_fit (pos_index) alongside.
#   key_players is ranked by Level %ile (rank_by="level_league") for the opponent — quality,
#     not Fit under our tactic.
#   rep["h2h"]["matches"] is the per-match DataFrame (date, venue, gf, ga, result,
#     our_shots/opp_shots, our_shots_on_target/opp_..., our_passes/opp_...,
#     our_passes_completed/opp_..., our_tackles_won/opp_..., our_interceptions/opp_...).

prior = db.load_scouts()
prior = prior[prior.opponent_tid == OPP] if not prior.empty else prior       # calibration check

# ... write the report from rep, ask the user for formation/style, apply the tactic step ...

rec = db.save_scout(rep, venue="H", formation="attacking 442", style="high-press",
                    note="short plan summary")                               # logs it, R2-synced
```

Gotchas that still cost time if you bypass `scout_report` and reach for raw SQL yourself:
- **Attribute columns are Capitalised** in `team_attribute_frame`/`club_attributes` — a lowercase
  `['pace', ...]` filter silently yields an empty list.
- **A raw `club_tid` filter on `staging.players` is not safe even within a single snapshot** —
  this used to say it was; it isn't. `club_attributes()` (and therefore `squad_frame`, and
  therefore every rating/key-player/matchup this skill touches) now filters on GENUINE presence
  (an `at_club`/`loan_in` spell from `mart.player_spells` covering the snapshot date), not raw
  `club_tid`. Confirmed on real data: Ernest Nuamah's loan to us ended 2023-06-30, but his row at
  the 2024-11-10 snapshot still read `club_tid=346, loaned_in=True` — a raw filter put him in a
  Brøndby scout's "our attacking outlets" 16 months after he left. If you bypass `club_attributes`
  for a raw query, reproduce this check yourself (`mart.player_spells`, `spell_type IN ('at_club',
  'loan_in')`, date between `valid_from`/`valid_to`) rather than trusting `club_tid` alone — and
  never trust `loaned_in`/`loaned_out` for loan STATUS prose either, same reason: set once, never
  cleared.
- Cross-snapshot per-player aggregates (e.g. "has this player grown since we last played them")
  must key on `person_id`, not `tid` — FM recycles retired players' slots.
- opponent `name` **resolves for every club** (the ETL id-resolver) — `squad_key_players` and
  `squad_frame` already carry it; you shouldn't need to re-join `staging.players` for it.

## No local store at all
If the machine has no `fm-<career>.duckdb` and rebuilding one isn't worth the ~1 min/snapshot for
a single scout, don't reimplement this pull against the R2-published mart either — hand off to
[`scout-from-site`](../scout-from-site/SKILL.md), which is built for exactly that (the deployed
site's JSON, or the mart via `ATTACH` if arbitrary SQL is genuinely needed — see
`site/AGENTS.md`'s cookbook). It carries its own, narrower set of caveats (no per-match H2H beyond
`matches.json`, ability *percentiles* not ranks for an opponent) — don't quietly deliver that
thinner report under this skill's name.

## Hard limitations — state them in the report
- **Opponent tactics/formation are NOT in the save** → rely on the user's in-game scout input.
- **Opponent player names ARE resolved** (the ETL runs the id-resolver — every club is named, not
  just ours) → **use real names** alongside position + percentile.
- **Opponent attributes are model estimates (±1)** for technical/mental (Pace/physical are exact;
  check the `*_est` flags in `mart.player_snapshots` if you need to know which). Treat as
  directional, not precise.
- **Squad status and loan flags are unreliable** (`staging.players.loaned_in`/`.loaned_out` — set
  once, never cleared). `scout_report`'s squad frame is snapshot-club-tid based, not flag based, so
  this mainly bites if you're tempted to assert loan status in prose — don't, from the flags alone.
- League-membership counts over-report (resolved across labels) — ignore for a single scout.
- **No-data opponents:** `rep["coverage"]["partial"]` is `True` (and `rep["flags"][0]` says so)
  when the frame has fewer than 11 rated players — a **newly-promoted side** we haven't parsed in a
  prior save, or a **lower-division Cup draw** FMM doesn't fully model. A **day-1 start save** (0
  matches) also has no H2H or league yet (`rep["h2h"]["played"] == 0`). Don't fake tables when the
  pulls come back thin — say plainly they're not in our data yet, that we're strong favourites
  (promoted/lower side), and give a **formation/style-only** briefing (interpret their shape, the
  structural threats — counter + set pieces — and how we break it down, tying to our identity + a
  tactic recommendation), keeping the same template but noting "none available / not in our data"
  in the data sections.

## Report template — KEEP THIS LAYOUT for every scout (consistency matters)
Technical-analyst tone, to the manager. Prose + small tables. Fill the skeleton below verbatim
(same headings, order, emoji, the italic caveat line, and the closing gaffer line + footer). Base
every claim on `rep`; don't invent numbers. If a prior scout exists (see "calibration" above), open
the Verdict with one line on whether it still holds.

```markdown
# 📋 Opposition briefing — <Club> (<H or A> this week)
*Their scout report: **<formation>**, **<style>**. Caveats: opponent attributes are model
estimates (±1) except pace/physicals; key players are named (names resolve for every club) and
profiled by position + league percentile.*

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
- <squad-profile + key-player + H2H bullets, drawn from `rep["flags"]`, `rep["key_players"]`
  (Level %ile — their quality, not their Fit under our tactic) and the "Their attack vs our
  defense" row of `rep["matchups"]`: danger unit, high-Level%ile men, lone standout vs drop-off,
  shot volume, direct/set-piece route.>

## Where we win
- <the "Our attack vs their defense" row of `rep["matchups"]` (do we have the quality edge going
  forward?) + attribute detail from `rep["unit_attrs"]` (their Defense unit's weak spots — already
  the right axis, since it's describing THEIR defensive line on its own terms) + space their shape
  concedes.>

## Key men to watch (named, by position)
- **<Name> (<POS>)** — <standout attribute + Level %ile / role, from `top_attrs`. Level %ile, not
  Fit — see "The engine already exists" above for why.>

## Game plan — tactic recommendation
- **Recommended method:** **`<method>`** — <why, keyed to the cheatsheet: favourite/underdog +
  their style + physical matchup>. **Fallback switch:** <the in-game lever, e.g. → `frem_lowblock_overload`
  if they bunker>.
- <shape vs theirs; who screens whom; where we attack — tie to our identity + the space their shape
  concedes. Prefer our real edges (width/pace/creativity) over their strengths (aerial/duels).>
- **Mentality:** <home = ...; away = ...>
- **Defend:** <funnel wide/deny centre; screen the direct ball; man-mark aerial threats on set pieces.>
- **Cutting edge / set pieces:** <if the H2H shows control-without-chances, stress chance quality;
  our aerial edge if any; who to track after our set pieces.>

**One-line to the gaffer:** *<punchy, quotable summary of the plan.>*

---
Eyeball it: **Team analysis → Scout a team → <Club>** — the **Face-off matchups** table for the
attack-vs-defense reads, the unit/position filters (e.g. Us→Attack vs Them→Defense) to probe any
matchup by hand, and the head-to-head drilldown. Switch the **method** selector to `<recommended>`
to preview our XI's Fit for this plan. This report has been saved to the scout log
(`uv run python fmq.py scouts` to review it alongside past reads on other opponents).
```

Keep it decision-useful and honest about the estimate limitations (attributes ±1; tactics not in
the save). One opponent at a time (opponent tactics vary, so a whole-season sweep would need each
team's in-game scout report as input — see [`season-outlook`](../season-outlook/SKILL.md) for the
group-level version of this, which hands off to this skill per-fixture). Offer at the end to scout
the next opponent.
