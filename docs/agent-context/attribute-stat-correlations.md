# What attributes actually make a player DO things

**Computed 2026-09-11 on the `frem-2026-03-22` store.** Four cuts, because a single one has twice
produced a claim that did not survive contact with a second:

| cut | what it is | n (player-seasons) |
|---|---|---|
| **US all divisions** | our players, ≥450 mins, every competition pooled | 104 |
| **US Superliga** | our players, ≥360 mins, top flight only | 41 |
| **US lower divs** | our players, ≥360 mins, 2./3. Division + NordicBet | 44 |
| **OPPONENTS** | players we have faced, ≥180 mins | 287 |

```bash
uv run python scripts/attribute_stat_correlations.py --competition '%Superliga%' --min-minutes 360
uv run python scripts/attribute_stat_correlations.py --who opponents --min-minutes 180
```

Or explore it interactively in **[The Attribute Lab](https://claude.ai/code/artifact/bae40c5f-a50a-485b-b4be-3d2735e2a5f5)**,
which also carries a workbench for rebuilding a role's attribute weights from this evidence
(`scripts/export_attribute_lab.py` builds its data; `scripts/import_weight_set.py` brings a
weight-set back into the store).

**All 23 attributes are covered as of 2026-09-12**, and there is now a GK unit. Two rules make
that safe; figures below that predate the re-run do not reflect them.

### Blank cells are a feature: the sd floor

A predictor with almost no variance does not yield a reassuring zero — one stray value drives the
coefficient. Standard deviation within outfield units:

| | min | median | max |
|---|---|---|---|
| The 18 real attributes | 1.85 | 2.64 | 3.64 |
| The 5 keeper attributes | 0.56 | 0.72 | 1.14 |

No overlap: outfielders average 1.5–2.3 on Handling/Reflexes/Throwing against a real keeper's
10–12. So `attribute_stat_correlations.py` **blanks any cell whose predictor varies by less than
`MIN_SD = 1.5` in that unit**, blanks any cell whose *outcome* never varies (keepers score no
goals), and pools only over the units where the attribute does vary. Without the last rule a
keeper attribute pools outfielders' 1–2 jitter with keepers' real 10–12 and reports a coefficient
that is nothing but the gap between the two groups.

This is the **restriction-of-range** caveat below, finally enforced in code rather than left to
whoever is reading. If a future squad's midfielders all sit between Shooting 8 and 12, that cell
blanks itself.

### Unit averages hide opposite effects — read the position too

The three outfield units are coarse, and inside them attributes can point opposite ways. Pace
against match rating, league-wide:

| | unit says | positions inside it |
|---|---|---|
| **Attack** | +0.21 | ST **+0.49** · AML +0.32 · AMR −0.24 · AMC **−0.19** |
| **Defence** | +0.06 | DL +0.22 · DR +0.26 · **DC +0.04 (n=111)** |

The Defence row is the clearest: 111 of its ~199 player-seasons are centre-backs, so the column is
effectively "what pace does for a centre-back" — nothing — and the full-backs' real effect never
appears. Same trap on interceptions, where **DR reads +0.40 and the Defence unit reads +0.07**.

So the export now emits **per-position correlations alongside per-unit ones**, wherever the cut has
`MIN_N` players at that position. Availability is uneven and the export states it per cut:

| cut | positions with n ≥ 12 |
|---|---|
| League · all | DC 111 · GK 59 · MC 57 · DR 44 · DL 43 · ST 40 · AMC 32 · DMC 29 · AML 25 · AMR 19 |
| League · Superliga | DC 38 · GK 22 · DMC 15 · DR 14 · MC 14 |
| Us · all | DC 20 · MC 20 · DR 13 |
| Us · Superliga | none |

**A position view is the sharpest and the thinnest read at once.** Twenty to a hundred
player-seasons is a direction, not a measurement, and usually only one cut can see it at all — so
nothing corroborates it. Check it against the unit before acting.

### Pace: the worked example

Pace is where this matters most, because the unit view makes it look inert. By position, against
match rating, and again controlling for the game's own ability model (`level_league`, i.e. *among
players of the same Level %ile at that position*):

