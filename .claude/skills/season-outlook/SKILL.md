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

## Reading attributes: a duel, not a squad average
**This section was missing from this skill until 2026-09 and it produced a wrong briefing on its
first use after that.** The rules are the same ones `scout-opponent` already carries — read
[`scouting-attribute-reads`](../../../docs/agent-context/scouting-attribute-reads.md) for the full
write-up; the short version is below, because a six-team outlook repeats whatever error it makes
five more times than a single scout does.

**Never average attributes across a whole outfield squad.** The old Step 1 here did exactly that
(`taf[taf.unit != "GK"][ATTR].mean()`), which mixes attackers and defenders into one number and
compares it to the opponent's equally mixed number. Two failure modes, both observed on the
2026-03-22 championship-group run:
- It reported "their strength is Tackling" for the two best sides — true of their *midfielders*,
  but the figure was dragged there by forwards who are not judged on Tackling at all.
- It reported "our edge is Movement +3.3" as if it applied everywhere, when Movement is only the
  **attacker's** side of a duel. Redone as *our attack's Movement vs their defence's Positioning*,
  the edge was +1.4 to +4.2 — same direction, different size, and for the first time comparable
  between opponents.

**Aggregate per UNIT and pair each unit against its counterpart**, the `matchup_table` reading:
our attack vs their defence, their attack vs our defence, midfield vs midfield. A back line does
not play a back line.

| The question | Attacker side | Defender's answer |
|---|---|---|
| Can they be run in behind? | **Movement**, Pace | **Positioning**, Pace |
| Who wins it back? | Dribbling, Technique | **Tackling** |
| Who wins the air? | Aerial, Strength | Aerial, Strength |
| Will they last 90? | Stamina | Stamina |

Movement is weighted **baseline** for a CB and **4** for a CM/ST; Positioning is **4** for a CB and
**baseline** for a ST/AMC/winger. Quoting an attribute a role is not scored on is quoting noise.

**Check individual defenders, never only the unit mean.** Confirmed again on Brøndby: back-line
Positioning averaged 12.7, and their first-choice left-back sat on **8** — the flank the whole plan
ended up pointing at. Then weigh it against the rest of that player's profile (the same left-back
has Tackling 15, so he can win a tackle, he just cannot track a runner off the ball).

**Level %ile, not Fit %ile, for every opponent in the group.** `eff` / `pos_index` / `pctile_league`
answer "how well would these players suit OUR tactic" — only a fair question about our own squad.
The old Step 1 ranked group difficulty on `eff`. Rank on `quality` (mean Level %ile) instead.

**Read the decoded numbers as exact** — ~63% exact / ~93% within ±1, and Pace, Strength, Stamina,
Technique, Aggression, Leadership, Agility and Teamwork are exact outright. No hedging.

> **Level %ile can understate a defence badly, and it is worth saying so in the report.** On
> 2026-03-22 our back line read 19 on Level while containing a centre-back with **Positioning 19,
> Tackling 18, Aerial 16** (Pace 10 — hence the low CA). The manager's own read, "our defence has
> been great", agreed with the attributes and not with the percentile. Use Level to rank *opponents*
> against each other; use the duel read to say what will actually happen.

