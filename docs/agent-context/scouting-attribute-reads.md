---
name: scouting-attribute-reads
description: "Which attribute actually answers which scouting question — the attacker/defender duel pairs (Movement vs Positioning), and which columns are trustworthy on a player who was never ours"
metadata:
  node_type: memory
  type: reference
---

Written after a run of opposition briefings quoted an opponent back line's **Movement** as a
weakness — twice, in two separate reports, as the headline exploit. Movement is not a defending
attribute. The rating model already knew that; the briefing didn't.

## The duel pairs — an attribute is only a weakness against its counterpart

`mart.role_weights` encodes this explicitly. Pulled from `frem_counter` (weights: 4 = key,
3 = important, 2 = useful, unlisted = 1 baseline — see [[role-weight-methods]]):

| attribute | CB | LB/RB | DM | CM | ST | AMC | AML/AMR |
|---|---|---|---|---|---|---|---|
| **movement** | **base** | 3 | 2 | 4 | 4 | 3 | 3 |
| **positioning** | **4** | 3 | 4 | base | **base** | **base** | **base** |
| tackling | 3 | 3 | 4 | 4 | base | base | base |
| aerial | 4 | 2 | base | base | 4 | base | base |
| pace | 4 | 4 | 2 | 3 | 4 | 2 | 4 |
| strength | 3 | base | 3 | 2 | base | base | base |

(`base` = absent from that role's weight list, so it scores at the weight-1 floor. Per
[[role-weight-methods]] there is no way to weight an attribute below baseline — an unlisted
attribute is not penalised; it is simply not what the role is judged on.)

Read across the table and the pairing falls out: **Movement is the attacker's side of the duel and
Positioning is the defender's answer to it.** A centre-back with Movement 6 is not slow to react —
Movement is simply not what he is judged on. The defender's equivalent question is *Positioning*. The
same symmetry runs the other way: Positioning is weighted zero for every forward, so "their striker
has Positioning 7" is equally meaningless.

**The rule:** before quoting an attribute as a strength or weakness, check it is weighted > 1 for
that player's role. If the role doesn't score it, the number is noise.

Practical pairings for a briefing:

| The question | Attacker column | Defender column |
|---|---|---|
| Can they track runners in behind? | Movement, Pace | **Positioning**, Pace |
| Can they win it back? | Dribbling, Technique | **Tackling** |
| Who wins the ball in the air? | Aerial, Strength | **Aerial, Strength** (same column both ends) |
| Will they be there at the end? | Stamina | Stamina |

## But: on an opponent, three of those columns are the *least* trustworthy in the table

Compounding trap. Per [[player-analysis-methods]], only **8 attributes are exact save-wide** (Pace,
Strength, Stamina, Technique, Aggression, Leadership, Agility, Teamwork). The other 15 — including
**Movement, Positioning and Aerial** — are a frozen linear decode for anyone outside our club. And
those three specifically are **compressed 8–24×** relative to their real values.

So the two columns that matter most for the defensive read are both estimated *and* compressed.
Consequences for a briefing:

- **Rank order within a squad probably survives** the compression (it's monotone-ish) — "Durmisi is
  their weakest aerial defender" is a fair call.
- **The magnitude does not.** Do not present "Positioning 8 vs 13" as a five-point gap, and do not
  build a plan on a two-point difference in these columns between two opponent players.
- **Pace and Strength are exact** — lean on them. "Their centre-back has Pace 10 and our forward has
  Pace 16" is the strongest single claim available about an opponent, because both halves are real.
- Prefer **Level %ile** (`level_*`) for "how good is he" and reserve attribute talk for "what kind of
  player is he" — see [[level-vs-fit-percentile]].

## Worked example of getting it wrong, then right

Two briefings led with "their back line has Movement 7.1 / 9.4 against our attack's 14.9" as the
biggest exploit in the fixture. Redone on Positioning, the same two opponents read:

- **AaB:** defence Positioning 12.7 vs our 12.9 — *level*, not a weakness. The real soft spot was one
  player (Solbes: Positioning 10 **and** Aerial 11, weakest on both counts) — which is why the
  striker's hat-trick landed. Right conclusion, wrong reasoning, and it would not have transferred.
- **AGF:** defence Positioning 12.0. The exploitable player was the *right-back* (Positioning 8,
  but Aerial 15) — a run-at-him weakness, not a cross-at-him one — while the left-back was the
  reverse (Aerial 4, Strength 7, Positioning 11). Two different exploits on opposite flanks, which
  the Movement reading had collapsed into one wrong one.

The unit-mean hid both. **Check the individual defenders, not just `unit_attrs`** — a back four
averaging 12 can contain an 8.
