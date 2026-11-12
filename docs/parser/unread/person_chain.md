# The per-person chain (per-person rows → rule files)

| | from | to | size | still unread |
|---|---|---|---|---|
| FMM22 (frem-2026-06-11) | 14,441,326 | 16,752,549 | 2.31 MB | 15,083,143 → 16,752,549, 1.67 MB |
| FMM27 (truro-2026-08-08) | 17,158,293 | 22,951,767 | 5.79 MB | 22,931,350 → 22,951,767, 20 KB |

A chain of counted blocks with no `0xFF` frames, which is why frame searches found nothing
here. Each block is one row per entity of a table we already read, and each walk lands
exactly on the next block's count:

| link | count | row | read by |
|---|---|---|---|
| 1 | u32 = persons | 14 / 15 B | [person_index](../person_index.md) |
| 2 | u16 = staff | 8 B | [staff_rows](../staff_rows.md) |
| 3 | u16 = clubs | 51 / 132 B, + 66 / 68 B when flagged | [club_rows](../club_rows.md) |
| 4 | u32 = players (attribute records) | variable | [player_status](../player_status.md) on FMM27; **not read on FMM22** (below) |
| 5 | u16 (1,706 on Truro) | 4 B, all `ff` so far | not read; then ~13.6 KB to the rule files |

## Link 4 on FMM22: one block per player

On FMM27 this link is read: [player_status](../player_status.md) (interested clubs, morale,
form). On FMM22 it is counted by the player-attribute count (26,505 on Frem), from where the club
rows end. Described from frem-2026-06-11 (FMM22).

### Known

- **Rows vary in length**, so no fixed width lands. A date reading 1 January 2000
  (`01 00 d0 07`, the save's "no date") recurs every 59 bytes on most rows and serves as an
  anchor: between two anchors, 2,226 of 3,000 sampled rows are 59 bytes, 476 are 64, 113 are 69.
- **The plain row (59 bytes), read from the anchor:** `[date][6 B][7 × u16]` (`ffff` = empty,
  a few hold ids such as 195 or 0x01d5), then **six u8 of 1–20 or `ff`** (`0d 07 05 08 07 07`),
  then `[4 B: a u32 or ffffffff][u8 0][u8 n][n items][u32][15 B]`, then the next row's date.
- **The items:** 5 bytes, `[00][u8 a][00][u8 b][u8 c]` (a 23–35, b small). An item whose first
  byte is 1 is 7 bytes (`01 [a] 00 16 00 00 00`, b always 22). Each extra 5 or 7 bytes matches
  the length past 59 on every plain row sampled.
- **A rich row:** where the byte before `n` is 1 (about one row in 20), the row carries more,
  with dates in 2025 and 2026 (`e9 07`, `ea 07`), club-sized u16s and runs of `ff`, which looks
  like contract or transfer state. Its layout is not worked out, and it is what stops the walk.

### Read on FMM27

The FMM27 block is read by [player_status](../player_status.md), with its evidence. Its
fields name the FMM22 ones: the seven u16 after the head are interested clubs, the six u8
after them morale then form.

### Next

1. FMM22: settle where a block starts (the first block reads 7 bytes longer than the item
   rule says), decode the rich rows, then prove the walk on all five FMM22 saves.
2. FMM27: name the event record (a transfer or contract event?) and link 5's 1,706 slots.

## Evidence that would help

For the FMM27 event record: a save on the same day as a Player Contract screen showing a
transfer offer or a contract being negotiated. For FMM22: a Frem save and its squad screen,
to pin the blocks' order before the walk.

## Tried

- **The staff block as 12-byte rows** (before link 2 was read): it landed on a u32 of 2 on
  FMM27 and on 896,000 on FMM22. The rows are 8 bytes and start two bytes after a u16 count.
- **A greedy walk on FMM27** (6,212 × 12 → 2 × 169 → …) picked whichever width landed on a
  small number; none of it survived once the counts were matched to tables.
