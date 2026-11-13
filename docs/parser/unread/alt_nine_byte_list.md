# After last transfers, 1: a nine-byte list

Between the [last transfers](../last_transfers.md) and the [name id-tables](../names.md), one of five sub-tables there on FMM27 (the others: the [unread index](README.md)). FMM27 only so far.

| save | from | to | size |
|---|---|---|---|
| truro-2026-11-16 | 41,147,145 | 41,147,471 | 326 B |

## Known

- Straight after the [last transfers](../last_transfers.md): a u16 count (36 on 16 Nov), then
  36 entries of 9 bytes:

  | offset | type | seen |
  |---|---|---|
  | +0 | u16 | `042f`, `029e`, `00f4` … (244–1,071) |
  | +2 | u16 | `028a`, `02aa`, `021a` … |
  | +4 | u8 | 5, 10, 15, 20 or 25: always a multiple of 5 |
  | +5 | u32 | an id: `6326` (25,382), `73dd` (29,661), `1816` … |

- The older doc saw `02 00 2f 04 8a 02 05 26 63 …` here on an earlier save: the same first
  entry under a count of 2, so the list grows during the season.

## Next

1. Look the +5 ids up as person tids (`mart.dim_person`) and as club tids: whose are they?
2. Count the list on every FMM27 save (22 Jul, 25 Jul, 8 Aug, 16 Nov) to see how it grows.
