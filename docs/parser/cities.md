# cities  ([`fmparser/tables/cities.py`](../../fmparser/tables/cities.py))

Every city's nation, coordinates, attraction and region. A count-framed grid of 10,956
fixed 20-byte records at ~13.49 MB, `[≥ 8 × 0xFF][count u16 = 10956]`, in id order, bounded by
`id == slot index`. The record has **no name**.

## Layout

| offset | width | field | meaning | how we know |
|---|---|---|---|---|
| 0 | 2 | `id` | u16, equals the slot index; that's what bounds the walk | true on every record |
| 2 | 4 | `uid` | u32, database id | |
| 6 | 2 | `nation_id` | u16 → [nations](nations.md) | Copenhagen → 138 Denmark |
| 8 | 4 | `latitude` | f32, degrees | Copenhagen 55.6761 (below) |
| 12 | 4 | `longitude` | f32, degrees | Copenhagen 12.5683 |
| 16 | 1 | `attraction` | u8 | |
| 17 | 2 | `region_id` | u16; the Region table isn't read yet | |
| 19 | 1 | (unknown) | | |

`locate_cities` searches 10–20 MB first, then the whole file, for a frame whose first five
records carry ids 0–4 on the 20-byte stride.

## Provenance

No in-game screen shows a city or its coordinates, so the ground truth is the real world.
Both Copenhagen grounds point at city 58 ([stadiums](stadiums.md)); its record, at byte
13,452,966 on `frem-2030-06-22`:

| real world | raw bytes | parsed |
|---|---|---|
| (the grounds' city) | `3a 00` · `46 00 00 00` | `id` 58 · `uid` 70 |
| Denmark | `8a 00` | `nation_id` 138 |
| Copenhagen 55.6761° N | `53 b4 5e 42` | `latitude` 55.676098 |
| Copenhagen 12.5683° E | `e9 17 49 41` | `longitude` 12.568337 |
| | `14` · `c9 05` · `00` | `attraction` 20 · `region_id` 1481 · unknown |

Tested by `tests/test_world_provenance.py`.

## Quirks

> **Quirk:** `nation_id` is 0 on 31 real cities with good coordinates. Nation 0 is Algeria,
> so don't trust a city's nation without checking the coordinates.

> **Quirk:** `scrape_cities` turns coordinates outside latitude −60…80 or longitude −180…180
> into `None`. No city on `frem-2030-06-22` is out of range; the check guards a misread.

> **Dead end:** a walk bounded by a gap tolerance, or a locator that hunts for "lots of valid
> latitudes and longitudes nearby", makes the row count a function of the constant: it once
> dropped 31 real cities (all referenced by a stadium) and invented 3, while Copenhagen's
> coordinates stayed exact. Only `id == slot index` bounds this table.

## Output

`output/<label>/cities.json`, `{id: city}` with each record's byte `offset`, loaded into
`raw.cities`.
