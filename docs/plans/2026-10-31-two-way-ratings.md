# Two-way ratings: an attacking and a defensive rating for every position

Status: **proposal**, nothing built. Prototype queries were run against the published store
(snapshot 2029-06-30); the figures below come from them.

## Why

FMM22 gives each slot a role but no duty, so there is no in-game "Support / Defend" switch. The
lever the manager actually has is **which player** fills the slot. A single role rating cannot
answer the question that choice is about ("I need this full-back to defend today"), because it
adds attacking and defensive attributes into one pool, so a strength in one half buys off a
weakness in the other.

The case that prompted this is the pivot. Kofod (Málaga) and Garly (ours) rate within a few
points on a single sum, but Kofod is creative and slow (Creativity 16, Pace 12) while Garly is
fast and less creative (Pace 19, Stamina 18, Creativity 10). With Garly at DMC (81 starts, at
least 60 minutes) we concede 0.94 a game against 1.33 for the next most-used DMC (45 starts);
that is unadjusted for opponent or era, but it matches the manager's read that the pivot has to
get back. A two-way view separates "can he create" from "can he recover" and shows that the
second is the one Kofod lacks.

Basketball analytics works the same way: a single plus-minus is split into offensive and
defensive halves, and positions differ in which half they earn their value in (centres in
defence, point guards in attack). The football equivalent is CBs and full-backs with an attacking
half (recycling possession, set pieces, overlapping) and attackers with a defensive half
(pressing, tracking back).

## Design

### 1. Two halves per position group

Each position group lists the attributes that make up its **attacking (O)** and **defensive (D)**
half. An attribute may sit in both (Pace for a full-back both overlaps and recovers). Draft lists,
from judgement, to be refined in step 3:

| Group | Positions | Defensive half | Attacking half |
|---|---|---|---|
| CB | DC | Tackling, Positioning, Aerial, Strength, Pace, Decisions | Passing, Technique, Decisions, Aerial |
| FB | DL, DR, DML, DMR | Tackling, Positioning, Pace, Stamina, Teamwork | Crossing, Pace, Dribbling, Passing, Movement, Stamina |
| DM | DMC | Pace, Stamina, Positioning, Tackling, Teamwork | Creativity, Passing, Dribbling, Movement |
| CM | MC | Tackling, Positioning, Stamina, Teamwork, Aggression | Passing, Creativity, Technique, Movement, Decisions |
| W | ML, MR, AML, AMR | Stamina, Teamwork, Tackling, Pace | Dribbling, Pace, Crossing, Technique, Movement, Shooting |
| AMC | AMC | Stamina, Teamwork, Aggression | Creativity, Passing, Technique, Dribbling, Shooting, Movement |
| ST | ST | Stamina, Aggression, Teamwork | Shooting, Movement, Aerial, Strength, Pace, Technique |

GK has no meaningful split and keeps its single rating.

### 2. Each half is a weighted sum, with every other attribute still counting

A half's score is the weighted sum of all 18 outfield attributes: its listed attributes at their
weights, every unlisted attribute at **0.5**. The rest of a player's game still matters, at half
weight, as the manager asked for the role ratings.

The draft lists above are superseded by the manager's own: each half opens with a sorting step
in which all 18 attributes are classed Key, Useful or Not relevant, starting blank so the draft
does not anchor the answer. Key attributes (2–6) are compared pairwise; Useful ones get a fixed
modest boost; Not relevant ones keep the 0.5 baseline.

### 3. Weights inside each half, and the balance between halves, come from AHP

