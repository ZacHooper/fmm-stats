# Rule files → contract grid, 3: formation presets

The third of five sub-tables between the [rule files](../rule_files.md) and the
[contract grid](../contracts.md), on both games. Before it: the
[season-year blocks](rf_season_years.md); after it: the [team selections](rf_team_selections.md).

| save | from | to | size |
|---|---|---|---|
| truro-2026-11-16 (FMM27) | 27,855,893 | 27,882,395 | 21 × 1,262 B |
| frem-2026-06-11 (FMM22) | 20,596,963 | 20,623,465 | 21 × 1,262 B |

## Known

- **21 records of 1,262 bytes on both games**, the same size on every save. Each holds
  `76 b9 f4 07` and then a formation name: 18 of the 21 read as formations (3-4-3, 4-1-2-2-1,
  4-1-4-1, 4-2-1-3, 4-2-2-2, 4-2-3-1, 4-2-4, 4-3-1-2, 4-3-2-1, 4-3-3, 4-4-1-1, 4-4-2,
  4-5-1, 5-1-2-2, 5-2-1-2, 5-2-2-1, 5-3-2, 5-4-1); FMM22 stores them in a different order
  (4-4-2 first).
- The same `76 b9 f4 07` + formation string opens the managed club's four saved tactics
  ([alt_managed_club](alt_managed_club.md)) and the tactics in [our matches](../matches.md),
  so this is the game's stock formation list in the tactic layout.
- The bytes in front of the team selections (`21 22 55 15 0a 00 00 00` repeated, then
  `12` × 11) close the last preset; the same run sits inside the saved tactics.

## Next

Read one preset field by field against the Tactics screen for that formation (positions, roles,
instructions), then reuse the layout for the saved tactics.
