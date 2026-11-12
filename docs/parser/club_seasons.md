# club_seasons  ([`fmparser/tables/club_seasons.py`](../../fmparser/tables/club_seasons.py))

**The managed club's record, season by season**: the league line (league, position, played,
won, lost, drawn, goals, points) and the cups it played. Straight after the
[saved tactics](saved_tactics.md), in a pool of 50 slots. The last stored season is the one
in progress.

| | seasons |
|---|---|
| frem-2021-06-27, truro-2026-07-22 (first days) | 1, not started |
| frem-2026-06-11 | 5 (2021–2025) |
| frem-2030-06-22 | 9 (2021–2029) |
| bucaspor-2023-04-01 | 2 |

## Layout

```
[u8 k]                                   seasons stored, less one
k + 1 seasons:
  [cup_count u8][club_tid u16][year u16]
  cup_count x 11 B                       a cup run
  14 B                                   the league line
then 50 - (k + 1) empty 19-byte slots    00 ffff b307 00 ffff 00 x 11
```

`year` is the season's start year (2025 = 2025/26).

The league line:

| offset | field | type | meaning | how we know |
|---|---|---|---|---|
| +0 | | u8 | 0 | |
| +1 | `cid` | u16 | the league; `ffff` before the season's first game | 3. Division 2021 → 2. Division → NordicBet Liga → 3F Superliga, Frem's path |
| +3 | `position_index` | u8 | final position on a finished season, 0 = 1st; not the table position mid-season | 0 in all four Frem title seasons |
| +4 | `played` | u8 | | |
| +5 | `won` | u8 | | the fixture list, below |
| +6 | `lost` | u8 | lost before drawn, as stored | the fixture list |
| +7 | `drawn` | u8 | | the fixture list |
| +8 | `goals_for` | u16 | | |
| +10 | `goals_against` | u16 | | |
| +12 | `points` | u16 | 3 × won + drawn on every season measured | |

A cup run is `[cid u16][club u16][year u16][u16][u16][ff]`: the cup (Sydbank Pokalen, EURO
Cup, European Champions Cup on Frem; the Turkish Cup on Bucaspor) and two u16s not read.
The second is a [round name](rounds.md) id on most runs ("Second Round", "Quarter Final")
but not on all ("Third Placed Teams" for a EURO Cup), so it is left unnamed.

**How it is found.** The byte after the saved tactics is `k`; the locator walks the k + 1
seasons and accepts them only if every one names the same club and the rest of the 50 slots
are empty.

## Evidence

`tests/test_club_seasons_evidence.py`, eight saves of both games. Against the world fixture
list on frem-2026-06-11: Frem's 2025/26 league stages (22 + 10 games) give 32 played, 14
won, 11 drawn, 7 lost, 44–27, 53 points, exactly the stored line (stored won, lost, drawn).
Frem's four league titles (2021, 2022, 2023, 2028, the savefile map's league-titles table)
read position index 0. Truro's 2026/27 line after the opener is played 1, won 1, 1–0, 3
points in the National League South (cid 331). No screen yet.

## Quirks

> **Quirk:** mid-season `position_index` is not the table: after its 1–0 opener Truro reads
> 17 while standing joint 4th–7th. A Manager History screen for a finished season, and one
> mid-season, would say what it holds then.

> **Lead:** the cup runs' two u16s. The Manager or Club History screen lists each cup's
> round reached; one season with a known run (Frem's 2027 European Champions Cup) would
> name both.

## Output

`output/<label>/club_seasons.json`: `[{club_tid, year, cups: [{cid}], league: {cid,
position_index, played, won, lost, drawn, goals_for, goals_against, points}}]`, oldest
first. Not loaded yet.