| position | n | raw | controlled for ability |
|---|---|---|---|
| **ST** | 39 | **+0.51** | **+0.44** |
| AML | 25 | +0.32 | +0.36 |
| DR | 43 | +0.30 | +0.33 |
| DL | 41 | +0.22 | +0.21 |
| MC | 58 | +0.18 | +0.16 |
| DC | 111 | +0.06 | +0.07 |
| GK | 59 | −0.01 | −0.01 |
| **AMC** | 31 | −0.19 | **−0.16** |

It survives the control, so it is not a proxy for "good player". And it is emphatically *not* good
everywhere — at AMC, who receives in front of the defence with no space to run into, it is
negative.

**Why the community says pace is king.** Against `level_league` within position, Pace averages
**−0.01** across positions while Technique averages +0.29, Passing +0.22 and Decisions +0.16. The
game's ability model barely charges CA for pace — so a pacy striker delivers performance the model
does not price. That also means **our own Level %ile scouting understates pacy strikers.**

**And it is the best evidence that off-the-ball work is real but invisible here.** Pace barely
touches the counting stats (goals +0.21 in attack, shots on target ~0, key passes −0.01) yet
predicts a striker's match rating at +0.51. That gap is the off-the-ball running: no stat records
it, and rating is the only measure that sees it.

### The GK unit, and what it cannot tell you

GK player-seasons: **league/all 59, league/Superliga 22, us/all 7, us/Superliga 2** — usable in
the league cuts, not in ours. But a keeper's match row holds `passA ≈ 21.7`, `intercept ≈ 0.47`
and essentially nothing else: **no saves, no clean sheets, no goals conceded**. So the unit
answers "does Kicking predict his distribution" and "what predicts his match rating", and
**nothing about shot-stopping**. One result worth having already: **Kicking → pass completion %
is −0.24 for keepers** — the better kickers get asked to hit longer passes, which complete less
often.

Method and traps: the [`attribute-profiles`](../../.claude/skills/attribute-profiles/SKILL.md)
skill. One row per (player, season) with **that season's** attributes; correlations computed
**inside a positional unit**; the figures below are unit-demeaned pools.

## Why the OPPONENTS cut is the important one

Every "us" figure is our players under **our** instructions — the single biggest caveat on this
whole exercise. The opponents cut is the same analysis on players from **57 different clubs under
57 managers**, so an effect that appears there is a property of the game rather than of
`frem_attacking_ss`. It is the out-of-sample check.

**Its coefficients are systematically smaller and that is expected, not a weaker result.** We only
see an opponent in the 2-4 games he plays us, so each observation is a few matches of noise, which
attenuates every correlation toward zero. **Compare signs and rank order with the "us" cuts, never
magnitudes.**

## What replicates in all four cuts — trust these

| Effect | US all | US SL | US low | OPP |
|---|---|---|---|---|
| **Aerial → headers won** | **.70** | **.64** | **.79** | **.52** |
| Strength → headers won | .55 | .64 | .44 | .29 |
| **Aerial → header win %** | .66 | .67 | .64 | .32 |
| **Shooting → shots on target** | **.61** | **.81** | .41 | **.32** |
| **Shooting → goals** | .45 | .60 | .32 | .33 |
| Aerial → dribbles | −.59 | −.57 | −.54 | −.24 |
| Pace / Dribbling / Movement → dribbles | +.49/.38/.31 | +.49/.47/.44 | +.46/.41/.49 | +.17/.21/.21 |
| **Positioning → interceptions** | .36 | .22 | .45 | .20 |
| **Tackling → interceptions** | .30 | .47 | .19 | .14 |
| Strength → key passes | −.38 | −.39 | −.35 | −.03 |

**Two solid negatives, confirmed on an independent sample:**

- **Nothing predicts tackle success %.** The largest coefficient anywhere is Passing −.41 in the
  Superliga (n=41) and it is ~0 in the other three cuts.
- **Nothing predicts cross completion %.** Same story.

Do not build a selection argument on either ratio.