The comparisons use a 7-step ratio scale (much / clearly / slightly better, equal: ×3, ×2, ×1.5,
×1), framed as a trade-off ("identical except +3 Pace or +3 Positioning: which is the better
defender?"), with sides and order shuffled. The coarse scale avoids the runaway weights a 1–9
scale produces; the redundancy of all-pairs comparison recovers finer gradations.

The analytic hierarchy process asks pairwise questions ("for a full-back's defending, how much
more does Positioning matter than Pace?") and turns the answers into weights, with a consistency
check that flags contradictory answers. One short questionnaire per half, plus one question per
position for the default balance between the halves. This replaces 1–4 judgement holds with a
recorded, consistent method, and it is the right tool for data this thin (see Validation).

### 4. Scale: percentile within the position

Raw half scores are not comparable with each other, because each half uses different attributes:
on the prototype every CB reads more defensive than attacking (Pedersen O 11.3 / D 15.2) and so
does every striker, because Stamina, Aggression and Teamwork are commonly decent. Each half is
therefore ranked against **every player natural at that position** (familiarity 15+) in the same
snapshot, giving an O percentile and a D percentile. A player's lean is then meaningful: "D 85th,
O 40th" says he is a defender's full-back, whatever the raw scales.

Only comparisons within a position are needed (the manager's requirement), so there is no
cross-position number to build.

### 5. Match-day blend: the duty switch the game doesn't have

```
rating(α) = D_pct^α × O_pct^(1 − α)       (weighted geometric mean)
```

The geometric mean makes the weaker half dominate, so a player has to be adequate at both to rate
well; α sets which half matters more. Each position gets a default α from the AHP balance
question (draft: CB 0.75, FB 0.5, DM 0.55, CM 0.45, W 0.3, AMC 0.25, ST 0.2). A per-slot
**Defensive / Balanced / Attacking** switch on the Builder moves α by ±0.2 for that slot only, so
"defensive left-back today" re-ranks only the full-backs.

## Validation, and what the data can and cannot do

The save records goal minutes (`mart.fact_match_event`, reconciled with every scoreline: 349/349
matches) and sub-on/off minutes (`mart.fact_player_match`), so **on-pitch goals for and against**
per player can be computed. First test, our players only, on minus off within the same season,
at least 600 on-pitch minutes (159 player-seasons, 66 players):

| | r |
|---|---|
| D half vs fewer goals conceded while on | 0.11 |
| Flat attribute average vs fewer conceded | 0.09 |
| O half vs more goals scored while on | 0.02 |
| Flat average vs more scored | −0.06 |

Per position the figures swing from −0.42 to +0.36 on 9–33 rows: noise. **Our matches alone
cannot fit the halves or prove them.** Goals are too rare, and team-mates are too collinear: XIs
change slowly, so players who always play together cannot be separated. Hence AHP for the
weights. The data is for:

- **Vetoes:** an attribute whose inclusion makes a half clearly worse on on/off goals or on the
  matching per-90 stats (interceptions and tackles won for D; key passes, dribbles and shots on
  target for O) is challenged in the AHP answers.
- **Sanity checks:** a well-known defensive player should rank high on D (Garly at DM is first
  on D among our DMs, 15.2).
- **Ridge later, if the data grows:** adjusted plus-minus (ridge regression of on-pitch goal or
  shot difference on who was on the pitch, with opponent and venue controls) is the principled
  outcome measure, because it removes team-mates. It needs more stints than we have. Opponents'
  players in our matches add stints but each opponent appears 2–4 times a season. Revisit once
  the store has several more seasons.

## Implementation sketch

1. `seeds/role_halves.csv`: `grp, half, attribute, weight` (AHP output), plus a
   `position_groups` mapping and the default α per group.
2. `int.player_two_way` (dbt): every player × natural position → O and D raw scores and
   percentiles within the position and snapshot. Raw CA/PA is not used, so no immersion issue.
3. A `site` mart carrying O/D percentiles per player and position; `scripts/export_data.py`
   ships it; `site/js` draws the two numbers and computes `rating(α)` in the browser. The blend
   is a single formula, so the SQL and the JS must agree on it to the last decimal, as role
   ratings do today.
4. Builder: a per-slot Defensive / Balanced / Attacking switch. Squad and Recruitment: O and D
   columns with the lean.
5. `scout-opponent`: recommend a defensive or attacking pick for a slot against a specific threat
   (e.g. a quick winger: D-leaning full-back on that side).

The existing role ratings (`frem_minmax_4231`) stay until the two-way view has earned its place.

## Open questions for the manager

- Are the draft half lists right? (Run the AHP questionnaire to settle weights.)
- Default α per position.
- Should Builder default to the blend, or keep the current role rating with O/D alongside?
