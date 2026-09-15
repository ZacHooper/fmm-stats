---
name: scout-opponent
description: Produce a technical-analyst opposition scouting report for a single upcoming opponent in the active FM career — expected style, threats with the numbers behind them, weaknesses, and a concrete game plan — our standing 4-2-3-1 plus any variation, settings and personnel calls this opponent justifies. Combines our data (head-to-head history, squad-attribute profile, ratings) with the in-game scout's report (formation + style), which the user must supply because opponent tactics are NOT in the save. Use when the user says "scout <team>", "how do we beat <team>", or "prep for <team> this week".
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
(`state/scouts/`, via `db.save_scout`). That log is worth using: it's a season's worth of "what we thought going in," so a scout for a team you've
faced before can open by saying what the last read was and whether it still holds. Call
`db.scout_report()` directly for the briefing (you need the DataFrames, not printed text) but still
call `db.save_scout(rep, venue=..., formation=..., style=..., note=..., fixture=...)` yourself
afterward so this report lands in the same log the CLI would write. **Always pass `fixture` — the
match date, straight off the Next Match screen** (`fixture="2026-04-20"`). It is what separates the
home and away meetings of the same opponent: the key used to be `(opponent_tid, snapshot_label)`
alone, so the second scout of a side between two imports replaced the first, which is two fixtures
losing one rather than a supersede. Without it you get the old single-slot behaviour, and
`save_scout` warns on stderr and sets `_collision` when it can see it is replacing a scout of a
different venue. **Check the `_sync` on what it returns**
(`state.SYNCED` / `LOCAL_ONLY` / `SYNC_FAILED`) and tell the user when it is not `synced` — a scout
that only reached local disk is one the next agent and the other machine will never see, and until
2026-09 that failure was silent. Two things the log still cannot tell you, so don't read an absence
as proof: `season-outlook` and `scout-from-site` never write to it at all, and the key is
`(opponent_tid, snapshot_label, fixture)` — pass `fixture` or the second scout of the same opponent
before the next import still overwrites the first.

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
  on it. Seen again since: a right-back playing out of position at centre-back, flagged in a briefing
  as the aerial weak link, finished as his side's best player on 6 tackles from 6 and 6 interceptions.
- **A duel has two sides — check OURS before ruling a route out.** A briefing told the manager not to
  cross because the opponent centre-backs read Aerial 15 and Strength 14. It never looked up our own
  target man: Aerial 16, Strength 18, better than both. We crossed 19 times anyway, won the header
  count 18-14, and he won 5 of his 8 aerial duels on the way to a 2-0. Quoting only the defender's
  number is the same one-sided error as quoting an attribute the role isn't scored on — state both
  sides of the duel, or don't call the route off.

Full write-up: [`scouting-attribute-reads`](../../../docs/agent-context/scouting-attribute-reads.md).

## Resolve the career context first (do NOT hardcode)
Everything below is parameterised off the active career — pull these from `db`, don't assume Bucaspor:
- **Us** = `db.MANAGED_CLUB_TID` (first team) + `db.OUR_CLUBS` (adds the reserve tid). e.g. Frem =
  346 (+7296 reserves); Bucaspor = 6567 (+11320).
