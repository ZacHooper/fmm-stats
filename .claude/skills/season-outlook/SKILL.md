---
name: season-outlook
description: Produce a wider-than-one-game preparation briefing across a SET of opponents — a promotion stage, a run-in, or a full remaining fixture list — for the active FM career. Ranks the group by difficulty (squad-quality gap + H2H), maps the recurring threat pattern, recommends a tactic/press plan per game-type, and gives standings-aware rotation guidance (which fixtures are safe to rest/blood players in, plus a minutes-load view when games have been played). Distinct from scout-opponent (which is one team + one match + the in-game formation); this needs NO per-team formation and hands off to scout-opponent for the games worth a full single-match scout. Use when the user says "season outlook", "how do we stack up against <group>", "prep for the run-in / promo stage", or asks for a minutes/fatigue/rotation view.
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

## Step 3 — Rotation guidance
Only meaningful with a **table cushion** (rotation licence) — tie the advice to the user's live
position. This has TWO parts; **lead with the fixture-level one** (it's the reliable signal and it
works on any save):

**3a — Which FIXTURES are safe to rotate into (PRIMARY — always available).** Straight from the
Step 1 difficulty ranking: the **comfortable games** (big eff gap, strong H2H, no elite threat) are
where you rest key men / start youngsters; the **danger side(s)** get full strength. This needs NO
minutes data, so it's the whole rotation answer on a **season-start save**. This is usually the more
useful output — surface it even when the player-load view below is empty.

**3b — Player minutes load (SECONDARY — only if games have been played).** A season-start save has
**zero minutes**, so skip this entirely then (say "no minutes logged yet — early-season save"). When
minutes exist, `match_player_stats` gives per-match `subOn`/`subOff`/`pos_order` (encoding:
**`pos_order` 1-11 = starters, 12+ = bench; `subOn`/`subOff` = 255 sentinel for "n/a"**). Rank by
**minutes + age + Stamina** — the durable signals for who can/can't handle a congested run.

> **Do NOT use `condition` as a fatigue signal.** It's the end-of-last-match reading and **recovers
> to ~100 by the next kickoff** — it tracks how gassed a player got in *one* game, not durable
> tiredness, so it's noise for rotation. (Kept in schema notes only as "what the column is.")

Minutes come from **`mart.match_player_facts`**, which already has `minutes`, `started` and
`appeared` computed and — critically — is deduped to one phase per season.

> **Never aggregate `staging.match_player_stats` directly here.** It is a ring buffer re-scraped
> on every import, so a season with 3 snapshots holds each match up to 3 times. The old version of
> this skill summed it with no phase filter and inflated every minutes total accordingly, which is
> exactly the signal this section rests on. `mart` applies the dedup once.

Guard for the 0-games case first:
```python
S = 2024                                     # season (end-year)
TEAM_GAMES = db.q(f"""SELECT COUNT(DISTINCT anchor) n FROM mart.match_player_facts
                      WHERE season={S} AND team_tid IN (SELECT club_tid FROM mart.managed_club)""").n[0]
if TEAM_GAMES == 0:
    ...  # early-season save: skip 3b, give the fixture-rotation flags (3a) only
else:
    load = db.q(f"""
    SELECT f.person_id, any_value(f.tid) AS tid,
           COUNT(*) FILTER (WHERE f.appeared) AS apps,
           COUNT(*) FILTER (WHERE f.started)  AS starts,
           SUM(f.minutes) AS mins,
           ROUND(AVG(f.rating) FILTER (WHERE f.appeared), 2) AS avg_rating
    FROM mart.match_player_facts f
    WHERE f.season={S} AND f.team_tid IN (SELECT club_tid FROM mart.managed_club)
    GROUP BY f.person_id""")
    # Names/age: join mart.player_growth_season on (person_id, season) — it carries name, age and
    # minutes already. Stamina: staging.player_attributes is WIDE (SELECT tid, Stamina).
    # min_pct = mins / (TEAM_GAMES*90) * 100.  (condition deliberately NOT pulled — see note above.)
```

**Use `mart.managed_club`, not `mart.our_clubs`, for anything match-related** — `our_clubs` also
holds the reserve side, whose fixtures would otherwise be counted as the first team's.
Two player buckets (only when 3b ran):
- **🔴 Heavy load — rotate to rest:** highest minutes, esp. **older** players (age ≥ ~30) and your
  **best performers by rating** (protect the talisman for the games that matter + next season);
  low-`Stamina` + high-minutes is the one to cap.
- **🟢 Fresh & underused — blood them:** low minutes, esp. **young** players — the cushion is licence
  to develop them for the division above. Flag anyone with 0 apps.
Caveats to state: `min_pct` uses `TEAM_GAMES×90`, so genuine mid-season arrivals read artificially
low; 90-min model ignores ET.

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

## Rotation
**Safe to rotate into:** <the comfortable fixtures from the group table — big eff gap + good H2H +
no elite threat — rest key men / start kids here>. **Full strength:** <the danger side(s)>.
<Player-load — only if games have been played; on an early-season save write "no minutes logged yet":>
🔴 Heavy load — rotate to rest: <players + mins% + age/Stamina why (talisman, veteran, low-stamina)>
🟢 Fresh & underused — blood: <players + why; flag 0-app squad members>
*Caveats: min% denom = G×90 (mid-season arrivals read low); minutes model ignores ET. Condition is
NOT used (it resets to ~100 each game).*

**One-line to the gaffer:** *<punchy summary: it's won bar X — press the field, cup-tie the danger side, rest legs + blood kids in the soft games.>*

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
