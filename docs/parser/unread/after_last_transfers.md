# Last transfers → surnames

| | from | to | size |
|---|---|---|---|
| FMM22 | 39,200,736 | 40,141,766 | 0.94 MB, holding the match-slot table at 40,042,185 |
| FMM27 | 39,933,439 | 41,255,436 | 1.32 MB, 00 38% / ff 33% / other 30% |

After [last transfers](../last_transfers.md), up to the [name id-tables](../names.md).

## Known

- **FMM22** keeps the [match-slot table](../match_slots.md) here (3,975 × 25 B, two clubs and a
  score), after 0.84 MB that is not read.
- **FMM27's match-slot table is not located**, and this is where it most likely is.
- FMM27 opens `02 00 2f 04 8a 02 05 26 63 00 00 9e 02 aa 02 0a …` straight after the last
  transfers.

## Next

1. Search for 25-byte rows whose two u16 clubs and score match results in the world
   [fixtures](../fixtures.md) (join on the clubs, let the score come out).
2. If it is there, give `match_slots` an FMM27 locator. Then the 0.84 MB in front of it on FMM22.
