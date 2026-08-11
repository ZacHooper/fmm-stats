---
name: season-outlook
description: Produce a wider-than-one-game preparation briefing across a SET of opponents — a promotion stage, a run-in, or a full remaining fixture list — for the active FM career. Ranks the group by difficulty (squad-quality gap + H2H), maps the recurring threat pattern, recommends a tactic/press plan per game-type, and gives standings-aware rotation & fitness guidance (minutes load + condition). Distinct from scout-opponent (which is one team + one match + the in-game formation); this needs NO per-team formation and hands off to scout-opponent for the games worth a full single-match scout. Use when the user says "season outlook", "how do we stack up against <group>", "prep for the run-in / promo stage", or asks for a minutes/fatigue/rotation view.
---

# Season / run-in outlook

The technical analyst zooming out from one match to the **whole run of games**. Answers: *how do we
stack up against this group, which fixtures actually bite, how should the tactic/press flex across
them, and — given where we sit in the table — who do we rest and who do we blood?* **Career-aware**
(reads the active career's store, not a hardcoded club). Immersion rule: reason with ratings,
percentiles, minutes, condition and attributes — **never surface CA/PA** (the Level %ile is the one
allowed CA-derived exception).

## What this is NOT
- Not a single-match game plan — it needs **no per-team formation** (that's `scout-opponent`, one
  team at a time, requiring the user's in-game scout). This is a squad-quality + risk + workload map.
- It **hands off** to `scout-opponent` for the one or two fixtures it flags as "circle this".

## Resolve context first (do NOT hardcode)
- **Us** = `db.MANAGED_CLUB_TID` (+ `db.OUR_CLUBS` for reserves). Method `M = db.config().get("default_method")`.
- **Snapshot** — latest phase, date-aware: `phs = db.q("SELECT DISTINCT phase FROM staging.players
  WHERE season=?", [S]).phase.tolist(); P = max(phs, key=db.phase_key)`. **Never a bare SQL
  `max(phase)`** — legacy word-phases (`start`) sort as epoch and would win over a real date.
- **The opponent set comes from the USER** (the stage/run-in list). Don't try to auto-derive it from
  `staging.standings` — a Danish promo/relegation split isn't modelled, and the stored table often
  **lags the live game** (see standings note). Resolve each name → **first-team** tid via
  `staging.clubs` (skip the `… Reserves` row).
- **Live table position** — ASK / take from the user (points, position, games left). Our stored
  `staging.standings` is a real table (`pos/played/won/drawn/lost/points`) but reflects the latest
  *imported* save, which can be behind where the user actually is. Use it as directional; **trust the
  user's stated live points when they differ.**

## Step 1 — Group comparison (the core engine)
For each opponent, pull vs us: **mean eff gap**, **H2H**, **top-3 threats (pos, eff, league %ile)**,
and **unit edges** (where they beat us / we beat them). Rank by mean eff (difficulty). Validated:
```python
import os, sys
os.environ["FM_CAREER"] = "frem"
os.environ["FM_DUCKDB"] = os.path.expandvars("$CLAUDE_JOB_DIR/tmp/outlook.duckdb")   # cp of the store
os.environ["FM_DUCKDB_READONLY"] = "1"
sys.path.insert(0, "dashboard"); import db, pandas as pd
S = 2022
phs = db.q("SELECT DISTINCT phase FROM staging.players WHERE season=?", [S]).phase.tolist()
P = max(phs, key=db.phase_key); M = db.config().get("default_method"); US = db.MANAGED_CLUB_TID
GROUP = {"Naesby":369, "VSK Aarhus":5320, "Herlev":1141, "Vanlose":1161, "FC Roskilde":2532}  # user's set
ATTR = ["Pace","Stamina","Strength","Aerial","Tackling","Passing","Technique","Dribbling","Shooting","Creativity","Decisions","Movement"]

eff = db.effective_table(S, P, M)
def prim(tid):                                            # primary-position row per player
    e = eff[eff.club_tid == tid]; return e.loc[e.groupby("tid")["familiarity"].idxmax()]
us_eff = prim(US)["eff"].mean()
taf = db.team_attribute_frame(S, P, M, [US] + list(GROUP.values()))   # attrs are Capitalised
us_out = taf[(taf.club_tid == US) & (taf.unit != "GK")][ATTR].mean()
h = db.our_match_history()
for name, tid in GROUP.items():
    pe = prim(tid); hh = h[h.opp_tid == tid]
    edge = us_out - taf[(taf.club_tid == tid) & (taf.unit != "GK")][ATTR].mean()   # +ve = we're better
    top = pe.sort_values("eff", ascending=False).head(3)
    # name, pe.eff.mean(), us_eff-pe.eff.mean(), W/D/L from hh.result, edge.nsmallest(2)=their strengths,
    # edge.nlargest(2)=our edges, top -> "POS(eff,pctile_league%)"
```
Read out per opponent: eff gap, H2H (P · W-D-L, GF-GA — **a prior loss flags the danger side even if
they're not 2nd on points**), their 1-2 strengths vs us, our 1-2 edges, and their top-3 men by eff +
`pctile_league`. Watch for a **lone elite** (one 95-100 %ile attacker) vs a flat squad — that one man
is the threat.

## Step 2 — Cross-group pattern read → run-in tactic plan
Don't just list five matchups — find what **repeats**, because it dictates the whole run:
- **What kind of threat recurs?** (e.g. "danger is almost always central MCs; only two sides carry
  elite wide pace"). Central-only threats → win midfield and most have no plan B.
- **Our universal edges** (e.g. "we beat all five on Stamina") — these justify the base approach
  (fittest side → a high press is low-risk here).
- **Where the base plan must flex** — the sides with **pace in behind** (high `Pace` / a 95-100 %ile
  winger/striker) are the ONLY ones that punish an attacking high line. Those are the "drop the line /
  go the deeper-line variant" games. Key it to `docs/fmm-tactic-blueprints.md` "when to use each":
  default proactive method for the field; the counter/deeper-line variant for the pace threats; the
  break-them-down variant for anyone who'll bunker (likely, if we're clear favourites forcing them to
  chase late).
Output a **base method + the 1-2 named games to flex**, not a wall of per-game plans.

## Step 3 — Squad load & fitness → rotation guidance
Only meaningful with a **table cushion** (rotation licence) — tie the advice to the user's live
position. `match_player_stats` carries per-match `condition` + `subOn`/`subOff`/`pos_order`. Encoding:
**`pos_order` 1-11 = starters, 12+ = bench; `subOn`/`subOff` = 255 sentinel for "n/a".** `condition`
is the value recorded AT the match (unused subs read 100; players who empty the tank read low) — a
**post-match fatigue proxy**, not a live "right now" %; read it as *who gets run into the ground*.
Validated minutes model (90-min matches; ignores stoppage/ET):
```python
S, P = "2022", "2022-03-19"      # season as str for the f-string; P from phase_key resolver above
TEAM_GAMES = db.q(f"SELECT COUNT(DISTINCT anchor) n FROM staging.match_player_stats "
                  f"WHERE season={S} AND team_tid={db.MANAGED_CLUB_TID}").n[0]
load = db.q(f"""
WITH mp AS (
  SELECT tid, date, rating, condition, pos_order,
    CASE WHEN pos_order<=11 THEN (CASE WHEN subOff=255 THEN 90 ELSE subOff END)
         WHEN subOn<255 THEN 90-subOn ELSE 0 END AS mins
  FROM staging.match_player_stats WHERE season={S} AND team_tid={db.MANAGED_CLUB_TID})
SELECT tid, SUM(CASE WHEN mins>0 THEN 1 ELSE 0 END) apps,
  SUM(CASE WHEN pos_order<=11 THEN 1 ELSE 0 END) starts, SUM(mins) mins,
  ROUND(AVG(CASE WHEN mins>0 THEN rating END),2) avg_rating,
  ROUND(AVG(CASE WHEN mins>0 THEN condition END),0) avg_cond,
  arg_max(condition, date) latest_cond
FROM mp GROUP BY tid""")
# join staging.players (name, dob, is_staff — FILTER is_staff out) + staging.player_attributes
# (WIDE table: SELECT tid, Stamina, Pace — NOT a long attribute/value shape). age = S_year - dob.year.
# min_pct = mins / (TEAM_GAMES*90) * 100.
```
Bucket into three calls:
- **🔴 Heavy load — rotate to rest:** highest minutes, esp. **older** players (age ≥ ~30) and your
  **best performers by rating** (protect the talisman for the games that matter + next season).
- **🟠 Fatigue flags:** low `avg_cond`/`latest_cond` — the tank-emptiers (often low-`Stamina` or
  high-work wide men); manage as impact subs, don't run them 90 every 3 days.
- **🟢 Fresh & underused:** low minutes, esp. **young** players — the cushion is licence to blood
  them for the division above. Flag anyone with 0 apps.
Caveats to state: `condition` is a post-match proxy (recovers between games); `min_pct` uses
`TEAM_GAMES×90`, so genuine mid-season arrivals read artificially low; 90-min model ignores ET.

## Report template — KEEP THIS LAYOUT
Technical-analyst tone, to the manager. Prose + small tables. Base every claim on the pulls.

```markdown
# 🏆 <Stage/run-in> outlook — <Us> (<N> matches, <k> opponents)
*Squad-quality + risk + workload map across the run. No per-team formations (that's the single-opponent
scout). <Live standing: leaders on X, 2nd on Y — an N-point cushion with M to play.>*

## Verdict
<favourite/underdog for the group + the single game that can actually bite + what the prep is really for.>

## The group (eff gap +ve = we're stronger)
| Team | Mean eff | Gap vs us | H2H (P·W-D-L) | GF-GA | Read |
|---|---|---|---|---|---|
| ... sorted; mark the ⚠️ danger side (a prior loss / a 95-100%ile attacker) ... |

## ⚠️ The one(s) to circle — <Team>
<why: the only side to beat us / their elite man at N-th %ile / they out-<attr> us; recommend a full
single-opponent scout when it comes up, and the likely tactic flex.>

## The pattern across the group
<the 2-3 things that repeat: recurring threat type, our universal edge(s), the exposure that flexes the plan.>

## Plan for the run-in
- **Default:** `<method>` + <press/approach> for <the field / named routine games>.
- **Flex:** <drop the line / `<counter variant>` for the pace-threat game(s); `<lowblock variant>` vs anyone who bunkers.>
- **Bank the cushion:** rotate — <who to rest, who to blood> (see fitness below).

## Squad load & fitness (<G> games played)
🔴 Heavy load — rotate: <players + mins% + why>
🟠 Fatigue flags: <players + condition + why>
🟢 Fresh & underused — blood: <players + why>
<rotation call: the specific rest/blood moves across the run, tied to the cushion.>
*Caveats: condition = post-match fatigue proxy; min% denom = G×90 (mid-season arrivals read low).*

**One-line to the gaffer:** *<punchy summary: it's won bar X — press the field, cup-tie the danger side, spend the cushion on legs + kids.>*

---
Eyeball it: **Team analysis** (unit filters per opponent) + the **Development / minutes** views. Run
`scout-opponent <danger side>` for the full single-match plan when that fixture lands.
```

## Gotchas (shared with scout-opponent)
- **Attribute columns are Capitalised** (`Pace`, `Stamina`…) in `team_attribute_frame`; and
  `staging.player_attributes` is a **WIDE** table (`SELECT tid, Stamina, Pace`), NOT long. A lowercase
  or `attribute='Stamina'` query yields empty / errors.
- **`phase` is a date** — resolve latest with `db.phase_key`, never a bare `max`.
- **Reserves rows** share a club's name — take the first team tid.
- **Standings can lag the live game** — take live points/position from the user.
- Query a **copy** of the store (`cp fm-<key>.duckdb $CLAUDE_JOB_DIR/tmp/outlook.duckdb`, set
  `FM_DUCKDB` + `FM_DUCKDB_READONLY=1` + `FM_CAREER`); run via a script file, not `python -c`.
- Opponent names/attributes limitations from `scout-opponent` apply (names NULL → profile by
  position + %ile; opponent attrs are ±1 estimates except pace/physicals).

Offer at the end to run a full `scout-opponent` on the circled fixture(s), or a deeper rotation plan.
