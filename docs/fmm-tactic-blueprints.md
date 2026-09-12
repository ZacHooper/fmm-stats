# FMM tactic blueprints — the meta, decoded

Reverse‑engineered from four FMM Vibe record‑setter threads (+ Black Hawk, FMM24), reading the
actual in‑game **formation / Shape / Defence / Attack** screenshots — not just the forum prose.
Purpose: a portable reference for building & tuning Frem's tactics (`frem_gegenpress`,
`frem_attacking_ss`) and situational variants.

## The five, side by side (screenshot‑verified)

| | Attacking SS | Kimmich Tiki‑Taka | Black Hawk | 433 No Striker | 4321 Plug‑n‑Play |
|---|---|---|---|---|---|
| Game / internal shape | FMM22 · `2-3-2-3` | FMM22 · `2-3-2-3` | FMM24 · `4-1-2-3` | FMM22 · `2-2-3-3` | `4-3-2-1` |
| GK | SK | SK | G (build‑out) | G | — |
| Back | CD, CD | **BPD**, BPD | WB‑**BPD**‑BPD‑WB | CD, CD | back 4 |
| Pivot | WB‑**BWM**‑WB | WB‑**RP**‑WB | **RP** | (flat 3) | — |
| 8s | **RP + BBM** | BBM + BBM | BBM + BBM | CM‑**BWM**‑CM | 3 CM |
| Front 3 | IF‑**SS**‑IF | IF‑**T**‑IF | IF‑**PF**‑IF | IF‑**T**‑IF | 2 IF + ST |
| Mentality | **Control** | **Control** | **Control** | — | direct |
| Width | **Narrow** | **Narrow** | **Narrow** | — | — |
| Tempo | Normal | Slow | Normal | — | — |
| Creative freedom | Balanced | Expressive | Expressive | — | — |
| Def. line | **High** | **High** | **High** | — | — |
| Closing down | **All Over** | **All Over** | **All Over** | — | — |
| Tackling | Normal | Normal | Normal | — | — |
| Offside trap | No | No | **Yes** | — | — |
| Passing | Mixed / Mixed | Mixed / Mixed | — | — | Mixed / Centre |

*Dashes = screen not in that post's images. The three "serious" tactics were fully captured;
433 No Striker showed only its formation, 4321 only its attack panel (a direct
Shoot‑on‑Sight / Run‑at‑Defence outlier that keeps a striker).*

## The common DNA (the three record‑setters are one tactic)
- **Control mentality · Narrow width · High line · All‑Over press · Normal tackling** — identical
  across two game editions.
- **Sweeper‑keeper**, build from the GK.
- **2 centre‑backs + 2 Wing‑Backs that supply ALL the width** (the forwards come inside).
- **Single deep pivot + two 8s.**
- **Front three = IF – central creator – IF. Never wingers.** The central man is the focal point.
- **Mixed passing** (not even Short — they want fast defence→attack).
- Net: *narrow, controlled possession + high line + all‑over press + inside‑forwards feeding a
  central creator.* A possession‑gegenpress hybrid — the FMM meta.

## The differences (the levers you actually choose between)
- **Tempo/creativity:** Kimmich = Slow + Expressive (hog the ball); Attacking SS = Normal +
  Balanced (win it, go vertical); Black Hawk between (Normal + Expressive).
- **Pivot:** **BWM** (Attacking SS, ball‑winner) vs **RP** (Kimmich/Black Hawk, deep creator /
  "undercover AM"). The biggest identity fork.
- **Central focal role:** **SS** (runs beyond) vs **Trequartista** (drops to link) vs **PF** (real
  striker who presses + finishes).
- **CBs & trap:** Black Hawk = Ball‑Playing Defenders + Offside Trap ON → needs genuinely fast CBs.
  Attacking SS = plain CDs, trap OFF.

## Authors' stated player traits → our 4/3/2/1 weighting
Weight convention: key=4, important=3, useful=2, unlisted=baseline 1. Universal DNA the authors
name everywhere: **Pace, Stamina, Teamwork, Decisions, Passing, Movement.**

