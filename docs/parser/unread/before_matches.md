# Team history → our matches

| | from | to | size |
|---|---|---|---|
| FMM22 | 55,882,728 | 55,884,748 | 2,020 B |
| FMM27 | 61,602,406 | 61,604,419 | 2,013 B (42,731 B on truro-2026-07-25) |

After [team history](../team_history.md), up to [our matches](../matches.md).

## Known

| save | size |
|---|---|
| frem-2026-06-11 / 2030-06-22 / bucaspor | 2,020 / 692 / 316 B |
| truro-2026-07-25 / 08-08 / 11-16 | 42,731 / 2,013 / 5,097 B |

- **A fixed head of 229 bytes on both games**: `00 [u32 25] ff ff 00 01 00 [u16 year] 00 01
  0d`, then 100 bytes of `ff`, `[u32 25]` and a few bytes, 100 more bytes of `ff`: two pools of 25
  empty u32 slots.
  The year is the career's first (2021 on every Frem save, 2026 on Truro), not the save's.
- **Then counted lists of u32 tids and short records**: on 8 Aug `[u32 13]` then 13 tids,
  bytes naming Truro (`35 0c`) and a length-prefixed surname ("Young"); on 16 Nov the name
  "Antell". On 25 Jul a long run of tids fills 42 KB.

## Next

Look the tids up (whose players, which club) on 25 Jul and 8 Aug: a pre-season list (trialists,
a transfer shortlist?) would explain the 42 KB on 25 Jul.
