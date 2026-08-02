---
name: scout-opponent
description: Produce a technical-analyst opposition scouting report for a single upcoming opponent in the FM Bucaspor save — expected style, threats, weaknesses, key players/positions, and a concrete game plan to beat them. Combines our data (head-to-head history, squad-attribute profile, ratings) with the in-game scout's report (formation + style), which the user must supply because opponent tactics are NOT in the save. Use when the user says "scout <team>", "how do we beat <team>", or "prep for <team> this week".
---

# Scout an opponent

Acts as the technical analyst briefing the manager on this week's opponent. Reads `fm.duckdb`
(refresh via `import-fm-saves` first if stale). Combine **our data** with the **in-game scout's
report** — neither is enough alone. Immersion rule: reason with ratings + match stats + attributes,
**never surface CA/PA**.

## Inputs to establish first
- **Opponent** — club name → tid. Resolve via `staging.clubs` (e.g. Karacabey Belediye = 6353).
- **Formation** — ASK THE USER (from the in-game scout). Opponent shape is NOT parsed. e.g.
  Karacabey = 4-1-2-2-1 (GK / back 4 / one holding DM / two central mids / two wide forwards /
  lone striker).
- **Style** — ASK THE USER (balanced / possession / counter / high-press / direct …).
- **Our tactic (method)** — `buca_433` (default). Our identity from Team analysis: strong
  Dribbling + Pace, weaker Passing → we suit **direct / transition**, not slow possession.
- **Snapshot** — latest `(season,'start')` for squad/ratings; `our_match_history()` for all H2H.

## Data to pull (dashboard/db.py helpers; read-only — kill Streamlit or query a `cp` of the db)
Set `sys.path.insert(0,'dashboard'); import db`. `S,P,M = <year>,'start','buca_433'`.

1. **Head-to-head** — `h = db.our_match_history(); h = h[h.opp_tid==OPP]`. Report P / W-D-L / GF-GA /
   PPG and the per-match splits: `our_shots` vs `opp_shots`, pass% (`*_passes_completed/*_passes`),
   `*_tackles_won`. Look for a pattern (do they out-shoot / out-possess us? are we clinical?).
2. **Squad profile by unit** — `db.team_attribute_frame(S,P,M,[OPP])` and same for
   `db.MANAGED_CLUB_TID`; compare per-unit (Defense/Midfield/Attack) means of Pace, Stamina,
   Strength, Aerial, Tackling, Passing, Technique, Dribbling, Shooting, Creativity, Decisions,
   Movement. Find where they beat us and where we beat them.
3. **Overall level** — mean `eff` (primary position) both clubs → who's the stronger squad.
4. **Key players / threats** — `eff = db.effective_table(S,P,M); e = eff[eff.club_tid==OPP]`;
   take primary-position row per tid (max familiarity), sort by `eff`, note `pctile_league`.
   High-percentile positions = their danger areas.
5. **Standout individuals** — `db.club_attributes(S,P,[OPP])` → `idxmax` per attribute (Pace,
   Aerial, Shooting, Creativity, Dribbling, Tackling, Strength, Passing) with the player's
   position. Flags e.g. "a DR with Pace 14" (attacking full-back), "a DL with Aerial 15"
   (set-piece threat).

### Validated pull snippet + gotchas
Query a **copy** of the db (the live Streamlit holds a write lock): `cp fm.duckdb /tmp/scout.duckdb`
then `FM_DUCKDB=/tmp/scout.duckdb`. Run via a **heredoc / script file**, not `python -c` (the
escaping bites). Gotchas that cost time last run:
- `db.club_attributes(season, phase, club_tids)` takes **3 args, no method**.
- In `db.q`, **quote `phase`** inside f-strings: `f"... phase='{P}' ..."`.
- opponent `name` is NULL → don't try to label players; map `tid → primary position` via
  `staging.player_positions` (`arg_max(position, familiarity)`) and describe by position.
