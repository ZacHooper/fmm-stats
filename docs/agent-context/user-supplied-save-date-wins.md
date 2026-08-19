---
name: user-supplied-save-date-wins
description: "When the user states a save's in-game date, use it as the phase — the last-match date is only a rough guide and is often wrong"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: c2b84fb3-998a-4381-ba2c-f3abcc2418da
  modified: 2026-08-18T23:06:57.409Z
---

**If the user gives the in-game date for a save, use THAT as the `phase`** — pass it via
`--phase` rather than letting the loader derive it.

**Why:** `phase` is derived from the **latest match date** in the save, but the user often plays
on past the last fixture before saving, so the two diverge — sometimes badly. Confirmed cases in
the frem career: `denmark-23-mid-start-of-winter.fms` derives 2022-11-19 (last match before the
winter break) but the weekly Player-Progress grid runs to **2023-01-06**, which is the real save
date — a seven-week error. The two end-of-season 22/23 saves both derive 2023-05-28 yet are
really 26 and 30 June, and collide on one phase unless overridden. The user's words:
*"The last match date is not always accurate to the in game date. It's only useful as a rough
guide."*

**How to apply:** ask for / accept the date, load with
`--season <end-year> --phase <YYYY-MM-DD>`. A cheap independent cross-check on the real save
date is the **end of the weekly Player-Progress grid** (see [[injury-progress-decode]]) — it runs
to the save date, so its last week dates the save even when no matches were played.

Related: [[phase-is-date]] (phase = in-game date convention).
