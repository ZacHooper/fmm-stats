# stadiums  ([`fmparser/tables/stadiums.py`](../../fmparser/tables/stadiums.py))

Every stadium: its capacity, expansion capacity and city. A count-framed table of 15,987
variable-length records in the reference block (~12.8 MB), `[8 × 0xFF][count u16 = 15987]`
and then record 0, whose `id` is 0. The count is the same in both careers.

## Layout

| offset | width | field | meaning | how we know |
|---|---|---|---|---|
| 0 | 4 | `id` | u32, the stadium id clubs point at (`clubs.stadium_id`) | Frem's 181 is its ground (screenshot) |
| 4 | 4 | `uid` | u32, database id | |
| 8 | 2 | `city_id` | u16 → [cities](cities.md) | Parken and Valby Idrætspark are both in city 58, Copenhagen |
| 10 | 4 | `capacity` | u32, seats | screenshot; Parken 38,065 |
| 14 | 4 | `expansion_capacity` | u32, the most the ground can be expanded to | |
| 18 | 4 + n + 1 | `name` | `[len u32][utf-8][00]`: the name is NUL-terminated as well as length-prefixed | |

## Provenance

`frem-2030-06-22`, Frem's Club Information screen. Stadium 181's record is at byte 12,783,119:

![Valby Idrætspark, capacity 30,000](img/stadiums-1.png)

| on screen | raw bytes | parsed |
|---|---|---|
| (the club's ground) | `b5 00 00 00` | `id` = 181 = Frem's `stadium_id` |
| | `4b 03 00 00` · `3a 00` | `uid` 843 · `city_id` 58 |
| Stadium Capacity `30,000` | `30 75 00 00` | `capacity` = 30,000 |
| | `d8 d6 00 00` | `expansion_capacity` = 55,000 |
| Stadium `Valby Idrætspark` | `11 00 00 00 "Valby Idrætspark" 00` | `name` (17 bytes: `æ` is two) |

Cardiff City's screen agrees as well: stadium 4261 `Cardiff City Stadium`, capacity 33,280
([clubs](clubs.md)). Tested by `tests/test_world_provenance.py`.

## Quirks

> **Quirk:** the length counts bytes, not characters, and a NUL follows the name.
> `Valby Idrætspark` is 16 characters, length 17, then `00`, and the next record starts after
> the NUL.

> **Decision:** walked from the count frame. `locate_stadiums` looks for the frame with the
> literal count 15987 and record 0's `id == 0`; if the frame is missing (a synthetic test
> buffer), it walks records from offset 0 while they parse. `_stadium_at`'s plausibility
> checks (name 1–120 bytes, capacity ≤ 300,000) only serve that fallback.

## Output

`output/<label>/stadiums.json`, `{id: stadium}` with each record's byte `offset`, loaded into
`raw.stadiums`.
