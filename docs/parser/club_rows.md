# club_rows  ([`fmparser/tables/club_rows.py`](../../fmparser/tables/club_rows.py))

**One row per club**, straight after the [staff rows](staff_rows.md): the third link of the
chain from the languages to the [rule files](rule_files.md). Its extent is proved and three fields
are named: the club's **transfer budget**, its **matches played** this season and its **last
six results**; `extract.py` writes them to `club_rows.json`, one row per club in tid order.

| | Truro (FMM27) | Frem (FMM22) | Bucaspor (FMM22) |
|---|---|---|---|
| rows (= clubs) | 9,830 | 11,331 | 12,278 |
| rows with the extra block | 1,088 (22 Jul) → 1,298 (8 Aug) | 232 (2021) → 474 (2030) | 314 |
| span | 1.39 MB | 0.60 MB | 0.65 MB |

## Layout

`[count u16]` with no `0xFF` frame, then per club, row k = club tid k:

| FMM27 | FMM22 | type | what is seen |
|---|---|---|---|
| +0 | +0 | u32 `transfer_budget` | pounds, as the Club Finances screen shows it |
| +4 | +4 | 103 / 22 B | mostly 0 |
| +107 | +26 | u8 `matches_played` | this season's matches, friendlies included |
| +108 | +27 | 9 B | mostly 0 |
| +117 | +36 | 6 × 2 B `recent_scores` | the last six results, `[for][against]` each, oldest first; `ff ff` = none |
| +129 | +48 | 2 B | 0 on most clubs |
| +131 | +50 | u8 `n` | 0 or 1: how many extra blocks follow |
| +132 | +51 | n × 68 / 66 B | the extra block |

The extra block on FMM22: `01 00 00 00 00`, an f32 that neighbouring clubs of one nation
share (1.45 on four Albanian clubs, 7.17 on Afghanistan, Bahrain and other Asian national
sides), then u32s that count up across those clubs (177, 178, 179, 180) and two that the
nation's clubs share, then zeros. The shape of a ranking or coefficient table; not yet
matched to a screen. On FMM27 the f32 is at +7 (4.0, 3.5, 7.5).

The count of clubs carrying the block grows over a career on both games.

**Recent results.** On truro-2026-11-16 Truro's twelve bytes read `02 00 01 00 06 00 03 02 01
00 01 02`: Slough 2-0, Ebbsfleet 1-0, Billericay 6-0, Bristol Rovers 3-2, Folkestone 1-0,
Herne Bay 1-2, and `matches_played` 25 (23 in the match table and the two friendlies before
the career began). Each summer save adds the new games on the right (2, 3, 5 matches on
22 Jul, 25 Jul, 8 Aug). Against the world fixture list, `matches_played` equals every club's
played fixtures on the four Truro saves, and the six results agree for 98% of clubs; the rest
are shoot-out games, where the pair is the shoot-out score on most (29 of 1,689 clubs on
16 Nov unexplained). On FMM22, whose fixture list spans two seasons, 80-86% agree.

These twelve bytes were first taken for the team instructions; they are not.

## How it is found

`locate_club_rows`: where the staff rows end, a u16 equal to the club count; the walk (each
row's `n` deciding its length, and refusing an `n` above 1) must then land on a u16 equal to
the [player-attribute](player_attributes.md) count: 26,505 on Frem, 26,292 on Bucaspor,
36,344 on Truro. That count opens the next link, one block per player
([what is known](unread/person_chain.md)).

## Evidence

`truro-2026-07-25`, Truro City (tid 3125): the row's first u32 is `10 27 00 00`, 10,000, and
the Club Finances screen that day reads **Transfer Budget £10,000**. Frem reads 1,030,284 on
frem-2026-06-11. Nothing else on the screen is in the row: no u32 reads the wage budget or wage
total, a year or a week (£1.01M / £1.03M), and no byte reads 50 (profit retention), and
the affiliate (Helston Athletic) is the [club record](clubs.md)'s `affiliates` list. Nor is
the wage budget in contract units (`wage_units`, £10 a week: 1,933-1,952 for £1.01M a year) in
this row or in Truro's club record. The row's only other non-zero early value is a u16 at
+9, 762 on Truro, unexplained.

![Truro City, Club Finances, 25 Jul 2026: Transfer Budget £10,000](img/club_rows-fmm27-1.png)

[`tests/test_person_chain_evidence.py`](../../tests/test_person_chain_evidence.py): start,
count and extra-block count on five saves of both games, the transfer budget on
truro-2026-07-25, and the landing on the player-attribute count. A walk with a 65-byte extra block finds nothing.

### FMM22

The row is 51 bytes and the extra block 66, against FMM27's 132 and 68.