## What does NOT replicate — do not act on these

| | US all | US SL | US low | OPP |
|---|---|---|---|---|
| **Aggression → interceptions** | +.09 | **−.32** | **+.34** | −.01 |
| Aggression → SOT % | .22 | .55 | .07 | .05 |
| Passing → key passes | .27 | .65 | .16 | .07 |

**Aggression on interceptions swings from −.32 to +.34 depending on the cut.** An earlier version
of this file reported it as "+0.45 in the lower divisions, −0.06 in the Superliga" and drew a story
about bullying the ball off lower-league midfields. The direction of the division contrast held
when the position bucketing was corrected, but the coefficients moved by 0.3 and the pooled figure
went from +.27 to +.09. **The honest read is that Aggression has no reliable effect on
interceptions.** Positioning and Tackling do, in all four cuts. That is the finding.

## Practical conclusions

1. **Shooting is the attribute to recruit for.** The only one that runs the whole chain — shots,
   shots on target, goals — in every cut including out-of-sample.
2. **Aerial is the most reliably measurable attribute in the game**, and it is a *role label* as
   much as a skill: strongly positive for headers, strongly negative for dribbles, crosses and
   assists. Read a big Aerial coefficient as "this is a centre-back or a target man" first.
3. **Interceptions are Positioning + Tackling, and forwards cannot supply them** — 0.5–1.4 per 90
   against 6–7 for centre-backs. Press intensity is a team instruction, not a selection.
4. **`SOT %` is nearly attribute-free while `shots on target` is attribute-dominated.** *Who shoots*
   is a player property; *how well the team shoots* is `Work Into Box`. See
   [`scoring-and-shot-quality`](scoring-and-shot-quality.md).

## Our XI's attributes do NOT predict what we concede

Match-level test (n=166 with a resolvable starting XI, 54 in the Superliga): mean attributes of our
starting outfield ten against opponent shots, shots on target and goals.

- **Pooled across divisions, every attribute correlates POSITIVELY with shots conceded** (.14 to
  .33). That is not a finding — it is the division confound. Our squad's attributes rose as we
  climbed, and so did the quality of who we faced.
- **Within the Superliga alone it collapses**: the largest |r| is .29 (Stamina) and nothing else
  clears .21. Tackling (−.19 on SOT conceded, −.18 on goals) and Positioning (−.13 on goals) point
  the sensible way but are far too small at n=54 to act on.

**What we concede is about the opponent and our instructions, not about which of our players
start.** Consistent with everything else here: the defensive dials are team settings.

## The first weighting this changed: `frem_attacking_ss` / ST

The point of the file. Scored **within role** against what strikers actually produced (league
player-seasons, n=40, correlation of the weighted attribute total with goals):

| weight-set | r vs goals |
|---|---|
| the old ST weights | **0.351** |
| flat — every attribute 1 | 0.411 |
| the new ST weights | **0.484** |
| Shooting alone | 0.469 |

⚠️ **Those four figures are POOLED across divisions**, which the next section shows inflates them
by roughly 60%. The ordering survives the control; the magnitudes do not. Quote the stratified
table below instead.

The old set was **worse than not weighting at all**, because it came from forum consensus rather
than measurement: Aggression 4, Stamina 4, Movement 4 and Shooting only 3. Shooting is the one
attribute that predicts shots, shots on target and goals in every cut. Nearly all of the gain is
Shooting — the rest of the set is tidy-up rather than discovery, which is worth remembering before
the next rewrite.

New set (`seeds/role_weights.csv`): shooting 4; aerial, decisions, pace, strength 3; agility,
movement, technique 2; **aggression, passing, stamina, teamwork dropped to baseline 1**.

Two caveats recorded deliberately:
- **Movement is held at 2 on the manager's judgement, not the data.** Measured it contributes
  nothing (sd 1.66, range 8-15 across our strikers; removing it costs 0.007). Off-the-ball work is
  the one thing the match stats cannot see, so this is a reasonable place to keep a thumb on the
  scale — but it is a belief, not a measurement, and should be labelled that way.
