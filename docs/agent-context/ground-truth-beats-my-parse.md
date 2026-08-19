---
name: ground-truth-beats-my-parse
description: "When the user's in-game reading disagrees with my parse, suspect the PARSE — and read their screenshots directly rather than a summary of them"
metadata:
  type: feedback
---

**When the user's in-game ground truth conflicts with what the parser says, the parser is the
suspect — not their reading.**

**Why:** 2026-08-19, decoding career history. The user transcribed a screenshot as "Dirksen: only
Holbæk 09/10 -> 16/17, then on a free to Frem **17/18** -> 22/23". My parse said he joined Frem in
18/19. I wrote their version off as "a one-year transcription slip" and moved on. It was not — my
reading rule was off by one (the club column leads the stats by one row). Their transcription had
been right the whole time, and treating it as noise cost a detour into a wrong season-base theory
("base is 1970?") that never made sense. A second case the same day: I reported Thrane's B36 row as
"missing from the table"; it was present, just an unresolvable club NAME.

**How to apply:**
- A single disagreement between parse and ground truth is a lead, not an outlier. Chase it before
  explaining it away — especially before writing the explanation into docs as fact.
- **Read the screenshots directly** (the Read tool renders images) instead of working from typed
  notes about them. Everything ambiguous in this session was unambiguous in the image.
- Prefer ground truth with a **checksum**: the FM History screen has a TOTAL line, and totals catch
  off-by-one errors that individual rows hide (an extra row or a dropped one both break the sum).
  Four of five per-season stat lines were also globally unique in a 265k-row table, which made
  "search the whole table for the real numbers and see where they land" decisive.
- Don't diagnose from a resolved NAME (club/player) — check the id. See [[name-resolution]].

Related: [[user-supplied-save-date-wins]] (same principle for save dates — the user's stated
in-game date beats the derived one), [[history-chain-pointers]], [[player-history-table]].
