---
name: fmm-tactic-options
description: "FMM22 (mobile) tactical options available to the user — role lists + team instructions, for tailoring tactical advice"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 6056134e-7972-47a0-8795-5fb9301fdd09
---

User plays **Football Manager Mobile (FMM22)** — far fewer tactical levers than desktop FM. No player instructions at all; the only per-player tweak is **man-marking in defensive positions**. So all advice must work within these menu options:

**CM roles:** AP, RP, B2B, CM, DLP, BWM
**DM roles:** DLP, RP, BWM, CM, Anchor

The tactics screen has six tabs: **Formation · Shape · Defence · Attack · Set Pieces · Captain**.
Every lever below is read off one of them, so when a session needs to know how we are set up, ask for
the **Shape**, **Defence** and **Attack** screenshots — those three carry all of it.

**SHAPE tab — team instructions:**
| Lever | Options (left → right on screen) |
|---|---|
| Team Mentality | Contain · Defensive · Counter · Balanced · Control · **Attacking** · Overload |
| Width | Narrow · Balanced · Wide |
| Tempo | Slow · Normal · Fast |
| Creative Freedom | Disciplined · Balanced · Expressive |

(Mentality is laid out as three rows of two-plus-one on the mobile screen, not a single slider —
Contain/Defensive, then Counter/Balanced/Control, then Attacking/Overload.)

**DEFENCE tab:**
| Lever | Options |
|---|---|
| Defensive Line | Deep · Balanced · High |
| Closing Down | Sit Back · Own Half · All Over |
| Tackling | Cautious · Normal · Committed |
| Offside Trap | No · Yes |
| Time Wasting | No · Yes |

**ATTACK tab — pick one from each pair:**
- Early crosses OR Look for overlap
- **Shoot on sight OR Work into box**
- Run at defense OR Through balls

**Passing style (pick one):** Short, Mixed, Direct, Long
**Passing focus (pick one):** Left, Centre, Right, Both flanks, Mixed
**GK distribution:** Short, Long, Mixed

**Roles are set per position on the Formation tab** and are what the screen labels each player with
(AF, AP, BBM, BWM, DM, W, IW, WB, FB, CD, PF, P …). Two things follow: a role label belongs to
whichever club's screen you are reading — say whose — and **a `role_weights` method is NOT a tactic**.
A method only weights attributes for rating; it sets none of the levers above. See
[[fmm-tactic-blueprints]] for which settings to actually pick.

Which settings to choose, and what has been tried: [[fmm-tactic-blueprints]].
Relates to [[fm-parser-project]] and [[etl-duckdb-dashboard]] (attributes come from v_player_attributes).
