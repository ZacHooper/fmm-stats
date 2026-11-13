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
| loans → transfer band, 1 | 1.16 MB in all, not split | 368 KB | ~5,300 position-masked headers, each with a short list | [al_position_lists](al_position_lists.md) |
| loans → transfer band, 2 | | 1.08 MB | 90,139 × 12 B ranked lists: the world's goalkeepers first | [al_rankings](al_rankings.md) |
| last transfers → surnames, 1 | 0.84 MB in all (then the match-slot table) | 326 B | a u16-counted list of 9 B entries ending in an id | [alt_nine_byte_list](alt_nine_byte_list.md) |
| last transfers → surnames, 2 | | 453 KB | 17,794 slots × 25 B, nearly all empty | [alt_slot_table](alt_slot_table.md) |
| last transfers → surnames, 3 | | 11.9 KB | the managed club's season goals, assists, apps, PoM per player; four saved tactics | [alt_managed_club](alt_managed_club.md) |
| last transfers → surnames, 4 | | 719 KB | one 16 B row per person (44,960), day-stamped | [alt_person_rows](alt_person_rows.md) |
| last transfers → surnames, 5 | | 139 KB | records with `00 82 00 ff ff 03`, ending on "Manager" | [alt_tail](alt_tail.md) |
| after the season stats → history | 85 KB | 197 KB | (FMM27) 1,020 inline-named records; (FMM22) rows of two u32 and a nation id | [player_season_stats](../player_season_stats.md#what-follows-unread) |
| club records → player progress | 0.19 MB | 0.20 MB | each competition's record book | [record_books](record_books.md) |
| player progress → training | 0.76 MB | 1.03 MB | padding, to prove | [progress_padding](progress_padding.md) |
| team history → our matches | 2 KB | 2–43 KB | not known | [before_matches](before_matches.md) |
| person stamps → tactic history | 148 B | 64 B | the user's club block: 17 players by position, set pieces? | [club_block](club_block.md) |
| club titles → player lists | 4.94 MB | 5.31 MB | FMM27: ten framed tables (pools, match lines, a row per player, per-staff rows, the player achievements) | [end_block](end_block.md) |
| player lists → archive | 4 KB | 149 KB | the game's scheduled events | [scheduled_events](scheduled_events.md) |

Unread *fields* inside tables that are read (award body bytes, derby bytes, the loan
option amount, the id list's ids, the tactic history's flag) are in each table's own doc.