- **Snapshot** — `S, P = db.latest_snapshot()` (backed by `mart.snapshots.snap_ix`, already
  chronological across seasons/phases — don't hand-roll a `max(phase)` or a `phase_key` sort).
- **Our rating basis** — for Frem pass **`frem_minmax_4231`** explicitly, to match the 4-2-3-1 we
  actually play. **Do not inherit `db.config().get("default_method")`**: it still returns
  `frem_attacking_ss` (`seeds/config_bundle.json`), which is the dashboard/site default but no
  longer our tactic, and `scout_report(method=None)` resolves to that same stale value. Bucaspor
  (archived) → `buca_433`. The method only decides how players are RATED — the game plan is a shape
  plus settings, see the game-plan section below.
- **Our identity** — read it off `rep["strength"]`/`rep["unit_attrs"]` means, don't recite a fixed
  line; the squad has turned over heavily and the old "strong Creativity/Shooting" read is dated.
  **Check `rep["strength"]`'s `n_us` per unit before quoting a unit mean** — our Midfield frame has
  come back with as few as 2 rated players against an opponent's 11, which makes both the unit
  quality figure and its attribute means a two-man sample. Say so rather than quoting a 40-point
  gap as if it were solid.

## Inputs to establish first
- **Opponent** — `matches = db.resolve_club(name_or_tid)`. Diacritic/Turkish-insensitive
  substring match, sorted by squad size descending, so a same-named **Reserves** side (smaller
  squad) already sorts below the first team — take `matches.iloc[0]` unless it's genuinely
  ambiguous (`len(matches) > 1` with comparable squad sizes), in which case list the candidates and
  ask.
- **Formation** — ASK THE USER (from the in-game scout). Opponent shape is NOT parsed.
  **Best artefact: their `Club Squad → Selection` screen (the `Pkd` column)** — the opposition
  manager's *actual* current selection with position badges, plus suspensions, injuries, condition %,
  form and season apps. On its first use it disagreed with the same fixture's Predicted XI in 2 of 11
  slots and revealed both first-choice full-backs unavailable, inverting the flank plan. Season apps
  also settle "is this name new?" outright. Failing that, **Next Match → Predicted XI** names eleven
  players and their slots.
  **Trust the Predicted XI for neither shape nor names, and COUNT SLOTS, NOT NAMES.** Across eleven
  checks names were wrong 2–7 of 11, and shape held for six, then broke on four straight. Lyngby away
  is the cleanest case: **8 of 11 names right, only 3 of 11 slots** — a 73% name accuracy concealing a
  completely different front four. Slot accuracy is volatile, not reliably bad (the same opponent went
  5/11 then 8/11 three weeks later), so a wrong sheet last time is no guide to this time. **What
  survives either way are the PROFILE reads, not the positional ones** — build the briefing so they do.
  - **Never let your single most specific recommendation depend on one predicted name.** The recurring,
    expensive error is naming a FLANK off a predicted full-back: three briefings running the named
    target was the wrong man (did not play / injured / replaced by the man who was the actual soft spot
    on the *opposite* flank). Name the weak **profile** and the zone, then say who fills it if the
    expected man is absent.
  - **Read their BENCH for the counter-profile to whatever your plan depends on.** Twice the
    non-predicted names did the damage — a centre-back swap answering our aerial threat, and a winger
    who scored. Once the two men shown on the bench were their two best midfielders and both started;
    once the named goalkeeper was benched and the one who played was their best, which alone
    invalidated the briefing's route to goal.
  - **When a predicted man's best slot in our data differs from the slot the screen assigns him, say
    so** — cheap, checkable, and it has fired correctly (`player_position_levels` had Çorlu's best slot
    as ST against the screen's AMR; he played ST). Caveat: `level_*` is CA-derived, so for a very
    high-quality player it reads high at *every* slot and the ordering is mostly familiarity — only
    flag a difference that is large and football-plausible.
- **Their squad is not their first-team list — read the RESERVE club too** (`resolve_club("<name>
  Reserves")`), and **compare reserves against the WEAKEST men in the predicted XI, not the best.**
  Getting that backwards cost a briefing: it saw nobody near Horsens' top players, wrote "nobody who
  would walk into this XI", then watched a reserve start at centre-back (rated 7, 6 interceptions)
  with another off the bench — 79.9 and 83.0 on `level_nation` against predicted starters at 71.7,
  74.6 and 75.8. Done right it pays: at Lyngby the check named Datkovic (79.9) as beating predicted
  starter Maxsø (75.7), and he started. **Profile the reserve, don't just rank him** — Datkovic is
  Pace 7 / Movement 7, so his selection made their back line *slower* and the in-behind route better.
  Two traps: **`level_league` is a percentile against that player's OWN league**, so a reserve-listed
  player reads ~100 against reserve peers and is not comparable to a first-teamer's Superliga number
  (rank cross-league candidates on `level_nation`/`level_global`); and a name in **no** club's squad
  is *often* a post-snapshot signing but **absence is weak evidence** — `scrape_players` once anchored
  on the "no nickname" sentinel and hid 2,072 nicknamed players, two of whom had 22 and 11 apps that
  season and scored/made both goals in a 1-2 that beat us
  ([`nickname-players-missing`](../../../docs/agent-context/nickname-players-missing.md); fixed, so a
  store rebuilt after 2026-09 carries them). Say **"our data has never seen him"**, not "he must be a
  new signing" — and the `Selection` screen's apps column settles it in one glance.
- **Style** — ASK THE USER (balanced / possession / counter / high-press / direct …). This half of
  the in-game report has held up; weight it more than the shape.
- **OUR OWN tactics screens** — ASK FOR THESE TOO (Shape / Defence / Attack). A shape sets none of
  mentality, line, closing down, tempo, width or the final-third instructions, and this skill was
  blind to them for a whole season of briefings. In particular check whether **`Work Into Box`** is
  already set before diagnosing poor shooting as a selection problem
  ([`scoring-and-shot-quality`](../../../docs/agent-context/scoring-and-shot-quality.md)). And **do
  not infer "sit deep" from a quality gap**: one briefing advised a deep line and "absorb and break"
  on a −39 gap; the manager ran Attacking / HIGH / All Over / Fast away at the division's best attack
  and won 6-0, having drawn 1-1 with the cautious version. State the settings you mean — see the
  game-plan section. Role labels (IW / PF / Poacher / AF / AP) belong to whichever club's screen you
  are reading — say whose, every time, or a briefing will attribute the opponent's roles to us.
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
does **not** append — it replaces the record at `(opponent_tid, snapshot_label)`. It used to replace
*everything*, which cost four fixtures their pre-match briefing; it now carries the post-match half
forward and files the superseded prediction into `revisions`, so a corrected read can be written
over the top with the fix stated in the `note` without losing what it corrected. The log is what the
next agent reads, and a note carrying reasoning we already know to be wrong is worse than no note.

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
- **Write the grading with `db.grade_scout(opp_tid, result_note=..., result="W 2-0 (H)",
  fixture=...)`, NOT `save_scout`.** A scout record has two halves: `note` is what we thought BEFORE the game and
  `result_note` is how that read graded afterwards, and the pairing is the entire reason the log is
  calibration rather than a pile of old opinions. `grade_scout` writes `result_note` / `result` /
  `graded_at` and leaves `note` alone; name the `fixture` when the opponent has more than one scout
  — it raises rather than guess which briefing your result belongs to, since a wrong guess writes
  over a grading that was already right — and returns `None` if there is nothing saved to grade (say
  so rather than inventing a record). Check
  its `_sync` like any other write. Grading through `save_scout` with the grading text in `note` is
  what destroyed the Lyngby, Midtjylland, OB and FCK briefings — the FCK one was recoverable, the
  other three are not.
- Feed anything durable back into this skill or `docs/agent-context/`. `docs/` is in git and
  versioned; the scout log is not, and R2 has no object versioning — so a bad write there is gone.

Manager observations beat the model here. Three corrections from one session that no query would
have surfaced: that a defender's counter to Movement is Positioning (the model agreed — the briefing
had not checked); that both late goals arrived after the press was pulled back (see the game-plan
section on line vs press); and that a single poor performance is not evidence to move a player who
has been good all season. **Do not restructure a recommendation off one match's stat line** — that
is the same n=1 error the skill warns about elsewhere, applied to our own squad.

### Game plan — a 4-2-3-1 and the variations off it (THE career-specific value-add)

**Do NOT output a "recommended method + fallback switch".** That was this skill's deliverable until
2026-09 and it was the wrong unit of advice: a `role_weights` method is a **rating weight-set**, not
a game plan, and ranking five of them told the manager nothing he could do on a team screen. He runs
a **4-2-3-1 with a back four** as the standing shape and varies it per opponent. So the deliverable
is **that baseline plus the specific variations this opponent justifies**, each tied to the threat or
weakness that triggers it.

**The method is now only the RATING BASIS — pick it to match the shape, and say so once.** For a
4-2-3-1 rate with **`frem_minmax_4231`**, which is derived from this career's own match data rather
than from a tactic author's stated traits (`scripts/derive_weight_set.py` — read its docstring before
touching the set). Two things to know about it:
- **It has no AML/AMR block.** Only 8 roles are weighted (GK/CB/LB/RB/DM/CM/AMC/ST); the wide
  attacking roles failed to beat a flat weighting and were left flat **on purpose**. Fit numbers at
  AML/AMR still appear in `effective_table` — they are simply flat-weighted, so treat a wide Fit as
  a rough quality read, not a role-tuned one, and lean on `level_*` there instead.
