# The per-person chain (per-person rows → rule files)

| | from | to | size |
|---|---|---|---|
| FMM22 | 14,441,326 | 16,752,549 | 2.31 MB |
| FMM27 | 17,158,293 | 22,951,767 | 5.79 MB |

Starts where [person_index](../person_index.md) ends and runs to the [rule files](../rule_files.md).

## Known

- It is a **chain of counted blocks with no `0xFF` frames**, which is why frame searches
  found nothing here. The first link is read: `person_index`, `[count = person count]` then
  one row per person, ending exactly on a u32 equal to the **staff count** (4,642 / 6,212).
- So the next block is **one row per staff member**: `[u32 4,642 / 6,212]` then rows.
- `person_index.row_b` (set for 36 people on Frem, 27 on Truro; values 58–84 on Truro, 417–6,566
  on Frem) points into a table not read yet, possibly in this chain.
- The region opens, on both games, with mostly `00` and `ff` (FMM27: 00 62% / ff 22% /
  other 16%), and changes between saves a few weeks apart (about half its bytes on Truro).

## Tried

- **The staff block's row width.** Scored by column agreement: on FMM27 a 12-byte row lands on
  a u32 of 2, plausibly the next count; on FMM22 12 bytes lands on 896,000, not a count, and
  the widths from 6 to 15 land only on 0, `ffffffff` or round numbers (4,096, 131,072). So the FMM22 width is not 12, or the rows
  are not fixed-width.
- **Walking on greedily (FMM27 only, unproven):** 6,212 × 12 → 2 × 169 → 76 × 90 →
  131,328 × 43 → 255 × 251 → 30 × 13, then no plausible count. Each step only picked the
  width that landed on a small u32; none is checked.

## Next

1. Find the staff block's row width on FMM22: try variable rows (a counted list inside the
   row, as player attributes has), and check the first rows against the staff table
   (`id2` order, the user's staff record last).
2. Then walk on link by link, each count proved by landing on the next, on both games.
3. Diff a staff member's row across the three Truro saves.

## Evidence that would help

A save from the same day as a Staff Profile screen (coaching ratings, attributes), to match a
row against.
