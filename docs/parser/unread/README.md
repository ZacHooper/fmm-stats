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
| rule files → contract grid, 1 | 228 B | 444 B | head slots: 19 × 12 B (FMM22), 73 × 6 B (FMM27) | [rf_head_slots](rf_head_slots.md) |
| rule files → contract grid, 2 | 575 KB | 524 KB | season-year blocks, 48/52 B rhythm | [rf_season_years](rf_season_years.md) |
| rule files → contract grid, 3 | 26 KB | 26 KB | 21 formation presets × 1,262 B | [rf_formation_presets](rf_formation_presets.md) |
| rule files → contract grid, 4 | 8.54 MB | 1.87 MB | each team's matchday squad: slot k = team k (14,506 × 589 B / 17,804 × 105 B) | [rf_team_selections](rf_team_selections.md) |
| rule files → contract grid, 5 | 3.9 KB | 3.9 KB | a tail opening `[u32 52]` | [rf_tail](rf_tail.md) |
| loans → transfer band, 1 | 1.16 MB in all, not split | 368 KB | ~5,300 position-masked headers, each with a short list | [al_position_lists](al_position_lists.md) |
| loans → transfer band, 2 | | 1.08 MB | 90,139 × 12 B ranked lists: the world's goalkeepers first | [al_rankings](al_rankings.md) |
| last transfers → surnames, 1 | 314 KB not split, then the person rows and the match-slot table | 326 B | a u16-counted list of 9 B entries ending in an id | [alt_nine_byte_list](alt_nine_byte_list.md) |
| last transfers → surnames, 2 | | 453 KB | 17,794 slots × 25 B, nearly all empty | [alt_slot_table](alt_slot_table.md) |
| last transfers → surnames, 3 | | 11.9 KB | the managed club's season goals, assists, apps, PoM per player; four saved tactics | [alt_managed_club](alt_managed_club.md) |
| last transfers → surnames, 4 | 527 KB | 719 KB | one 16 B row per person, day-stamped, refreshed daily for players | [alt_person_rows](alt_person_rows.md) |
| after the season stats, 1 | 85 KB, not split | 97 KB | 125 variable records naming the managed club | [sst_records](sst_records.md) |
| after the season stats, 2 | | 41 KB | 14 B tid rows in groups | [sst_tid_groups](sst_tid_groups.md) |
| after the season stats, 3 | | 58 KB | ~1,020 records with names typed in | [sst_named](sst_named.md) |
| club records → player progress | 0.19 MB | 0.20 MB | each competition's record book | [record_books](record_books.md) |
| player progress → training | 0.76 MB | 1.03 MB | 23 B per person: attribute changes, the managed squad only | [attribute_changes](attribute_changes.md) |
| team history → our matches | 0.3–2 KB | 2–43 KB | a fixed 229 B head of two 25-slot pools, then tid lists | [before_matches](before_matches.md) |
| person stamps → tactic history | 148 B | 64 B | the user's club block: 17 players by position, set pieces? | [club_block](club_block.md) |
| club titles → player lists | 4.94 MB | 5.31 MB | FMM27: ten framed tables (pools, match lines, a row per player, per-staff rows, the player achievements) | [end_block](end_block.md) |
| player lists → archive | 4 KB | 149 KB | the game's scheduled events | [scheduled_events](scheduled_events.md) |

Unread *fields* inside tables that are read (award body bytes, derby bytes, the loan
option amount, the id list's ids, the tactic history's flag) are in each table's own doc.
