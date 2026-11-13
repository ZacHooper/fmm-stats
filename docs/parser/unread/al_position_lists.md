# After loans, 1: position-masked headers with short lists

Between the [loans](../loans.md) and the [transfer band](../savefile-map.md#the-transfer-band),
the first of two sub-tables there on FMM27. The other is the
[ranked player lists](al_rankings.md).

| save | from | to | size |
|---|---|---|---|
| truro-2026-11-16 | 36,683,286 | 37,051,936 | 368 KB |
| frem-2026-06-11 (FMM22) | the region is 34,276,977 → 35,438,751 (1.16 MB) | | not split |

## Known

- **400 bytes of `ff`** straight after the loan pool (36,683,286 → 36,683,686), then a short
  run of 12-byte rows `[u32 id][0][0]` with ascending ids (0x33, 0x34 … 0x3f).
- **About 5,300 records**, each a 38-byte header followed by a list of 12-byte rows (the gap
  to the next header is 38 + 12k bytes on 4,544 of 5,309; the rest are 2–10 bytes over, so
  some headers or rows are longer). Header:

  | offset | type | seen |
  |---|---|---|
  | +0 | u8 | 0x54–0xab, or 0 |
  | +1 | u8 | 0 |
  | +2 | u8 | 1 |
  | +3 | u16 | **a position bitmask**: 0x01, 0x04, 0x10, 0x40, 0x0404, 0x0104, 0x0110, 0x0240, 0x0820 … |
  | +5 | u16 | 1 |
  | +7 | u32 | 4 or 0 |
  | +11 | u16 | the same mask again |
  | +13 | u32 | `ffffffff`, or an id (`9ada`, `677f`, `1d3f` …) |
  | +17 | u16 | the same mask a third time |
  | +19 | | `ff` × 8, `00 00 00` (or `01 00 00`), `ff` × 8 |

- Early on the headers come in fours with the masks 0x01, 0x04, 0x10, 0x40: by the look of it
  goalkeeper, defence, midfield, attack. The masks are the position bits the player tables use;
  not checked against them.
- Most lists are empty (4,190 headers have no rows); the rest hold 1–9 rows. The rows read
  under the header have not lined up as `[tid][value][value]` yet.

## Next

1. Fix the row alignment under a header, then look the ids up as person and club tids.
2. Count the records per save (22 Jul, 25 Jul, 8 Aug, 16 Nov): if they track clubs × 4
   position groups, this is a per-club depth chart.
3. Check whether the region's last header owns the [ranked lists](al_rankings.md) that follow.
