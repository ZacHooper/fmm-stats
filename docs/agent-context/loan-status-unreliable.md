---
name: loan-status-unreliable
description: Squad status is not a loan flag and not availability — loans out come from Player Progress (mart.loan_out_spells); there is no loaned_out column
metadata: 
  node_type: memory
  type: project
  originSessionId: 681be847-7279-4c83-87e8-ccd414e19fd8
---

**There is no `loaned_out` column any more, and `squad_status` must not be used to infer
one.** `loaned_out` used to be derived from the training row's squad-status byte, and it was
wrong: Selahattin Seyhun (tid 22908, Bucaspor) read `loaned_out=True` while a first-choice
starter — ST eff 407 (86th pct), 26 goals in 2255 mins. The user confirmed (2026-07-28) the
flag was outdated, and (2026-10-01) that training should not decide who is loaned out, so the
data-layers step 7 stopped deriving it.

`squad_status` is still carried (`raw.training.squad_status`, `mart.player_snapshots`) as the
raw contract term it is — a code on the training row, not a statement about availability.

**Who is out on loan:** `mart.loan_out_spells` for now, drawn from the weekly Player Progress
rows (`raw.player_progress` via `mart.progress_weeks`). In the semantic model
([`docs/data-model/contract-transfer.md`](../data-model/contract-transfer.md)) a loan is
`fact_loan_spell`, in the contracts-and-transfers area (data-layers step 16): a spell on top of
an unchanged contract, never a transfer and never a contract at the borrowing club. The
squad-status "loaned out" code is kept only as a CHECK against that spell, never as its source. **Who is ours:** `mart.squad_current` /
`mart.squad_on('<date>')`. `loaned_in` survives in `mart.player_snapshots` only for the parent
club's name; the save never clears it, so it is not evidence a loan is live.

**How to apply:** when analysing the squad (rotation, best XI, scouting, availability), treat
everyone in the squad as available and rank by **minutes played** + rating + age. Do NOT
filter on `squad_status` — doing so silently drops real regulars (it hid Seyhun, Yusuf Can
Abay (MC, eff 427/99th pct), and Özcan Sertgöz from a rotation analysis).

Related: [[etl-duckdb-dashboard]] [[preseason-squad-review]]
