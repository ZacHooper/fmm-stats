# fixtures  ([`fmparser/tables/fixtures.py`](../../fmparser/tables/fixtures.py))

Every result in the loaded world, every club, for this calendar year and the last: the
Fixtures/Results screens of every club and competition. 92-byte records in the save's zstd
archive, member `fix_man.dat` ([`docs/save-archive.md`](../save-archive.md) has the
container), stored as one grid per calendar year, the current year first. 26,627 records on
`frem-2030-06-22` (7,915 for 2030, 18,712 for 2029), across both careers' clubs and national
sides alike. Our own clubs' matches in full detail are [matches](matches.md).

## Layout

Offsets from the record's first byte.

| offset | field | type | meaning | how we know |
|---|---|---|---|---|
| +1 | `opener` | u8 | always `0x14` | the locator keys on it |
| +2 | | 4 | `ff ff ff ff` | the locator keys on it |
| +6 | `home_goals` | u8 | home score after 90 minutes | our 70 matches |
| +7 | `home_extra_goals` | u8 | home score after extra time; `ff` = no extra time | 3-2 after 2-2 |
| +8 | `home_pens` | u8 | home shoot-out score; `ff` = none | |
| +11 | `away_goals` | u8 | away score after 90 minutes | |
| +12 | `away_extra_goals` | u8 | | |
| +13 | `away_pens` | u8 | | |
| +31 | `stage_key` | u32 | the stage: a record index into `comp_man.dat`'s stage grid (`tables/comp_stages.py`) | |
| +35 | `seq_id` | u16 | **the venue's stadium id**, not a sequence (Quirks) | |
| +41 | `home_tid` | u32 | home club | our 70 matches, venue right on all |
| +47 | `away_tid` | u32 | away club | |
| +53 | `day_raw` | u16 | day of the year **1-based** in the low 9 bits; the top 7 bits (1, 2 or 3) unnamed | |
| +55 | `year` | u16 | the match's year | |
| +57, +59 | `day2_raw`, `year2` | u16 | a second date, unread | |
| +66 | `season_year` | u16 | the campaign's **start** year: 2028 for 2028/29; 0 on friendlies | |
| +76 | `stage_index` | u8 | the stage's `indx` in the competition's rules ([`tables/comp_rules.py`](../../fmparser/tables/comp_rules.py)); `ff` = none | |
| +77 | `round_index` | u8 | the round in the stage's `rnds`; `ff` on league stages | |
| +78 | `round` | u8 | the matchday within the stage, 0-based; for a knockout, the round; `ff` on friendlies | |
| +83 | `subr` | u8 | stage class from the rules file; unnamed values | |

The rest (+0, +9, +14..30, +37, +45, +51, +61, +68, +79..82, +84..91) is declared in
`FIXTURE` and unread; +16..23 is constant zero and +26..30 constant `00 00 00 00 14`.
`stage_attr_80`/`81` are named for being constant within a stage, nothing more.

**How it is found.** `segments` scans the decompressed member for the opener `[u8][0x14]
[ff ff ff ff]` and splits the hits into runs of exact 92-byte steps. Each run tiles its span
exactly (`count × 92`). The grids are walked in file order.

## Evidence

Screenshots pending.

## Quirks

> **Quirk:** it is a results list, not a fixture list. On every save measured, mid-season
> included, no record is unplayed; the last is the day before the save. A future fixture
> isn't in the save in this form. (`ff` in the score bytes is coded for, never seen.) The
> rule files' `fxds`, `ofxd`, `nfxd` and `mtdy` records are scheduling rules (a day of the
> week, a day and month in template year 2000, a kick-off time such as 1900), with no clubs
> and no score.

> **Quirk:** only two calendar years are held: the save's year and the one before. On
> `frem-2030-06-22` the list runs from 1 January 2029 to 21 June 2030, so the first half of
> 2028/29 is already gone. Union across snapshots for a whole season.

> **Quirk:** the day is 1-based, unlike every other day field in the save. Reading it 0-based
> shifts every date a day late. Measured by joining our own matches on clubs and score and
> letting the date come out: every one needed −1 (`DAY_BASE`). Never check this field by
> joining on it: a uniform shift only makes fewer rows join.

> **Quirk:** `+6`/`+11` are the 90-minute score. A match that went to extra time keeps the
> 90-minute score there and the after-extra-time score at `+7`/`+12` (2-2, then 3-2). A tie
> decided on penalties without extra time has the shoot-out at `+8`/`+13` and `ff` at
> `+7`/`+12`. `mart.match_stages` takes the full-time score from our own matches where it
> holds them.

> **Quirk:** `seq_id` is the venue's stadium id ([stadiums](stadiums.md)): the home club's
> stadium on 17,787 of 26,627 records on `frem-2030-06-22`, and its parent club's on 8,054 more
> (reserve and youth sides have no stadium of their own). The rest are other grounds. Every
> Frem home match reads 181, Frem's stadium. Nothing downstream uses it as a sequence.

> **Quirk:** the record carries no competition. A fixture's competition comes from a match
> we played in the same `stage_key`, or the stage's rules (`mart.match_stages`). A group stage
> is one `stage_key` per group, and each leg of a two-legged knockout tie is its own
> `stage_key` (the second leg's `subr` reads 44 on every tie of ours).

> **Quirk:** the record is home-first and the venue is right on all of our 70 matches. The
> 25-byte [match_slots](match_slots.md) table, by contrast, holds no venue.

> **Quirk:** a match is held once: no `(date, home, away)` repeats on `frem-2030-06-22`. The
> two grids are 117 KB apart, and what sits between them is not identified.

> **Quirk:** national sides appear as club-shaped tids from the club table (tid 0 is Algeria).

## Output

`output/<label>/world_fixtures.json`: one row per record, in file order (`home_tid,
away_tid, date, year, round, home_goals, away_goals, home_extra_goals, away_extra_goals,
home_pens, away_pens, stage_key, seq_id, season_year, stage_index, round_index, subr`), `ff`
read as null and the date 0-based. Loads into `raw.world_fixtures`. `extract.py --no-archive`
skips it.
