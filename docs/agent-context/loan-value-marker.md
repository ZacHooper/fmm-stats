---
name: loan-value-marker
description: "SOLVED: a loaned-in player's exact attribute+value record is anchored by [parent_club_tid][managed_tid], not [club][0xffff] — attributes.loan_marker(). Also: audited whether anything is hardcoded for reserve players and found no bug — 2 of 3 reserve misses are genuinely absent from the save."
---

**The finding: a loaned-IN player's exact record uses a different marker shape.** An owned
player's attribute+value block is anchored by `tid + 8 bytes == [club_tid][0xffff]`
(`attr_record`'s `CLUB_MARKER`). A loanee's block sits at the **identical relative offset**,
but the 4 bytes there are `[parent_club_tid][managed_tid]` (both u16 LE) — no `0xffff`. This
is the same loan pair `own_squad_full` already uses to find loanees on the squad LIST
(`tid = mm[j-10:j-6]`, `parent = mm[j-2:j]`); it turns out to anchor the ATTRIBUTE record too,
just nobody had tried it there.

Verified byte-for-byte on `frem-2024-11-10`: Emil Rosberg Møller (parent 344, us 346) has
`58 01 5a 01` sitting at the exact `M` offset where Adam Jakobsen (owned) has `5a 01 ff ff` —
same `attrs`/`positions`/`feet`/`value` layout around it. Decoded for all 5 current loanees
and every one comes back sane (1-20 attributes, plausible positions, real transfer fees
£604K-£2.9M) where before every one of them silently fell to the ±1 estimate path with no
value at all.

**Fix shipped** (2026-08-30): `attributes.loan_marker(managed_tid, parent_tid)` builds the
marker; `extract.build_database`'s `own_exact` loop tries it first for any tid `own[tid]`
marks `loaned_in` (using the `parent_club_tid` that scan already found), falling through to
the existing owned/reserve path — which for a loanee already correctly returns nothing, so
there is no regression risk to the non-loan path.

## The other half of the ask: is anything hardcoded that's causing a RESERVE miss?

No bug found. Audited the whole reserve squad (3 players — the only 3 at `club_tid=7296` in
this snapshot) against every hardcoded assumption in the pipeline:

- **`squad_snapshot_bounds`'s union window vs the full hit range**: real, but not the cause
  here. The reserve marker's *raw* hits span into a second region (~61.5M+) that
  `snapshot_bounds`'s clustering doesn't include in its returned window — the same
  already-documented tradeoff `attr_record`'s docstring calls out for the club marker
  ("a minority of players whose live copy lives in a separate secondary list... resolve to
  their freshest IN-REGION copy"). Checked directly: neither of the 2 missing reserve
  players (Adelgaard, Fugl) has ANY reserve-marker hit anywhere in the 63 MB file, bounds or
  no bounds — a full unrestricted `mm.find` sweep, not a bounds artifact. The save genuinely
  never wrote them a reserve squad-list record this snapshot.
- **`reserve_tid`/`managed_tid` (careers.py)**: cross-checked against `club_record()` —
  resolve to "Boldklubben Frem Reserves" / "Boldklubben Frem" correctly, not stale.
- **`own_squad_full`'s hardcoded tid range `1000 < tid < 70000`**: our closest squad members
  are tid 1007 and 1451 — safely inside. Nobody in the info spine sits outside the range
  (tids ≤1000 belong to non-player ids like staff/managers, not real reserve squad members).
- **`own_squad_full`'s parent-club range `1 <= parent < 70000`**: max real club_tid seen
  anywhere is 65535 (the `0xffff` "no club" sentinel, already excluded elsewhere) — nothing
  legitimate sits near the boundary.

So: **the reserve miss is real save data absence, not a decode bug.** The one player who does
have a live reserve-marker record (Valdemar Frahm) decodes correctly with exact attrs and a
real value. This matches [[reserve-marker-stale-attrs]]'s precedent (Hervé Buur) — falling
through to the estimate is the *correct* honest behaviour when no live copy exists, not a gap
to force-fix by trusting a frozen first-team copy.
