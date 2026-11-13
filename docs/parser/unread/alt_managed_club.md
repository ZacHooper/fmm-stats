# After last transfers, 3: the managed club's season lists and tactics

Between the [last transfers](../last_transfers.md) and the [name id-tables](../names.md), one of five sub-tables there on FMM27 (the others: the [unread index](README.md)). Seen on FMM27; FMM22 most likely
has it too (a Frem formation string at 39,267,138 on frem-2030-06-22).

| save | from | to | size |
|---|---|---|---|
| truro-2026-11-16 | 41,600,030 | 41,611,956 | 11.9 KB |

## Known

- **41,600,030 → 41,605,223 (5.2 KB), not read.** It holds u32 ids (`0c42`, `0763` …) among
  00 and ff. At 41,605,160 sits Truro's tid twice (`35 0c ff ff 01 00 00 00 35 0c`), so the
  block belongs to the managed club.
- **41,605,223: five lists**, each a u32 count, then `[tid u32][value u16]` entries. A u32 0 sits
  between the second and third. Every value checked matches our match table across all of
  Truro's first-team matches this season, friendlies included (reserve matches are not in it):

  | count | is | checked |
  |---|---|---|
  | 17 | goals | Greenslade 13 (10 league + 2 cup + 1 friendly), Bogle 9, Starkie 4 |
  | 16 | assists | Greenslade 8 (7 + 1 FA Trophy) |
  | 2 | clean sheets, by the look of it | tid 7422 11 (9 league + 1 cup + 1 friendly); tid 8350's 2 against the 1 we count is not settled |
  | 25 | appearances | Bogle 21 (14 + 4 + 1 + 2 friendlies), Starkie 13, Greenslade 20, 7422 17 |
  | 11 | player of the match | Greenslade 5, Bogle 1 |

- **Four saved tactics** follow, about 1,594 bytes apart (formation strings at 41,605,678,
  41,607,452, 41,609,046 and 41,610,640), each `76 b9 f4 07` then the formation name
  (`4-1-2-1-2`). Between them are runs of small u16 pairs (2–34),
  position grids by the look of them. The same string sits 4 times on truro-2026-08-08
  (40,391,444 onwards).
- Not checked: whether any other club has such a block. The list counts suggest only the
  user's club: formation strings appear nowhere else in this region.

## FMM22

The region between the last transfers and the [match-slot table](../match_slots.md) is 0.84 MB
on frem-2026-06-11 (39,200,736 → 40,042,185), not read. The formation string at 39,267,138 on
frem-2030-06-22 puts this block in it; the rest of that 0.84 MB is not split yet.

## Next

1. Read the five lists as a table (`[count][tid][u16]` × 5) and test them on the 25 Jul and
   8 Aug saves against the match table.
2. Compare the four tactics with the in-game Tactics screen (formation, roles, instructions):
   a screenshot of each slot would show which bytes are which.
3. The 5.2 KB in front.
