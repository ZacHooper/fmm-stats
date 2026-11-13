# After last transfers, 5: the tail before the surnames

Between the [last transfers](../last_transfers.md) and the [name id-tables](../names.md), one of five sub-tables there on FMM27 (the others: the [unread index](README.md)). FMM27 only so far.

| save | from | to | size |
|---|---|---|---|
| truro-2026-11-16 | 42,331,316 | 42,470,054 | 139 KB |

## Known

- Opens `4b ce 0d 25 00 00 82 00 ff ff 03 ff ff ff ff ff ff 25 01 00 6b 00 40 00 51 00 …`;
  the group `00 82 00 ff ff 03 ff ff ff ff ff ff` comes back every 25 or 50 bytes, with small
  u16 values (0x23, 0x15, 0x0d, 0x3a …) between.
- Ends just before the surname id-table on the text "Manager" and two `[u32][u32]` pairs
  (`2a b9 00 00 fd 02 00 00`).

## Next

Find the record stride and a key, then compare its size across the four FMM27 saves.
