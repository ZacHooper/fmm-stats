# stadiums  ([`fmparser/tables/stadiums.py`](../../fmparser/tables/stadiums.py))

Every stadium: its capacity, expansion capacity, city and names. A count-framed table of
variable-length records in the reference block, `[8 × 0xFF][count u16]` and then record 0, whose
`id` is 0, with `id == slot`: 12,509 stadiums on both Truro saves (FMM27), the walk ending on
the [cities](cities.md) frame. On FMM22 it is 15,987 in both careers, at ~12.8 MB, and each
record has one NUL-terminated name (Layout, FMM22).

## Layout

The 18-byte head was checked against screens on FMM22 (Evidence, FMM22) and holds on FMM27's
two Club Information stadiums.

| offset | width | field | meaning | how we know |
|---|---|---|---|---|
| 0 | 4 | `id` | u32, the stadium id clubs point at (`clubs.stadium_id`) | Frem's 181 (FMM22), Truro's 11983 and Torquay's 95 (FMM27) are their grounds (screenshots) |
| 4 | 4 | `uid` | u32, database id | |
| 8 | 2 | `city_id` | u16 → [cities](cities.md) | Parken and Valby Idrætspark are both in city 58, Copenhagen (FMM22) |
| 10 | 4 | `capacity` | u32, seats | screenshot; Parken 38,065 |
| 14 | 4 | `expansion_capacity` | u32, the most the ground can be expanded to | |
| 18 | 4 + n | `name` | `[len u32][utf-8]`, the name | Truro City Stadium, Plainmoor (Club Information) |
| | 4 + n | `alt_name` | `[len u32][utf-8]`, the sponsor-free name; equals `name` on 12,273 | Vitality Stadium → Bournemouth Stadium, Cegeka Arena → KRC Genk Arena, CEPAC Vélodrome → Stade Vélodrome |
| | 4 + n + 1 | `name_3` | `[len u32][utf-8][ff]`; equals `name` on all 12,509 | |
| | 3 | | 3 × u8, unnamed: 255 on 12,271 and 0 on 238; a bitfield shape (0, 1–4, 64–67, 128–132); 0, 1 or 8 | fmm-editor reads three unknown bytes after its terminator |

**How it is found.** `STADIUMS_TABLE_FMM27` chains from the [nations](nations.md) table's
end: the first count frame whose records 0 and 1 hold ids 0 and 1.

### FMM22

`STADIUMS_TABLE`. The same 18-byte head, then one name and nothing after it:

| offset | width | field | meaning |
|---|---|---|---|
| 18 | 4 + n + 1 | `name` | `[len u32][utf-8][00]`: the name is NUL-terminated as well as length-prefixed |

No `alt_name`, `name_3` or trailing bytes. The locator looks for the count 15,987, a
constant of the FMM22 database.

## Evidence

`truro-2026-07-25`, the two Club Information screens ([clubs](clubs.md)):

| on screen | raw bytes | parsed |
|---|---|---|
| Truro City Stadium, capacity 4,100 | @15,898,536 `cf 2e 00 00 | 7f 47 3b 77 | b5 0e | 04 10 00 00 | 07 1c 00 00` | id 11983 (Truro's `stadium_id`), city 3765, `capacity` 4,100, expansion 7,175 |
| Plainmoor, capacity 6,200 | @14,786,034 `5f 00 00 00 | d7 02 00 00 | 53 03 | 38 18 00 00 | 40 1f 00 00` | id 95 (Torquay's), `capacity` 6,200, expansion 8,000 |

Tested by `tests/test_reference_fmm27_evidence.py`.

### FMM22

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
([clubs](clubs.md)). Tested by `tests/test_world_evidence.py`.

## Quirks

> **Quirk:** the length counts bytes, not characters, and on FMM22 a NUL follows the name.
> `Valby Idrætspark` is 16 characters, length 17, then `00`, and the next record starts after
> the NUL.

> **Decision:** on FMM22, walked from the count frame. `locate_stadiums` looks for the frame
> with the literal count 15987 and record 0's `id == 0`; if the frame is missing (a synthetic test
> buffer), it walks records from offset 0 while they parse. `_stadium_at`'s plausibility
> checks (name 1–120 bytes, capacity ≤ 300,000) only serve that fallback.

## Output

`output/<label>/stadiums.json`, `{id: stadium}` with each record's byte `offset`, loaded into
`raw.stadiums`. On FMM27 each stadium also carries `alt_name` and `name_3`.
