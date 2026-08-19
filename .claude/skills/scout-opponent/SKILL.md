---
name: scout-opponent
description: Produce a technical-analyst opposition scouting report for a single upcoming opponent in the active FM career — expected style, threats, weaknesses, key players/positions, a concrete game plan, and a recommendation of WHICH of our tactic methods to run. Combines our data (head-to-head history, squad-attribute profile, ratings) with the in-game scout's report (formation + style), which the user must supply because opponent tactics are NOT in the save. Use when the user says "scout <team>", "how do we beat <team>", or "prep for <team> this week".
---

# Scout an opponent

Acts as the technical analyst briefing the manager on this week's opponent. **Career-aware** —
reads the active career's store (`FM_CAREER` / newest `fm-<key>.duckdb`), not a hardcoded club.
Refresh via `import-fm-saves` first if stale. Combine **our data** with the **in-game scout's
report** — neither is enough alone. Immersion rule: reason with ratings + match stats + attributes,
**never surface CA/PA** (the Level %ile is the one allowed CA-derived exception).

## Resolve the career context first (do NOT hardcode)
Everything below is parameterised off the active career — pull these from `db`, don't assume Bucaspor:
- **Us** = `db.MANAGED_CLUB_TID` (first team) + `db.OUR_CLUBS` (adds the reserve tid). e.g. Frem =
  346 (+7296 reserves); Bucaspor = 6567 (+11320).
- **Snapshot** — use the **latest phase** (phase is now the save's in-game DATE, not `start/mid/end`).
  Resolve it with the phase-sort key, NOT a plain `max` — legacy word-phases (`start`) sort as epoch,
  and a bare SQL `max(phase)` picks `'start'` over a real date (`'s' > '2'` lexically). Use:
  `phs = db.q("SELECT DISTINCT phase FROM staging.players WHERE season=?", [S]).phase.tolist();
  P = max(phs, key=db.phase_key)`. Don't hardcode `'start'`.
- **Our default method** = `db.config().get("default_method")` (Frem → `frem_attacking_ss`;
  Bucaspor → `buca_433`). This is the *base* for the game plan; the tactic step (6) may recommend
  switching to a situational variant.
- **Our identity** — read it off the unit means you pull (step 2), don't recite a fixed line. (Frem:
  strong Creativity/Movement/Shooting/Pace, physically lighter → suits proactive control + width +
  pace, not an aerial/physical scrap.)

## Inputs to establish first
- **Opponent** — club name → tid. Resolve via `staging.clubs` (watch for a same-named **Reserves**
  row — take the first team, e.g. Slagelse = 376, not 7326).
- **Formation** — ASK THE USER (from the in-game scout). Opponent shape is NOT parsed.
- **Style** — ASK THE USER (balanced / possession / counter / high-press / direct …).

## Data to pull (dashboard/db.py helpers; read-only — kill Streamlit or query a `cp` of the db)
Set `sys.path.insert(0,'dashboard'); import db`. `S = <season end-year>`, `P = <latest phase>`,
`M = <our default method>` (all resolved above, not literals).

1. **Head-to-head** — `h = db.our_match_history(); h = h[h.opp_tid==OPP]`. Report P / W-D-L / GF-GA /
   PPG and the per-match splits: `our_shots`/`opp_shots`, **`*_shots_on_target`** (a 7-shot game
   with 0 on target is a *finishing/penetration* story, not a control one — say so), pass%
   (`*_passes_completed/*_passes`), `*_tackles_won`. Look for the pattern that dictates the plan.
2. **Squad profile by unit** — `db.team_attribute_frame(S,P,M,[OPP, db.MANAGED_CLUB_TID])` returns
   BOTH clubs in one frame (column `unit` ∈ GK/Defense/Midfield/Attack). Compare per-unit and
   team-wide outfield means; the biggest ± deltas are the story. **Attribute columns are
   Capitalised** (`Pace`, `Aerial`, `Strength`, `Passing`, `Creativity`, `Shooting`, `Movement`…).
3. **Overall level** — mean `eff` (primary-position row per tid = max `familiarity`) both clubs →
   who's the stronger squad, and by how much.
