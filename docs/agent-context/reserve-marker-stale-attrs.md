---
name: reserve-marker-stale-attrs
description: "SOLVED: reserve-squad players read STALE attributes because the snapshot scan used only the first-team club marker; fixed via Career.squad_markers + attr_records"
metadata: 
  node_type: memory
  type: project
  originSessionId: c2b84fb3-998a-4381-ba2c-f3abcc2418da
  modified: 2026-08-18T22:55:10.676Z
---

**The reserve side keeps its OWN squad snapshot under its OWN marker** (`<reserve_tid u16 LE>
+ ff ff`), separate from `CLUB_MARKER` (built from the first-team tid). A player who moves
between the two lists keeps a record under BOTH; the copy under the club he is **currently**
in is live, the other **freezes on the day he left that list**. Scanning only the first-team
marker returned stale attributes for every reserve player.

**Diagnostic signature: a player's attribute row is byte-identical across many consecutive
snapshots.** Real players (especially youth) move; a frozen row means you're reading a
dead copy. Found 2026-08-19 when the user said Hervé Buur (tid 3733) "should have 16 pace"
and the store said 10 — his row hadn't changed across eight snapshots since Jul 2022.

Ground truth in `denmark-24-start.fms` (in-game 2023-07-01):
`@58.954M marker 346 -> Pace 10` (stale) vs `@58.975M marker 7296 -> Pace 16` (real).

**Fix shipped:** `careers.Career.squad_markers` → (first-team, reserve);
`attributes.attr_records()` returns one record per marker; `attributes.squad_snapshot_bounds()`
unions the per-marker windows; `extract.build_database` picks the record whose marker matches
the player's current `club_tid`. Re-extraction changed exactly 7 of 42 frem squad rows, **all
club 7296**, zero first-team movement — that split is the regression guard to re-run.

**No matching marker -> USE THE ESTIMATE (2nd fix, same day).** A player out on LOAN or sold
keeps his frozen record under our marker for months, and serving it labels stale data
`estimated=False` ("exact") — worse than an honest +/-1. `_pick(..., strict=True)` now returns
None for ATTRIBUTES when no marker matches the player's current `club_tid`, so he falls through
to `estimate_player`, the same global scrape every non-managed player uses. Names keep the loose
fallback. Buur four days before truth: frozen said Pace 10 / Dribbling 3; the estimate said
16 / 8; truth was 16 / 8. **Payoff: a loaned-out player's development is now visible** — Buur
reads Pace 10 -> 12 -> 16 across his loan instead of a flat false 10. Blast radius: 7 players per
late-22/23 frem snapshot flip exact->estimated, only 2 of 41 current-squad rows move.

**Exact attributes exist ONLY for our two clubs.** Scanned other club markers (702, 2713, 5000):
zero records. So there is no loan-club snapshot to read — a loaned-out player's exact attributes
are simply not in the file, and the estimated scrape is the best available (and it is good:
pace/physicals come back exact even there).

**RESOLVED (not open): out-of-bounds clusters are OLD writes — never widen `snapshot_bounds`.**
The clusters ARE cleanly filler-delimited (620 KB of ~90% 00/ff between them), so finding them is
easy — but they are stale. Proof: Nordberg's copies vs his 11-May-2023 screenshot — cluster-0 LAST
copy matched all 17 attributes exactly, cluster-0 first copy got 14 wrong, the outer cluster 6
wrong. Squad-wide, 35 of 38 outer copies are byte-identical to a reading from a save 7 MONTHS
earlier (vs 6 of 38 for the in-bounds-last copy). So "last copy within snapshot_bounds" is right
and widening would regress it. §7.2's per-record freshness flag is not needed here.

Full write-up: `docs/ATTRIBUTE_DECODING.md` §7.3. Related: [[seyhun-attr-investigation]]
(the in-bounds multi-copy case), [[denmark-region-drift]], [[phase-is-date]].
