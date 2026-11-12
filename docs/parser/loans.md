# loans  ([`fmparser/tables/loans.py`](../../fmparser/tables/loans.py))

**Every loan in the world**: the player, the club he is on loan at, the start and end dates,
a percentage and an option. A pool of 25-byte slots after the [contract grid](contracts.md);
a player on loan points at his slot from the [per-person rows](person_index.md)
(`loan_slot`). His parent club is his own `club_tid` in the [person table](person_info.md).

| | capacity | loans |
|---|---|---|
| frem-2021-06-27 (day one) | 6,243 | 1,962 |
| frem-2023-07-02 (after a rollover) | 6,243 | 512 |
| frem-2026-06-11 | 6,243 | 2,312 |
| bucaspor-2023-04-01 | 6,243 | 2,624 |
| truro-2026-08-08 | 6,637 | 3,010 |

## Layout

`[u16 0][u32 capacity]`, then `capacity` slots of 25 bytes. The same layout on both games.

| offset | field | type | meaning | how we know |
|---|---|---|---|---|
| +0 | `tid` | u32 | the player; `ffffffff` on an empty slot | every used slot is pointed at by exactly this person |
| +4 | `club_tid` | u16 | the club he is on loan at | the four slots naming Frem are players loaned to Frem (below) |
| +6 | `start` | `[day u16][year u16]` | | |
| +10 | `end` | `[day u16][year u16]` | the season's end on most loans | every Frem loan on frem-2026-06-11 ends 29 June 2026 |
| +14 | `pct` | u8 | 0–100 in steps of 10 or 20; probably the share of wages the loan club pays | |
| +15 | | u8 | 1 on every slot | |
| +16 | `option` | u8 | 1 on about a third of loans | |
| +17 | | u32 | with `option` 1, money-sized (1,656 to 75,000,000): probably the fee to buy. With 0, either 0 or a number like 1,508,051 that is not money | the transfer band holds the same numbers on loan bids |
| +21 | | 4 B | 0 on FMM22; 0 or `ffffffff` on FMM27 | |

An empty slot is always `ffffffff ffff 0000b307 0000b307 00 01 00 ffffffff ffffffff`.

**How it is found.** The pool has no `0xFF` frame, and on frem-2030-06-22 it does not start
where the contract grid's span ends (89 bytes later), so it is found by its back-links: the
first person with a `loan_slot` gives a candidate base wherever his tid occurs after the
contract grid, and the base is accepted only if every linked person's slot holds his tid and
every other slot below the capacity is the empty pattern.

## Evidence

`tests/test_loans_evidence.py`, on eight saves of both games: the pool is found, its
capacity is the game's, every loan's person points at its slot, every other slot is empty,
every loan club is a club, and no player is on loan at his own club.

Against the [player progress](player_progress.md) table, whose on-loan bit the store's loan
spells come from, on frem-2026-06-11: the 11 Frem players progress marks as out on loan are
exactly the loans whose player belongs to Frem or its reserves (to Fredericia, Hvidovre,
Holbæk, Hobro, Roskilde, …). The four slots whose `club_tid` is Frem are the four players
loaned in, from Granada and the Midtjylland, Nordsjælland and Brøndby reserves; progress
does not mark them, as it marks loans out only.

No in-game screen yet.

## Quirks

> **Lead:** `pct` and the u32 at +17. A loan's screen (the Loan tab of a player out on loan,
> or the loan offer) would show the wage split and any option to buy.

> **Quirk:** the pool covers the whole world, not just our club: this is where a "who is
> on loan where" view for every league can come from, which the progress bit (our squad
> only) can't give.

## Output

`output/<label>/loans.json`: `[{slot, tid, club_tid, start, end, pct, option}]` for every
used slot, in slot order. Not loaded yet.
