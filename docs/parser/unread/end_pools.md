# The three 50-slot pools (block tables 1–3)

Part of [the block after the club titles](end_block.md). FMM27, relative to the block start:

| table | rel. offset | frame | used |
|---|---|---|---|
| 1 | 0 | `[u8 n][50 × 12 B]` | 1 on every save |
| 2 | 601 | `[u8 n][50 × 6 B]` | 0 on every save |
| 3 | 902 | `[u8 n][50 × 7 B]` | 0 on every save |

The same shape as the [club seasons](../club_seasons.md) pool: a count of used slots, then
50 slots whether used or not.

## Known

- **Table 1**: the used slot is `35 0c ea 07` + 8 zero bytes: Truro (tid 3125) and 2026, the
  career's first season. Empty slots are `ff ff` + 10 zero bytes. FMM22 opens the same way with
  11-byte slots: the used one names Frem (346) and 2021.
- **Table 2**: 50 slots of `ff × 6`. **Table 3**: 50 slots of `00 ff ff ff ff 00 00`.

## Next

Table 1 looks like one entry per club managed (a manager's career clubs); a save after a job
change would add a second slot. Tables 2 and 3 need a save where something fills them.

## Evidence that would help

A save from a career where the manager has moved clubs, or been sacked.
