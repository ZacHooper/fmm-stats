# Last transfers → surnames

| | from | to | size |
|---|---|---|---|
| FMM22 | 39,200,736 | 40,141,766 | 0.94 MB, holding the [match-slot table](../match_slots.md) at 40,042,185 |
| FMM27 | 41,147,145 | 42,470,054 | 1.32 MB on truro-2026-11-16 |

After [last transfers](../last_transfers.md), up to the [name id-tables](../names.md). On FMM27
the region is six things one after another, each with its own page. Offsets are from
truro-2026-11-16.

| # | from | to | size | what | known | page |
|---|---|---|---|---|---|---|
| 1 | 41,147,145 | 41,147,471 | 326 B | a u16-counted list of 36 × 9 B entries, `[u16][u16][u8, a multiple of 5][u32 id]` | layout only | [alt_nine_byte_list](alt_nine_byte_list.md) |
| 2 | 41,147,471 | 41,600,030 | 453 KB | 7.7 KB repeating at 150 B, then 17,794 slots × 25 B, nearly all empty | layout of an empty slot; 48 filled slots share one key pair | [alt_slot_table](alt_slot_table.md) |
| 3 | 41,600,030 | 41,611,956 | 11.9 KB | **the managed club's block**: the season's goals, assists, clean sheets, appearances and player-of-the-match per player, then four saved tactics | five lists checked against our matches | [alt_managed_club](alt_managed_club.md) |
| 4 | 41,611,956 | 42,331,316 | 719 KB | **one 16 B row per person** (44,960, row = tid), stamped with the day it last changed | the row key and the day; the rest unnamed | [alt_person_rows](alt_person_rows.md) |
| 5 | 42,331,316 | 42,470,054 | 139 KB | records repeating `00 82 00 ff ff 03 ff ff ff ff ff ff`, ending on the text "Manager" | nothing yet | [alt_tail](alt_tail.md) |

## FMM22

The [match-slot table](../match_slots.md) (3,975 × 25 B) closes the region; the 0.84 MB in
front of it is not read. A formation string (`4-1-2-2-1`, Frem's) sits at 39,267,138 on
frem-2030-06-22, so FMM22 most likely keeps the same managed-club block (#3) here.
Whether FMM22 has the per-person rows (#4) is not checked.

## Next

Choose one page to work. #3 and #4 are the closest to read: #3 already matches our match
table list for list; #4 has a known key (the person tid) and a day stamp.
