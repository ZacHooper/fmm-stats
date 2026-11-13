# A 100,000-slot pool (block table 10)

Part of [the block after the club titles](end_block.md). FMM27, at block offset 2,907,675
on truro-2026-11-16: `[u32 100,000][100,000 × 24 B]`, then one byte `00`, then the player
lists. 2.4 MB, most of it empty.

| save | used slots |
|---|---|
| 22 Jul | 0 |
| 25 Jul, 8 Aug | 1 |
| 16 Nov | 887 |

## Known

- A capacity, not a count: 100,000 on every save. Slots fill from the front.
- An empty slot is `00 ff ff ff ff 00 00 00 00 ff × 14 00`.
- Used slots start with a u32 near 5.5 million (`38 33 54 00` = 5,518,136; 5,532,728), then
  `00 80 00 00` or `00 02 00 00`, then small numbers and `ff`. Slot 0 differs between saves.

## Next

Find what the first u32 counts (it is near 5.5 million on every used slot: an id range of
its own?), and what grows from 1 slot to 887 between August and November (news items?
history entries?).
