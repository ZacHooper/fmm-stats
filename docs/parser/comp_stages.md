# comp_stages  ([`fmparser/tables/comp_stages.py`](../../fmparser/tables/comp_stages.py))

The first table in the archive member `comp_man.dat` ([savefile map](savefile-map.md#the-archive)):
a 42-byte header declaring a record count, then that many 78-byte records. A fixture's
`stage_key` ([fixtures](fixtures.md), +31) is read as a row number in this grid. The framing is
proven; what a row means is mostly not. 2,181 rows on frem-2030-06-22, 2,316 on
frem-2026-06-11; the count changes save to save.

## Layout

```
header  [03 01 'tad.'][u16 8][u16 20][u16][u16 year_start][u16 year_end][u32 n_stages]
        [u16 2000][u32 1][u32 211][8 × 00][ff ff ff ff]
grid    n_stages × 78 B, from byte 42
then    [00][1,825 day blocks][03 00 00 00 00 03]     not read (below)
then    the roll of honour                              comp_honours
```

**Header** (`HEADER`): `year_start` / `year_end` (+12, +14) are the current season, 2029 and
2030 on frem-2030-06-22 (2025, 2026 on frem-2026-06-11). `n_stages` (+16) is the exact row
count. The module's `unk0`/`unk2`/`unk4` read 8, 20 and 363 (361 on frem-2026-06-11),
`base_year` (+20) 2000, `unk16` 1 and `unk20` 211 on both.

**Row** (`STAGE`). The module names many of its fields; on frem-2030-06-22 they read as
follows, and **none of the names below is verified** except where the last column says so.

| offset | module name | what it holds (2,181 rows) | verified |
|---|---|---|---|
| +0 | `opener` | u8, 23 values; 1 on 1,209 rows | |
| +1..+29 | | flags and small values; +16..+27 a u32 and two FourCCs (`wint`, `star`, `end `) on ~40 rows | |
| +30..+45 | | `ff` × 16 on every row | the grid's alignment |
| +46, +48 | `start_year`, `end_year` | 1900 on most rows, else a year 2017–2030 | not validity years |
| +50, +52, +54 | | 0 on 2,138 / 2,169 / 2,179 rows | |
| +56 | `base_year` | 2000 on 1,006 rows, else a year | |
| +58 | `format_flag` | 1, 4, 2, 1000, 100, 5 | |
| +60, +68 | | 0 on every row | |
| +62 | `region_code` | 325 distinct values, 0 on 342 | |
| +64 | `kickoff_time` | 28 values, all a valid `HHMM` (1000–2300; 1930, 1500, 2000 most common), 0 on 475 | plausible: every value is a clock time |
| +66 | `match_week` | 73 values up to 255 | not a 0–60 week |
| +70 | `match_capacity` | a u32 that is a [round-name](rounds.md) id on 1,849 rows (76 Group A, 20 Final …), else a FourCC (`summ`, `midw`, `open`) | the round name is **not** the name of the fixture's stage at that row, below |
| +74 | `scheduling_priority` | a u32: 0–n counting up through runs of rows, `ffffffff`, or a FourCC (`clos`) | |

> **Dead end — row `stage_key` does not carry that stage's name.** For the 42 stage keys our
> fixtures use that the store can place in a competition, the round or stage name the rules
> give the fixture (`comp_<uid>.dat`, [comp_rules](comp_rules.md)) appears at row
> `stage_key` +70 on **none**, and on fewer than a third at any offset or a row ±3 away. Runs
> such as rows 286–299 (fourteen "Group A" rows, +74 counting 0, 0, 0, 1, 1, 1 …) look like
> a schedule of match slots, not one row per stage. The 3F Superliga's Championship Group
> (key 133) does carry `summ`/`clos` at +70/+74, and its Preliminary Phase (key 45) and the
> NordicBet Liga's (key 46) rows are byte-identical. **That `stage_key` indexes this grid is
> unproven**: fixture keys run 21–868 against 2,181 rows, which is all that is known. TODO,
> "Which competition a fixture belongs to: finish the link".

**The day blocks** after the grid (not read): one `00`, then 1,825 blocks of
`[u32 n][n × (u32, u16 year)]`, five 365-day years (2028–2032 on frem-2030-06-22), then
`03 00 00 00 00 03` and the [roll of honour](comp_honours.md)'s count. That walk holds on six
of the seven saves measured; on frem-2024-11-22 it does not start at the grid's end + 1.

## Evidence

`frem-2030-06-22`, `comp_man.dat`. The header:

```
03 01 74 61 64 2e | 08 00 | 14 00 | 6b 01 | ed 07 | ee 07 | 85 08 00 00 | d0 07 | 01 00 00 00 | d3 00 00 00 | 00 × 8 | ff ff ff ff
```

year_start 2029, year_end 2030, `n_stages` 2,181; 42 + 2,181 × 78 = 170,160, where the day
blocks begin. Row 133 (the Superliga's Championship Group key), at byte 10,416:

```
01 ff ff 00 00 00 00 00 00 00 ff 00 00 04 00 00 ff × 12 00 00 ff × 16
6c 07 6c 07 1f 08 00 00 00 00 d0 07 01 00 00 00 00 00 00 00 05 00 00 00 6d 6d 75 73 73 6f 6c 63
```

+70 `mmus` and +74 `solc` are `summ` and `clos` stored reversed.

## Output

Not extracted. `comp_stages.scrape(blob)` reads the grid from the decompressed member
(`archive.extract(mm, "comp_man.dat")`), adding `stage_key` (the row number).
