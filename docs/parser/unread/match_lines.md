# Per-player lines of our matches (block table 4)

Part of [the block after the club titles](end_block.md). FMM27, at block offset 1,253:
`[u16 n][n × 26 B]`, then one byte `00`.

| save | lines |
|---|---|
| 22 Jul, 25 Jul | 0 (friendlies only so far) |
| 8 Aug | 27: the league opener, both squads |
| 16 Nov | 548: 20 competitive matches |

## Known

One line per player per competitive match of the managed club, both sides:

| offset | type | what |
|---|---|---|
| +0 | u32 | the player's tid |
| +4 | u16 | the opponent (Herne Bay 2424 for Truro's lines; Truro for theirs) |
| +6 | u8 | 2 or 3 |
| +7 | u24 | a match id, counting up (`dc d4 0f` = 1,037,532 for 8 Aug) |
| +10 | u16 | the player's club |
| +12 | 6 B | 0 on most lines; a byte 1 or 8 at +14 on a few |
| +18 | u8 | 1–20: equal to `player_status.morale` on 8 Aug for all 27 |
| +19 | u8 | the match rating; 0 when he did not play |
| +20 | u8 | goals, or goals conceded on a goalkeeper's line |
| +21 | u8 | assists |
| +22 | u8 | 0 on most lines (1 on Law's on 8 Aug) |
| +23 | u8 | yellow cards |
| +24 | u8 | 0 on lines measured |
| +25 | u8 | 9 came on, 10 went off; 4 and 16 seen once |

**Example** (16 Nov, Truro at Herne Bay on 14 Nov, lost 1-2): En-Neyah rating 7, goals 1;
Greenslade rating 8, assists 1; Lavercombe rating 6, conceded 2; Love-Holmes yellow 1, went
off; Jephcott, Bell and Matthews came on (9); Bogle and Harrison went off (10).

These are separate bytes from the [match table](../matches.md) (which ends before the person
stamps) and hold less: a summary of what it already reads in full.

## Next

Name +6, +12 and +25's other values; check +18 against morale at the time of each match
(a save straight after a match).