- **Pace at 3 is a position-specific call.** Pace correlates +0.51 with a striker's goals (+0.44
  controlled) but +0.06 for centre-backs and −0.19 at AMC, and it barely moves Level %ile (−0.01
  against Technique's +0.29) — so the game charges little CA for it and our Level-%ile scouting
  *understates* pacy strikers. Do not generalise the 3 to other roles without measuring them.

It re-ranked our strikers immediately. Our actual current squad at ST (`mart.squad_current`, not
a raw `club_tid` filter — which pollutes the list with departed loanees):

| | old | new |
|---|---|---|
| 1 | Nordberg 477.8 | **Ementa 409** |
| 2 | Ementa 476.0 | Olesen 403 |
| 3 | Olesen 459.0 | Nordberg 390 |

Ementa up one, Nordberg down two: Shooting 11 against Ementa's 15, and the Aggression 15 the old
set paid 4 for now counts once. His Pace 16 (now weighted 3, against Ementa's 12) wins some of it
back — it is not enough.

## The division confound eats most of the signal — control for it

**Measured 2026-09-12, and it qualifies every pooled number in this file.** The cuts above pool
four divisions. Our club climbed from the 3. Division to the Superliga, so a player-season's
per-90 output and his attributes BOTH rise with the standard he was playing in, and a pooled
correlation credits the attribute for the promotion. The file already said this about what we
concede; it is just as true of what we produce.

`scripts/derive_weight_set.py` therefore computes every figure inside a **(position, division)
stratum** of 8+ rows — the division a player-season mostly belongs to, by minutes. Restricting to
the Superliga instead would be cleaner and would leave 14-38 rows a position, which is no sample;
stratifying removes the same confound and keeps every row.

What it costs, on the ST "finish" target (shots on target + goals, n=39):

| reading | old ST weights | flat | new ST weights | Shooting alone |
|---|---|---|---|---|
| pooled across divisions | +0.442 | +0.499 | **+0.565** | +0.553 |
| **stratified by division** | +0.160 | +0.204 | **+0.238** | +0.222 |
| Superliga only, 90+ mins (n=34) | +0.353 | +0.337 | **+0.387** | +0.298 |

**Roughly 60% of the apparent effect was the league, not the player.** Two things survive, and they
are the two that matter:

- **The ordering is stable in every reading** — new > flat > old, and Shooting is the top attribute
  for a striker whichever way it is cut. The ST rewrite stands; only the SIZE of its advantage was
  overstated. Quote the stratified figures from now on.
- **Weighting matters MORE once the confound is removed, not less.** Flat is what the confound
  flatters: a good player in a good league scores well on every attribute at once. At CM the
  derived set beats flat by +0.146 pooled and **+0.176** stratified; at RB by +0.220 and +0.203.
  Removing the confound shrinks flat's score further than it shrinks a targeted one.

Per-cell z-scoring versus one pooled sd makes almost no difference (ST +0.265 vs +0.260), so the
collapse is the control itself and not noise from small-cell standard deviations.

### A flat role was unrepresentable, and it silently deleted positions

Shipping "this role is flat" as *no rows in `role_weights`* looked natural — `COALESCE(weight, 1)`
already defaults an unlisted attribute to 1 — but both rating views built their method x role list
as `SELECT DISTINCT method, role FROM role_weights`. A role with no rows therefore did not exist,
and **every position mapping to it vanished from the ratings**: the first derived pair shipped with
AML and AMR flat, and the squad's 13 AMLs and 10 AMRs had no fit rows at all, so the depth chart
read "no player rated here" for two positions we are deep in.

Fixed in both `fmstats/mart.py` (`PLAYER_ROLE_RATINGS`) and `load_duckdb.py`
(`v_player_ratings`) — `combos` is now every method x every role from `position_role_map`. Existing
methods all carry all ten roles, so the change is a no-op for them; `git diff site/api` after an
export is the check.

### Re-seeding silently doubled a new method's weights

`--refresh-only` re-seeds `seeds/role_weights.csv` (added the same day, so that editing the CSV
reaches an existing store). But `seed_role_weights` deleted a **hardcoded list of seven method
names** and then inserted the whole file, so a method added to the CSV but not to that list gained
a duplicate row set on every refresh — and the rating view, a LEFT JOIN with a SUM, counted its
weights twice. Two refreshes took a centre-back from 431 to 777 and reordered the depth chart,
which is how it was caught: the second run of a best-XI query disagreed with the first.

It now deletes exactly the methods the CSV names (`SELECT DISTINCT method FROM read_csv_auto`), so
the list cannot go stale again. Verified idempotent over two consecutive refreshes: 743 rows, zero
duplicates. **If ratings ever look inflated, check `staging.role_weights` for duplicate
(method, role, attribute) rows first** — the symptom is a plausible-looking number, not an error.

### Determinism: the position pick used to drift between runs

6,148 (person, season) pairs are equally familiar at two positions in the same snapshot. The
primary-position query broke those ties with nothing stable, so DuckDB's parallel `ROW_NUMBER`
resolved them differently run to run: **n moved (CB 111 or 112, ST 39 or 40) and coefficients moved
in the second decimal with nothing about the data changing.** `build()` now appends `"position"` to
the ORDER BY. Alphabetical is arbitrary; the point is that it is the same arbitrary choice every
time, so a figure quoted here can be reproduced. Figures computed before 2026-09-12 may differ by
±1 row.

## Two failure modes this file has already hit

**Restriction of range — a zero can mean "we have never had one".** Shooting drives midfielders'
shots (.72) and shots on target (.76) but not their goals (.06). Every midfielder we have fielded
sits between Shooting 8 and 12, so there is no variance to detect an effect in. The cost is
visible directly: Garly (Shooting 9) has **37 Superliga shots and 0 goals in 4,089 minutes**, and
Chukwuani (9) converts 12% of his shots against Ementa's 21% and Jakobsen's (17) 26%. Check the
spread within the unit before reading a near-zero as "does not matter".

**Position bucketing moves coefficients at low n.** Switching from `match_player_facts.unit` (which
records where a player lined up in one arbitrarily-chosen match) to primary position from
`mart.player_position_levels` moved the Superliga Positioning-on-interceptions figure from .65 to
.22. The current script uses `player_position_levels`, which is stable and covers every club. Treat
any single-cut coefficient at n≈40 as indicative only.

## Re-run once a season

The sample grows ~20 player-seasons a year (ours) and ~90 (opponents). Re-run after each season-end
import, keep the dated tables, and expect large coefficients on small n to shrink toward the middle.
A finding that survives three seasons *and* the opponents cut is worth building a recruitment rule on.

## The attribute-level audit (2026-09-12) — a block can beat flat while half its lines are noise

The first run of `scripts/derive_weight_set.py` shipped two derived weight-sets in which **only
three of twenty blocks were actually derived**. Everything else was either flat or BORROWED from a
hand-built method, because `choose()` compares whole blocks on their total score and then ships the
winner verbatim. Nothing ever checked the individual attributes in a borrowed block against the
evidence, and the manager spotted the consequence by eye before any of it was measured.

What the borrowed blocks were asserting, against the measured partial correlation in that same
(position, division) stratified cell:

| set | role | the line | measured | verdict |
|---|---|---|---|---|
| 4411 | AML | Shooting **4** | **−0.32** | wrong sign, at *key*, on a defend-first wide midfielder |
| 4411 | AMC | Dribbling **3** | **−0.32** | wrong sign |
| 4411 | DM | Shooting **4** | +0.09 | under the floor that earns a 2 |
| 4411 | LB | Pace **4** / Positioning **4** / Tackling **4** | −0.07 / +0.06 / +0.02 | all three *key* attributes at nothing |
| 4231 | CB | Positioning **4** | −0.08 | wrong sign, at *key* |
| 4231 | RB | Crossing **4** / Movement **4** | +0.07 / +0.03 | nothing |
| 4231 | AMC | Passing **4**, while Agility sat at **2** | −0.03, and Agility **+0.52** | inverted |

Each of those blocks genuinely beat flat — `black_hawk`'s 4411 AML scores +0.100 against flat's
+0.041 and wins 97% of bootstraps. **It was beating flat on Passing (+0.32) while five other lines
contributed noise.** A block-level verdict does not license the lines inside it, and a min-max set
whose selling point is "every weight is evidence" cannot carry lines like these.

`audit_block()` now filters every block, derived or borrowed, against the same bands the derivation
uses: an attribute keeps its place only if its partial clears the 0.10 floor, and it is re-banded to
what it measures rather than to the donor's opinion. Attributes are only ever **dropped or
downgraded** — adding one would turn a borrowed block into a derived one by stealth and lose the
provenance. The audited block is then re-scored, and falls back to flat if the audit ate what it was
living on (which is what happened to 4411's CM). The two sets went from 64 and 66 weight rows to
**42 and 32**.

### Leadership is a status proxy, not a role requirement

The line that started the audit was **Leadership 4 for the 4-2-3-1 left-back**. It is not a typo —
it measures +0.34, second only to Pace in that cell — but it fails every check:

- **A third of it is playing time.** Controlling for minutes within the stratum as well as the flat
  attribute sum takes it from +0.341 to **+0.232**. `r(leadership, minutes) = +0.33` and
  `r(target, minutes) = +0.45`.
- **It is positive in every attacking brief and negative in the defensive ones** — LB +0.34,
  AML +0.34, RB +0.26, DM +0.22, ST +0.22, against CB −0.13 and CM −0.07. An attribute that mildly
  helps everything going forward and mildly hurts everything defensive is reading "established
  first-choice player", a quality signal the flat-sum control does not fully absorb.
- **n=44 puts the standard error near 0.16**, so +0.34 is about two of them.

It is therefore capped at `LEADERSHIP_CAP = 2` wherever it survives and never introduced into a
block that lacks it — real enough to nudge a ranking, nowhere near solid enough to decide one.
Note what the cap is NOT: a claim the coefficient is zero. At RB and AML it *strengthens* under the
minutes control, so "it's just minutes" is only part of the story; the cross-role sign flip is the
stronger argument.

### Two attributes are HELD against the measurement, on the record

`HELD` exists so a judgement call is a named exception rather than a silent patch:

- **`("DM", "passing")`** — UNMEASURABLE, not refuted. Every DM in the sample sits inside 1.5 points
  of Passing, so the cell has no spread to correlate and `partials()` returns `None`. This is the
  restriction-of-range rule firing correctly; rating a deep pivot with no passing weight at all
  would be nonsense, so it keeps its donor weight.
- **`("ST", "movement")`** — measures −0.26 and is held at 2 on the manager's judgement.

Anything else the audit strips is stripped. Notably that includes **Decisions 3 and Strength 3 from
the ST block** agreed earlier the same day (+0.08 and +0.05 stratified): the ST rewrite's direction
survived, its breadth did not.

### Row order was load-bearing, and the win-rate gate was a coin flip

`KFold(shuffle=True)` permutes row POSITIONS, not identities, so a different row order is a
different set of folds. DuckDB returns rows in whatever order its parallel scan finished in, so
three identical runs of the script against an identical store scored the 4-2-3-1 LB block at
**64%, 80% and 84%** against an 80% bar. The block shipped or not on a coin flip — which is how
Leadership 4 came to be there at all. `frame` is now sorted by `(person_id, season)` before
anything is measured. Two full runs now produce byte-identical output.

This is the same class of bug as the position-pick drift above, found the same way: run it twice.

### A method must not borrow from itself, or from a sibling

`stored` is read from the store, so once a derived method has been seeded its own blocks come back
as candidates — fitted on these very rows, so they bootstrap at ~100% and beat every honest rival.
Re-deriving then re-ratifies the last run's output and the audit trail becomes a loop; the report
said `best stored +0.193 (frem_minmax_4231, 100%)` while deriving `frem_minmax_4231`. Sibling
methods are the same loop one step removed: 4-4-1-1 was borrowing 4-2-3-1's CM block. The rival
pool is now the hand-built methods only — written from a tactic author's stated player traits,
never from these rows. 4411's CM was surviving entirely on that cross-borrow and is now flat.

## The briefs were the bug (2026-09-12, same day, after the audit)

The audit above made the weights honest and left three of them plainly wrong as football. The manager
rejected all three on sight, and in every case the fault was the BRIEF, not the statistics. This is
the most transferable lesson in this file: **when a derived weighting looks wrong to someone who
watches the team play, check what question you asked before you check the maths.**

### 1. Ask the striker to be the focal point and the answer changes completely

The striker was briefed `finish` = shots on target + goals. That measures a finisher. It never asks
the centre forward to BE the target, so the attributes of a target man could not earn a place, and
the audit correctly stripped Strength and Decisions for want of evidence. Rebriefed as
`finish + win_the_air`, on the same rows, same stratification, same everything:

| attribute | `finish` | `finish + win_the_air` |
|---|---|---|
| Aerial | +0.16 | **+0.50** |
| Strength | +0.05 | **+0.30** |
| Shooting | +0.29 | +0.30 |
| block vs flat | +0.238 / +0.204 (85%) | **+0.261 / +0.180 (100%)** |

Aerial is now the largest coefficient anywhere in this analysis. Note also that Movement, HELD at 2
on judgement because it measured −0.26 under `finish`, clears the key band on its own under the new
brief — the hold is no longer load-bearing. The HELD notes now print the live measurement for exactly
this reason: a hold whose justification has expired should say so rather than quietly persist.

The practical consequence: Anosike Ementa goes from second at striker to **99.0 Fit %ile, clear
first choice.** The physical centre forward was never a hunch the data merely tolerated.

### 2. Symmetric roles derived separately answer a different question than you asked

LB and RB cells share **zero players** — 36 distinct left-backs, 36 distinct right-backs, no overlap,
because a full-back plays one side. So "Pace −0.07 at LB and +0.46 at RB off one brief" was never
about flanks; it was the gap between two groups of footballers. Same for AML/AMR.

`SYMMETRIC = [("LB","RB"), ("AML","AMR")]` pools the positions into one cell (n=89 and n=50 instead of
44/45 and 28/22). `strata()` still gives each position its own baseline inside that cell, so pooling
cannot reintroduce a DL-vs-DR gap — it only doubles the sample.

**Pooling the data was not enough.** With one cell but still one fold seed per ROLE, identical evidence
shipped different blocks: left-back took its derived set at a 96% win rate, right-back took
`frem_game_state`'s at 88%, off the same numbers. Fold noise was deciding a football question. The pair
now shares a seed and the decision is made once, then copied — the report says `-> LB (SYMMETRIC)` so
the copy is visible.

### 3. Defensive quality is the one thing rebriefing cannot fix

Centre-back came back with no tackling and the screening pivot came back a regista. The measured
figures at CB are Tackling **+0.03** and Positioning **−0.08** over n=112.

**This is not restriction of range.** That was the first hypothesis and it is wrong: Tackling sd 2.70
and Positioning sd 2.71, both spanning 6–19. There is plenty of spread and the correlation is still
nothing. The mechanism is that the outcome is a **volume** statistic — interceptions and tackles won
per 90. A well-positioned defender who reads the game makes FEWER tackles, and how much defending
anybody does is set by territory and team style rather than by ability. Per-90 defensive counts
measure how MUCH you defend, not how WELL.

That is the fourth independent route to the same conclusion in this file. It also means no brief built
from this save's defensive stats can ever value a defender properly, so the honest options are a thin
data-only block or a declared judgement call. The manager chose the latter and it is recorded as such:
`BRIEFS[...]["hold"]` carries the non-negotiables (CB and DM in both shapes, plus the big-game shape's
full-backs, who are there to defend; the 4-2-3-1's full-backs are briefed to create and are not held).

**A hold is the only thing permitted to ADD a weight the evidence did not produce** — the audit itself
may only drop or downgrade. That asymmetry is the point: an addition is a manager's call and must be
declared in the brief where it can be argued with, while a removal is just what the evidence says.
