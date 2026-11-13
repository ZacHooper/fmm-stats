# The block after the club titles (club titles → player lists)

| | from | to | size |
|---|---|---|---|
| FMM27 (truro-2026-11-16) | 63,322,627 | 68,630,307 | 5.31 MB |
| FMM22 (frem-2026-06-11) | 56,316,108 | 61,253,092 | 4.94 MB |

**On FMM27 it is a chain of nine framed tables**, each walked to the next on all four Truro
saves (22 Jul, 25 Jul, 8 Aug, 16 Nov), ending one byte (`00`) before the player lists.
Offsets are from the block's start (the [club titles](../club_titles.md)' end); the block
drifts between saves, so find it by that table, never by its number.

| # | rel. offset (16 Nov) | frame | rows | what is known | page |
|---|---|---|---|---|---|
| 1 | 0 | `[u8 n][50 × 12 B]` | 1 used | the managed club and its first season | [end_pools](end_pools.md) |
| 2 | 601 | `[u8 n][50 × 6 B]` | 0 used | empty on every save | [end_pools](end_pools.md) |
| 3 | 902 | `[u8 n][50 × 7 B]` | 0 used | empty on every save | [end_pools](end_pools.md) |
| 4 | 1,253 | `[u16 n][n × 26 B]` then `[u8 0]` | 0 / 0 / 27 / 548 | **read**: the Player Form page | [player_form](../player_form.md) |
| 5 | 15,504 | `[u32 n][n × 72 B]` | 36,343 / 36,345 | **read**: ability on the league's scale, working state | [player_ability_scales](../player_ability_scales.md) |
| 6 | 2,632,348 | `[u32 n][n × 72 B]` | 1 | the same row shape, one person | [player_ability_scales](../player_ability_scales.md) |
| 7 | 2,632,424 | `[u32 cap][cap × 32 B]` | cap 2,841 / 5,682; 0–71 used | a slot pool sized by the coach count | [coach_slots](coach_slots.md) |
| 8 | 2,814,252 | `[3 B][u16 n][n × 10 B]` | 1,157 | one row per physio, all empty | [physio_rows](physio_rows.md) |
| 9 | 2,825,827 | 787 × 104 B, no count | 772 with data | one row per scout, and 15 spare | [scout_rows](scout_rows.md) |
| 10 | 2,907,675 | `[u32 100,000][100,000 × 24 B]` then `[u8 0]` | 0 / 1 / 1 / 887 used | **player achievements** (screen-checked) | [player_achievements](../player_achievements.md) |

Per save (rows of 4 / 5 / 7 used / 10 used): 22 Jul 0 / 36,343 / 0 of 5,682 / 0; 25 Jul
0 / 36,343 / 0 of 2,841 / 1; 8 Aug 27 / 36,343 / 55 of 2,841 / 1; 16 Nov 548 / 36,345 / 71 of
5,682 / 887. The block is 5.20–5.31 MB on every save: the two big tables (5 and 10) are
fixed or preallocated, so it barely grows.

**Proving the chain.** Each frame's count and width land exactly on the next frame, and the
last pool ends one byte before the player lists, on all four saves. A locator that walks
1 → 10 and refuses any other landing would read the whole block as tables (extent proved,
fields mostly unnamed).

## FMM22

Not mapped past the first pool. It opens the same way, `[u8 1]` then 11-byte slots, the
used one naming Frem (346) and 2021, then an `ff` run; after that the periods differ (16 and
24 bytes), and there is no 72-byte row per player (the longest tid-ordered 72-byte run is
68 rows). Next: walk it frame by frame as above, starting from the pool's end.

## Next

1. Tables 4 and 5 are read ([player_form](../player_form.md), [player_ability_scales](../player_ability_scales.md)). Turn the rest of the FMM27 chain into a table module (`end_block` locator, nine record declarations,
   fields `UNKNOWN`), so the save map counts the 5.3 MB as read.
2. Name fields table by table (each page's Next).
3. Map FMM22's version.
