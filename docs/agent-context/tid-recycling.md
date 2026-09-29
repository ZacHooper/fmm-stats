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


## Two ways a tid stops meaning one person (found 2026-09-23)


   **Two mechanisms found 2026-09-23, doing a "where are they now" retrospective — the second
   one CONFIRMED with hard evidence, not just a lead.** Both came from `tid`s that stopped
   matching one real person over the save's life; neither is the 6,077-sid gradual-shortening
   pattern itself, but both are candidate contributors worth checking against it.

   **(a) `is_staff` flipping `True` truncates the player-history walk.** Two Frem players (tid
   9231, 9430) had `mart.player_career_seasons` come back completely empty despite a full, real,
   multi-season history (including their move away from Frem) in every prior snapshot.
   `f.staging.player_history_seasons` by tid across every season/phase shows the chain intact
   and growing right up to `2026-07-02`, then **zero rows at `2027-04-25`**, the very next
   snapshot, for both — a hard cutoff, not a gradual shortening. `staging.players.is_staff`
   reads `False` at `2026-07-02` and `True` at `2027-04-25` for both.

   **(b) A `tid` is a recycled slot, and `staging.players.name` does NOT reliably change when a
   new person takes it over — confirmed by comparing `dob`, not just believing the name.** Two
   more Frem players (tid 9584 "Mikkel Bruhn", tid 9400 "Mikkel Andersson") went through the
   same `is_staff` cutoff as (a) — full history, then `is_staff=True`, unattached, for several
   snapshots — and were read as "retired." But `SELECT DISTINCT dob FROM staging.players WHERE
   tid=<tid>` returns **two** birth dates for each: the original (1990-10-16 for Bruhn,
   1990-03-17 for Andersson) through the `is_staff=True` snapshots, then a completely different,
   much younger `dob` (2009-10-19 / 2008-08-26) from the snapshot where `is_staff` flips back to
   `False` at a small foreign club — **while `name` stays "Mikkel Bruhn" / "Mikkel Andersson"
   throughout, unchanged.** This is not the two real players un-retiring; it's the tid being
   handed to an unrelated newgen, with the OLD display name incorrectly carried onto the new
   occupant. A third case makes clear this isn't universal: tid 4240 ("Thomas De Clercq," a
   Belgian signing who himself went `is_staff=True` in March 2022) was reassigned to a genuinely
   new player from 2022-07-01 — and there, **`name` DID update correctly** (to "Johan
   Nordberg", dob 2005-08-18), while `player_spells`/raw history, queried by bare tid with no
   `dob` filter, still blended the old occupant's real transfer history (from Belgium's KSV
   Bornem) onto the new one's card, since nothing before Nordberg's first Frem season belongs to
   him. So the bug isn't consistently "name never updates" — case (b) and case 4240 disagree on
   that — but a **`dob` mismatch always exposes it**, and it happened at least three times in
   one squad's worth of players. **Next step: find what actually determines whether `name`
   refreshes on recycle** (case (b) vs tid 4240) — likely something about how long the tid sat
   in the `is_staff`/unattached state, or which code path resolves `name` for an unattached
   record vs a freshly-assigned club one, but neither has been checked yet.

   **Practical fallout, already applied to the skill and its published output**: don't trust
   "no career-history chain" as evidence of a free-agent origin (an early guess in
   `.claude/skills/where-are-they-now/SKILL.md` that turned out wrong for reason (a)), and don't
   trust a stable `name` across a gap as evidence you're looking at the same person (wrong twice
   over for reason (b), corrected in the two published `where-are-they-now` retrospective
   artifacts after the human reviewer noticed neither name currently exists as a player
   in-game). **Always run the `DISTINCT dob` check per tid before writing up a "the trail goes
   cold" or "here's their new club" story.**
