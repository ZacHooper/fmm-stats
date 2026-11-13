# After last transfers, 2: a 25-byte slot table

Part of [last transfers → surnames](after_last_transfers.md). FMM27 only so far.

| save | from | to | size |
|---|---|---|---|
| truro-2026-11-16 | 41,147,471 | 41,600,030 | 453 KB |

## Known

- **41,147,471 → 41,155,180 (7.7 KB)**: a pattern repeating every 150 bytes, mostly 00 and
  ff, with `ff 04` and `01 00 ff ff` at fixed places. Not split into rows yet.
- **41,155,180 → 41,600,030: 17,794 slots of 25 bytes.** 17,746 are the same empty slot:

  ```
  ff ff ff ff ff ff 00 ff ff ff ff f4 01 00 00 00 00 00 00 00 00 00 00 0a 00
  ```

  `f4 01` (500) varies in the filled slots, between 408 and 750.
- 48 slots carry the u16 pair 185, 71 at the front, most in one run near the start, with a
  u16 around 500 and a small u8 (8, 9 or 12) after it, e.g.
  `b9 00 47 00 ff ff 00 ff ff ff ff 1b 02 0c 00 …`.
- It is 25 bytes, like FMM22's [match-slot table](../match_slots.md), but it is not that table:
  no `87 01 ff ff` trailer, and no slot holds two clubs and a score.

## Next

1. Settle where a slot starts (the empty slot's `0a 00` may be the last field or the first).
2. Find what 185 and 71 are (club tids, nation ids, a competition?) and compare the slots
   across the four FMM27 saves: do the filled ones grow with matches played?
