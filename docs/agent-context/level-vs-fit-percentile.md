---
name: level-vs-fit-percentile
description: "Two percentiles in the dashboard: Fit %ile (tactic role-weights) vs Level %ile (CA-derived, tactic-agnostic); how to read them"
metadata:
  node_type: memory
  type: reference
  originSessionId: e454ef70-998b-4f22-a5f3-5cc24a02618f
---

**Every rated player now carries TWO percentiles**, both ranked within (position, league/nation/global):
- **Fit %ile** (`pctile_league/nation/global` in `effective_table`) — how well the player fits the
  *selected tactic's* role weight-set (e.g. frem_counter). High = good FOR OUR SYSTEM, not
  necessarily objectively good. Depends on the chosen method.
- **Level %ile** (`level_league/nation/global`) — a **tactic-agnostic quality** percentile derived
  from the game's overall-ability number (CA). Method-independent. Answers "is he actually a good
  player at this position for this level?"

**Immersion guard (house rule).** The raw CA/PA number is NEVER surfaced. `effective_table` selects
`* EXCLUDE (ca)` and computes `level_*` as `PERCENT_RANK(ca)` in the same window as the fit
percentiles — so only the *percentile* ever leaves the query. `ca`/`pa` must stay out of every
returned frame. This is an explicit allowed exception to "never surface CA/PA" (see CLAUDE.md); do
NOT delete Level %ile thinking it violates the rule. Surfaced as "Fit %ile" / "Level %ile" on Home,
Squad Tool, and Team pages (both our standouts and opponent key players).

**How to read the gap (Fit − Level)** — this is the decision aid:
- **Fit ≫ Level = "system player"** the tactic flatters. On Frem 22-start: Møller-Jensen DMC
  (Fit 58 / Level 2 — DM weighting over-rates a bottom-tier player), Herslov AMC (96/58),
  Aslani AML (99/72 — great fit + genuinely good, but not the literal best AML). Watch these when
  scouting/comparing — don't overpay on a fit-inflated rating.
- **Level ≫ Fit = under-used quality** — objectively good but wrong role for our system:
  Skovgaard MC (Level 96 / Fit 61 → use him as the DM anchor, not a mobile shuttler),
  Sørensen GK (90/73), Grønne/Sundstrup DC (88/75). Find a role that fits them.

CA↔frem_counter eff correlate only ~0.58, so Level adds real signal. CA is 100% populated across the
division. See [[role-weight-methods]], [[etl-duckdb-dashboard]].
