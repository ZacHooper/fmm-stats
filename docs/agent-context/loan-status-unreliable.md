---
name: loan-status-unreliable
description: The loaned_out / squad_status flag in fm.duckdb is stale/wrong — never use it to judge availability or filter squad selection
metadata: 
  node_type: memory
  type: project
  originSessionId: 681be847-7279-4c83-87e8-ccd414e19fd8
---

**IGNORE `staging.players.loaned_out` and `squad_status` for availability / selection.** The
user confirmed (2026-07-28) it's outdated: e.g. Selahattin Seyhun (tid 22908) reads
`loaned_out=True` but is a first-choice starter — ST eff 407 (86th pct), 26 goals in 2255
mins last season. It comes from `scrape_contract_status` (a separate structure), NOT the
attribute-snapshot reads we fixed in [[seyhun-attr-investigation]], so it was never corrected
and appears to be a stale copy / wrong code interpretation.

**How to apply:** when analysing the squad (rotation, best XI, scouting, availability), treat
EVERYONE in `db.squad()` as available and rank by **minutes played** (`match_player_stats`,
`team_tid=6567`) + eff rating + age. Do NOT filter on `status=='First team'` /
`loaned_out` — doing so silently drops real regulars (it hid Seyhun, Yusuf Can Abay (MC, eff
427/99th pct), and Özcan Sertgöz from a rotation analysis). The dashboard still labels some
players "Loan"/"Reserve" from this field — that labelling is not trustworthy.

Possible cleanup later: suppress or re-derive the loan/status field, or stop surfacing it.
Related: [[etl-duckdb-dashboard]] [[preseason-squad-review]]