```python
import sys; sys.path.insert(0, 'dashboard'); import db, pandas as pd
OPP, S, P, M = 6353, 2024, 'start', 'buca_433'
h = db.our_match_history(); h = h[h.opp_tid == OPP].sort_values('date')      # head-to-head
taf = db.team_attribute_frame(S, P, M, [OPP, db.MANAGED_CLUB_TID])            # unit profile + eff
ca = db.club_attributes(S, P, [OPP])                                         # standouts: ca[attr].idxmax()
eff = db.effective_table(S, P, M); e = eff[eff.club_tid == OPP]              # key players + pctile_league
pos = db.q(f"SELECT tid, arg_max(position,familiarity) AS pos FROM staging.player_positions "
           f"WHERE season={S} AND phase='{P}' GROUP BY tid")                 # tid -> position (for standouts)
```

## Hard limitations — state them in the report
- **Opponent tactics/formation are NOT in the save** → rely on the user's in-game scout input.
- **Opponent player names are unavailable** (only our own squad is named) → describe key players
  by **position + standout attribute + league percentile**, not by name.
- **Opponent attributes are model estimates (±1)** for technical/mental (Pace/physical are exact;
  check the `*_est` flags). Treat as directional, not precise.
- League-membership counts over-report (resolved across labels) — ignore for a single scout.
- **No-data opponents:** some clubs resolve a name but have NO loaded squad / league / results
  (squad size ~0-1, no attributes, no H2H, no resolved league — Bergama Belediyespor 1677 is one).
  Two common causes: a **newly-promoted league side** we haven't parsed in a prior save yet, or a
  **lower-division Cup draw** FMM doesn't fully model — decide from context / ask the user which.
  When the pulls come back empty, DON'T fake tables. Say plainly they're not in our data yet, that
  we're strong favourites (promoted/lower side), and give a **formation/style-only** briefing
  (interpret their shape, the structural threats — counter + set pieces — and how we break it down,
  tying to our identity), keeping the same template but noting "none available / not in our data"
  in the data sections. Flag that the Team-analysis Scout tab won't list them either. (This blind
  spot is realistic — you scout a promoted side cold, same as a real manager.)

## Report template — KEEP THIS LAYOUT for every scout (consistency matters)
Technical-analyst tone, to the manager. Prose + small tables. Fill the skeleton below verbatim
(same headings, order, emoji, the italic caveat line, and the closing gaffer line + footer). Base
every claim on the pulled data; don't invent numbers.

```markdown
# 📋 Opposition briefing — <Club> (<H or A> this week)
*Their scout report: **<formation>**, **<style>**. Caveats: opponent attributes are model
estimates (±1) except pace/physicals; opponent names aren't in our data, so key players are
profiled by position + league percentile.*

## Verdict
<one line: favourites/underdogs + our H2H record + the single biggest threat + our single biggest edge.>

## Head-to-head (<competitions>)
| Date | V | Score | Res | Shots (us–them) | Pass% (us–them) |
|---|---|---|---|---|---|
| <yyyy-mm-dd> | H/A | x–y | W/D/L | a–b | c–d |
<one/two-line pattern read: do they out-shoot / out-possess us? are we clinical? home vs away?>

## Expected shape & where their space is
<interpret their formation + style positionally; name the exploitable space, e.g. behind
attacking full-backs, either side of a lone pivot.>

## Their threats
- <squad-profile + key-player + H2H bullets: danger unit, high-percentile men, shot volume, set pieces.>

## Where we win
- <units/attributes we beat them on + space their shape concedes.>

## Key men to watch (by position — no names in our data)
- **<POS>** — <standout attribute + league percentile / role>

## Game plan (our 4-3-3-DM / buca_433)
- <shape vs theirs; who screens whom; where we attack — tie to our identity: direct/transition,
  use Pace + Dribbling, don't get drawn into a slow possession game we lose.>
- **Mentality:** <home = ...; away = ...>
- **Defend:** <funnel wide/deny centre; man-mark aerial threats on set pieces; etc.>
- **Attack set pieces:** <our aerial edge if any; who to track afterwards.>

**One-line to the gaffer:** *<punchy, quotable summary of the plan.>*

---
Eyeball it: **Team analysis → Scout a team → <Club>** (unit/position filters, e.g. Us→Attack vs
Them→Defense) and the head-to-head drilldown.
```

Keep it decision-useful and honest about the estimate/name limitations. One opponent at a time
(opponent tactics vary, so a whole-season sweep would need each team's in-game scout report as
input). Offer at the end to scout the next opponent.
