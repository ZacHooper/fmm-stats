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

**Team instructions (attack) — pick one from each pair:**
- Early crosses OR Look for overlap
- Shoot on sight OR Work into box
- Run at defense OR Through balls

**Passing style (pick one):** Short, Mixed, Direct, Long
**Passing focus (pick one):** Left, Centre, Right, Both flanks, Mixed
**GK distribution:** Short, Long, Mixed

Relates to [[fm-parser-project]] and [[etl-duckdb-dashboard]] (attributes come from v_player_attributes).
