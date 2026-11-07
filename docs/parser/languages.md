# languages  ([`fmparser/tables/languages.py`](../../fmparser/tables/languages.py))

The game's languages, each with its home nation and a difficulty. A count-framed table of 124
variable-length records in the reference block (~13.97 MB), `[≥ 8 × 0xFF][count u16 = 124]`,
in id order. Nation records and person records point at it by `id`. The count is the same in
both careers.

## Layout

| field | type | meaning | how we know |
|---|---|---|---|
| `id` | u16 | what person and nation language lists reference | Denmark's list names 31, which is `Danish` |
| `uid` | u32 | database id; 1,000,000+ on the game's own UI locales | |
| `name` | `[len u32][utf-8]` | no NUL | |
| `other_name` | `[len u32][utf-8]`, may be empty | an alternative name; empty on 42 records | |
| `nation_id` | u16 → [nations](nations.md) | the language's home nation; `0xFFFF` on the UI locales | Danish → 138 Denmark, Welsh → 175 Wales |
| `difficulty` | u8 | 0–20 | |

`locate_languages` finds record 0 by its bytes (`id 0`, `uid 1`, length 8, `Albanian`) and
checks that a run of `0xFF` sits in front of the count.

## Provenance

No in-game screen lists languages, so the check is the language lists that point here: each
nation's list ([nations](nations.md)) should name its own languages. On `frem-2030-06-22`,
Danish is record 31 at byte 13,957,127:

| check | raw bytes | parsed |
|---|---|---|
| Denmark's list leads with 31 at proficiency 100 | `1f 00` · `20 00 00 00` | `id` 31 · `uid` 32 |
| … and 31 is Danish | `06 00 00 00 "Danish"` `06 00 00 00 "Danish"` | `name`, `other_name` |
| … at home in Denmark | `8a 00` · `0b` | `nation_id` 138 · `difficulty` 11 |

England's list is English (7) alone; Wales's is English 100 and Welsh (112, home nation 175
Wales) 70. Tested by `tests/test_world_provenance.py`.

## Quirks

> **Quirk:** an empty `other_name` is data, not a terminator. A reader that required a
> non-empty string stopped at Malayalam (77), the first record with one, and lost the last 47
> languages. The competition table had the same failure with an empty code field.

> **Quirk:** the last five records are the game's UI locales (`Latin American`, `Brazilian`,
> `Chinese (Simple)`, `Chinese (Traditional)`, `English (US)`), uid 1,000,000+, with no home
> nation.

## Output

`output/<label>/languages.json`, `{id: language}` with each record's byte `offset`, loaded
into `raw.languages`.
