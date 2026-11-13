# A slot pool sized by the coach count (block table 7)

Part of [the block after the club titles](end_block.md). FMM27, at block offset 2,632,424 on
truro-2026-11-16: `[u32 cap][cap × 32 B]`.

| save | cap | used slots |
|---|---|---|
| 22 Jul | 5,682 | 0 |
| 25 Jul | 2,841 | 0 |
| 8 Aug | 2,841 | 55 |
| 16 Nov | 5,682 | 71 |

## Known

- `cap` is the coach count (2,841, [staff_roles](../staff_roles.md)) or exactly twice it,
  switching between saves.
- An empty slot is `ff × 32`. A used slot is `ff ff [u32][u16 318 or 319]` then `ff`: on
  16 Nov slot 2874 holds 25360 and 318, slot 2963 holds 8809 and 319.
- Where the used slots sit follows the capacity: slots 50–2,840 on 8 Aug (cap 2,841),
  2,874–5,662 on 16 Nov (cap 5,682, the second half only). A pool that doubles and uses one
  half at a time, perhaps.

## Next

Read the used slots' u32 as a person or club tid; find what 318/319 count (days? a round?).
Check whether slot k, k < 2,841, lines up with coach row k.
