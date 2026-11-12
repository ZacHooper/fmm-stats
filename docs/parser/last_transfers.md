# last_transfers  ([`fmparser/tables/last_transfers.py`](../../fmparser/tables/last_transfers.py))

**Each player's latest transfer since the career began**: the fee and the buying club. One
30-byte row per [player attribute](player_attributes.md) record, straight after the
transfer band. The band holds this window's bids and is emptied every July; this table keeps
each player's last completed move across seasons.

| | rows (= player attribute records) | filled |
|---|---|---|
| frem-2021-06-27 (day one) | 26,505 | 0 |
| frem-2023-07-02 (two days after a rollover) | 26,505 | 5,016 |
| frem-2026-06-11 | 26,505 | 10,323 |
| bucaspor-2023-04-01 | 26,292 | 4,579 |
| truro-2026-08-08 | 36,344 | 428 |

## Layout

`[count u32]`, then `count` rows of 30 bytes, row k = attribute record k. The same layout on
both games.

| offset | field | type | meaning | how we know |
|---|---|---|---|---|
| +0 | `fee` | u32 | pounds; 0 on a free | the accepted bid's fee on 418 of 428 Truro rows |
| +4 | | 4 B | 0 on every filled row | |
| +8 | `club_tid` | u16 | the buying club | the accepted bid's buyer on 424 of 428 Truro rows |
| +10 | `tid` | u16 | the player | the person whose attribute record the row is: all 428 on Truro, 10,183 of 10,323 on Frem |
| +12 | | 2 B | 0 | |
| +14 | | u8 | 1; 8 on 14 Frem rows | |
| +15 | | 3 B | 0 | |
| +18 | | u32 | equal to `fee` on every filled row measured | |
| +22 | | 4 B | 0 | |
| +26 | `as_of` | `[day u16][year u16]` | the save's own day, on every row, filled or empty | every save |

An empty row's first 26 bytes are `ff × 14, 00 × 4, ff × 8`.

**How it is found.** The transfer band in front has no parser table, so the locator takes
the first u32 equal to the player attribute count after the [loan pool](loans.md) whose rows
all end in one valid date.

## Evidence

`tests/test_last_transfers_evidence.py`, on eight saves of both games: one row per attribute
record, every row dated the save's header date, no filled row on a career's first days. On
truro-2026-08-08, against the transfer band's accepted (`0d`) bids: every filled row is a
player with one, the buying club and the fee match on nearly every row, and Amir
Rrahmani's row is his 8,846,250 move from Parthenope to Ipswich Town (he has not moved yet
on that save: the deal is agreed). No in-game screen yet.

## Quirks

> **Quirk:** on Frem, 140 of 10,323 rows name a tid that is no longer the attribute
> record's person: a retired player's slot reused by a newgen. Read the row's own `tid`.

> **Lead:** whether the row is written when the deal is agreed or when the player moves.
> Rrahmani's row is there before he has moved, so probably on agreement; a save after a
> deal falls through would show whether the row is cleared.

## Output

`output/<label>/last_transfers.json`: `[{row, fee, club_tid, tid, as_of}]` for every filled
row, in attribute-record order. Not loaded yet.