| Our role (tactic role) | Author priorities (SS / Kimmich / Black Hawk) | key (4) | important (3) |
|---|---|---|---|
| GK (SK) | sweep + short build‑out | reflexes, handling, positioning, decisions | kicking, communication |
| CB (CD/BPD) | "Pace cannot be stressed enough"; Decisions, Tackling, Aerial | pace, decisions, tackling | aerial, positioning |
| LB/RB (WB) | Pace, Stamina, Crossing (+Movement/Decisions) — supply all width | pace, stamina, crossing | movement, decisions, positioning |
| DM (BWM) | Pace, Tackling, Passing, Decisions — mobile ball‑winner | tackling, decisions, passing, pace | positioning, stamina, teamwork, aggression |
| CM (RP+BBM) | Passing, Decisions, Stamina (+Teamwork/Movement/Creativity) | passing, decisions, stamina | teamwork, movement, creativity, tackling |
| AMC (SS) | Pace, Shooting, Aerial‑if‑few‑headers — runs beyond & finishes | movement, shooting, pace | decisions, technique, teamwork |
| AML/AMR (IF) | Pace, Shooting, Passing, Movement — cut in to score, NOT crossers | pace, shooting, movement | passing, technique, dribbling, decisions |
| ST (PF) | ~~Stamina + Aggression/Aerial/Movement "overkill trio"~~ — **measured and replaced 2026‑09‑12, see below** | shooting | aerial, strength, pace, decisions |

> **The ST row was measured and rewritten on 2026‑09‑12.** The "overkill trio" came from forum
> posts, never from data. Across 40 league strikers, the old weighting ranked them **worse than
> weighting nothing at all** — r=0.351 against goals where a flat average scored 0.411 — because
> three of its four highest weights sat on attributes with no measurable effect (Movement −0.00,
> Aggression −0.11, Stamina +0.01 against goals, controlling for ability) while Shooting, at
> +0.50, was only third tier. The rewritten set scores **0.484**. Full working, including the
> corroboration rule that kept Tackling out of it, is in
> [`attribute-stat-correlations`](agent-context/attribute-stat-correlations.md).
>
> Movement is held at **2 on the manager's judgement**, not on the data — it is the one null with
> too little spread at ST (sd 1.66, range 8–15) to be confident about, and it costs 0.007.

Seeded as method **`frem_attacking_ss`** (94 rows, both stores). Sits alongside `frem_gegenpress`.
Contrast: attacking_ss weights **crossing KEY on WBs** and **shooting KEY / crossing‑baseline on the
IFs** (they cut in), where gegenpress dropped crossing entirely and made dribbling key on the wide men.

## Frem in‑game recipe (mirror the record‑setter, adjusted for our squad)
Shape (Attacking‑SS branch — BWM pivot, since we have a ball‑winner not a Kimmich):
`SK / CD‑CD / WB‑BWM‑WB / RP‑BBM / IF‑SS‑IF`.

- **Copy the blueprint:** Mentality **Control** · Width **Narrow** · Tempo **Normal** · Passing
  **Mixed** · Closing Down **All Over** · Tackling **Normal** · Offside **No** · no fixed
  final‑third calls (adjust in‑game).
- **The one deviation — defensive line = Balanced, not High.** Every blueprint plays High but
  assumes fast CBs; ours (Jørgensen pace 10, Schou 11) can't, so keep the all‑over press but sit the
  line a notch. This is the single most important adaptation and the exact failure mode every author
  warns about (slow / ball‑carrying CB → gap in behind).
- Personnel: SK Bruhn · WB Randolf/M.Andersen · CD Jørgensen+Schou · BWM **Andersson** ·
  RP/BBM Garly + Haarbo · IF Nuamah + Aslani · **SS Haarbo** (the focal point — put our best
  attacking mid there; Herslov is the natural‑fit alternative).

## Situational variants (ideas — not yet built)
- **vs a low block / weaker side:** push mentality to Attacking/Overload, line High, keep Narrow —
  overload the box (the "3‑goals‑a‑game" mode).
- **vs a stronger side / to protect a lead:** Balanced mentality, line Deep/Balanced, tempo down;
  BBM→CM, DM as Anchor (the Attacking‑SS author's "conceding too much" fix: DM→3rd CB, middle CB
  libero vs 2 strikers).
- **vs pace in behind (our Achilles):** drop line Deep, trap OFF, man‑mark their runner; consider a
  slower, deeper block and hit on the counter instead.
- **vs a packed midfield / possession side:** Kimmich branch — RP pivot, Slow tempo, Expressive,
  keep the ball off them.
- Could be encoded as extra weight‑set methods (e.g. `frem_lowblock_overload`, `frem_game_state`)
  and/or documented as team‑instruction presets to switch to in‑game.

