# After the season stats, 1: 125 variable records

The first of three sub-tables between the [player season stats](../player_season_stats.md) and
the [career-history pool](../history.md). The others: [grouped tid rows](sst_tid_groups.md),
[named records](sst_named.md).

| save | from | to | size |
|---|---|---|---|
| truro-2026-11-16 (FMM27) | 45,832,154 | ~45,928,922 | ~96.8 KB |
| frem-2026-06-11 (FMM22) | 42,545,168 | 42,630,093 | 85 KB, the whole region, not split |

## Known

- **FMM27** opens with a u32 **125**, then `9b 13 00 00 00 01 fb 00 00 00 01 00 3a 01 00 00
  03 01 3c 24 …`. The rhythm changes every 0.5–2 KB (strides 4, 8, 24, 32, 48, 64), so the
  records are long and of varying length: 125 records of ~770 B on average.
- Truro's tid (`35 0c`) recurs all through it (at +1,482 as `78 09 00 00 … 35 0c 00 00`), along
  with u16 day-of-year values (0x011e, 0x0130 …) and the year 2026 (`ea 07`).
- **FMM22's 85 KB here** (the whole region) opens `32 00 00 00 1b 00 00 00 01 00 c9 11 …`: a u32
  50 in the same place, then rows of two u32 and a u16 nation id (`8b`, `a3`, `a7` …).

## Next

Walk the 125 records: find the record head that repeats (`9b 13 00 00 00 01` opens the first
and recurs at +36,868), and check whether the 125 grows between the Truro saves.
