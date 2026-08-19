---
name: injury-progress-decode
description: "SOLVED (partial): FMM 'Player Progress' weekly table decoded — per-player weekly skill ratings + an injury flag; gives injury count+length for our squad incl. training injuries"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 688e0f6a-5453-4b6d-a360-1b5c36799636
---

**The in-game "Player Progress" page (weekly skill graph + Injured/Off-Season/On-loan bands) is
stored as a per-player weekly table** in the Frem saves at **~47–49M** (`0x02d00000–0x02f00000` in
`denmark-mid-w-loans-22.fms`, the 26-Jun-2022 save). This is how we get **injury count + length**
for our squad — including **training injuries that match-events miss** (`match_events type='injury'`
only catches in-match ones; see [[match-minutes-condition]]).

**Record layout** (found by searching a player's TID as u32-LE in the zone; each weekly entry):
- `+0`  : player TID (u32) — the search key.
- `+4,+6,+10,+12,+14` : the **five skill-category lines** (Physical / Mental / Attacking /
  Defending / Overall), each ~5–14, matching the graph. (`+8` often `0xFFFF` = N/A.)
- `+16` : **status BITFIELD (u16)** — SOLVED 2026-08-18:
  - bit0/bit1 (`1`,`2`) = **INJURED** that week (`flag & 3`).
  - **bit5 (`32`) = OUT ON LOAN** — the graph's on-loan band, exact weekly windows.
  - bit4 (`16`) = the single off-season week at the season boundary.
  - `8`/`64`/`65` are NOT status: they only appear on **off-grid dates** at +70/+140 bytes,
    i.e. bytes from the interleaved SECOND table. Don't read them.

  **How bit5 was pinned (the discriminator that matters):** it is NOT "in the reserve squad".
  Probed `denmark-23-mid-start-of-winter.fms` — Dirksen is registered to Frem RESERVES and
  never carries bit5, while Balck is registered to the FIRST team and carries it for 48 weeks.
  It tracks the **loan**, not the squad. Wedege/Davidsen/Møller-Jensen carry it across both
  seasons (user named Wedege as a known loan-out). **Players loaned IN are never flagged** —
  from this save's point of view they are here, not away; use `players.loaned_in` for those.
  Earlier probing with Nuamah (a loanee IN) is what made this look undecodable — wrong subject.
- `+20` : week date `[day-of-year u16 (0-based, like DOB)][year u16]`.

**Reconstruct injury spells:** collect weeks where `+16 ∈ {1,2}`, group runs ≤8 days apart → one
spell each. **Validated exactly** against user ground truth (Randolf twisted-knee 22 May, Bruhn
thigh 27 May, Bramsborg broken-nose 10 Jun, Tånnander Apr+Jun). Frem 21/22 (26-Jun save): **12
spells / 9 players**.

**Gotchas / still open:**
- Series spans the FULL season (~1 Sep → 30 Jul); a naive `year==2022` filter DROPS the 2021 half
  (miss e.g. Nuamah's Sep/Oct injuries). Parse both halves.
- **Two interleaved copies** ~70 bytes apart (the "domestic vs internal" tables) → dedupe by date.
- Stride is irregular (per-player blocks, not a fixed grid) — locate each player's entries by TID
  search within the zone, don't assume a fixed stride.
- **Injury TYPE + SEVERITY are NOT here** — they live only in a separate *current*-injury record
  (the domestic injury table; active injuries only). Not yet located; user is fine skipping it.
- Our-squad-only region (opponents not present) — which is all the user wants.
- Zone offsets are Frem-tuned & per-save; re-derive per save/career (region drift, see
  [[denmark-region-drift]], [[savefile-boundary-map]]).

Productionization: DONE — `fmparser/injuries.py` → `staging.player_injuries` → `db.player_injuries`
(Awards) and `db.player_injury_spells(tid)` (Development → Player detail).

**Loan history = THREE sources, best-first** (see `db.player_loan_spells`):
0. **`staging.player_loans`** — bit5 of THIS table: exact weekly windows for loans OUT. No club
   name (the weekly record doesn't carry one); fold in a matching history row to name it.
1. `staging.player_history_seasons.fee = 'loan'` — a season at a named club with apps/goals,
   for any player, back through their whole career. Only some snapshots parsed it fully
   (Frem: `start` + `2022-03-19` have ~20k players; later phases ~100), so take the snapshot
   with the most rows for that player.
2. `staging.players.loaned_in` + `parent_club` across dated snapshots — for players loaned IN
   to us; bounds are SNAPSHOT dates, not real transfer dates.

**Cross-save union is mandatory for both.** A save's weekly series spans only {season-1, season},
so a spell an early save recorded is absent from later ones, and a loanee's progress data leaves
with them when the loan ends. `db.player_injury_spells` unions every snapshot then merges ranges
within 8 days (loans use 22 days, so the off-season week doesn't split one loan in two).

**Gotcha for any career-wide union: FMM RECYCLES TIDS on regen.** tid 3733 is "Tab Ramos" (free
agent) in the 21/22 saves and "Hervé Buur" at Frem from 22/23 — unioning on tid alone splices two
people together. `db._identity_snapshots(tid)` restricts the union to snapshots where the tid
carried its CURRENT name. Apply the same guard to any other cross-save per-player join.

**The weekly grid runs to the season END**, so a spell in force at the save date extends past it —
its end date is SCHEDULED, not observed (Wedege's loan reads to 2023-01-06 in a 2022-11-19 save).
`player_loan_spells` flags those `ongoing`.

Related: [[phase-is-date]] made this possible by giving every snapshot a real date.