4. **Key players / threats** — `eff = db.effective_table(S,P,M); e = eff[eff.club_tid==OPP]`; take
   primary-position row per tid, sort by `eff`, note `pctile_league` (tactic Fit) and `level_league`
   (quality %ile — immersion-safe). High-percentile positions = their danger areas; watch for a
   lone standout vs a big drop-off to the next man. **Names are now resolved for EVERY club** (the
   ETL runs the id-resolver — verified 100% named), so pull `name` and use real names: build
   `nm = dict(db.q(f"SELECT tid,name FROM staging.players WHERE season={S} AND phase='{P}' AND club_tid={OPP}").values)`
   and `e['player'] = e.tid.map(nm)`.
5. **Standout individuals** — simplest from the **`team_attribute_frame`** you already pulled (it
   carries every attribute + `position` + `eff`): for each attribute, `sl.loc[sl[A].idxmax()]`
   over the opponent rows. (`db.club_attributes(S,P,[OPP])` also works — 3 args, no method, same
   Capitalised columns.) Flags e.g. "Wagué, a CB with Aerial 16 / Strength 15" (set-piece + duel
   threat), "their ST at 88 %ile" (their one real danger) — name the player now that names resolve.

### 6. Tactic recommendation — consult our playbook (THE career-specific value-add)
After profiling, **recommend which of our methods to run**, keyed to
[`docs/fmm-tactic-blueprints.md`](../../docs/fmm-tactic-blueprints.md) → **"When to use each —
cheatsheet"**. Read that table live (methods evolve); don't hardcode the mapping. The decision
inputs are already in your pulls:
- **Favourite vs underdog** (step 3 mean-eff gap) → proactive default (`frem_attacking_ss`) when
  we're better/equal; the counter variant (`frem_counter`) when they're stronger / carry pace to
  hit in behind.