## Variants — BUILT (methods + settings + personnel)
Five Frem methods now exist: `frem_attacking_ss` (base), `frem_gegenpress`, `frem_lowblock_overload`,
`frem_game_state`, `frem_counter`. Weight‑sets aren't about a different first XI (the core XI is
stable) — they tell us **which bench player to bring on per situation** and **which style the squad
is built for**.

**When to use each — cheatsheet.** Default method (`app_config.default_method`) = `frem_attacking_ss`.
"Fit" = best‑XI mean Fit %ile mid‑22 (how well *this* squad suits the style).

| Method | Use when | Style | Fit |
|---|---|---|---|
| **`frem_attacking_ss`** ⭐default | **vs equals** — standard proactive game | FMM record‑setter meta: Control · Narrow · all‑over press · BWM pivot + SS | 69.0 |
| **`frem_counter`** | **vs stronger sides** / hit on the break with pace (Nuamah, Randolf, Balck); also the *pace‑in‑behind* answer (deeper line) | Direct, wing‑play, 4‑2‑3‑1 | **69.5** |
| **`frem_lowblock_overload`** | **vs a weak side parking the bus** — break down a low block, overload the box ("3 goals a game") | Attacking mentality, box overload; dribblers off the bench | 69.1 |
| **`frem_gegenpress`** | **suffocate / press harder** — physically overrun a side | High press 4‑1‑2‑3, stamina‑hungry; Andersson the presser sub | 68.6 |
| **`frem_game_state`** | **protect a lead / close out** — emergency only | Defensive, sit deep; Schou/Sundstrup/Grønne on | **64.5** |
| `black_hawk` | reference baseline, not Frem‑tuned | generic FMM24 meta | — |
| `personal` | custom weight‑set (manual tweaks) | — | — |

**Squad style‑lean — RECOMPUTED 2026‑09‑10 on the 2025‑11‑30 snapshot (37‑man squad, `squad_current`,
best XI picked per method over a generic GK/DL/DC/DC/DR/DMC/MC/MC/AML/AMC/AMR frame):**

| Method | Fit %ile now | mid‑22 |
|---|---|---|
| `frem_counter` | **89.1** | 69.5 |
| `frem_game_state` | **87.3** | 64.5 |
| `frem_lowblock_overload` | 87.2 | 69.1 |
| `frem_attacking_ss` | 87.0 | 69.0 |
| `frem_gegenpress` | 86.5 | 68.6 |

Compare the *ranking*, not the levels (different squad, and the best‑XI frame here may not match
whatever was used in 22). **The mid‑22 read no longer holds: `frem_game_state` has gone from a clear
outlier 4.5 points off the pace to SECOND, and the spread across all five has collapsed from 4.5 to
2.6.** The old conclusion — "materially worse at shutting up shop, game‑state is emergency‑only,
the players who'd play it are squad fillers" — is superseded; this squad no longer has a style it
cannot play. That stale number was quoted at a 2026 squad during the 2026‑09 session and put a wrong
claim into `scout-opponent`, so:

> **Convention: any number in this doc that drives a decision carries the date and the squad it was
> computed on.** A dated number that is stale is recoverable; an undated one gets quoted forever.

The recruitment gap noted in 22 (a lock‑down DM + a commanding CB) may also have closed — recheck
before repeating it.

**In‑game SETTING presets per scenario.** The full menu surface (every lever and its options) is in
[`fmm-tactic-options`](agent-context/fmm-tactic-options.md) — read it first; a `role_weights` method
sets NONE of these. The Attack tab was missing from this table entirely until 2026‑09 and it turned
out to hold the most consequential lever of the lot, so it is now columns of its own.

| Scenario | Mentality | Line | Tempo | Width | Press | Final third | Passing | Notes |
|---|---|---|---|---|---|---|---|---|
| **Current default (2026‑03, evidence below)** | **Attacking** | **High** | **Fast** | Narrow | All Over | **Work Into Box** + Run At Defence | Short, focus **Centre** | Expressive; won 6‑0 away at the league's best attack |
| Base (vs equals) *(mid‑22, unverified since)* | Control | Balanced | Normal | Narrow | All Over | — | — | the "slow‑CB deviation from High" it cites refers to a 22 back line |
| vs low block / weak | Attacking | High | Normal | Narrow→Bal | Own Half | Work Into Box | Centre | overload the box |
| vs pace in behind | Balanced | **Deep** | Normal | Narrow | Own Half | — | — | trap OFF, man‑mark the runner |
| ~~Protect lead / vs strong~~ *(disproved 2026‑03)* | ~~Balanced~~ | ~~Deep/Bal~~ | ~~Slow~~ | | | | | see below |

