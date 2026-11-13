# After the season stats, 2: grouped 14-byte tid rows

The second of three sub-tables between the [player season stats](../player_season_stats.md) and
the [career-history pool](../history.md), after the [125 records](sst_records.md). FMM27 only.

| save | from | to | size |
|---|---|---|---|
| truro-2026-11-16 | ~45,928,922 | ~45,969,882 | ~41 KB: about 2,900 × 14 B |

## Known

- **14-byte rows** `[tid u32][u16][u16][u8 0][u16 group][u8][u16 0x0120]`, e.g. `35 15 00 00 a2
  06 04 01 00 b3 00 02 20 01`. Within a group the tids ascend; one group of 157 rows (group
  0xb3, the u8 = 1) runs 45,929,086 → 45,931,284.
- The group u16 reads 0xb1, 0xb2, 0xb3 and the u8 1, 2 or 3; the second u16 is 207, 220 or
  230 on most rows (days of the year: 26 Jul, 8 Aug, 18 Aug?). The first u16 varies freely
  (971–5,981).
- Then about 1.3 KB of 10-byte rows `[u32][u16][u16][u16]` (`ea 42 00 00 2a 01 00 00 aa 00`)
  up to the [named records](sst_named.md).

## Next

Look the tids up (whose players, which clubs) and read the group key against competitions or
days.