- **Their style** (user's scout) → if they'll **park a deep block**, the break-them-down variant
  (`frem_lowblock_overload`); if they'll **try to play out**, pressing their weak build-up
  (`frem_gegenpress`).
- **Physical matchup** (step 2) → if they edge us on Strength/Aerial and play direct to a target
  man, **don't** open in a high-press/duel game that plays to their one advantage; control instead.
- **Game state** → protecting a lead late = the close-out variant (`frem_game_state`).

Output a **"Recommended method + why + fallback switch"** call: a base method to start, and the
in-game lever to pull if the game turns (e.g. "start `frem_attacking_ss`; if they bunker like the
0-0, switch to `frem_lowblock_overload`"). Optionally re-run `effective_table` under the
recommended method to sanity-check our XI's Fit under it. Fold this into the game-plan section of
the report (see template).

### Validated pull snippet + gotchas
Query a **copy** of the db (a live Streamlit holds a write lock): `cp fm-<key>.duckdb
$CLAUDE_JOB_DIR/tmp/scout.duckdb`, then set `FM_DUCKDB` to it (+ `FM_DUCKDB_READONLY=1`,
`FM_CAREER=<key>`). Run via a **heredoc / script file**, not `python -c` (the escaping bites).
Gotchas that cost time:
- **Attribute columns are Capitalised** in `team_attribute_frame`/`club_attributes` — a lowercase
  `['pace', ...]` filter silently yields an empty list. Use `Pace`, `Aerial`, `Strength`, …
- **`phase` is a date now** — resolve the latest with `max(phase)`, never assume `'start'`.
- `db.club_attributes(season, phase, club_tids)` takes **3 args, no method**.
- In `db.q`, **quote `phase`** inside f-strings: `f"... phase='{P}' ..."`.
- opponent `name` **resolves now** (ETL id-resolver) → join `staging.players` for `name` and use it.
  Still map `tid → primary position` via `staging.player_positions` (`arg_max(position, familiarity)`)
  to label each player's role. (Edge case: a handful of match participants not in any squad snapshot —
  ~28 tids in `match_player_stats` — stay unnamed; that's a join miss, not a resolver gap.)
- Matches **do** parse for the Frem winter save (H2H present); a *day-1* start save has 0 matches
  (no H2H / league yet) — fall back to the formation/style-only briefing (see "No-data opponents").
```python
import os, sys
os.environ["FM_CAREER"] = "frem"                                             # active career
os.environ["FM_DUCKDB"] = os.path.expandvars("$CLAUDE_JOB_DIR/tmp/scout.duckdb")
os.environ["FM_DUCKDB_READONLY"] = "1"
sys.path.insert(0, "dashboard"); import db, pandas as pd
OPP = 376                                                                    # opponent first-team tid
S   = 2022
phs = db.q("SELECT DISTINCT phase FROM staging.players WHERE season=?", [S]).phase.tolist()
P   = max(phs, key=db.phase_key)                                             # latest snapshot (date-aware; NOT bare max)
M   = db.config().get("default_method")                                      # our base tactic
h   = db.our_match_history(); h = h[h.opp_tid == OPP].sort_values("date")     # head-to-head
taf = db.team_attribute_frame(S, P, M, [OPP, db.MANAGED_CLUB_TID])           # BOTH clubs, unit + attrs
eff = db.effective_table(S, P, M); e = eff[eff.club_tid == OPP]              # key players + pctiles
sl  = taf[taf.club_tid == OPP]                                              # standouts: sl.loc[sl['Pace'].idxmax()]
pos = db.q(f"SELECT tid, arg_max(position,familiarity) AS pos FROM staging.player_positions "
           f"WHERE season={S} AND phase='{P}' GROUP BY tid")                # tid -> position
nm  = dict(db.q(f"SELECT tid,name FROM staging.players WHERE season={S} AND phase='{P}' "
                f"AND club_tid={OPP}").values)                             # tid -> name (resolves for ALL clubs now)
# e['player'] = e.tid.map(nm); sl['player'] = sl.tid.map(nm)  — use real names in the report
```

## Hard limitations — state them in the report
- **Opponent tactics/formation are NOT in the save** → rely on the user's in-game scout input.
- **Opponent player names ARE resolved** (the ETL runs the id-resolver — every club is named, not
  just ours) → **use real names** alongside position + percentile. (A few match participants absent
  from any squad snapshot stay unnamed — a minor join miss.)
- **Opponent attributes are model estimates (±1)** for technical/mental (Pace/physical are exact;
  check the `*_est` flags). Treat as directional, not precise.
- League-membership counts over-report (resolved across labels) — ignore for a single scout.
- **No-data opponents:** some clubs resolve a name but have NO loaded squad / league / results
  (squad size ~0-1, no attributes, no H2H, no resolved league). Two common causes: a **newly-promoted
  side** we haven't parsed in a prior save yet, or a **lower-division Cup draw** FMM doesn't fully
  model — decide from context / ask the user. A **day-1 start save** (0 matches) also has no H2H or
  league yet. When the pulls come back empty, DON'T fake tables. Say plainly they're not in our data
  yet, that we're strong favourites (promoted/lower side), and give a **formation/style-only**
  briefing (interpret their shape, the structural threats — counter + set pieces — and how we break
  it down, tying to our identity + a tactic recommendation), keeping the same template but noting
  "none available / not in our data" in the data sections.

## Report template — KEEP THIS LAYOUT for every scout (consistency matters)
Technical-analyst tone, to the manager. Prose + small tables. Fill the skeleton below verbatim
(same headings, order, emoji, the italic caveat line, and the closing gaffer line + footer). Base
every claim on the pulled data; don't invent numbers.

```markdown
# 📋 Opposition briefing — <Club> (<H or A> this week)
*Their scout report: **<formation>**, **<style>**. Caveats: opponent attributes are model
estimates (±1) except pace/physicals; key players are named (names resolve for every club) and
profiled by position + league percentile.*

## Verdict
<one line: favourites/underdogs + our H2H record + the single biggest threat + our single biggest edge.>

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
- <squad-profile + key-player + H2H bullets: danger unit, high-percentile men, lone standout vs
  drop-off, shot volume, direct/set-piece route.>

## Where we win
- <units/attributes we beat them on + space their shape concedes.>

## Key men to watch (named, by position)
- **<Name> (<POS>)** — <standout attribute + league percentile / role>

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
Eyeball it: **Team analysis → Scout a team → <Club>** (unit/position filters, e.g. Us→Attack vs
Them→Defense) and the head-to-head drilldown. Switch the **method** selector to `<recommended>` to
preview our XI's Fit for this plan.
```

Keep it decision-useful and honest about the estimate limitations (attributes ±1; tactics not in
the save). One opponent at a time
(opponent tactics vary, so a whole-season sweep would need each team's in-game scout report as
input). Offer at the end to scout the next opponent.
