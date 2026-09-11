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

## Reading attributes: check the role weights before calling anything a weakness

**An attribute is only a strength or a weakness against its counterpart.** `mart.role_weights`
already encodes which attributes a role is even scored on, and a number the role does not score is
noise. The pair that has bitten this skill twice:

| | CB | LB/RB | DM | CM | ST | AMC | AML/AMR |
|---|---|---|---|---|---|---|---|
| **movement** | **baseline** | 3 | 2 | 4 | 4 | 3 | 3 |
| **positioning** | **4** | 3 | 4 | baseline | **baseline** | **baseline** | **baseline** |

("baseline" = absent from that role's weight list, so it scores at weight 1 — the floor. There is no
way to weight an attribute *below* baseline, so an unlisted attribute is not penalised; it is simply
not what the role is judged on.)

**Movement is the attacker's side of the duel; Positioning is the defender's answer to it.** Two
consecutive briefings led with "their back line has Movement 7.1" as the headline exploit. A
centre-back with Movement 6 is not slow to react — Movement is not what he is judged on. Redone on
Positioning, one of those defences was *level* with ours, and the other's weak link turned out to be
a different player on the opposite flank. Same trap in reverse: "their striker has Positioning 7"
says nothing.

Before quoting any attribute, check it is weighted above baseline for that player's role:

| The question | Attacker column | Defender column |
|---|---|---|
| Can they track runners in behind? | Movement, Pace | **Positioning**, Pace |
| Can they win it back? | Dribbling, Technique | **Tackling** |
| Who wins the ball in the air? | Aerial, Strength | **Aerial, Strength** |
| Will they last 90? | Stamina | Stamina |

**A ball-playing centre-back is a threat, not just a press target.** `rep["key_players"]` ranks by
Level %ile and a deep-lying creator can sit mid-table on it while running the game. If an opponent
defender's profile is Passing/Technique-led, check him as an attacking outlet too — one such
centre-back finished a scouted fixture on 53 passes, 45 completed, **4 key passes**, 11 tackles with
9 won and 7 interceptions, the best player on the pitch, having appeared in the briefing only as a
note about how they build from the back.

**Read the decoded numbers as exact.** Attributes for a player who was never ours are a frozen
decode, but held-out accuracy is ~63% exact / ~93% within ±1 (`fmparser/model.py`), so quote them
without hedging. Eight are exact outright (Pace, Strength, Stamina, Technique, Aggression,
Leadership, Agility, Teamwork) — a Pace or Strength comparison is the hardest claim available about
an opponent. Do **not** import the 8-24x "compression" figure from
[`player-analysis-methods`](../../../docs/agent-context/player-analysis-methods.md): that is about
year-over-year *growth* and belongs to forecasting, not to a point-in-time scouting read.

The two reads that do need care are about football, not decode error:

- **Check individual defenders, not just `rep["unit_attrs"]`** — a back four averaging 12 can contain
  an 8, and the unit mean hides exactly the player you want to attack.
- **One attribute does not decide a duel.** A full-back with Positioning 8 but Tackling 13 and Aerial
  15 can still have an excellent game (observed: 8 tackles, 6 won, 5 interceptions, rated 8). Name
  the weakness, then weigh it against the rest of that player's profile before building a flank plan
  on it.

Full write-up: [`scouting-attribute-reads`](../../../docs/agent-context/scouting-attribute-reads.md).

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
- **Formation** — ASK THE USER (from the in-game scout). Opponent shape is NOT parsed. **Treat the
  in-game scout's shape as a prior, not a fact** — it has been wrong on both occasions it has been
  checked against what the opponent actually lined up in (a "5-2-2-1 counter" side played a 4-2-3-1;
  the style half of the same report, "counter-attack, very physical", was accurate). The **Next
  Match → Predicted XI** screen is a better source when the user has it: it names eleven players and
  their slots, which resolves shape, personnel and their bench in one screenshot. Ask for it. Build
  the briefing so the *personnel* reads survive a shape that turns out different — name which of
  their players is the problem and which is the soft spot, not just which zone. **Trust the Predicted
  XI for shape, not for names:** on its first check the shape was right and **3 of the 11 names were
  wrong**, and two of the three (a centre-back swap that was their answer to our aerial threat, and a
  winger who then scored) were the players who did the damage. So always read their **bench** for the
  counter-profile to whatever your plan depends on — if the plan is "our target man beats their
  centre-backs in the air", find the aerial centre-back they have not started.
