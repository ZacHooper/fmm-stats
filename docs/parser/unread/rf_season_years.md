# Rule files → contract grid, 2: season-year blocks

The second of five sub-tables (two now read) between the [rule files](../rule_files.md) and the
[contract grid](../contracts.md), on both games. Before it: the [head slots](rf_head_slots.md);
after it: the [formation presets](../formations.md).

| save | from | to | size |
|---|---|---|---|
| truro-2026-11-16 (FMM27) | 27,331,493 | 27,855,891 | 524 KB (531 KB on 22 Jul) |
| frem-2026-06-11 (FMM22) | 20,021,849 | 20,596,961 | 575 KB (601 KB on 2021-06-27, 583 KB on 2030-06-22) |

## Known

- Blocks repeating every 48 or 52 bytes, carrying **season years and dates**: `ff ff ff ea 07
  eb 07 06 00 02 0a 07 ea 07 0d 07 ea 07 0c 07 ea 07 0c 07 ea 07 01 00 6c 07 01 00 6c 07 62 00
  03 0b 58 3e 02 00 02 0e 07 ea 07 11 07 ea 07 10 07 ea 07 10 07 ea 07 01 …` (`ea 07` = 2026,
  `eb 07` = 2027). Read as each competition's current-season state is the lead.
- **FMM22 has it too** (`e8 07`, `e9 07`, `ea 07`: 2024–2026 on frem-2026-06-11), the same
  48/52-byte rhythm.
- The only part of the region whose size moves between saves of a career; it shrinks
  during a season (531 KB → 524 KB on Truro). The region changes between 25 Jul and 8 Aug
  (76% of bytes the same).

## Next

Frame the blocks: look for a count and a cid in front of each, and check the cids against
the [competitions](../competitions.md) and their dates against the [fixtures](../fixtures.md).
