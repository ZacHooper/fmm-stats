---
name: scout-opponent
description: Produce a technical-analyst opposition scouting report for a single upcoming opponent in the active FM career — expected style, threats with the numbers behind them, weaknesses, and a concrete game plan — our standing 4-2-3-1 plus any variation, settings and personnel calls this opponent justifies. Combines our data (head-to-head history, squad-attribute profile, ratings, and now the opposing manager's own formation/Style record) with anything fresher the user can add from the in-game scout screens — no longer required, since the manager's preferences are in the save. Use when the user says "scout <team>", "how do we beat <team>", or "prep for <team> this week".
---

# Scout an opponent

Acts as the technical analyst briefing the manager on this week's opponent. **Career-aware** —
reads the active career's store (`FM_CAREER` / newest `fm-<key>.duckdb`), not a hardcoded club.
Refresh via `import-fm-saves` first if stale. The opposing manager's own formation/Style record
(`rep["manager"]`) is now the baseline for shape and intent — no user input required to get a
report started. Layer on anything fresher the user can add (this week's team news, an in-game
scout screen) as a refinement, not a prerequisite. Immersion rule: reason with ratings + match
stats + attributes,
**never surface CA/PA** (the Level %ile is the one allowed CA-derived exception). No local store
to hand? Use the [`scout-from-site`](../scout-from-site/SKILL.md) skill instead — same job, the
deployed site's JSON, works from anywhere.

## The engine already exists — call it, don't re-derive it

`scout.scout_report(st, opp_tid, method=None)` (`fmstats/scout.py`, where `st` is an open
`fmstats.store.Store`) is the shared engine behind `fmq.py scout <team>`. It already does every
correctness-sensitive pull this report needs, so **this skill's job is to call it once and write
the narrative, not to hand-roll SQL that re-derives what it already gets right**:

- **H2H** via `match_history()` over `mart.club_matches` — one row per match (the match table is a
  ring buffer; a naive scan across every snapshot double-counts), with per-venue records in
  `rep["h2h"]["H"]` / `["A"]`.
- **Who has actually hurt us** via `h2h_players()` → `rep["h2h_players"]` — each opponent player's
  goals, assists, key passes and shots in matches against us, with `still_there`. **Read it before
  the threat section, not after.** Level %ile ranks QUALITY, not output: against OB it put Ely,
  Nørgaard and Weiss top while the men who had actually hurt us were Nielsen (5 goals, Level 53) and
  Þrándarson (11 key passes, Level 23) — a briefing built on the ranking alone called Nielsen the
  back-up striker. The auto-read flags anyone still there with 2+ goals and assists against us.
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
  `scout_report` ranks their `key_players` by — which is exactly why `h2h_players` sits beside it.
- **Auto-read** via `_scout_flags()` — bogey-side / we-own-them H2H calls, the same face-off
  matchup edges, danger men (Level %ile), and their defensive soft spots (a fixed threshold list),
  plus a `⚠️ PARTIAL DATA` flag when the frame doesn't reach 11 rated players. **This already covers
  the old "no-data opponent" detection** — check `rep["coverage"]["partial"]` and read `rep["flags"]`
  instead of eyeballing empty DataFrames yourself.
  **On a partial frame the squad-derived flags are now WITHHELD, not hedged** (2026-09): team
  strength, matchups, danger men and defensive soft spots are suppressed and only the warning plus
  H2H come back. They used to be emitted with full confidence off however few players existed, which
  is worse than no flags — scouting Hajduk Split off **two** rated players produced "We're stronger —
  team index 126 vs 116" and "Their defence: weak in the air (Aerial 5) — target it", where the
  Aerial 5 was ONE full-back standing in for a back four. Acting on it means bombarding the box: 21
  crosses, 17 headers won to 7, six corners to nil, one goal, lost 1-3. H2H survives the suppression
  because it comes from match history, not the squad frame.
  **`resolve_club`'s `n_players` is NOT coverage** — it is `mart.clubs.squad_size` (ownership, all
  snapshots of the save); `rep["coverage"]` is the only honest answer to "how many are rated".

Writing your own query for any of this reopens exactly the traps these helpers exist to close —
ring-buffer double counts, `tid` recycling across snapshots, a raw `club_tid` filter that still
matches a player whose loan lapsed without clearing, and (new) rating an opponent by how well they'd
fit a tactic they don't play. If a report needs something `scout_report` doesn't return (e.g. a
deeper individual-attribute cut), pull that one extra thing with `st.con.execute(...)` — don't
re-derive what's already there. `fmq.py output --club <them> --vs <us>` is the same producers table
from the CLI, and `fmq.py matches --opp <them>` the head-to-head.