**`Work Into Box` is the shot‑quality lever, and it is a team instruction, not a selection problem.**
Shots ON TARGET predicts our goals at r=+0.72 while shot volume is flat across every accuracy
quartile ([`scoring-and-shot-quality`](agent-context/scoring-and-shot-quality.md)). With Work Into
Box set, our worst‑accuracy shooters simply stop shooting: the squad's most prolific wasteful shooter
(19 shots, 1 goal, 26% accuracy on the season) took 0 shots in one match and 2 in the next, and team
SOT rate went from a 36.2% season average to 47–67%. Set it before reaching for a different XI.

**Why "Protect lead / vs strong" is struck through.** Away at Midtjylland (quality gap 45 v 84) the
cautious version of the plan — counter method, deep line, absorb and break — drew 1‑1 with 3 shots.
The same fixture replayed with **Attacking / High / All Over / Fast / Work Into Box** finished **6‑0**,
15 shots and 7 on target. A large quality gap is NOT on its own a reason to sit deep with this squad;
`frem_game_state`'s Fit (above) says the same thing from the other direction. Keep a deep line for the
specific case it was written for — genuine pace in behind against slow centre‑backs.

**Line and press are two levers, not one.** These presets move them together, which makes it easy to
write "drop the line" and have it read as "drop the press". Against a side whose creativity runs
through one deep passer, pulling the *press* is the more expensive of the two: a 3‑0 became 3‑2
immediately after the press came off, with their deep playmaker finishing on 32 passes / 28 completed,
by ten the most on the pitch. When protecting a lead against a technical build‑up, **drop the line and
keep the press on**, and say which lever you mean.

**Bench specialists (bring on for…)** — ⚠️ **STALE PERSONNEL (mid‑22).** Most of the players named
below have left; the Fit numbers are from a squad two-plus seasons old. Treat the *shape* of the list
(which archetype to bring on for which problem) as still useful and re‑derive the names against
`squad_current` before quoting any of them.

- **Press harder / full gegenpress:** Andersson (70→**79** — the presser: aggression 17, teamwork 15).
- **Break a low block:** Lodberg (55→**66**), Fugl (49→**64**), Tånnander (55→**64**) — dribble/creative
  risers; Nuamah even more dangerous here (76→**82**). Strong bench for parked buses.
- **Close a game / defend:** Schou (best defensive CB: game_state 75, counter 77), Sundstrup & Grønne
  (rise in game_state), Randolf (counter FB). Thin group overall — see recruitment gap.
- **Counter:** Schou/Jørgensen behind, Nuamah + Randolf pace, Balck as a fast ST outlet.

## Two DERIVED variants (2026-09-12) — `frem_minmax_4231`, `frem_minmax_4411`

**Different in kind from the five above.** Every earlier method was assembled from what a tactic's
author said his players needed. These two were built by `scripts/derive_weight_set.py`: name what
each slot in the shape is FOR, and let the match data choose the attributes. Read that script's
docstring before editing either — hand-editing a derived set throws away the audit trail that is
the whole point of it.

The method is per role: partial-correlate every attribute against the role's outcome mix,
**controlling for the flat attribute sum**, inside a (position, division) stratum, then ship the
block only if it beats a flat weighting out-of-fold in ≥80% of cross-validation splits. Stored
blocks face the same test, bootstrapped. **A role that nothing beat stays flat on purpose** — that
is a finding, not a gap. Then, since the 2026-09-12 audit, **every line in the winning block has to
clear the 0.10 floor on its own** (`audit_block()`), so a block can no longer beat flat on two
attributes and carry five passengers.

