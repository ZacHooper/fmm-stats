# player_achievements  ([`fmparser/tables/player_achievements.py`](../../fmparser/tables/player_achievements.py))

The last table of [the block after the club titles](unread/end_block.md) (its table 10). `extract.py` writes `player_achievements.json`, one row per used slot in slot order, with its `row`. FMM27 and FMM22 store it the same way. FMM27, at block offset 2,907,675
on truro-2026-11-16: `[u32 100,000][100,000 × 24 B]`, then one byte `00`, then the player
lists. 2.4 MB, most of it empty. **It is the Player Achievements screen**: one row per
achievement, every player's in one log.

| save | used slots |
|---|---|
| 22 Jul | 0 |
| 25 Jul, 8 Aug | 1 (the same row: Serhou Guirassy's African Footballer of the Year, Dortmund) |
| 16 Nov | 887 (866 players) |

FMM22: none on frem-2021-06-27 (the career's first day), 16,520 on frem-2023-07-02, 36,653 on
frem-2026-06-11, 11,407 on bucaspor-2023-04-01. Nothing is cleared at the rollover: the
2026 Frem save still holds 2021's rows.

A capacity, not a count: 100,000 on every save. Rows fill from the front in the order the
achievements happen (the July super cups first, then the monthly awards), and a freed slot
is reused (93 empty slots among the used ones on frem-2023-07-02), so the row number is not
an id and the person tids are unsorted. An empty slot is
`00 ff ff ff ff 00 00 00 00 ff × 14 00`.

## Layout

| offset | field | type | meaning |
|---|---|---|---|
| +0 | `year` | u8 | years since 1970, the season's first year: `38` = 2026, shown "2026" on a one-off and "2026/27" on an award. 50–56 across the FMM22 saves (2020–2026) |
| +1 | `tid` | u32 | the player |
| +5 | `kind` | u32 | 1, 2, 4, 8, 16, 32, 64, 128 or 512 (below) |
| +9 | `cid` | u16 | the competition; `ffff` for an award with none (African Footballer of the Year) |
| +11 | | 2 B | `ffff` on every row |
| +13 | `club_tid` | u16 | his club at the time, not now |
| +15 | `award_id` | u32 | the award on a kind-128 row, else `ffffffff` |
| +19 | `next_row` | u32 | the row of the same player's next achievement; `ffffffff` on his last. Every link, on every save, is to a row of the same player, none reached twice; a reused slot can make one point back. Wint 92 → 182 → 183, Guirassy 0 → 70 |
| +23 | | u8 | 0 |

`kind` on truro-2026-11-16:

| kind | rows | screen text | checked |
|---|---|---|---|
| 2 | 45 | "Community Shield Winner" (Minor) | Declan Rice: Arsenal, English Community Shield. The other winners: PSG (UEFA Super Cup), Bayern (Franz Beckenbauer Supercup) |
| 1 | 38 | "Community Shield Runner-Up", "Supercup Runner-Up" | Enzo Fernández: Man City, Community Shield. Guirassy: Dortmund, Franz Beckenbauer Supercup. Also Aston Villa (UEFA Super Cup) |
| 32 | 629 | "Manager Sacked" (Adverse) | Jarrod Bowen: West Ham, whose manager went from Nuno Espírito Santo to Steven Schumacher. A row for every squad player of 21 clubs, 11 of them with a manager first seen on this save |
| 128 | 175 | the award's name (Domestic; Continental for Guirassy's African Footballer of the Year, season 2026/27) | Jack Wint's three rows are the screen's three lines, in order (Young Player, Player, Young Player of the Month, Kidderminster); Tom Tweedy and Harvey Greenslade one each (Player of the Month, Truro) |

FMM22 adds kinds the first FMM27 season has not reached (frem-2026-06-11):

| kind | rows | reading | evidence, not yet screen-checked |
|---|---|---|---|
| 4 | 2,291 | league won | Frem's squads in the 3. Division 2021, 2. Division 2022 and NordicBet Liga 2023, the [club titles](club_titles.md) |
| 8 | 5,242 | promoted | the same three Frem squads; leagues only |
| 16 | 10,505 | relegated | leagues only; Daniel S. Jørgensen with Europa, Spanish Federation Second Group 5, 2025 |
| 64 | 837 | ? | leagues only, mostly third and fourth tiers; Eupen's squad, Belgian Pro League A 2023 |
| 512 | 41 | ? | no competition, no award; about ten a year at big clubs (Maignan at Milan 2023 and 2024, Salah at Liverpool 2021, 2022, 2024) |
| 32 | 11,400 | "Manager Sacked" on FMM27 | here also on national teams after a tournament (Maignan, France, World Cup 2022) |

Wint is 1st in `award_history` three times and 2nd once, and has three rows: a row is a
win, not a placing. The screen's category (World, Continental, Domestic, Major, Minor,
Adverse) and season text ("2026" for a one-off, "2026/27" for an award) are not stored; they
follow from the kind and the competition. No date is stored.

![Bowen: Manager Sacked](img/player_achievements-fmm27-1.png)
![Rice: Community Shield Winner](img/player_achievements-fmm27-2.png)
![Wint: three monthly awards](img/player_achievements-fmm27-3.png)
![Fernández: Community Shield Runner-Up](img/player_achievements-fmm27-4.png)
![Guirassy: Supercup Runner-Up, Footballer of the Year](img/player_achievements-fmm27-5.png)

## Open

- Where a player's first row is found: something per person must point at the head of his
  chain. Not needed to read the table, which is read whole.
- Whether past seasons' achievements stay here after the rollover.
- FMM22: the block after the club titles is not mapped, so the table is not located there.