## Step 1 — Group comparison (the core engine)
For each opponent pull, vs us: **Level-%ile quality gap**, **per-unit quality**, **H2H**,
**top threats by Level %ile**, and the **duel edges** above. Rank by quality (difficulty).
Use `db.squad_frame` + `db.team_strength` — they already pick the primary-position row, apply the
spell-based "who is really on their books" check (a hand-rolled `club_tid` filter silently includes
lapsed loans), and return Level %ile alongside Fit.
```python
import os, sys
os.environ["FM_CAREER"] = "frem"
os.environ["FM_DUCKDB"] = os.path.expandvars("$CLAUDE_JOB_DIR/tmp/outlook.duckdb")   # cp of the store
os.environ["FM_DUCKDB_READONLY"] = "1"
sys.path.insert(0, "dashboard"); import db, pandas as pd
S, P = db.latest_snapshot(); M = db.config().get("default_method"); US = db.MANAGED_CLUB_TID
GROUP = {"FC Nordsjaelland": 2465, "Midtjylland": 360, "Broendby": 337,
         "Lyngby": 364, "Horsens": 326}                      # the user's set

fr = db.squad_frame(S, P, M, [US] + list(GROUP.values()))     # spell-safe, carries the 23 attrs
us_units, us_team = db.team_strength(fr, US)                  # .quality = Level %ile; .pctile = Fit
h = db.our_match_history()
for name, tid in GROUP.items():
    units, team = db.team_strength(fr, tid)
    hh = h[h.opp_tid == tid]                                  # date, venue, gf, ga, result
    # gap = us_team["quality"] - team["quality"]; per-unit from units[["unit","quality"]]
    # threats: db.squad_key_players(fr, tid, M, rank_by="level_league")  <- Level, not Fit
    # individual defenders: fr[(fr.club_tid == tid) & fr.position.isin(["GK","DL","DC","DR","DMC"])]

# DUEL EDGES — per unit, against the counterpart unit (never one outfield average)
taf = db.team_attribute_frame(S, P, M, [US] + list(GROUP.values()))   # attrs are Capitalised
def unit(tid, u, cols): return taf[(taf.club_tid == tid) & (taf.unit == u)][cols].mean()
ourA = unit(US, "Attack",  ["Movement", "Pace", "Shooting"])
ourD = unit(US, "Defense", ["Positioning", "Pace", "Aerial", "Tackling"])
for name, tid in GROUP.items():
    tA = unit(tid, "Attack", ["Movement", "Pace", "Shooting"])
    tD = unit(tid, "Defense", ["Positioning", "Pace", "Aerial", "Tackling"])
    # WE ATTACK:   ourA.Movement - tD.Positioning   and   ourA.Pace - tD.Pace
    # THEY ATTACK: tA.Movement  - ourD.Positioning  and   tA.Pace  - ourD.Pace
    # MIDFIELD:    unit(US,"Midfield",C) - unit(tid,"Midfield",C) for Tackling/Passing/Decisions/Stamina/Creativity
```
Read out per opponent: quality gap, per-unit quality (**a lone elite unit matters more than the
mean** — a group-best keeper or one 95-100 %ile attacker decides a fixture), H2H with GF-GA (**a
prior defeat flags the danger side even when the quality table does not**), the duel edges, and the
named threats. Check the **goalkeeper** explicitly: a 100 %ile keeper is the single most common
reason a favourable outlook produces no goals.

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

### A quality gap is NOT a reason to plan a cautious game — the trap this step is most prone to
A season outlook often sizes up a group where **we are the underdog in most of it**, and the
temptation is to write four counter-attacking game plans. That was tested and it failed. Away at
Midtjylland with a 45-v-84 quality gap, the cautious plan (counter method, deep line, absorb and
break) drew 1-1 **from 3 shots**. The same fixture replayed with the proactive default —
**Attacking / High / All Over / Fast / Work Into Box / Short through the Centre** — finished **6-0**
on 15 shots, 7 on target. Being out-rated on Level %ile is not the trigger for sitting deep.

**The one genuine trigger is pace in behind against slow centre-backs** — and check it as a *duel*
(their attack's Pace vs our defenders' Pace, plus the individual pacy threat), not as "they're
better than us". On the 2026-03 group, four of the five out-rated us and only one had a real pace
edge over our back line.

**Line and press are two levers.** "Drop the line" reads as "drop the press" and that is the more
expensive half: a 3-0 became 3-2 immediately after the press came off, their deep playmaker
finishing on 32 passes / 28 completed, by ten the most on the pitch. When a game needs protecting,
drop the line and **keep the press on**.

### Carry the shot-quality lever into the plan
If the group contains sides that will bunker, or a top-tier goalkeeper, the binding constraint is
chance *quality*, not chance volume. Shots on target predicts our goals at **r=+0.72** while shot
volume is flat across every accuracy quartile, and crossing has an optimum around 11 and declines
beyond it ([`scoring-and-shot-quality`](../../../docs/agent-context/scoring-and-shot-quality.md)).
**`Work Into Box` is the lever** — with it set, the squad's worst shooters simply stop shooting and
team SOT rate went from a 36.2% season average to 47-67%. It is a team instruction, not a selection
problem; say so before recommending a different XI.

### Check who actually scores before recommending anything
A run-in plan that ignores where the goals come from is decoration. Pull goals and assists by
position and by player for the season, and compare each contributor's **share of output** to his
**share of minutes** — on the 2026-03 group this surfaced the whole answer: two players held 73% of
our goals while playing 59% and 46% of available minutes. Under-playing the top scorer is a bigger
lever than any setting in the briefing, and it only shows up if you look.
```python
f = db.q(f"""SELECT tid, SUM(goals) g, SUM(assists) a, SUM(minutes) mins
             FROM mart.match_player_facts WHERE season={S}
             AND team_tid IN (SELECT club_tid FROM mart.managed_club) GROUP BY tid""")
# position comes from the squad_frame (mart.player_snapshots has NO position column) —
# f["pos"] = f.tid.map(fr.set_index("tid")["position"])
```

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