- **`db.config().get("default_method")` still returns `frem_attacking_ss`** (`seeds/config_bundle.json`),
  which is no longer what we play. Pass the method explicitly rather than inheriting the config
  default, and don't describe `frem_attacking_ss` as "our tactic".

**Rate the slot, not the player.** The same winger can be a 92 at MR and an 85 at AMR, and a deep
left slot has flipped which of two candidates was correct by 25 percentile points. If the manager
shares a formation screen, rate that XI at the slots each player really occupies
(`db.effective_table(S, P, method)` filtered to `name` + `position`).

**The variation vocabulary — these are the manager's own levers, so propose in these terms:**

| Variation | Trigger to look for in `rep` |
|---|---|
| **Drop one forward wing AM → M** (e.g. AML → ML) | their strongest attacking outlet is on that flank, or their full-back on that side is their best attacking contributor — buys cover without changing the back four |
| **Drop the 10 to a 6** (second pivot beside the DM) | their AMC is a genuine threat (high Level %ile, Technique/Creativity-led) and would otherwise play between our lines |
| **Turn a WB into an IWB** | their winger on that side is a dribbler who comes inside, or we need an extra body in central midfield without losing a defender |
| **Back 3, or a single anchor + two strikers** | **reserved for the very top sides (FCK)** — do not propose it for mid-table opposition |

