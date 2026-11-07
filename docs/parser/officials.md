# officials  ([`fmparser/tables/officials.py`](../../fmparser/tables/officials.py))

The match officials: one 99-byte record per referee, with his six refereeing attributes and
the competitions he takes charge of. A count-framed grid, `[>= 8 × ff][count u32]`, at
~6.24 MB, directly in front of [rounds](rounds.md). 622 records on every Frem save, 1,109 on
Bucaspor. Each official is also a person in [person_info](person_info.md), which holds his
name, date of birth and nationality. Not extracted.

## Layout

| offset | field | type | meaning | how we know |
|---|---|---|---|---|
| +0 | `slot_id` | u32 | the record's index, 0..N−1 | dense on every record |
| +4 | `uid` | u32 | the person's uid | = the person record's uid, 622 of 622 |
| +8 | `tid` | u32 | the person's tid | |
| +12 | `ca` | u16 | current ability | |
| +14 | `pa` | u16 | potential ability | |
| +16 | `reputation` | u16 | | |
| +18 | `allowing_flow` | u8 | 1–20 | name unverified |
| +19 | `discipline` | u8 | 3–20 | name unverified |
| +20 | `important_matches` | u8 | 1–20 | name unverified |
| +21 | `pressure` | u8 | 1–20 | = the person record's `pressure`, 622 of 622 |
| +22 | `refereeing` | u8 | 3–20 | name unverified |
| +23 | `running_match` | u8 | 1–20 | name unverified |
| +24 | | 5 | small values; `00 00 00 00 00` on 486 | |
| +29 | `null_year` | u16 | 1900 on every record | |
| +31 | `competitions_raw` | 16 × u32 | the competitions he referees, by competition **uid**, packed from the front; `ffffffff` fills the rest | 1,103 of 1,332 entries are a loaded competition's uid |
| +95 | `day_of_year`, `year` | 2 × u16 | a date: in 2029 or 2030 for 365 officials, day 0 of 2021 for the other 257 (unverified: the last match he took?) | |

**How it is found.** From the end of the [rounds](rounds.md) signature, step back over the
`ff` run to the end of this table. The last record's `slot_id` gives the count, and the
`count u32` in front of record 0 must declare the same number.

## Evidence

Screenshots pending.

## Quirks

> **Quirk:** the competitions are uids, not cids (`raw.competitions.uid`). Mike Dean (tid
> 444) lists 11 and 12: the English Premier Division and the Sky Bet Championship.

> **Quirk:** the match record names no official. No byte of a match row holds an official's
> tid or uid at a fixed offset, so who refereed a match is not known from the save.

> **Quirk:** `ca` and `pa` are raw ability numbers. Nothing extracts them; if they ever reach
> the store they fall under the immersion rule (`[immersion] hide_ability`).

## Output

None: parsed, not extracted (TODO "Raw mirrors the save, one table per table").
`tests/test_rounds_officials.py` checks the count and Mike Dean's record.
