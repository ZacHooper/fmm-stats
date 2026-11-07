# names  ([`fmparser/tables/names.py`](../../fmparser/tables/names.py))

How a person's name ids become text. Two parts: the browse strings, a flat list of names near
the start of the file, and three id-tables (first names, surnames, nicknames) that map a name
id to a position in that list. A [person_info](person_info.md) record holds the three ids.

```
person.first_name_id ──► first-name id-table[id].ordinal ──► browse[ordinal]   "Simon"
person.last_name_id  ──► surname id-table[id].ordinal    ──► browse[ordinal]   "Adingra"
person.common_name_id ─► nickname id-table[id].ordinal   ──► browse[ordinal]   (0xFFFFFFFF = none)
```

## Layout

**Browse strings.** `[len u32][utf-8]` repeated, starting a few hundred bytes into the file
(byte 299 on `frem-2030-06-22`, 45,942 strings to byte 515,797). In front of them sit
`ff ff ff ff` and a u32 of 60,000 in both careers: a capacity, not a count (Bucaspor holds
45,834). `walk_browse_bounds`
takes the first run of more than 1,000 well-formed strings (length 1–40, no control bytes).

**Id-tables.** Three count-framed tables, `[8 × 0xFF][count u32]`, back to back at ~40 MB,
16-byte entries, `id == slot index` on every used slot:

| offset | field | type | meaning |
|---|---|---|---|
| +0 | `ordinal` | u32 | position in the browse strings |
| +4 | `id` | u32 | equals the slot index; `0xFFFFFFFF` on an unused slot (all 16 bytes `FF`) |
| +8 | | 8 B | unnamed |

| table (file order) | declared | used on `frem-2030-06-22` |
|---|---|---|
| surnames | 32,148 | 28,625 |
| first names | 19,128 | 15,367 |
| nicknames | 9,480 | 1,950 |

`discover_id_tables` finds the first table by its run of consecutive ids, then chains forward
on each table's declared count. The three are told apart by size: the largest is surnames,
the next first names, the smallest nicknames.

## Evidence

`frem-2030-06-22`. Simon Adingra (tid 26552): `first_name_id` 9932, `last_name_id` 20420,
`common_name_id` none.

| id-table entry | raw bytes | ordinal | browse string |
|---|---|---|---|
| first names, slot 9932 (byte 40,570,893) | `27 94 00 00 cc 26 00 00 00 18 00 00 00 03 00 ff` | 37,927 | `Simon` |
| surnames, slot 20420 (byte 40,224,321) | `93 44 00 00 c4 4f 00 00 00 18 00 00 00 01 00 ff` | 17,555 | `Adingra` |

The same chain names everyone on the screens in this group: Gustav Ullits (4646 / 8770),
Valdemar Lund Jensen, and the people in their relationship lists (Presnel Kimpembe).

A nickname: Vendsyssel's tid 19158 has first name `Juan Carlos`, surname `Lázaro` and
`common_name_id` 1131 → `Kaiser` (nickname slot at byte 40,736,137, `8e b1 00 00 6b 04 00
00 …`). `mart.dim_person` names him Kaiser. Brøndby's tid 20905 is Carlos Polo with nickname 1449,
`Peque Polo`, the name Brøndby's team sheet shows. Tested by `tests/test_people_evidence.py`.

## Quirks

> **Quirk:** a name id is an index into its id-table, not into the browse strings. Reading
> `browse[first_name_id]` gives a plausible wrong name: Adingra's 9932 and 20420 read
> `Cohen Lampe`.

> **Quirk:** the three tables are assigned by size, not by position. If a career's
> nickname table ever outgrew its first-name table, the labels would swap.

> **Quirk:** 1,583 people have a nickname. The game shows the nickname where there is one
> ("Kaiser"), so a name built from first + last alone doesn't match the screen for them.

## Output

`output/<label>/browse_names.json`: the browse strings, in order, loaded into
`raw.name_strings`. `output/<label>/name_ids.json`: `{first_names, surnames, nicknames}`,
each its used slots as `{id, ordinal}`, loaded into `raw.name_ids`.
