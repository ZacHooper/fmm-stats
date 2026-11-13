# Rule files → contract grid, 1: head slots

The first of five sub-tables (two now read) between the [rule files](../rule_files.md) and the
[contract grid](../contracts.md), on both games. The others:
[season-year blocks](rf_season_years.md), [formation presets](../formations.md),
[team selections](../team_selections.md), [the tail](rf_tail.md).

| save | from | to | size |
|---|---|---|---|
| truro-2026-11-16 (FMM27) | 27,331,049 | 27,331,493 | 444 B |
| frem-2026-06-11 (FMM22) | 20,021,621 | 20,021,849 | 228 B |

## Known

- **FMM27**: `ff ff ff ff 00 00`, then **73 six-byte slots** `[ffffffff][u16 1]`, the last
  `[ffffffff][u16 65,281]`. None filled on any Truro save.
- **FMM22**: **19 twelve-byte entries** `[ffffffff][u16 0x1d][u16][u16][u16 0x10]`, e.g.
  `ff ff ff ff 1d 00 78 00 7a 00 10 00` (frem-2026-06-11: 120, 122). The two middle u16 move
  between saves (2021: 124, 124; 2023: 121, 120). The same 19 on every FMM22 save, Bucaspor too.

## Next

Compare the FMM22 middle u16s with the save's date or season. Fill something FMM27's 73 slots
might hold (73 is not a count we know).
