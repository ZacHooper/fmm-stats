# person_index  ([`fmparser/tables/person_index.py`](../../fmparser/tables/person_index.py))

**One short row per person**, right after the [languages](languages.md), holding two row
numbers into tables not read yet. The first link of a chain of counted tables that runs to
the [rule files](rule_files.md); the next link is counted by the staff table.

| | Truro (FMM27) | Frem (FMM22) | Bucaspor (FMM22) |
|---|---|---|---|
| rows (= persons) | 44,960 × 15 B | 32,966 × 14 B | 34,312 × 14 B |

## Layout

`[count u32]` with no `0xFF` frame, then the rows, row k = person tid k.

| FMM22 | FMM27 | field | type | meaning |
|---|---|---|---|---|
| +0 | +0 | | u8 | 0, 1 or 3 |
| +1 | +1 | | u8 | 0 or 1 |
| | +2 | | u8 | 0 on every row measured |
| +2 | +3 | `row_a` | u16 | a row in a table not read yet; `ffff` for most people |
| +4 | +5 | `row_b` | u16 | a row in a table not read yet; set for about 30 people |
| +6 | +7 | | u16 | `ffff`, or 0 where `row_b` is set |
| +8 | +9 | | u8 | small values |
| +9 | +10 | | 5 / 3 B | 0 on every row measured |
| | +13 | | 2 B | `ffff` on every row measured |

`row_a` is set for 2,312 people on frem-2026-06-11 (all distinct, up to 2,589: a pool with
gaps) and 3,010 on truro-2026-08-08 (exactly 0–3,009). `row_b` is set for 36 and 27. Who
holds them is not tied to one club or nation.

**How it is found.** At the languages' end: a u32 equal to the person count, whose rows end
exactly on a u32 equal to the staff count. That landing is the extent proof; the locator
refuses a frame that doesn't make it.

## Evidence

The landing on the staff count, on all eight saves measured, both games
(`tests/test_world_lists_evidence.py`).

## Quirks

> **Open:** the staff-counted block that follows has no row width that lands cleanly on
> FMM22 (12 bytes fits FMM27 only). Walk it next, then the smaller counted blocks after it.
> The table `row_a` points into should have about 3,010 rows on Truro.

## Output

`output/<label>/person_index.json`: `[{tid, row_a, row_b}]` in tid order. Not loaded.
