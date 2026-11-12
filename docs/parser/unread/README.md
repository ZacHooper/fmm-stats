# Unread regions: what is known so far

The save regions no parser table reads yet, and everything learned about each: where it
sits on both games, the bytes seen, what was tried and ruled out, and the next step. Each
page is the place to pick a region up, with no other context needed. When a region is read,
its findings move into a table doc in [`docs/parser/`](../) and its page here is deleted.

Offsets are from `frem-2026-06-11` (FMM22) and `truro-2026-08-08` (FMM27). They drift between
saves: find a region by the tables either side of it, never by its number. The whole file is
the [save file map](../savefile-map.md); the order the regions are worked is the
[plan](../../plans/2026-11-12-unknown-regions.html); open items are in [TODO](../../TODO.md).

| region (between) | FMM22 | FMM27 | what it probably is | page |
|---|---|---|---|---|
| club rows → rule files | 1.67 MB | 0.02 MB | FMM22: one block per player (read on FMM27 as player_status); FMM27: a u16-counted slot list, then 13.6 KB | [person_chain](person_chain.md) |
| rule files → contract grid | 9.15 MB | 2.43 MB | FMM22 padding; FMM27 a slot pool, then season-year blocks | [season_blocks](season_blocks.md) |
| loans → transfer band | 1.16 MB | 1.50 MB | not known | [after_loans](after_loans.md) |
| last transfers → surnames | 0.94 MB | 1.32 MB | FMM22 holds the match-slot table here; FMM27's not found | [after_last_transfers](after_last_transfers.md) |
| nicknames → history | 1.52 MB | 2.14 MB | small numbers, then (FMM27) 1,020 inline-named records | [named_records](named_records.md) |
| club records → player progress | 0.19 MB | 0.20 MB | each competition's record book | [record_books](record_books.md) |
| player progress → training | 0.76 MB | 1.03 MB | padding, to prove | [progress_padding](progress_padding.md) |
| team history → our matches | 2 KB | 2–43 KB | not known | [before_matches](before_matches.md) |
| person stamps → tactic history, and after the club titles | 148 B + 4.94 MB | 64 B + 5.20 MB | the user's club block: set pieces / captain?, then an empty pool | [club_block](club_block.md) |
| player lists → archive | 4 KB | 149 KB | the game's scheduled events | [scheduled_events](scheduled_events.md) |

Unread *fields* inside tables that are read (award body bytes, derby bytes, the loan
option amount, the id list's ids, the tactic history's flag) are in each table's own doc.
