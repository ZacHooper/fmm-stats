# One row per scout (block table 9)

Part of [the block after the club titles](end_block.md). FMM27, at block offset 2,825,827 on
truro-2026-11-16: 787 × 104 B, no count in front.

## Known

- 772 rows hold data on every Truro save, exactly the scout count
  ([staff_roles](../staff_roles.md)); the other 15 are `ff` (the last ending in zeros).
- A row with data starts `[4 B][u8][19 00 00 00]` and is otherwise `ff`: row 0
  `00 00 00 00 00 19 00 00 00 ff …`, rows 1 on `ff ff ff ff ff 19 00 00 00 ff …`. The 25
  (`19`) is the same on all rows.
- Unchanged in shape from 22 Jul to 16 Nov. A scout's assignment (a region, a player to
  report on) is the lead.

## Next

Find the row count's source (787 = 772 + 15) and send a scout on an assignment between two
saves.

## Evidence that would help

Two saves either side of giving one of your scouts an assignment, with the assignment screen.
