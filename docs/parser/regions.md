# regions  ([`fmparser/tables/regions.py`](../../fmparser/tables/regions.py))

The **regions** of each nation (South-East, London, West Midlands for England; Sikasso for
Mali): the table a [city](cities.md)'s `region_id` points into. fmm-editor's FMM26 `Region`,
field for field. The last of the four tables between [cities](cities.md) and
[currencies](currencies.md).

| | Truro (FMM27) | Frem (FMM22) |
|---|---|---|
| regions | 2,532 | 2,467 |

## Layout

| offset | field | type | meaning | how we know |
|---|---|---|---|---|
| +0 | `id` | u16 | the slot index; a city's `region_id` | every row |
| +2 | `uid` | u32 | | |
| +6 | `name` | `[len u32][utf-8][terminator]` | `00` on FMM22, `ff` on FMM27 | |
| then | `nation_id` | u16 | | resolves on every region |
| then | `weather_id` | u16 | `ffff` on most; fmm-editor's `WeatherId` | |

`[>= 8 x ff][count u16]` in front.

**How it is found.** The frame after the derbies' last record, whose record 0 has id 0. The
walk ends on the currencies' frame.

## Evidence

Cross-table (`tests/test_world_lists_evidence.py`): every region's nation resolves, and of
the cities with a region, 10,373 of 10,445 on frem-2026-06-11 (7,178 of 7,243 on Truro) sit
in that region's nation. Region 0 is South-East, England, on both games.

## Quirks

> **Quirk:** the exceptions are all Spanish cities in "Pays Basque", a region the table
> gives to France. The Basque Country spans both nations; the data is the game's.

## Output

`output/<label>/regions.json`: `[{id, uid, name, nation_id, weather_id}]`. Not loaded yet.
