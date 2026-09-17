---
name: light-results-rolling-buffer
description: "SUPERSEDED — the region is the CLUB RECORDS tables, not a results list; the rolling-buffer/deletion story was wrong"
metadata:
  node_type: memory
  type: reference
---

# SUPERSEDED 2026-09-17 — this note was wrong about what the region IS

The original note (August 2026) concluded that the ~47 MB region holds simulated match
results in a 1.2 MB ring buffer, and that the engine **physically overwrites** old fixtures
so early-season games "physically cease to exist". Both halves are wrong.

**It is not a results list.** It is the **Club History** screens, per club: Team Records
(biggest win, biggest defeat, highest scoring match, longest streaks) and Player Records
(most goals in a season, youngest player, highest transfer fee). Decoded slot-for-slot
against in-game screenshots and parsed by
[`fmparser/clubrecords.py`](../../fmparser/clubrecords.py).

**Nothing is being deleted.** Three of six opening-day fixtures (16 Aug 2025) are present
with correct scores in a save dated 11 Jun 2026 — ten months later. The original authors saw
~13 rows per club and inferred a 13-game window; the real reason is that there are **~12
record CATEGORIES**.

Everything the note treated as evidence of a ring buffer has a simpler cause:

| observed | actual cause |
|---|---|
| ~13 rows per club | ~12 record categories |
| "fixtures stored in >=2 copies" | "Highest scoring match" and "Highest scoring LEAGUE match" are one game in two slots; a record in both the Overall and per-season table appears 4x |
| rows not in date order | they are in CATEGORY order |
| computed standings showing 5-13 games played | they were computed from record-holding matches |
| "multiple 1.2 MB arrays" | per-club blocks, one table each |

**What still holds.** These are real matches with real club tids and competition ids, so
`lightresults.club_leagues()` / `leagues()` remain sound as a club->league MEMBERSHIP source.
Do not build a fixture list or a league table from them.

Full write-up: [`docs/light-results-record.md`](../light-results-record.md). The hunt for
complete results continues in [`docs/TODO.md`](../TODO.md) #4 — and it is not in this region.
