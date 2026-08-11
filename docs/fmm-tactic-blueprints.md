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
| ST (PF) | Stamina + Aggression/Aerial/Movement "overkill trio" (for variants) | stamina, aggression, movement | aerial, pace, shooting, teamwork |

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

**Squad style‑lean (best‑XI mean Fit %ile, mid‑22):** counter 69.5 ≈ lowblock 69.1 ≈ attacking_ss
69.0 ≈ gegenpress 68.6, but **game_state only 64.5.** Read: *this squad is built to attack — roughly
equally good at any proactive style, and materially worse at shutting up shop.* Game‑state is
emergency‑only; the players who'd play it are squad fillers, not the stars. Recruitment gap = a
lock‑down DM (Anchor) + a commanding CB if we ever want to defend leads reliably.

**In‑game SETTING presets per scenario:**
| Scenario | Mentality | Line | Tempo | Width | Press | Notes |
|---|---|---|---|---|---|---|
| Base (vs equals) | Control | **Balanced** | Normal | Narrow | All Over | our slow‑CB deviation from High |
| vs low block / weak | Attacking | High | Normal | Narrow→Bal | Own Half | overload the box |
| Protect lead / vs strong | Balanced | Deep/Bal | Slow | Narrow | Own Half | Anchor DM, BBM→CM |
| vs pace in behind | Balanced | **Deep** | Normal | Narrow | Own Half | trap OFF, man‑mark runner, counter |

**Bench specialists (bring on for…):**
- **Press harder / full gegenpress:** Andersson (70→**79** — the presser: aggression 17, teamwork 15).
- **Break a low block:** Lodberg (55→**66**), Fugl (49→**64**), Tånnander (55→**64**) — dribble/creative
  risers; Nuamah even more dangerous here (76→**82**). Strong bench for parked buses.
- **Close a game / defend:** Schou (best defensive CB: game_state 75, counter 77), Sundstrup & Grønne
  (rise in game_state), Randolf (counter FB). Thin group overall — see recruitment gap.
- **Counter:** Schou/Jørgensen behind, Nuamah + Randolf pace, Balck as a fast ST outlet.
