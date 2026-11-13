# Whole-file map: `frem-2026-06-11.fms` (63,936,873 bytes)

Every table the save holds, in file order, with the doc that describes it. The offsets were
measured on this one save, by calling the named parser or by the structural test in the
notes; no offset is carried over from another save. Use them to know what sits next to what,
never to seek: [locate a table by its own frame or invariant](../../fmparser/AGENTS.md#finding-a-table-the-locator-shapes).

> **Visual version:** [`savefile-map.html`](savefile-map.html) draws this map and the [FMM27](#fmm27) one to
> scale, with a game-version switch, an offset lookup, a hex/decimal toggle and charts. GitHub shows it as source, so download it or
> clone the repo and open it in a browser. This file is the source of truth: the HTML copies its
> regions by hand, so a change to the map lands in both.

## Read this first: the drift boundary

| anchor | `frem-2021-07-01` | `frem-2026-06-29` | drift over 5 years |
|---|---|---|---|
| tagged data dictionary end | 20,206,373 | 20,294,619 | **+88 KB** |
| match-slot table start | 37,009,585 | 40,393,355 | **+3.38 MB**, and it oscillates |

Everything below ~20 MB is near-static: a reference-half offset from any save of the same
career is good to about ±100 KB, close enough to seek to and confirm with the table's header.
Everything above ~34 MB moves by megabytes and **not monotonically**: it sawtooths, because
the seasonal transfer band (35.4–38.4 MB) fills by ~2.5 MB each season and is wiped every
July. A career-half offset from another save is wrong in a direction that depends on where
you are in the season.

Locate reference-half tables by their declared count, career-half structures by their own
invariant. Never by a remembered offset.

## The map

Every region no table reads yet has a page in [`unread/`](unread/README.md): where it sits on
both games, the bytes seen, what was tried and what to try next.

`hdr` = found by its declared count behind a run of ≥ 8 `0xFF`
([shape A](../../fmparser/AGENTS.md#a-count-framed)); `struct` = found by the structural test in the
notes. The status column names the `core` table that reads it
([the locator shapes](../../fmparser/AGENTS.md#finding-a-table-the-locator-shapes)).

| start | end | size | what | over a career | shape / how | status |
|---|---|---|---|---|---|---|
| 0 | 250 | 250 B | **[save header](save_header.md)** — the slot title, `d/m/yy - manager (nickname)`, NUL-padded | game database; rewritten on every save | fixed offset | (`SAVE_HEADER`) |
| 299 | 515,797 | 0.52 MB | **[browse name table](names.md)** — 45,942 names; the `60,000` in front is a capacity, not a count | game database | Shape E | (`tables.names.walk_browse_bounds`) |
| 515,797 | ~572,037 | 0.06 MB | filler + a short run of unnamed records | — | — | — |
| **572,037** | ~3,988,960 | **3.42 MB** | **[the PERSON table](person_info.md)** — declares **32,966** (Frem) / **34,312** (Bucaspor), career-constant, so a **fixed pool**. A `01` header byte follows the count; records (68 B head, 17 B, counted languages, counted relationships) are walked by declaration, all declared, `tid == slot index`, ending on the next table's frame | game database; the count is fixed for the career ([person_info](person_info.md)) | Shape A | `PERSON_INFO_TABLE` |
| 3,988,968 | 6,056,358 | 2.07 MB | **[player attributes](player_attributes.md)** — 26,505 × 78 B | game database | Shape A | `PLAYER_ATTRIBUTES_TABLE` |
| 6,056,370 | 6,237,408 | 0.18 MB | **[staff attributes](staff.md)** — 4,642 × 39 B, `id2 == slot index` | game database | Shape C | `STAFF_TABLE` |
| 6,237,408 | 6,332,591 | 0.09 MB | the chained small tables: the three [staff role](staff_roles.md) tables, coaches / scouts / physios (`[id u32 = slot][specialism][1 B][aptitude]`; 1,971 / 560 / 816 on Frem), the 622 × 99 B [match officials](officials.md), the 273-entry [round/leg names](rounds.md) | game database | Shape A/C | `COACHES_TABLE`, `SCOUTS_TABLE`, `PHYSIOS_TABLE`, `OFFICIALS_TABLE`, `ROUNDS_TABLE` |
| 6,332,603 | ~12,607,190 | 6.27 MB | **[club + national team table](clubs.md)** — 11,331 records, `tid == slot index`, dense. National teams have `club_type` 1 (tids 0–50 and scattered); U21 sides are the last rows | game database | Shape A | `CLUB_TABLE` |
| 12,607,189 | 12,756,283 | 0.15 MB | **[competitions](competitions.md)** — `[8 × ff][count u16 = 1,372]`, record 0 at 12,607,199; 1,272 named + 100 blank slots, `cid == slot index` | game database (reputation and holders rewritten) | Shape A | `COMP_TABLE` |
| 12,756,293 | ~12,796,115 | 0.04 MB | **[nations](nations.md)** — declared 251, all walked by declaration; ends on the continent table's frame | game database | Shape A | `NATIONS_TABLE` |
| 12,796,123 | 13,471,770 | 0.68 MB | **[stadiums](stadiums.md)** — 15,987 ✓ | game database | Shape A | `STADIUMS_TABLE` |
| 13,471,776 | 13,690,902 | 0.22 MB | **[cities](cities.md)** — 10,956 ✓ | game database | Shape A | `CITIES_TABLE` |
| 13,690,908 | 13,833,145 | 0.14 MB | **[awards](awards.md)** — `[count u32 = 807]`; per award `[id = slot][uid][name][long name]`, a 23-byte body (continent, nation, competition, last date) and the latest edition's three entries (person, club, year, score, the winner's name ids) | game database; the entries rewritten as awards are decided | Shape A | `AWARDS_TABLE` |
| 13,833,155 | 13,833,340 | 185 B | **[nation unions](unions.md)** — 6: European Union, EEA, … | game database | Shape A | `UNIONS_TABLE` |
| 13,833,350 | 13,898,498 | 0.07 MB | **[derbies](derbies.md)** — 1,377 named rivalries, each two club tids (Merseyside: Everton v Liverpool) and unread career state | game database; some bytes career state | Shape A | `DERBIES_TABLE` |
| 13,898,508 | 13,965,511 | 0.07 MB | **[regions](regions.md)** — 2,467, each nation's regions, what a city's `region_id` points at | game database | Shape A | `REGIONS_TABLE` |
| 13,965,521 | ~13,969,900 | 0.004 MB | **[currencies](currencies.md)** — 173 ✓ | game database | Shape A | `CURRENCIES_TABLE` |
| 13,969,910 | 13,976,126 | 6,216 B | **[id list](id_list.md)** — 888 × 7 B (`[id u32][00 00 00]`, ids ascending with gaps), ends on the languages' frame; what the ids name is unread | game database | Shape A | `ID_LIST_TABLE` |
| 13,976,136 | ~13,978,480 | 0.002 MB | **[languages](languages.md)** — 124 ✓ | game database | Shape A | `LANGUAGES_TABLE` |
| 13,979,798 | 14,441,326 | 0.46 MB | **[per-person rows](person_index.md)** — `[count u32 = 32,966]` with no `0xFF` frame, then 32,966 × 14 B, row k = person tid k: two row numbers into tables not read yet. Ends exactly on a u32 equal to the staff count | game database | Shape A (lands on the staff count) | `PERSON_INDEX_TABLE` |
| 14,441,326 | 14,478,464 | 0.04 MB | **[staff rows](staff_rows.md)** — `[count u16 = 4,642]` with no `0xFF` frame, then 4,642 × 8 B, row k = staff id2 k; no field named yet. Ends exactly on a u16 equal to the club count | game database; managers' rows change | Shape A (lands on the club count) | `STAFF_ROWS_TABLE` |
| 14,478,464 | 15,083,143 | 0.60 MB | **[club rows](club_rows.md)** — `[count u16 = 11,331]`, then per club 51 B (first, its transfer budget), plus a 66 B block on 406 clubs (a nation-shared f32 and ranking-like u32s). Ends exactly on a u16 equal to the player-attribute count | game database; flagged rows grow | Shape A (lands on the player count) | `CLUB_ROWS_TABLE` |
| 15,083,143 | 16,752,549 | 1.67 MB | **UNIDENTIFIED** ([what is known](unread/person_chain.md)) — `[count u16 = 26,505]`, one variable-length block per player: a plain 59-byte row with counted 5-byte items, and richer rows with 2025/26 dates that stop the walk | — | — | — |
| 16,752,549 | 20,021,621 | 3.27 MB | **[rule files](rule_files.md)** — the tagged data dictionary: 667 count-framed rule files (`[u32 n][n tagged fields]`), 99.2% of the span; the 27 KB between them is per-save state, undecoded | game database; the gaps between rule files change | Shape A | `RULE_FILES_TABLE`; `team_counts` → `competition_team_counts.json` |
| 20,021,621 | 29,171,689 | **9.15 MB** | **FILLER — 94% `0xFF`, 2% `00`.** Not a research target on FMM22; FMM27's smaller version holds slots and season-year blocks ([what is known](unread/season_blocks.md)) | — | — | — |
| **29,171,689** | **31,907,618** | **2.74 MB** | **[contract grid](contracts.md)** — dense **83-byte** records, capacity 59,632, 33,127 slots walked (one per person tid, plus 161 past the person table) | **reserved space**: room for 59,632 slots, one per person, rewritten in place | Shape C | `CONTRACT_TABLE` |
| 31,907,618 | 34,120,896 | 2.21 MB | the contract grid's empty slots, up to its capacity (59,632 × 83 B) | reserved space | Shape C | `CONTRACT_TABLE` |
| 34,120,896 | 34,276,977 | 0.16 MB | **[loans](loans.md)** — `[u16 0][u32 capacity = 6,243]`, then 25 B slots: `[tid][loan club u16][start][end][pct][1][option][u32][4 B]`, 2,312 used. Every player on loan points at his slot (`person_index.loan_slot`) | **reserved space**: slots filled and emptied as loans start and end | found by its back-links | `LOANS_TABLE` |
| 34,276,977 | 35,438,751 | 1.16 MB | **UNIDENTIFIED** ([what is known](unread/after_loans.md)) | — | — | — |
| **35,438,751** | **38,405,582** | **2.97 MB** | **[seasonal transfer band](#the-transfer-band)** — `[u32 65,000][u32 count = 20,747][2 B]`, then 20,747 × 143 B transfer-negotiation rows, row k holding k at +109: every bid, and the accepted one with its fee and contract terms. The rows fill the whole span | **resets every July**; the span's collapse IS the file's July shrink | Shape A | hdr (no parser table) |
| 38,405,582 | 39,200,736 | 0.80 MB | **[last transfers](last_transfers.md)** — `[count u32 = 26,505]`, one 30 B row per player attribute record: each player's latest transfer (fee, buying club), 10,323 filled; every row dated the save's day | **grows** as players move; survives the July rollover | count = the attribute count, rows share one date | `LAST_TRANSFERS_TABLE` |
| 39,200,736 | 40,042,185 | 0.84 MB | **UNIDENTIFIED** ([what is known](unread/after_last_transfers.md)) | — | — | — |
| 40,042,185 | 40,141,560 | 99,375 B | **[match-slot table](match_slots.md)** — 3,975 × 25 B, two clubs and a score, no venue | **reserved space**: slots reused | Shape C | `MATCH_SLOTS_TABLE` |
| 40,141,778 | 40,656,146 | 0.51 MB | **[surname id-table](names.md)** — 32,148 slots, 28,625 used | game database | Shape C | `SURNAMES_TABLE` |
| 40,656,158 | 40,962,206 | 0.31 MB | **[first-name id-table](names.md)** — 19,128 slots, 15,367 used | game database | Shape C | `FIRST_NAMES_TABLE` |
| 40,962,218 | 41,113,898 | **0.15 MB** | **[nickname id-table](names.md)** — 9,480 × 16 B | game database | Shape C | `NICKNAMES_TABLE` |
| 41,113,898 | 42,630,105 | 1.52 MB | **UNIDENTIFIED** ([what is known](unread/named_records.md)), 82% zero — mostly padding | — | — | — |
| 42,630,093 | 46,876,865 | 4.25 MB | **[career-history pool](history.md)** — `[count u32]` + 265,423 records × 16 B (`[stats][club, fee, next]`, one season line each), pointer forest | **reserved space**: filled as players play seasons | Shape B | `HISTORY_TABLE` |
| 46,876,865 | 48,166,114 | 1.29 MB | **[club-records](club_records.md)** — `[count u16]` (1,057 clubs Frem, 1,060 Bucaspor), then per club `[tid u16][n u8][n × 212 B league history][Team/Player Records, overall + this season: 4 × 12 slots of 21 / 22 B]` | **grows** 212 B per new league a club plays in | Shape A, record blocks C | `CLUB_RECORDS_TABLE` |
| 48,166,114 | 48,353,064 | 0.19 MB | **UNIDENTIFIED** ([what is known](unread/record_books.md)) — `[count u32]` = 162 on every save and variable-length rows carrying 21-byte record-shaped matches, then 24-byte filler rows (TODO, "The unclaimed regions of the career half"); the same size on every save of a career | — | — | — |
| 48,353,064 | 52,721,064 | 4.37 MB | **[player progress](player_progress.md)** — 62,400 rows × 70 B (the same count on every save): `[tid u32][6 × u16 skill lines][status u16][0][day u16][year u16][23 × u16]`, usually one row per player per week, a few weeks two to four; the Player Progress page, injured / on-loan bits | **reserved space**: oldest rows overwritten once full | Shape C (seeded from unused rows, walked both ways) | `PLAYER_PROGRESS_TABLE` |
| 52,721,064 | 53,479,282 | 0.76 MB | **UNIDENTIFIED** ([what is known](unread/progress_padding.md)), mostly zero; the training table sits exactly 758,222 B after the progress pool on every Frem save | — | — | — |
| 53,479,282 | 55,490,212 | 2.01 MB | **[training](training.md)** — `[count u32 = 32,966][32,966 × 61 B]`, row k = person tid k (`ffffffff` unused, role `ffff` on staff): intensity `+21`, Focus Role `+23`, attribute focus `+27`, Focus Pos `+29/+30` as the match slot pair, `contracted` `+37` (`87` under contract) and squad status `+39`; the Club Squad > Training page | game database; rewritten as focus changes | Shape A (count-framed, `tid == row`) | `TRAINING_TABLE` |
| 55,490,212 | 55,615,704 | 0.13 MB | **[award history](award_history.md)** — `[count u32 = 1,364]`, 92 B editions: `[award_id][day][year]` + 1st to 3rd (person, name ids, club, score). Every year of an annual award; the current season's weeks or months of a weekly or monthly one | **grows** by an edition per award decided | count-framed | `AWARD_HISTORY_TABLE` |
| 55,615,704 | 55,882,728 | 0.27 MB | **[team history](team_history.md)** — `[count u32 = 845]`, 316 B teams: `[award_id][day][year]` + 11 × (person, name ids, club, rating). Every year of a season team; the current season's Teams of the Week | **grows** | count-framed | `TEAM_HISTORY_TABLE` |
| 55,882,728 | 55,884,748 | 2,020 B | **UNIDENTIFIED** ([what is known](unread/before_matches.md)), before our matches | — | — | — |
| 55,884,748 | 56,178,674 | 0.29 MB | **[our matches](matches.md)** — `[count u8 = 57]`, then one row per match: `[home, away, cid, day][n u8][n x 17 B events][5,093 B body]` -- the body repeats the head from our side, then 50 event slots, two team blocks (`[77 B][20 x 62 B player slots][46 B]`, our score at +52) and our tactic (formation string, 11 starting positions, per-starter items, a coordinate grid) | **resets every July**; appends in-season | Shape A (u8 count, row length from its event count) | `MATCHES_TABLE` |
| 56,178,674 | 56,178,684 | 10 B | five u16 nation ids, unread | — | — | — |
| 56,178,684 | 56,310,550 | 0.13 MB | **[person stamps](person_stamps.md)** — `[01][01][count u32 = 32,965]` (the person count less one), then 4 B per person: `[knowledge u8][day u16][year offset u8]` | rewritten as the career goes on | Shape A | `PERSON_STAMPS_TABLE` |
| 56,310,550 | 56,312,470 | 1,920 B | **[tactic history](tactic_history.md)** — a 60 B block and 6 counted person entries (unread), then `[u16 30]` × 59 B records: tactic setups the game has recorded for the user (a role per position, a formation or "uber tactic" name), capped at 30 | grows with play, to 30 | count-framed | `TACTIC_HISTORY_TABLE` |
| 56,312,470 | 56,313,476 | 1,006 B | **[club seasons](club_seasons.md)** — `[u8 k]` then 50 slots: the managed club's league line (position, W/L/D, goals, points) and cups, season by season | **grows** a season a year | count + fixed pool | `CLUB_SEASONS_TABLE` |
| 56,313,477 | 56,314,027 | **550 B** | `0xFF` run, 550 bytes on every Frem save. It is not the end of our matches: the match table ends 134,803 B earlier | — | — | — |
| 56,314,027 | 56,316,108 | 2,081 B | **[club titles](club_titles.md)** — `[u8 count = 3]`, then 32 slots of 65 B: `[cid][club][30 × year][n_years]`, one per competition the managed club has won (3. Division 2021, 2. Division 2022, NordicBet Liga 2023) | **grows** by a year a title | count + fixed pool | `CLUB_TITLES_TABLE` |
| 56,316,108 | ~61,253,092 | 4.94 MB | **UNIDENTIFIED** ([what is known](unread/end_block.md); on FMM27 ten framed tables) (`00` 29% / `ff` 53% / other 18%). Opens with `[01][club][first season year]` and empty 11-byte slots (`ffff` + 9 zero bytes; 12 on FMM27). One small player-list block sits at 56,336,372 (`Jeppe Corfitzen` / `FC København` / `Res Group 1`), so the structure below starts earlier than its first EMPTY slot | — | — | — |
| **61,253,092** | **62,631,642** | **1.38 MB** | **[player lists](player_lists.md)** — 66 lists of `[100 scrapbook entries][14 B trailer: u8, season u16 (end year; ffff in progress), 11 B]`; an entry is 8 length-prefixed strings (`[full name][first][last][""][last][club short name][""][competition]`) + a 168 B tail (the 23 attributes, 15 position ratings, tid, club marker, value, feet). Lists 0–30 world (100 players a season), 31–61 our club's squad per season, 62–65 two copies of a world/club pair; an unused entry is 200 B | **reserved space**: 66 lists, filled season by season | Shape E (seeded both ways) | `PLAYER_LISTS_TABLE` |
| *61,896,648* | *62,002,727* | *0.11 MB* | ↳ *of which:* our club's squad lists (31–61) — the managed squad, one list per season | — | — | every entry emitted (`player_scrapbook.json`); the store picks our squad's (`raw.squad_scrapbook`) |
| 62,631,781 | 62,635,766 | 3,985 B | **scheduled events** (unread, [what is known](unread/scheduled_events.md)) — 14 B units `[u32 FFFFFFFF][u16 type][u16 day-of-year][u16 year][u32 tid]`, dates a fortnight ahead of the save. Type 9 is a transfer going through on that day: all 41 on frem-2026-06-11 are players with an accepted bid and a [last transfers](last_transfers.md) row. FMM27 stores this region differently (149 KB) | — | Shape C | struct |
| **62,635,766** | **63,936,873** | **1.30 MB** | **the `sicomps` archive** — 159 zstd members and a directory, 6.58 MB decompressed: [the archive](#the-archive) | **grows** with the career | Shape D | container `archive.locate`; [fixtures](fixtures.md) (`fix_man.dat`), [comp_stages](comp_stages.md) and [comp_honours](comp_honours.md) (`comp_man.dat`), [comp_rules](comp_rules.md) (147 × `comp_<uid>.dat`) |

## Four kinds of region: what happens to each over a career

Ask one question of every region: what happens to it as the career goes on? The answer says
whether an offset or a count from another save still holds, and whether an empty-looking
stretch is missing data or room not yet used.

| category | meaning | members | consequence |
|---|---|---|---|
| **game database** | The world as it ships. Full from the start: values change (attributes, reputations, training focus), rows don't. | everything 0–20 MB, the three name id-tables, training, the save header | Walk it by its declared count; the count is exact. |
| **reserved space** | A block of fixed size set aside when the career starts and filled as you play. Some overwrite their oldest rows once full. | contract grid, career-history pool, player progress, player lists, match-slot table | The count is a capacity, never a measure of how much data exists. On an early save much of it is empty slots, not missing data. |
| **grows** | Gets bigger as the career goes on, and is never cleared. | club-records, club titles, award and team history, the `sicomps` archive | Its extent differs from save to save. Club-records gains 212 B each time a club plays in a new league; club titles a year a title. |
| **resets every July** | Fills up over the season and is emptied on rollover day. | transfer band (35.4–38.4 MB), our matches | Whatever is in them at the end of June is gone in July. A late-June save each year is the only way to keep a season's transfers or matches. |

The unidentified spans and the padding sit outside these: the HTML version labels them *not
yet understood* and *padding*.

> **Dead end:** club-records and our matches each once passed for a fixed pool. Neither is:
> club-records holds 1,057 clubs on every Frem save while its size grows 1,224,589 →
> 1,345,853 bytes from 2023 to 2030, and our matches grow with the match count and empty on
> the rollover day. To tell a pool from a structure that grows by insertion, follow one entity
> across saves (one club's row), never a region's size: the region moves for reasons of its
> own. And check a "constant" on a third save: two that agree prove nothing.

> **Quirk:** the history pool's count is a capacity fixed at career creation: 265,423 on all
> five Frem saves (2023–2030), 295,648 on both Bucaspor saves. Club-records starts exactly at
> its end, on every save; the gap a byte-pattern scan once measured (209 bytes on most saves,
> 513 on one) was the distance to the first record that scan could decode, not a frame.

## The July rollover, measured

> Measured on saves not re-checked for this map (`frem-2026-06-29`, `frem-2026-07-02` and
> the rollover pairs below); unverified here, but nothing contradicts it.

The career half does not drift smoothly; it sawtooths, and the whole sawtooth is one event.
`frem-2026-06-29` -> `frem-2026-07-02` loses **3,004,689 bytes**. Anchor-matching one save into
the other -- take a 48-byte non-filler sample every 64 KB, find its unique match in the other
save, watch the offset delta -- localises every byte of that:

| where | delta | what |
|---|---|---|
| below 34.59 MB | −8,952 | data-dictionary edits, nothing structural |
| **34.59 – 39.55 MB** | **−2,541,720** | the transfer band |
| 39.55 – 55.6 MB | (carries −2,550,551) | everything downstream just slides |
| **55.6 – 59.8 MB** | **−383,862** | our matches, exactly the region's own size |
| tail | −59,274 | |

**The transfer band accounts for its step on its own.** Across that pair its extent goes
**3.32 MB -> 0.79 MB** (6,877 -> 1,720 rows carrying contract terms) — a 2.53 MB collapse against a 2.54 MB measured
deletion. Matches go 60 anchors -> 0 over the same pair.

The wipe is a discrete event on rollover day and **the date moves year to year**:
`2023-06-30` 44 match anchors -> `2023-07-01` 0; `2024-06-28` 59 -> `2024-06-30` 0;
`2026-06-29` 60 -> `2026-07-02` 0; `2028-06-28` 75 -> `2028-06-29` 0. So a save taken even two days late has already lost the
season.

**The drift mechanism (365-day engine clock):**
The game advances an internal season counter of exactly 365 days rather than binding to a fixed Gregorian calendar date (e.g. June 30). Because leap years insert February 29th without the 365-day interval compensating, each leap year slips the in-game calendar rollover backwards by exactly one calendar day:
- **2021–2023 (0 leap days):** Rollover on 30 June (or 1 July).
- **2024–2027 (1 leap day, Feb 2024):** Rollover slips 1 day to 29 June (28 June had matches; 30 June had 0).
- **2028+ (2 leap days, Feb 2028):** Rollover slips another day to 28/29 June (28 June 2028 had 75 matches; 29 June 2028 had 0).

The reference-half floor the band resets to is stable across five years
(17.96 / 17.55 / 17.69 / 17.83 / 17.66 MB measured from the datadict's end to the first name
id-table), so nothing accumulates here between seasons.

**Limit of the method, stated because it bounds the claim above:** the anchor probe separates
"this sample is not in the other save" from "it moved", not "deleted" from "rewritten". Inside
34.59–39.55 MB every sample is absent, so the deletion cannot be localised more finely than
that span by this means.

## Gaps, ranked by unexplained non-filler bytes

Size alone misleads; the filler fraction matters more.

| span | size | other% | ≈ real bytes | note |
|---|---|---|---|---|
| 0.57 – 3.99M | 3.42 MB | 45% | 1.55 MB | the person table ([person_info](person_info.md)); the records are walked, the bytes inside them are partly unnamed |
| 56.32 – 61.25M | 4.94 MB | 18% | ~0.9 MB | between the [club titles](club_titles.md) and the player lists ([end_block](unread/end_block.md)) |
| 34.28 – 35.44M | 1.16 MB | — | not re-measured | after the [loans](loans.md), in front of the transfer band |
| 39.20 – 40.04M | 0.84 MB | — | not re-measured | between the [last transfers](last_transfers.md) and the match-slot table |
| 15.08 – 16.75M | 1.67 MB | — | not re-measured | after the [club rows](club_rows.md): one variable-length block per player ([what is known](unread/person_chain.md)) |
| 41.11 – 42.63M | 1.52 MB | 18% | 0.27 MB | 82% zero, mostly padding |
| 52.72 – 53.48M | 0.76 MB | 0% | 0 | all `00` and `ff` |
| 20.02 – 29.17M | 9.15 MB | 3% | 0.3 MB | 94% `0xFF`: padding, not a target |

> **Dead end:** ranking a gap by its printable fraction. Compressed data is 37.1% printable by
> construction (95 of 256 byte values), so the archive at the tail once ranked as "the most
> text-dense unparsed span" for a reason that was false. Rank by block entropy
> (`scripts/audit/entropy_profile.py`): filler ~1.4 bits/byte, records 3–6, compressed 7.9+.

## Reproducing the structural rows

- **contract grid** — scan for `[tid u32][0x01][wage u16][6×00][doy u16][year u16]`, keep hits
  whose gaps are exact multiples of 83; the run's extent divided by 83 is the slot count.
- **transfer band** — `[u32 65,000][u32 count]` in front of row 0 (the row frame starts 2 bytes after the count), and every row k holds k as a u32 at +109; see [the transfer band](#the-transfer-band).
- **player-progress pool** — two consecutive unused 70-byte rows, then walked both ways row by
  row (`tables/player_progress.py`).
- **club-records extent** — the u16 club count after the history pool, walked row by row.
- **player-list blocks** — an unused list (`14 01 00 0a 00` at tail +121 of 100 snapshots, 200
  bytes apart), then walked list by list (`tables/player_lists.py`).
- **the archive** — the first `28 b5 2f fd` (zstd magic) in the file; `archive.locate`.
- **drift class** — compare any two saves: the reference half moves in tens of KB, the career
  half in megabytes.

## The transfer band

Every transfer negotiation of the season so far, each bid a row; no parser table reads it.
`[u32 65,000][u32 count][2 B]`, then `count` rows of 143 bytes, row k holding k (u32) at
+109. The 65,000 is a capacity, the count is exact, and the rows fill the band to the end:
20,747 rows, 2,966,821 bytes on `frem-2026-06-11`. Measured on seven saves:

| save | header at | rows | row k holds k at +109 |
|---|---|---|---|
| `frem-2023-07-02` | 35,417,994 | 5,097 | all |
| `frem-2024-11-22` | 35,462,624 | 15,852 | all |
| `frem-2026-03-28` | 35,408,609 | 18,621 | all |
| `frem-2026-06-11` | 35,438,751 | 20,747 | all |
| `frem-2030-06-22` | 35,421,876 | 19,157 | all |
| `bucaspor-2022-06-19` | 36,797,816 | 16,527 | all but 30 of the last 54, which read 0 |
| `bucaspor-2023-04-01` | 36,808,207 | 18,766 | all |

Offsets from the row start (the header's end + 2):

| offset | type | meaning | how we know |
|---|---|---|---|
| +0 | u8 | kind: `13` a bid, `0d` the accepted one; `01`, `05`, `06`, `09`, `0b` also occur (74, 11, 69, 17, 5 rows), unread | each signing below: its bids, then one `0d` row |
| +4 | u16 | a club tid or `ffff`; unread | |
| +6 | u32 | the player's tid | resolves to a person on 20,747 of 20,747 rows; 8,949 people |
| +10 | u8 | 1 when the row carries contract terms (6,362 rows) | |
| +11 | u16 | wage, in the [contract grid](contracts.md)'s wage units | below |
| +19 | `[day u16][year u16]` | contract expiry | below |
| +42 | `[day u16][year u16]` | a date in the negotiation: 181–183 / 2025 on the signings below, the start of July | |
| +87 | u32 | the fee bid, in pounds, on a permanent move; on a loan a larger number that is not money (1,508,051 … 1,558,051), unread | the screen's fees, below |
| +101 | u16 | the selling club's tid | |
| +103 | u16 | the buying club's tid | |
| +109 | u32 | the row's index | every row on six saves |
| +113 | u32 | a serial, not dense; `ffffffff` on 428 rows | |

The rest is unread. A player has as many rows as bids for him: Gregers Dehn has 21, from 12 buying clubs, two of
them `0d`. Read a row as a bid, never as a transfer.

**Evidence.** `frem-2026-06-11`, Frem's Transfers screen, 2025/26 Transfers In (11 Jun 2026),
as transcribed from the author's screenshot (the image is not in the repo). The screen shows
eleven signings, four fees (£300K, £200K, £130K, £120K) and no dates. Every one has a `0d` row
with +101 the club he came from and +103 Frem (346); for the four with a fee, the bids rise
to it and the `0d` row's +87 is the fee on screen, rounded:

| player | rows (+0, +87) | on screen |
|---|---|---|
| Johannes Tjørnelund, FC København | `13` 32,000, 200,000, 250,000, 275,000; `0d` 302,162 | £300K |
| Marcelo Schöne, Brøndby IF | `13` 14,949, 60,000, 120,000, 170,000, 190,000; `0d` 203,676 | £200K |
| Mads-Emil Wass, FC Roskilde | `13` 21,709; `0d` 130,000 | £130K |
| Gregers Dehn, FC Roskilde | `13` 2,000, 40,000, 80,000, 100,000, 110,000; `0d` 116,929 | £120K |
| Mounir Secka (Nordsjælland), Jakob Larsen (Midtjylland) | `0d`, +87 0 | Bosman |
| Anders Noer, from tid 65191 (not in the club table) | `0d`, +87 65,519 | Graduation |
| Bertil Juel Andersen (Granada), Mikkel Lejbowicz (København), Lauge Gülstorff (Brøndby), Oliver Sørensen (Midtjylland) | `0d`, +87 1,080,284 / 755,284 / 1,508,051 / 1,508,051 | Loan |

On the accepted row the terms are the contract signed: Tjørnelund +11 `32 00` (50) and +19
`b3 00 ec 07` (2028-06-28), the contract grid's 50 and 2028-06-28; Schöne 23, Wass 37, Dehn 7,
all to 2028-06-28. Across the table, of the players whose last accepted row is to the club
they are at now, 2,203 of 3,030 match their current contract on both wage and expiry
(`frem-2026-06-11`; 2,548 of 3,474 on `frem-2030-06-22`). The rest differ, renewals since
being the likely reason (unverified).

> **Quirk:** the row frame starts 2 bytes after the count. Framed from the index instead
> (index at +8, tid at +48), each row's selling club sits at +0 of the next row, which reads
> like a column offset. It is a framing error: start from the header.

> **Quirk:** `0d` rows exist that the screen doesn't list as 2025/26 signings: Tochi
> Chukwuani (Nordsjælland, a loan-sized +87) and two dated April 2026 with +87 0 (Aksel
> Behrndtz, Chris Gernsøe). Pre-agreed moves for next season would fit; unverified.

> **Dead end:** searching for the fees as £000s u16, or in a ±25% band at fixed offsets from
> the player tid in the index-framed row. The fee is a u32 in whole pounds at +87, and only
> the `0d` row holds the agreed one.

What is open is in TODO, "The transfer band: read the rest of the row".

## The archive

The save ends in a zstd archive, `sicomps`: a chain of `[u32 stored][zstd frame]` members and a
directory that names them, ending on the file's last byte. The container, the directory's
layout and its unnamed fields are specified in `fmparser/core/archive.py`; `tests/test_archive.py`
proves the extent (the chain lands on the directory's header, whose size ends on the last
byte), the entry count, the tiling of the member area and every member's decompressed size.
Every member's payload opens `[03][01]['tad.']` (`.dat` reversed). Reading needs
`zstandard` (`uv sync`).

Twelve named members and one `comp_<uid>.dat` per loaded competition, named by the
competition's uid (147 on Frem, 149 on Bucaspor). Decompressed sizes in bytes:

| member | frem-2023-07-02 | frem-2026-06-11 | frem-2030-06-22 | bucaspor-2023-04-01 | what |
|---|---|---|---|---|---|
| `fix_man` | 3,086,909 | 2,518,076 | 2,603,976 | 2,616,655 | the world results list: [fixtures](fixtures.md) |
| `comp_man` | 213,552 | 232,446 | 236,866 | 208,270 | [comp_stages](comp_stages.md) (header and 78 B grid), unread day blocks, [comp_honours](comp_honours.md) |
| `comp_<uid>` × 147 | 2,862,697 | 3,562,444 | 3,474,528 | (× 149) | each competition's stages and rounds: [comp_rules](comp_rules.md) |
| `stadium` | 131,970 | 133,322 | 132,698 | 133,413 | opens `[u16 3][u32 15984]` then 8-byte pairs; unexamined |
| `rule_group` | 64,004 | 66,561 | 65,786 | 66,656 | the only plain text in the archive: engine log lines (`Promoted seeding for Denmark …`) |
| `comp_hosts` | 25,436 | 30,567 | 37,477 | 25,440 | unexamined |
| `rgman` | 18,235 | 20,947 | 21,403 | 17,779 | a 20-byte grid `[u32 index][u32 value][16 × ff]` |
| `friend_man` | 15,302 | 16,918 | 17,719 | 6,280 | friendlies; unexamined |
| `reserves` | 1,500 | 1,500 | 1,500 | 1,753 | constant within a career |
| `national_teams` | 295 | 371 | 1,343 | 263 | unexamined |
| `discipline` | 254 | 254 | 254 | 254 | byte-identical on every save of both careers: a static enumeration |
| `squad_man` | 153 | 17 | 41 | 17 | a stub |
| `fifa_rankings` | 14 | 14 | 14 | 14 | a date and one u16; no ranking table |
| **all 159 (161)** | 6,420,321 | 6,583,437 | 6,593,605 | 6,948,920 | stored: 1.06 / 1.30 / 1.27 / 1.35 MB |

> **Quirk:** the archive is current state. `fix_man` is a two-calendar-year window and the
> rules are this season's; a 2026 save knows nothing of 2021. History comes from keeping
> snapshots, not from any one save.

What is open in the members is in TODO, "Archive members and framing not yet read".

### FMM27

`truro-2026-07-25` (69,883,057 bytes) stores the same archive **without length prefixes**:
168 members as bare zstd frames from 69,357,132, the 13 constant bytes ending right before
member 0, and a 9-byte directory header (`02 01 'fmf.' 08 00 00`, no size) at 69,881,010
whose frame runs to EOF. The directory is FMM22's, its offsets counting from member 0's
first byte and `stored` the frames' own size: the 168 entries tile the 523,878 bytes up to
the header. `fix_man` is 1,219,757 bytes unpacked (499 friendlies, 95-byte records:
[fixtures](fixtures.md)); the comp members have a 53-byte header ([comp_rules](comp_rules.md));
`comp_man` does not read with FMM22's declarations (the audit's PAD check fails on its stage
grid). `tests/test_career_fmm27_evidence.py` checks the extent and every member's size.

The reference half keeps FMM22's order. Between the cities and the currencies on
`truro-2026-07-25`: [awards](awards.md) from 16,106,644 (1,123), [unions](unions.md) (6),
[derbies](derbies.md) (1,681) and [regions](regions.md) (2,532), whose walk ends on the
currencies' frame. Then the [id list](id_list.md) (924 × 7 B) to the languages, and the
[per-person rows](person_index.md) from 16,468,667: 44,960 × 15 B, ending on the staff count
(6,212). The chain goes on as on FMM22: [staff rows](staff_rows.md) (6,212 × 8 B), then
[club rows](club_rows.md) (9,830 × 132 B, plus 68 B on the clubs that carry the extra block),
ending on the player-attribute count (36,344): [player_status](player_status.md), one block
per player (interested clubs, morale, form; 4.34 MB on truro-2026-08-08), then a u16-counted
list of 1,706 four-byte slots and ~13.6 KB unread before the rule files
([what is known](unread/person_chain.md)).

The career half on `truro-2026-07-25`, in file order:

| from | table | notes |
|---|---|---|
| 29,539,097 | [contract grid](contracts.md) | 83 B, capacity 81,465, 44,960 used; four `ff` bytes added to the frame |
| 36,300,713 | [loans](loans.md) | 6,637 × 25 B slots, 2,513 loans; then ~1.48 MB unread to the transfer band |
| ~37.95M | transfer band | 143 B rows |
| 38,044,512 | [last transfers](last_transfers.md) | 36,344 × 30 B, none filled yet on this save |
| 40,459,247 | [name id-tables](names.md) | surnames, first names, nicknames; FMM22's locators |
| 43,991,857 | [history](history.md) | 452,090 rows declared |
| 51,225,299 | [club_records](club_records.md) | 1,087 clubs |
| 52,553,450 | [player progress](player_progress.md) | 62,400 × 70 B; template year 2025 |
| 57,955,530 | [training](training.md) | count 44,960, 61 B rows |
| 60,698,094 | [award history](award_history.md), [team history](team_history.md) | 1,124 editions, 0 teams; then ~43 KB unread to our matches |
| 60,844,241 | [our matches](matches.md) | one row; 70 B player slots, not read yet |
| 60,850,122 | [person stamps](person_stamps.md) | `[01][01][44,959]`, 4 B per person, straight after our matches |
| 61,030,325 | [tactic history](tactic_history.md), [club seasons](club_seasons.md), [club titles](club_titles.md) | 5 tactic-history records, the 50-slot season pool (one season so far), then a `00`, 550 `ff` and the 32-slot titles pool (none yet) |
| 61,033,908 | **unread** ([the block after the club titles](unread/end_block.md)) | ten framed tables, each walked to the next: three 50-slot pools, the [player form](player_form.md) lines (read), [a 72-byte row per player](player_ability_scales.md) (36,343; read), a one-row list, a coach-sized slot pool, a row per physio, a row per scout, the [player achievements](unread/player_achievements.md) (100,000 slots), then one `00` |
| 66,236,284 | [player lists](player_lists.md) | 132 lists, 192 B tails |
| 69,357,106 | the archive | bare frames, to EOF |

History and club_records locate with FMM22's locators and the audit raises nothing on them,
but no FMM27 screen has checked them yet. `match_slots` is not located on FMM27.