**These are the AUDITED sets.** The first run shipped 64 and 66 weight rows; the audit cut them to
**42 and 32**, dropping Shooting 4 from a defend-first wide midfielder (measured −0.32), Positioning
4 from centre-back (−0.08), three of the 4-4-1-1 full-back's four *key* attributes (all ≈0), and
capping Leadership at 2 everywhere. The full before/after and the reasoning is in
[`attribute-stat-correlations`](agent-context/attribute-stat-correlations.md#the-attribute-level-audit-2026-09-12--a-block-can-beat-flat-while-half-its-lines-are-noise).

| role | brief | `frem_minmax_4231` | `frem_minmax_4411` |
|---|---|---|---|
| GK | — | inherits `frem_attacking_ss` | inherits `frem_attacking_ss` |
| LB | 4231 create · 4411 defend | **derived** pace 4, crossing 3, leadership/teamwork/technique 2 | `frem_game_state`, audited → aerial 4, decisions/strength 3 |
| RB | same | `black_hawk`, audited → positioning 3, pace/technique 2 | **derived** aerial/pace/stamina 4, leadership/positioning 2 |
| CB | win the air + win it back | `frem_counter`, audited → aerial/pace 3, strength 2 | same |
| DM | screen | `personal`, audited → creativity/dribbling/passing 4, decisions/shooting 2 | `black_hawk`, audited → creativity/passing 4 |
| CM | 4231 keep+progress · 4411 win it back+keep | **derived** agility/technique 4, decisions/movement/pace/passing 3, aggression/creativity/teamwork 2 | **flat** — it only ever survived by borrowing the 4-2-3-1 block |
| AML | 4231 progress+create · 4411 defend+break | **flat** | `black_hawk`, audited → passing 4, creativity/decisions 3 |
| AMR | same | **flat** | **flat** |
| AMC | 4231 create · 4411 finish+progress | `frem_lowblock_overload`, audited → agility/technique 4, creativity/dribbling/shooting 3 | `personal`, audited → decisions/positioning 3, creativity/passing 2 |
| ST | finish | `frem_attacking_ss`, audited → shooting 4, aerial/movement/pace 2 | same |

Two notes on that table worth carrying forward:

- **The two full-backs diverge sharply in this shape.** On the 4-4-1-1's defend-first brief, Pace
  measures **−0.07 at left-back and +0.46 at right-back** in the same stratified cell. One borrowed
  full-back profile cannot serve both sides, which is why LB ends up on an aerial/strength block and
  RB on a pace/stamina one.
- **`frem_minmax_4411`'s ST and `frem_attacking_ss`'s ST are no longer identical.** The audit kept
  Shooting 4 and the held Movement 2 but stripped Decisions 3 (+0.08) and Strength 3 (+0.05), which
  the stratified cell does not support. The direction of the ST rewrite survived; its breadth did
  not. If you want those two lines back, add them to `HELD` with the argument — do not hand-edit the
  CSV.

**Squad Fit %ile, best XI on the generic frame, recomputed 2026-09-12 AFTER the audit, on the
`frem-2026-03-22` snapshot (37-man `squad_current`):** `black_hawk` 88.7 · `frem_counter` 88.7 ·
`personal` 88.5 · **`frem_minmax_4411` 86.3** · `frem_game_state` 86.3 ·
`frem_lowblock_overload` 85.9 · `frem_attacking_ss` 85.7 · `frem_gegenpress` 85.6 ·
**`frem_minmax_4231` 85.3**. The whole field sits inside 3.4 points, so read the ranking and not
the levels.

The audit cost both derived sets a little height — 4-2-3-1 88.2 → 85.3, 4-4-1-1 87.2 → 86.3 — and
that is the expected direction, not a regression. Stripping unsupported weights moves a block
toward flat, and a flatter block scores a squad more evenly, so **the pre-audit figures were partly
measuring the passengers**. `black_hawk`, `frem_counter`, `personal`, `frem_game_state`,
`frem_attacking_ss` and `frem_gegenpress` are unchanged to the decimal, which is the check that the
audit touched only what it was meant to.

⚠️ **One figure moved that should not have:** `frem_lowblock_overload` reads 85.9 against the 87.1
recorded earlier the same day, and its weights are untouched in this change. The likeliest cause is
that this recompute ran against the R2-PUBLISHED store, pulled down fresh, whose seeded weights
predated last session's `seed_role_weights` de-duplication fix; the `--refresh-only` run that
re-seeded from the CSV would then have corrected them. That is a hypothesis, not a verified
cause — the pre-refresh state was overwritten. If you see a hand-built method's Fit figure move
without a weight change, check `mart.role_weights` against `seeds/role_weights.csv` for duplicates
first (`count(*)` vs `count(DISTINCT method||role||attribute)`; it is 687/687 as of this commit).

**Best XI under the audited sets** (`eff`, Fit %ile), and the selection consequences are real:

| | `frem_minmax_4231` | `frem_minmax_4411` |
|---|---|---|
| GK | Ullits 63.0%ile | Ullits 63.0%ile |
| LB | Dehn 91.7 | Buur 86.5 |
| CB | **Kabongo** 80.7 · Gülstorff 74.1 | **Kabongo** 80.7 · Gülstorff 74.1 |
| RB | **Karlsen** 100.0 | **Karlsen** 100.0 |
| centre | **Chukwuani** 94.1 · Tjørnelund 93.4 | **Chukwuani** 100.0 · **Sørensen** 96.3 |
| wide | Wass 79.7 · Secka 84.0 | Wass 85.4 · Secka 87.1 |
| AMC | Bech 90.4 | Bech 96.3 |
| ST | **Olesen** 91.3 (Ementa next) | **Olesen** 91.3 (Ementa next) |

Three changes worth arguing about before you pick a side on this: **Anton Pedersen drops out of both
back fours** (Kabongo in), **Karlsen passes Jakob Larsen at right-back**, and **Tobias Olesen now
rates ahead of Ementa at striker** — the last of those is a direct consequence of the audit removing
Strength 3 and Decisions 3 from the ST block. If Ementa's physical presence is the point of playing
him, that argument belongs in `HELD` in `scripts/derive_weight_set.py`, with the reasoning written
down, rather than as a hand-edit to the seed CSV.

### What the derivation could NOT do, and why that matters

**Six of the ten 4-4-1-1 roles came back flat or borrowed.** Every defensive brief — LB and CM
"win it back", AMR "win it back + progress" — failed to beat a flat weighting. That is the same
result this project has now reached three separate ways: *our XI's attributes do not predict what
we concede* ([`attribute-stat-correlations`](agent-context/attribute-stat-correlations.md)). The
defensive dials are team instructions, not selection.

So **`frem_minmax_4411`'s value is its SHAPE and its settings, not its weights.** Do not expect its
Fit column to tell you much about who should play in a big game; expect the 4-2-3-1 set to, because
the creative and progressive briefs are the ones the data can see.

**The goalkeeper cannot be derived at all.** A keeper's match row holds passes and essentially
nothing else — no saves, no clean sheets, no goals conceded — so both methods inherit
`frem_attacking_ss`'s GK block rather than inventing one.

**A flat role used to be unrepresentable.** Shipping "no weights" for AML/AMR made those positions
disappear from the depth chart entirely, because both rating views built their method x role list
from the pairs present in `role_weights`. Fixed in `fmparser/mart.py` and `load_duckdb.py`; if you
ever see "no player rated here" for a position the squad clearly covers, that is the shape of the
bug to look for.

### In-game settings

The weight-set sets NONE of these; the full menu surface is in
[`fmm-tactic-options`](agent-context/fmm-tactic-options.md).

| | `frem_minmax_4231` (vs equals / weaker) | `frem_minmax_4411` (vs FCK-class) |
|---|---|---|
| Shape | `SK / WB-CD-CD-WB / BWM-DLP / IF-AM-IF / AF` | `SK / FB-CD-CD-FB / WM-BWM-CM-WM / SS / AF` |
| Mentality | **Attacking** | **Balanced** |
| Defensive line | **High** | **Balanced** |
| Tempo | Fast | Normal |
| Width | Narrow | Balanced |
| Closing down | All Over | **All Over — keep the press on** |
| Final third | **Work Into Box** + Run At Defence | **Work Into Box** |
| Passing | Short, focus Centre | Mixed |

Two rules carry over from what is already established here and they are not optional:

- **A quality gap is not a reason to sit deep.** Away at Midtjylland the cautious plan drew 1-1 with
  3 shots; the same fixture on Attacking / High / All Over / Fast / Work Into Box finished 6-0. The
  4-4-1-1 is a change of SHAPE — an extra body in midfield and a split striker to press the first
  pass — not a change of intent. Keep a deep line for the one case it was written for: genuine pace
  in behind against slow centre-backs.
- **Line and press are two levers.** Against a side whose build-up runs through one deep passer,
  pulling the press is the expensive one: a 3-0 became 3-2 immediately after the press came off.
  Drop the line if you must; keep the press.

**`Work Into Box` is in both columns deliberately.** Shots on target predict our goals at r=+0.72
while shot volume is flat across every accuracy quartile, and this is the instruction that moves
accuracy — team SOT rate went from a 36.2% season average to 47-67% with it set.