## After the fixtures — close the loop
This skill predicts a whole group, which makes it cheap to grade and therefore inexcusable not to.
When the user reports results from the run, revisit the briefing and say plainly which calls held:
the difficulty ranking (did the circled side actually bite?), the duel edges (did we out-move them?),
the recommended base method, and the rotation calls. `db.our_match_history()` has the results and
`mart.match_player_facts` the per-player minutes, so the grade is a pull, not a memory exercise.
Record anything that *changed* our understanding in `docs/fmm-tactic-blueprints.md` (dated), not just
in the chat — an undated finding gets quoted forever, and a finding left in a transcript is lost.

## Report template — KEEP THIS LAYOUT
Technical-analyst tone, to the manager. Prose + small tables. Base every claim on the pulls.

```markdown
# 🏆 <Stage/run-in> outlook — <Us> (<N> matches, <k> opponents)
*Squad-quality + risk + workload map across the run. No per-team formations (that's the single-opponent
scout). <Live standing: leaders on X, 2nd on Y — an N-point cushion with M to play.>*

## Verdict
<favourite/underdog for the group + the single game that can actually bite + what the prep is really for.>

## The group (Level %ile — quality, not Fit; +ve gap = we're stronger)
| Team | Level %ile | Gap vs us | D / Mf / A / GK | H2H (P·W-D-L) | GF-GA | Read |
|---|---|---|---|---|---|---|
| ... sorted by Level %ile; mark the ⚠️ danger side (a prior defeat / a 95-100 %ile attacker / a
  top-tier keeper). Per-unit quality earns its column: a group-best GK or one elite unit decides a
  fixture that the squad mean says is even. ... |

## The duels (per unit, against its counterpart — never a squad average)
| Team | We attack: our Movement v their Positioning | their def Pace | They attack: their Movement v our Positioning | their Pace | Midfield edge |
|---|---|---|---|---|---|
| ... +ve = our advantage. Name the individual outlier too — the back-line mean hides the 8. ... |

## ⚠️ The one(s) to circle — <Team>
<why: the only side to beat us / their elite man at N-th %ile / they out-<attr> us; recommend a full
single-opponent scout when it comes up, and the likely tactic flex.>

## The pattern across the group
<the 2-3 things that repeat: recurring threat type, our universal edge(s), the exposure that flexes the plan.>

## Where our goals come from
<goals + assists by position, then the share-of-output vs share-of-minutes comparison. If a top
contributor is under-played, say it here — it outranks every setting below.>

## Plan for the run-in
- **Default:** `<method>` + <press/approach> for <the field / named routine games>.
- **Flex:** <drop the line / `<counter variant>` for the pace-threat game(s); `<lowblock variant>` vs anyone who bunkers.>

## Rotation
**Safe to rotate into:** <the comfortable fixtures from the group table — big quality gap + good H2H +
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
- **`mart.player_snapshots` has NO position column** (nor `pos`) — it is the 23 attributes wide plus
  `age`/`reputation`. Positions come from `effective_table`/`squad_frame`. And **`mart.squad_current`
  carries no `age`** (`person_id, tid, name, club_tid, is_loan_in, is_reserve, valid_from, as_of`) —
  join `mart.player_snapshots` for age. Both of these cost a query on the 2026-03 run; the fuller
  table is in [`player-analysis-methods`](../../../docs/agent-context/player-analysis-methods.md).
- **Don't hand-roll the primary-position/club filter** — `db.squad_frame` does it and applies the
  spell check; a bare `club_tid` filter includes players whose loan lapsed without being renewed.
- **A `role_weights` method is a rating weight-set, NOT a tactic.** Recommending `frem_counter` sets
  no mentality, line, press, tempo or final-third instruction — name the in-game settings too. The
  full menu surface is [`fmm-tactic-options`](../../../docs/agent-context/fmm-tactic-options.md).
- **Any Fit number quoted from a doc must carry the date and squad it was computed on** — a mid-22
  Fit table was quoted at a 2026 squad and put a wrong claim into `scout-opponent`.
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