Almost always a back four. A variation is worth naming only when something in the data triggers it;
**listing all four as a menu is noise.** Usually the honest answer is "standard 4-2-3-1, no
variation needed" plus the settings — say that rather than manufacturing a tweak.

**The decision inputs are already in `rep`:**
- **Favourite vs underdog** — `rep["overall"]["us_quality"]` vs `["them_quality"]` (Level %ile, not
  the Fit-based `us`/`them`, since the latter judges them under a tactic they don't run). This sets
  mentality and how much cover the shape needs, **not** which weight-set to quote.
- **Their style** (user's scout) → a deep block is a width-and-patience problem; a side that tries to
  play out is a pressing opportunity keyed to their weakest build-up player.
- **The on-pitch matchups** (`rep["matchups"]`) → "Our attack vs their defense" says whether to
  expect chances; "Their attack vs our defense" says what to protect, and is the row that justifies
  a wing dropping to M. If they edge that second row on Strength/Aerial (check `rep["unit_attrs"]`)
  and play direct to a target man, **don't** open in a high-press duel game that plays to their one
  advantage.

**Check the weights against the opponent before trusting a shape or a route.** A weight-set is
selected for a duel, and the cheatsheet's situational mapping can point at the wrong one: against a
side with a slow but dominant aerial centre-back, the "break down a low block" set weighted **aerial
highest and pace lowest**, rewarding the duel we lose and ignoring the one we win. Read
`mart.role_weights` (**attribute names are lowercase there** — a capitalised filter returns nothing)
when a route recommendation hinges on it.

**Line and press are two levers, not one.** It is easy to write "drop the line" and have it read as
"drop the press". Against a side whose creativity funnels through one deep passer, pulling the
*press* hands that player time on the ball and is the more expensive of the two. Observed: a 3-0
became 3-2 immediately after the press was pulled, with their deep playmaker finishing on 32 passes
/ 28 completed, by ten the most on the pitch. When protecting a lead against a technical build-up
(check the opponent Defense unit's Passing/Technique in `rep["unit_attrs"]`), **drop the line and
keep the press on**. Say which lever you mean, every time.

**Settings and personnel are the valuable half — spell them out.** A shape sets none of Mentality,
Line, Tempo, Width, Press, Final third or Passing; those live on the manager's Shape / Defence /
Attack screens and the presets are in
[`docs/fmm-tactic-blueprints.md`](../../../docs/fmm-tactic-blueprints.md) → **"In-game SETTING
presets per scenario"** (read it live). Two that repeatedly matter:
- **`Work Into Box` vs `Shoot On Sight` is the shot-quality lever** — a team instruction, not a
  selection problem (see
  [`scoring-and-shot-quality`](../../../docs/agent-context/scoring-and-shot-quality.md)). Check it is
  set before proposing a different XI.
- **Justify Line and Width from the duel, not the preset.** "vs pace in behind → drop deep" does not
  apply when our Defense unit Pace beats their Attack unit Pace; narrow does not apply when their
  wide men don't track back. Quote both sides of the comparison.

Personnel calls are what the manager actually acts on: name the centre-back pairing and why (a
high line behind a Positioning-19/Pace-10 defender needs a quick partner), the flank to load and the
pace gap that justifies it, the in-behind runner, and who man-marks the aerial threat at set pieces.
Note whose screen a role label belongs to (IW / PF / Poacher / AF / AP) every time, or a briefing
will attribute the opponent's roles to us.

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
M = "frem_minmax_4231"        # match the shape we play; do NOT inherit the stale config default

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
# there may be SEVERAL rows per opponent now — one per fixture. `fixture`, `venue` and
# `saved_at` say which is which; `result_note` marks the ones already played and graded.

# ... write the report from rep, ask the user for formation/style, apply the tactic step ...

FIXTURE = "2026-04-20"                        # the match date off the Next Match screen
rec = db.save_scout(rep, venue="H", formation="attacking 442", style="high-press",
                    note="short plan summary", fixture=FIXTURE)
# ALWAYS pass fixture — without it the two meetings of a season share one key and the second
# replaces the first. Then report what the write actually did:
if rec["_sync"] != "synced":                  # LOCAL_ONLY (no remote) / SYNC_FAILED (push died)
    print(f"scout saved LOCALLY ONLY ({rec['_sync']}) — tell the user")
if rec.get("_collision"):                     # replaced an undiscriminated scout of another venue
    print("that overwrote a scout of the other leg")

# AFTER THE MATCH, when the user posts the FT stats — never save_scout with the grading in
# `note`, that destroys the briefing you are grading:
db.grade_scout(OPP, result_note="what held, what didn't, and why",
               result="W 2-0 (H)", fixture=FIXTURE)
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
omits the rating layer, and Fit/Level both need it. `db.save_scout()` and `db.grade_scout()` both
still work and still sync from a downloaded store — check the returned `_sync` either way.

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
<ONE section — named player, the numbers behind the threat, and what it means for us. Do NOT also
write a separate "key men" list: that duplicated this section almost line for line in every
briefing, which is why it was removed. Four or five bullets, each in the form
**Name (POS)** — the stat that makes him a threat + the tactical consequence:>
- **<Name> (<POS>)** — <Level %ile + the two or three attributes that drive the threat, from
  `rep["key_players"]`/`top_attrs`. Level %ile, not Fit — see "The engine already exists" above.
  Then the consequence: who picks him up, which lever contains him, what he punishes if ignored.>
- <plus the non-player threats, still with their numbers: the "Their attack vs our defense" row of
  `rep["matchups"]`, the direct/set-piece route and the aerial group that delivers it, shot volume
  from the H2H, and anything in `rep["flags"]`.>
- <their BENCH, when it holds a counter-profile to our plan or a player stronger than a predicted
  starter — this is where the briefing has been caught out most often.>

## Where we win
- <the "Our attack vs their defense" row of `rep["matchups"]` (do we have the quality edge going
  forward?) + attribute detail from `rep["unit_attrs"]` (their Defense unit's weak spots — already
  the right axis, since it's describing THEIR defensive line on its own terms) + space their shape
  concedes. **Then go per-player**: name the individual defender who is the soft spot and say which
  KIND of soft spot he is — a Positioning weakness is a run-at-him weakness, an Aerial/Strength
  weakness is a duel-and-deliver one, and they are usually different players on opposite flanks. A
  unit mean hides both. Read the columns the role is actually scored on — see "Reading attributes"
  above.>

## Game plan
- **Shape: standard 4-2-3-1.** <One line on how it sits against theirs — who screens whom, where we
  attack, tied to our real edges (width/pace/creativity) rather than their strengths (aerial/duels).>
- **Variation:** <ONLY if the data triggers one, in the manager's own vocabulary — a forward wing
  dropping AM→M for cover, the 10 dropping to a 6 against a dangerous opposing AMC, a WB becoming an
  IWB, back four almost always. Name the trigger with its number. If nothing triggers one, write
  "none needed — standard 4-2-3-1" and move on; do not list the menu.>
- **Settings:** <Mentality / Line / Tempo / Width / Press / Final third / Passing — each justified
  from a duel or a number, not from the preset. Say which of Line and Press you mean, every time.>
- **Personnel:** <the centre-back pairing and why, the flank to load with the gap that justifies it,
  the in-behind runner, who takes the danger man.>
- **Defend:** <funnel wide/deny centre; screen the direct ball; man-mark aerial threats on set pieces.>
- **Cutting edge / set pieces:** <if the H2H shows control-without-chances, stress chance quality;
  our aerial edge if any — checking BOTH sides of the duel before recommending a route; who to track
  after our set pieces.>

**One-line to the gaffer:** *<punchy, quotable summary of the plan.>*

---
Eyeball it: **Team analysis → Scout a team → <Club>** — the **Face-off matchups** table for the
attack-vs-defense reads, the unit/position filters (e.g. Us→Attack vs Them→Defense) to probe any
matchup by hand, and the head-to-head drilldown. Set the **method** selector to
`frem_minmax_4231` to preview our XI's Fit in this shape. This report has been saved to the scout log
(`uv run python fmq.py scouts` to review it alongside past reads on other opponents).
```

Keep it decision-useful and honest about the estimate limitations (attributes ±1; tactics not in
the save). One opponent at a time (opponent tactics vary, so a whole-season sweep would need each
team's in-game scout report as input — see [`season-outlook`](../season-outlook/SKILL.md) for the
group-level version of this, which hands off to this skill per-fixture). Offer at the end to scout
the next opponent.
