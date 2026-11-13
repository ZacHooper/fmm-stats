# After last transfers, 4: one 16-byte row per person

Between the [last transfers](../last_transfers.md) and the [name id-tables](../names.md), one of five sub-tables there on FMM27 (the others: the [unread index](README.md)). On both games.

| save | from | to | size |
|---|---|---|---|
| truro-2026-11-16 | 41,611,956 | 42,331,316 | 719 KB: 44,960 × 16 B |
| frem-2026-06-11 (FMM22) | 39,514,743 | 40,042,199 | 527 KB: 32,966 × 16 B, ending under the [match-slot table](../match_slots.md)'s first slot |

## Known

- **One row per person, row = tid**: 44,960 rows, the person count of
  [person_info](../person_info.md), [contracts](../contracts.md) and [training](../training.md).
  No count in front. Read against Truro's players (row at `start + 16 × tid`), the fields
  vary player by player.

  | offset | type | seen |
  |---|---|---|
  | +0 | u8 | 92 for most, 75, 88, 100; 0 on some |
  | +1 | u16 | **a day of the year**: 203 (22 Jul, the career's first day) on rows untouched since, 319 (16 Nov, the save's day) on every Truro player, 277, 313–317 between |
  | +3 | u8 | 0 or ff |
  | +4 | u16 | 10,000 by default, else 8,400–9,999 (a hundredths-of-a-percent scale?) |
  | +6 | u16 | the same: 10,000 by default |
  | +8 | i16 | about −1,000 to +1,150 |
  | +10 | u16 | ffff, or a small value (144, 148, 1,780, 2,234, 3,132) |
  | +12 | u8 | ff on almost all |
  | +13, +14 | u8 | 0, or 1 |
  | +15 | u8 | ff, or a small value (5, 6, 17, 30, 35, 39, 58) |

- Rows 0–400 are all day 203 and default; row 0's +0 is 0, the other 400 read 75. The
  [player_ability_scales](../player_ability_scales.md) rows also start at tid 401.
- Among Truro's players, the five rows with +10 set (tids 4353 Starkie, 7724, 8207, 9271,
  39634) also have +15 set, and three of them have +14 = 1. Injured or recovering players,
  by the look of it; not checked.
- Not the match condition: Truro players' last-match condition does not line up with +4
  or +6.

- **Daily, for players only.** Between 8 Aug and 16 Nov, 36,361 rows changed; on 16 Nov
  35,151 rows read day 319 (the save's day) and 8,632 still read 203. 44,960 − 36,344
  players = 8,616: the untouched rows are the staff (and the 401 unused tids), the refreshed
  ones the players. The bytes that move most: +1/+2 (the day, on 36,293 rows), +8 (35,180),
  +9 (31,252), +6/+7 (17,834), +15 (11,860), +4/+5 (9,324), +10/+11 (5,431).
- **FMM22 has the same table**: row 0 and row 1 are byte-for-byte Truro's (`00 cb 00 00 10 27
  10 27 …`, `4b cb …`), and 25,714 rows read day 161, frem-2026-06-11's own day (203 stays the
  untouched rows' stamp on both games).

## Next

1. Ask for in-game screens: the squad's condition, match sharpness, morale and injuries for a
   few Truro players on 16 Nov, then line them up with +0, +4, +6, +8, +10 and +15.
2. Compare the same players' rows across the four FMM27 saves.