**`fmq.py scout <team> [--venue H|A --fixture <date> --formation "..." --style "..." --note "..."]`**
is the CLI form of the same call and — unless `--no-save` — writes the result into the R2-synced
scout log (`state/scouts/`, via `scout.save_scout`). That log is worth using: it's a season's worth of "what we thought going in," so a scout for a team you've
faced before can open by saying what the last read was and whether it still holds. Call
`scout.scout_report()` directly for the briefing (you need the DataFrames, not printed text) but still
call `scout.save_scout(st, rep, venue=..., formation=..., style=..., note=..., fixture=...)` yourself
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
Everything below is parameterised off the active career — pull these from `st`, don't assume Bucaspor:
- **Us** = `st.career.managed_tid` (first team) + `st.career.reserve_tid`. e.g. Frem =
  346 (+7296 reserves); Bucaspor = 6567 (+11320).
- **Snapshot** — `st.season, st.phase` (the latest row of `mart.snapshots` by `snap_ix`, already
  chronological across seasons/phases — don't hand-roll a `max(phase)` or a `phase_key` sort).
- **Our rating basis** — `scout_report` defaults to the career's `rating_method`
  (`fmparser/careers.py`): **`frem_minmax_4231`** for Frem, matching the 4-2-3-1 we actually play;
  `buca_433` for archived Bucaspor. `app_config.default_method` still reads `frem_attacking_ss`,
  the site's display default — not our tactic, so don't pass it. The method only decides how players are RATED — the game plan is a shape
  plus settings, see the game-plan section below.
- **Our identity** — read it off `rep["strength"]`/`rep["unit_attrs"]` means, don't recite a fixed
  line; the squad has turned over heavily and the old "strong Creativity/Shooting" read is dated.
  **Check `rep["strength"]`'s `n_us` per unit before quoting a unit mean** — our Midfield frame has
  come back with as few as 2 rated players against an opponent's 11, which makes both the unit
  quality figure and its attribute means a two-man sample. Say so rather than quoting a 40-point
  gap as if it were solid.

## Inputs to establish first
- **Opponent** — `matches = scout.resolve_club(st, name_or_tid)`. Diacritic-insensitive; ranks
  an exact name, then initials ("OB", "FCK", "AGF"), then a name starting with the query, then a
  later word, then a substring; within a tier domestic clubs first, then squad size, so a
  **Reserves** side sorts below its first team. Take `matches.iloc[0]` unless it's genuinely
  ambiguous (several domestic clubs in the same `tier`), in which case list them and ask.
- **Manager, formation & Style — read automatically, no ask required.** `rep["manager"]`
  (`opponent_manager()`/`mart.club_managers`, one row per club per snapshot) names who is in
  charge and gives his **preferred / attacking / defensive formation** plus a derived **Style**
  (Attacking / Normal / Defensive, `attacking_intent` banded — confirmed 7/7 on a
  predict-then-check run spanning both edges, `docs/record-expansion.md` §F). This is
  now the BASELINE for the report: open with the preferred shape and Style, and use the
  attacking/defensive variants for the one read this report has ever had on **what he changes to
  when the game state changes** — the shape he shifts into chasing a goal, and the one he shuts
  up shop in. Quote the Style label as read, not hedged. One caveat: it is the manager's
  *standing* preference, not a guarantee of today's XI (a manager still departs from habit for a
  big occasion, and a club WE manage correctly returns no row/`None`) — so it is a starting point
  to state plainly, not a promise, and asking the user is now optional refinement rather than a
  prerequisite: don't block the report on it.
