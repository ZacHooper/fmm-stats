---
name: tid-recycling
description: "A tid is a SLOT not a person — FM reuses retired players' tids for newgens (829 frem / 1503 buca swaps); use (tid,dob) as the person key"
metadata: 
  node_type: memory
  type: reference
  originSessionId: c2b84fb3-998a-4381-ba2c-f3abcc2418da
  modified: 2026-08-18T23:43:41.906Z
---

**FM reuses a retired person's tid for a newgen**, so `tid` is a slot, not an identity.
Measured 2026-08-19: **829 identity changes in `fm-frem.duckdb`, 1,503 in `fm-buca.duckdb`.**
Any cross-save join keyed on tid alone splices two people into one fake career.

**Shape of a swap** (829 frem): outgoing mean age **41.3**, 95% free agents, only 3.5% have
attributes — usually a dormant retired name. Incoming mean age **16.9**, 68% exactly 16, 100%
have attributes. Swaps come in **off-season bursts** (the newgen intake); mid-season snapshots
see almost none.

**Nothing is inherited from the previous occupant.** Over the 1,098 swaps where the outgoing was
a real player with attributes: primary position matches 12.4% (chance ~10%), GK-vs-outfield 79.5%
(chance ~79% — GK→ST/DR/DMC is common), preferred foot 65.1% vs **chance 65.3%**, nationality
17.7%. The tid is just a free slot. Don't be fooled by near-misses like De Clercq (AMC:20/ST:14)
→ Nordberg (AMC:20/ST:15) — that is coincidence.

**USE `(tid, dob)` AS THE PERSON KEY.** dob separates all 2,332 identity changes across both
stores with **0 collisions and 0 nulls**. Name is mutable and non-unique; dob is neither.

**IMPLEMENTED 2026-08-19 (phases 1-2), no re-extraction needed** (dob already in every players
slice): loader builds `staging.persons` + `staging.person_slices`; `person_id` = `'<tid>-<dob>'`.
`db.keep_current_person(df)` drops rows belonging to a previous occupant of a tid (no-ops when
nothing in the frame was recycled); `db.person_history(tid)` audits a slot. Guarded: Development
attribute chart, player_role_series, squad_role_series, primary_position_map, injuries/loans.
Phase 3 still TODO: match aggregates (latent — 0 spliced tids today) and retention.

**Why it matters beyond dedup:** keying on tid alone means a player who retires out of OUR squad
**loses his history** as soon as a newgen takes the slot. `(tid, dob)` keeps both as distinct
persons so retired players' match stats/injuries/attributes stay queryable. Current mitigation
`dashboard/db.py::_identity_snapshots(tid)` only restricts a union to snapshots where the tid
carried its CURRENT name — right for "show me this player", but it **discards** the earlier
occupant. The retain-retired-players case is NOT yet handled (user flagged it as a real if
edge-case concern).

**Frem's own intake, all recycled tids:** Demyttenaere→Adelgaard, Tab Ramos→Buur, De Clercq→
Nordberg (all 2022-07-01), Thieren→Louka Pingel (2023-07-01). Two of those four outgoing
identities were REAL players with attributes (De Clercq AMC rep 1750; Thieren a **goalkeeper**
rep 3000) — so "the outgoing side is always a harmless shell" is false.

Full write-up: `docs/IDS.md` § TID RECYCLING. Related: [[injury-progress-decode]] (where the
gotcha first bit), [[reserve-marker-stale-attrs]], [[name-resolution]].