- **Style** — ASK THE USER (balanced / possession / counter / high-press / direct …). This half of
  the in-game report has held up; weight it more than the shape.
- **OUR OWN tactics screens** — ASK FOR THESE TOO. This skill recommends a *method*
  (`frem_attacking_ss`, `frem_counter`, …), but a method is only a **rating weight-set**: it does not
  set mentality, defensive line, closing down, tempo, width, or the final-third instructions. Those
  live on the manager's Shape / Defence / Attack screens and this skill was blind to them for a whole
  season of briefings. Two things that cost real accuracy:
  - **`Work Into Box` vs `Shoot On Sight` is the shot-quality lever**, and it was already set while
    the briefings were diagnosing poor shooting as a selection problem (see
    [`scoring-and-shot-quality`](../../../docs/agent-context/scoring-and-shot-quality.md)). Check the
    instruction before proposing a change of personnel.
  - **A method recommendation is not a game plan.** One briefing recommended `frem_counter` with a
    deep line and "absorb and break" on a −39 quality gap; the manager ran Attacking mentality, a
    HIGH line, All Over closing down and Fast tempo away at the division's best attack and won 6-0,
    having drawn 1-1 with the cautious version. Do not infer "sit deep" from a quality gap alone, and
    state the settings you mean rather than leaving them implied by the method name.
  Note also that role labels on a formation screen (IW / PF / Poacher / AF / AP) belong to whichever
  club's screen you are reading — say whose, every time, or a briefing will attribute the opponent's
  roles to us.
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

**Re-save a scout when its reasoning changes, not just when the fixture does.** `db.save_scout`
appends, so a corrected read can be written over the top with the fix stated in the `note` — the log
is what the next agent reads, and a note carrying reasoning we already know to be wrong is worse
than no note.

## After the match — close the loop (do this when the user posts the FT stats)
The scout log only becomes calibration if someone checks it. When the user shares a full-time stat
screen for a fixture that was scouted, **grade the briefing explicitly**: which calls landed, which
did not, and which were right for the wrong reason. This is where the durable learning comes from,
and it is cheap — the FT screen already has everything needed.

- Anchor the match against the **season baseline**, not against feel. Pull it:
  `m = db.our_match_history()` filtered to the season, then shots / shots-on-target / conversion /
  passes per game. **Use that helper rather than raw `staging.match_player_stats`** — one match is
  stored under up to five `anchor`s and the obvious `(anchor, tid)` dedup is a no-op (trap 4 in
  [`player-analysis-methods`](../../../docs/agent-context/player-analysis-methods.md)).
- **The FT stat screen lists starters and substitutes separately** — scroll before totalling, or a
  starters-only count gets compared against the store's full-match figures. That error manufactured a
  fake "shot collapse" across two briefings. Column key: `PaA/PaC` passes attempted/completed,
  `Key` key passes, `Ass` assists, `TaA/TaW` tackles, `Int` interceptions, `HeA/HeW` headers,
  `CrA/CrC` crosses, `Dri` dribbles, **`Mis` = mistakes** (not misplaced passes), `MiG` mistakes
  leading to a goal, `ShA/ShO` shots attempted/on target, `Con` condition.
- **Test a pattern before you write it down.** Four hypotheses from this skill's briefings looked
  compelling over 3–4 matches and died against the full history (see
  [`scoring-and-shot-quality`](../../../docs/agent-context/scoring-and-shot-quality.md)). A
  per-opponent record of "3 wins from 3" implies an effect several times larger than anything that
  survives a league-wide test. "11 shots and 3 goals" means nothing until it sits next to "7.1 shots and 0.82
  goals per game, 11.7% conversion".
- **A right conclusion off wrong reasoning still counts as a miss** — say so. It will not transfer to
  the next opponent otherwise.
- Read the **per-player** columns for the specific claim the briefing made: if the plan was "attack
  their weak aerial full-back", check the aerial-duel counts, not just the scoreline.
- Feed anything durable back into this skill or `docs/agent-context/`, and re-save the scout note.