- **If the user has it, an in-game scout screen still refines the above — ask for it, don't
  require it.** It answers something the manager record structurally cannot: this week's actual
  team news (injuries, suspensions, who's actually fit), not the manager's general habit.
  **Best artefact: their `Club Squad → Selection` screen (the `Pkd` column)** — the opposition
  manager's *actual* current selection with position badges, plus suspensions, injuries, condition %,
  form and season apps. On its first use it disagreed with the same fixture's Predicted XI in 2 of 11
  slots and revealed both first-choice full-backs unavailable, inverting the flank plan. Season apps
  also settle "is this name new?" outright. Failing that, **Next Match → Predicted XI** names eleven
  players and their slots.
  **Trust the Predicted XI for neither shape nor names, and COUNT SLOTS, NOT NAMES** — this is
  exactly why it is no longer a required input: across eleven
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
  - **The rule applies to the THREAT LIST too, and that is where it was missed.** Against Vejle the
    briefing led on Eiting ("press him and never take it off", 95.9 league Level) and Gyökeres (the
    stated reason the centre-back pair needed pace cover) — **both were benched**, and Remberg (39.3)
    and Ponce (35.7) started instead. The flank call was hedged; the threat section was not, so the
    most-emphasised half of the report aimed at men who never played. For the top two threats, always
    add the one-line fallback: *if X doesn't start, the threat becomes Y*.
  - **A thin H2H record is not a thin threat — profile the striker who actually STARTS.** FCK at home
    (2027-05-22): the briefing wrote "the striker is not the danger" off Babacar (Pace 6) and Fenger's
    2 apps / 0 goals against us. Fenger started as a pressing forward fed by their AMC and went 8 shots,
    5 on target, 2 goals, rated 10 in a 2-3. `h2h_players` ranks who HAS hurt us; it says nothing about
    a man who has barely played us. When the starting XI is known, read the starting No. 9's
    Shooting/Stamina and who supplies him before ruling the central route out.
  - **Ask for the `Club Squad → Selection` (`Pkd`) screen — this is now GRADED, not promising.** That
    screen would have shown Eiting at S5 and Gyökeres at S7 and inverted the threat section before
    kickoff. It is the single highest-value artefact to request.
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
Before pulling fresh data: `s = scout.load_scouts(); s = s[s.opponent_tid == OPP]` (or
`uv run python fmq.py scouts --opp <team>`). If a saved report exists for this opponent, open the briefing with
what it said (index gap, method planned, any note) and whether it still holds — squad, tactic and
even our own personnel may have moved since. If nothing's saved, say so and proceed; this scout
will be the first entry once you save it.

**Re-save a scout when its reasoning changes, not just when the fixture does.** `scout.save_scout`
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
  `m = scout.match_history(st)` filtered to the season, then shots / shots-on-target / conversion /
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
- **Write the grading with `scout.grade_scout(opp_tid, result_note=..., result="W 2-0 (H)",
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
- **`app_config.default_method` still reads `frem_attacking_ss`** (`seeds/config_bundle.json`),
  which is no longer what we play. `scout_report` ignores it in favour of the career's
  `rating_method`; don't describe `frem_attacking_ss` as "our tactic".

**Rate the slot, not the player.** The same winger can be a 92 at MR and an 85 at AMR, and a deep
left slot has flipped which of two candidates was correct by 25 percentile points. If the manager
shares a formation screen, rate that XI at the slots each player really occupies
(`scout.effective_table(st, method)` filtered to `name` + `position`).

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
- **Their style** (`rep["manager"]["style"]`, refined by the user's scout if they have one) → a
  deep block is a width-and-patience problem; a side that tries to play out is a pressing
  opportunity keyed to their weakest build-up player.
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

**Before proposing a personnel change, split that player's OWN record BY POSITION.** Attributes say
what a player could do; the match record says what he actually does in a given slot, and the two
disagree often enough to flip a recommendation. It is a cheap query — dedup at match level first
(one anchor per `(date, opponent_tid)`, newest snapshot first, `team_tid = 346`; see trap 4 in
[`player-analysis-methods`](../../../docs/agent-context/player-analysis-methods.md), because a raw
`SUM` multiplies every total by 1–5×) then group by `season, position`. Two live findings it produced
in one sitting:
- **Chukwuani**: at MC in 2025, 27 apps, rating 7.33, 6 goals, 5 assists. At AMC in 2026, 8 apps,
  rating 6.75, **2.25 shots a game at 0.38 on target, zero goals, zero assists**. The manager's read
  — "he liked being the main creator" — was exactly right, and the split also identified him as one
  of the wasteful shooters behind a bad shots-to-goals night.
- **Larsen**: 2.78 mistakes per game at DR over 9 apps, against 2.00 at DC and 1.00 at DMC. A
  4-mistake match was not an outlier but the top of his normal distribution there.
**And check the position before blaming the player.** Across 194 matches our right backs average
**2.38** mistakes a game to the left backs' **1.55** — stable in ALL FIVE seasons, across four
divisions and ~18 players, and **2.36 with the current incumbent removed**. So "our right back is
error-prone" is a fact about the slot, and swapping the man does not fix it (his replacement reads
2.44). Swap for quality; do not promise an error reduction the data does not support.
**One bad game is not a pattern** — the same sitting had a player rated 4 immediately after an 8 with
2 assists. Move on a split, not on a scoreline.
**But a position split answers "how does he rate there", not "can he do THIS job".** Against FCK
(2027-05-22) the briefing withdrew "Tjørnelund screens their 10" because his DMC rating split was poor
(6.20 over 5 starts). He started at MC, Mensah ran the first half (39 passes, 1 assist, Fenger fed
twice) and we were 0-2 down; Tjørnelund moved to DMC at half-time and the game turned. Against a
creative AMC behind a striker, guarantee a screen in front of the back four from kick-off, and do not
talk a matchup assignment away with a small rating split.
**A DM's rating is not comparable to anyone else's.** DMs average 6.58 to a central midfielder's
7.07 for the same performance (within-player gap +0.48), and the rating rewards a DM's key passes,
not his screening. A DM averaging 6.5 is par, 6.7+ is playing well — see
[`match-rating-position-bias`](../../../docs/agent-context/match-rating-position-bias.md).
Note whose screen a role label belongs to (IW / PF / Poacher / AF / AP) every time, or a briefing
will attribute the opponent's roles to us.

### Validated pull snippet + gotchas
This whole path is `duckdb` + `pandas` — `uv sync` (no extras) is enough. `store.open_store()`
reads the career's published store from R2 (cached at `~/.cache/fmm-stats/`, re-checked every 10
min) and prints which snapshot it opened; pass `db="fm-frem.duckdb"` (or set `$FM_DUCKDB`) to read
a local build instead. It copies a locked store to a temp file itself. Run via a **heredoc /
script file**, not `python -c` (the escaping bites).

```python
from fmstats import scout, store

st = store.open_store()                       # career from $FM_CAREER, else frem
# st.con (read-only duckdb connection), st.career (.managed_tid, .reserve_tid, .rating_method),
# st.season / st.phase / st.phase_date / st.label — the latest snapshot

OPP = int(scout.resolve_club(st, "OB").iloc[0]["tid"])   # exact > initials > prefix > substring
rep = scout.scout_report(st, OPP)             # rated with st.career.rating_method (frem_minmax_4231)
# rep = {opp, season, phase, method, coverage, overall, strength, matchups, units, unit_attrs,
#        key_players, h2h, h2h_players, flags, manager} — DataFrames for strength/matchups/units/
#        unit_attrs/key_players/h2h_players.
#   overall/strength carry BOTH ratings: us/them (+ us_pctile/them_pctile) is our tactic's
#     Fit; us_quality/them_quality is tactic-agnostic Level %ile. Use *_quality for "how
#     good are they", *_pctile for "how would this suit OUR system".
#   matchups is the face-off pairing: rows "Our attack vs their defense" / "Their attack vs
#     our defense" / "Midfield (contested)", each with us_quality/them_quality/edge (Level
#     %ile) and us_fit/them_fit (pos_index) alongside.
#   key_players is ranked by Level %ile — quality, not output. h2h_players is output: goals,
#     assists, key_passes, shots, on_target, avg_rating, last_played, still_there, per player,
#     in matches against us.
#   rep["h2h"] has played/w/d/l/gf/ga/ppg, per-venue "H"/"A" records, and "matches" — the
#     per-match DataFrame (date, venue, gf, ga, result, our_/opp_ shots, shots_on_target,
#     passes, passes_completed, tackles_won, interceptions).

prior = scout.load_scouts()
prior = prior[prior.opponent_tid == OPP] if not prior.empty else prior       # calibration check
# there may be SEVERAL rows per opponent — one per fixture. `fixture`, `venue` and
# `saved_at` say which is which; `result_note` marks the ones already played and graded.

# ... write the report from rep — formation/style default to rep["manager"], override with
# whatever fresher in-game scout info the user offers — then apply the tactic step ...

FIXTURE = "2026-04-20"                        # the match date off the Next Match screen
mgr = rep.get("manager") or {}
rec = scout.save_scout(st, rep, venue="H",
                       formation=mgr.get("formation_preferred", "unknown"),
                       style=mgr.get("style", "unknown"),
                       note="short plan summary", fixture=FIXTURE)
# ALWAYS pass fixture — without it the two meetings of a season share one key and the second
# replaces the first. Then report what the write actually did:
if rec["_sync"] != "synced":                  # local-only (no remote) / sync-failed (push died)
    print(f"scout saved LOCALLY ONLY ({rec['_sync']}) — tell the user")
if rec.get("_collision"):                     # replaced an undiscriminated scout of another venue
    print("that overwrote a scout of the other leg")

# AFTER THE MATCH, when the user posts the FT stats — never save_scout with the grading in
# `note`, that destroys the briefing you are grading:
scout.grade_scout(OPP, result_note="what held, what didn't, and why",
                  result="W 2-0 (H)", fixture=FIXTURE)
```

Gotchas that still cost time if you bypass `scout_report` and reach for raw SQL yourself:
- **Attribute columns are Capitalised** in `club_attributes`/`squad_frame` — a lowercase
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
- **The MIRROR of that trap: a spell filter at a SEASON-BOUNDARY snapshot DROPS players who are
  genuinely ours.** A raw `club_tid` keeps players who have left; the spell check loses players who
  are still here, because a loan with a 30 June expiry looks lapsed at a 2 July snapshot and the
  renewal falls after it. Confirmed: at `2026-07-02` both Chukwuani and Gülstorff had `loan_in`
  spells ending `2026-06-30`, so `mart.snapshot_squad` excluded them — and a month later they
  started against Vejle and were two of our three best performers (Chukwuani rated 8 with 2 assists;
  Gülstorff 8 tackles from 8). **Reconcile every squad pull against `mart.clubs.squad_size` and say
  so if they disagree** — the tell was sitting in the briefing's own output and went unread:
  `squad_size` said **42**, the spell-filtered pull returned **25**. A shortfall that large at a July
  snapshot means expired-loan exclusions, and the fix is to check `mart.player_spells` for loans
  ending at the season boundary rather than trusting either filter blindly.
- Cross-snapshot per-player aggregates (e.g. "has this player grown since we last played them")
  must key on `person_id`, not `tid` — FM recycles retired players' slots.
- opponent `name` **resolves for every club** (the ETL id-resolver) — `squad_key_players` and
  `squad_frame` already carry it; you shouldn't need to re-join `staging.players` for it.

## No local store at all
Nothing to do: `store.open_store()` already reads the published full store from R2. Only if rclone
or the remote isn't configured does it fail — then hand off to
[`scout-from-site`](../scout-from-site/SKILL.md), which is built for exactly that (the deployed
site's JSON, or the mart via `ATTACH` if arbitrary SQL is genuinely needed — see
`site/AGENTS.md`'s cookbook). It carries its own, narrower set of caveats (no per-match H2H beyond
`matches.json`, ability *percentiles* not ranks for an opponent) — don't quietly deliver that
thinner report under this skill's name.

## Hard limitations — state them in the report
- **The exact XI on the day is NOT in the save** — `rep["manager"]` gives his standing
  preferred/attacking/defensive formation and Style, which is now the baseline, but it is a
  preference, not a guarantee. A fresher in-game scout screen from the user narrows this further
  (this week's team news) but is optional, not required.
- **Opponent player names ARE resolved** (the ETL runs the id-resolver — every club is named, not
  just ours) → **use real names** alongside position + percentile.
- **Opponent attributes are model estimates (±1)** for technical/mental (Pace/physical are exact;
  check the `*_est` flags in `mart.player_snapshots` if you need to know which). Treat as
  directional, not precise.
- **Squad status and loan flags are unreliable** (`staging.players.loaned_in`/`.loaned_out` — set
  once, never cleared). `scout_report`'s squad frame is snapshot-club-tid based, not flag based, so
  this mainly bites if you're tempted to assert loan status in prose — don't, from the flags alone.
- League-membership counts over-report (resolved across labels) — ignore for a single scout.
- **Check how stale the snapshot is against the fixture date, and say so.** `st.phase_date`
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
- **No-data opponents:** `rep["coverage"]["partial"]` is `True` (and `rep["flags"][0]` says so, with
  the squad-derived flags withheld — see "The engine already exists")
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
every claim on `rep`; don't invent numbers.

**Two sections are load-bearing and are never dropped for brevity, even when thin:**
- **The prior-scout line in the Verdict.** Check the log (see "calibration" above) and say what we
  said last time and whether it still holds — or that this is the first scout of them. That pairing
  is the only thing that makes the log calibration rather than a pile of old opinions.
- **The Head-to-head table.** Keep it even when it is two old fixtures; the manager reads it. Say
  plainly how much weight it carries (a two-season-old meeting after both squads turned over is
  near-worthless as evidence, and a promotion or relegation in between is worth naming), and still
  pull the one pattern that survives — home vs away, clinical vs wasteful, out-shot or not.

```markdown
# 📋 Opposition briefing — <Club> (<H or A> this week)
*<Manager name> — preferred **<formation>**, **<Style>** (shifts to <attacking formation> chasing
a goal, <defensive formation> protecting one). <If the user supplied a fresher in-game scout read
that differs, say so and which one this briefing follows.> Caveats: opponent attributes are model
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
- **<Name> (<POS>)** — <pick the men from BOTH lists: `rep["h2h_players"]` (still_there, with
  goals/assists/key passes against us — lead with that record when he has one) and
  `rep["key_players"]` (Level %ile + `top_attrs`). A proven producer against us outranks a
  higher-rated player who has never hurt us. Level %ile, not Fit — see "The engine already exists"
  above. Then the consequence: who picks him up, which lever contains him, what he punishes if
  ignored.>
- <plus the non-player threats, still with their numbers: the "Their attack vs our defense" row of
  `rep["matchups"]`, the direct/set-piece route and the aerial group that delivers it, shot volume
  from the H2H, and anything in `rep["flags"]`.>
- <their BENCH, when it holds a counter-profile to our plan or a player stronger than a predicted
  starter — this is where the briefing has been caught out most often.>

## Game plan
<This section carries WHERE WE WIN inside it — there is no separate "Where we win" heading. That
split made the report state an edge in one section and the instruction acting on it three sections
later; folding them ties the why to the what, which is how the manager reads it. So **every bullet
below names the number or duel that justifies it**, and the edges to work from are the "Our attack
vs their defense" row of `rep["matchups"]` (do we have the quality edge going forward?), their
Defense unit's weak attributes in `rep["unit_attrs"]`, and the space their shape concedes.
**Go per-player, not per-unit** — name the individual defender who is the soft spot and say which
KIND he is: a **Positioning** weakness is a run-at-him weakness, an **Aerial/Strength** weakness is
a duel-and-deliver one, and they are usually different players on opposite flanks, so a unit mean
hides both. Read only the columns the role is actually scored on — see "Reading attributes" above.>
- **Shape: standard 4-2-3-1.** <How it sits against theirs — who screens whom, and which flank or
  channel we attack, with the edge that makes it the right one. Prefer our real edges
  (width/pace/creativity) over their strengths (aerial/duels).>
- **Variation:** <ONLY if the data triggers one, in the manager's own vocabulary — a forward wing
  dropping AM→M for cover, the 10 dropping to a 6 against a dangerous opposing AMC, a WB becoming an
  IWB, back four almost always. Name the trigger with its number. If nothing triggers one, write
  "none needed — standard 4-2-3-1" and move on; do not list the menu. A variation you argued AGAINST
  is worth one line when the reason is a finding (e.g. their AMC is their weakest starter, so the
  second pivot buys nothing) — that is analysis, not a menu item.>
- **Settings:** <Mentality / Line / Tempo / Width / Press / Final third / Passing — each justified
  from a duel or a number, not from the preset. Say which of Line and Press you mean, every time.>
- **Personnel:** <the centre-back pairing and why, the flank to load with the gap that justifies it
  (name the pace/positioning numbers on both sides), the in-behind runner, who takes the danger man.>
- **Defend:** <funnel wide/deny centre; screen the direct ball; man-mark aerial threats on set pieces.>
- **Cutting edge / set pieces:** <if the H2H shows control-without-chances, stress chance quality;
  our aerial edge if any — checking BOTH sides of the duel before recommending OR ruling out a
  route, and saying where to deliver rather than just whether to; who to track after our set pieces.>

**One-line to the gaffer:** *<punchy, quotable summary of the plan.>*

---
Eyeball it: `uv run python fmq.py scout <Club> --no-save` prints the same numbers;
`fmq.py output --club <Club> --vs Frem` who has produced against us, `fmq.py matches --opp <Club>`
the head-to-head. This report has been saved to the scout log (`uv run python fmq.py scouts --opp
<Club>` to review it alongside past reads, `fmq.py grade <Club> --fixture <date> ...` after the match).
```

Keep it decision-useful and honest about the estimate limitations (attributes ±1; tactics not in
the save). One opponent at a time (opponent tactics vary, so a whole-season sweep would need each
team's in-game scout report as input — see [`season-outlook`](../season-outlook/SKILL.md) for the
group-level version of this, which hands off to this skill per-fixture). Offer at the end to scout
the next opponent.
