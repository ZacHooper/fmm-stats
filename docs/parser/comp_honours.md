# comp_honours  ([`fmparser/tables/comp_honours.py`](../../fmparser/tables/comp_honours.py))

The roll of honour: for every competition season the game has finished, its winner and
runner-up (and third, for a league). The last table in the archive member `comp_man.dat`
([savefile map](savefile-map.md#the-archive)), after the [stage grid](comp_stages.md) and the
calendar blocks: `[count u32][count × 55 B]`, ending on the member's last byte. Grows by one
record per competition season; 721 records on frem-2030-06-22, 78 on bucaspor-2022-06-19.

## Layout

```
header  [count u32]                       e.g. d1 02 00 00 = 721
record  [cid u32][season u32][1st u32][2nd u32][3rd u32][4th u32]
        [20 × ff][00 00 00][start u16][end u16][u16 1][u16 1900]
```

| offset | field (module) | type | meaning | how we know |
|---|---|---|---|---|
| +0 | `comp_cid` | u32 | the competition's **cid** ([competitions](competitions.md)) | |
| +4 | `season` | u32 | the season, by its **end** year (2029 = 2028/29); `ffff` or 2000 on a placeholder row | matches `raw.club_league_history` (start year 2028), below |
| +8 | `winner_tid` | u32 | 1st: the champion, or the cup winner; club **tid** | |
| +12 | `runner_up_tid` | u32 | 2nd: the runner-up, or the losing finalist | |
| +16 | `third_place_tid` | u32 | 3rd (leagues and some tournaments); `ffffffff` on a cup | |
| +20 | `fourth_place_tid` | u32 | `ffffffff` on every record of every save measured; unverified | |
| +24 | | 20 B | `ff` on every record | |
| +44 | | 3 B | `00` on every record | |
| +47 | `start_year` | u16 | the season's first calendar year | |
| +49 | `end_year` | u16 | its last; equal for a calendar-year competition | `season` lies in (start, end) on 716 of 721 |
| +51 | `format_flag` | u16 | 1 on every record; unnamed | |
| +53 | `base_year` | u16 | 1900 on every record | |

Records are in the order the seasons finished, so a competition's rows are spread through the
table. The first rows are the database's own history (seasons 2018–2021); a competition
with none has one placeholder row: no clubs, season `ffff` (3. Division, EURO Cup
II) or 2000 (the reserve groups). The five records whose season is outside (start, end) are
the European International League (season one less than its finals year) and the Oceania
Nations Cup.

> **Quirk — the module's framing is off by 39 bytes.** `locate_comp_honours` finds the first
> `ff ff ff ff ff 00 00 00` and steps 55 from there, so it treats bytes +39..+54 of one record
> as the head of the next. Each parsed row therefore carries the *previous* record's
> `start_year`, `end_year`, `format_flag` and `base_year`, and record 0 is dropped (720 rows
> of 721 on frem-2030-06-22; one short on all seven saves measured). The cid, season and
> clubs are right. The real frame is the u32 count in front of record 0: `count × 55` tiles
> to the member's last byte exactly on all seven saves of both careers, and with that frame
> `season` falls inside the record's own years on 716/721. Nothing reads the table today
> (it is not extracted), so no output is wrong. See TODO, "Frame the roll of honour by its
> count".

## Evidence

`frem-2030-06-22`, `comp_man.dat` (236,866 bytes decompressed). The count at byte 197,207 is
`d1 02 00 00` = 721, record 0 starts at 197,211, and 197,211 + 721 × 55 = 236,866.

The 3F Superliga's last record, at byte 236,811 (the member's last 55 bytes):

```
02 00 00 00 | ed 07 00 00 | 5a 01 00 00 | 51 01 00 00 | a1 09 00 00 | ff ff ff ff
ff × 20 | 00 00 00 | ec 07 | ed 07 | 01 00 | 6c 07
```

cid 2, season 2029; Frem (346), Brøndby IF (337), FC Nordsjælland (2465); 2028–2029. That is
the 2028/29 table (`raw.club_league_history`, year 2028: Frem 1, Brøndby 2, FC Nordsjælland 3).
The 2029/30 season, finished on this save, has no record yet; its top three are in the
competition record's holders tail ([competitions](competitions.md)).

The Sydbank Pokalen's 2028/29 record, at byte 235,931: cid 263, season 2029, winner AaB (328),
runner-up Frem (346).

Pending: the in-game Roll of Honour for both competitions, to pin the season label and the
places.

## Output

Not extracted. `comp_honours.scrape(blob)` reads it from the decompressed member
(`archive.extract(mm, "comp_man.dat")`), keeping the rows in file order and mapping
`ffffffff` clubs to `None`.