Manager observations beat the model here. Three corrections from one session that no query would
have surfaced: that a defender's counter to Movement is Positioning (the model agreed — the briefing
had not checked); that both late goals arrived after the press was pulled back (see the game-plan
section on line vs press); and that a single poor performance is not evidence to move a player who
has been good all season. **Do not restructure a recommendation off one match's stat line** — that
is the same n=1 error the skill warns about elsewhere, applied to our own squad.

### Tactic recommendation — consult our playbook (THE career-specific value-add)
After profiling, **recommend which of our methods to run**, keyed to
[`docs/fmm-tactic-blueprints.md`](../../../docs/fmm-tactic-blueprints.md) → **"When to use each —
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
- **Game state** → protecting a lead late = the close-out variant (`frem_game_state`). **Recompute its
  Fit before quoting one** — the 64.5-vs-~69 figure this line used to cite was from mid-22, and on the
  2025-11-30 squad `frem_game_state` recomputes to 87.3, *second* of the five, with the whole spread
  collapsed to 2.6 points. The old "shutting up shop is this squad's worst option" no longer holds.
  Same trap as the attribute reads: an undated number gets quoted at a squad four seasons newer.
- **The XI the user has actually drawn.** If they share a formation screen, rate that XI at the slots
  each player really occupies (`db.effective_table(S, P, method)` filtered to
  `name` + `position`) and compare the mean Fit %ile across candidate methods. The shape itself is
  evidence: a 4-2-3-1 with an AF and a wide W is `frem_counter`'s shape, and on one real XI nine of
  eleven players scored higher under it than under the proactive default. **Rate the slot, not the
  player** — the same winger can be a 92 at MR and an 85 at AMR, and a deep left slot flipped which
  of two candidates was correct by 25 percentile points.

**Line and press are two levers, not one.** The cheatsheet's scenario presets move both together,
which makes it easy to write "drop the line" and have it read as "drop the press". Against a side
whose creativity funnels through one deep passer, pulling the *press* hands that player time on the
ball and is the more expensive of the two. Observed: a 3-0 became 3-2 immediately after the press was
pulled, with their deep playmaker finishing on 32 passes / 28 completed — by ten the most on the
pitch. When protecting a lead against a technical build-up (check the opponent Defense unit's
Passing/Technique in `rep["unit_attrs"]`), **drop the line and keep the press on**. Say which lever
you mean, every time.

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
**First try pulling the published full store down and running the real engine against it** — on a
remote/web session this takes seconds and costs nothing in fidelity, which beats both a rebuild and
a thinner report:

```bash
rclone copy r2:fmm-stats/site-data/fm-frem.duckdb "$SCRATCH"      # ~48 MB, retry on a 501
```
then point `db.py` at the copy (`FM_DUCKDB=$SCRATCH/fm-frem.duckdb`, `FM_DUCKDB_READONLY=1`) and
call `db.scout_report()` exactly as below. Pull the **full** store, not `-mart`: the mart object
omits the rating layer, and Fit/Level both need it. `db.save_scout()` still works and still syncs.

Only if rclone or the remote isn't configured — hand off to
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
- **Check how stale the snapshot is against the fixture date, and say so.** `db.latest_snapshot()`
  is the last *parsed* save, not today's game. Scouting a February fixture off a November snapshot
  means the entire January window is invisible: on one real briefing **six of the opponent's starting
  eleven had arrived since the snapshot**, including the man who ran the game, and on the next
  opponent it was both first-choice full-backs. Sanity-check the user's predicted-XI screenshot
  against `rep["key_players"]` — **a name in their XI that is absent from the frame is a new signing**,
  and one you can often still rate off their previous club
  (`WHERE name ILIKE '%<name>%'` without a club filter). State the gap in the caveat line and
  prompt for an import.
- **In-game news items name players from BOTH squads.** An "opposition report on <Club>" screen
  mixes their scout's read with our own players' morale notes. Three names in one such report were
  all ours. Resolve every name against `club_tid` before attributing it — do not assume a name in
  an opposition report belongs to the opposition.
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
profiled by position + league percentile. <If the snapshot predates the fixture by a window, say so
here and name the players in their XI that our data has never seen.>*

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
  concedes. **Then go per-player**: name the individual defender who is the soft spot and say which
  KIND of soft spot he is — a Positioning weakness is a run-at-him weakness, an Aerial/Strength
  weakness is a duel-and-deliver one, and they are usually different players on opposite flanks. A
  unit mean hides both. Read the columns the role is actually scored on — see "Reading attributes"
  above.>

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
