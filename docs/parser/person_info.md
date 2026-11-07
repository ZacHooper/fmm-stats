# person_info  ([`fmparser/tables/person_info.py`](../../fmparser/tables/person_info.py))

Every person in the database, players and staff alike: identity, nationality, club,
international record, personality, languages and the people and clubs they are linked to.
A count-framed table near the start of the file, `[≥ 8 × 0xFF][count u32][01]`, then the
records in tid order from 0, walked by declaration with `tid == slot index`. Variable-length
records. The count is a fixed pool, the same on every save of a career: 32,966 on Frem,
34,312 on Bucaspor.

## Layout

A record is a 68-byte head, 17 bytes, then two counted lists:

| offset | field | type | meaning | how we know |
|---|---|---|---|---|
| +0 | `tid` | u32 | the person id; equals the slot index | the walk's invariant |
| +4 | `uid` | u32 | database id | |
| +8 | `first_name_id` | u32 | → [names](names.md) | resolves to the name on screen |
| +12 | `last_name_id` | u32 | → [names](names.md) | |
| +16 | `common_name_id` | u32 | the nickname, → [names](names.md); `0xFFFFFFFF` = none | 1,583 people have one |
| +20 | `dob` | date `[day-of-year u16, 0-based][year u16]` | date of birth | Player Personal (below) |
| +24 | `nationality_id` | u16 | → [nations](nations.md) | Adingra Ivorian, Lund Jensen Polish |
| +26 | `second_nationality_id` | u16 | `0` or `0xFFFF` = none (→ `None`) | Lund Jensen: Other Nationality Danish |
| +28 | `ethnicity` | u8 | a small enum (fmm-editor's name) | |
| +29 | | 4 B | unnamed | |
| +33 | `type_flag` | u8 | 1 on every player; 0, 1 or 16 on a non-player | |
| +34 | `unknown_date` | date | unnamed | |
| +38 | `international_caps` | u8 | | 25 for Adingra and Lund Jensen |
| +39 | `international_goals` | u8 | | 6 and 1 |
| +40 | `u21_caps` | u8 | | Ullits 3 |
| +41 | `u21_goals` | u8 | | Ullits 0 |
| +42 | `club_tid` | u32 | the club holding his registration; above `0xFFFF` → `0xFFFF` (no club) | |
| +46 | `joined_date` | date | when he joined `club_tid` | equals the contract's `start_date` for Adingra |
| +50 | | 2 B | unnamed | |
| +52 | `adaptability` … `temperament` | 8 × u8 | personality, 1–20, in this order: adaptability, ambition, determination, loyalty, pressure, professionalism, sportsmanship, temperament | seven managers' profiles, byte for byte (`tests/test_staff_records.py`) |
| +60 | `sid` | u32 (hex) | → the [player_attributes](player_attributes.md) slot; `ffffffff` = not a player | |
| +64 | `id2` | u32 | → the [staff](staff.md) slot; `0xFFFFFFFF` = not staff | |
| +68 | | 4 × u32 + u8 | unnamed; the ids are `0xFFFFFFFF` on 94–98% of people | |
| +85 | `languages` | `[u8 n][n × (language_id u16, level u8)]` | → [languages](languages.md); level 0–10, `255` on 4% of entries | Player Personal (below) |
| | `relationships` | `[u16 m][m × 8 B]` | clubs and people this person is linked to (below) | Lund Jensen's favoured club and person |

A relationship is `[u8 unnamed][target_kind u8][target_id u32][u8 unnamed][u8 unnamed]`.
`target_kind` 1 is a club tid, 3 a person tid.

A player has a `sid` and a staff member an `id2`. 319 people on `frem-2030-06-22` have both
(player-coaches) and 2,427 have neither.

## Evidence

`frem-2030-06-22`. Valdemar Lund Jensen (tid 10446), record at byte 1,679,979:

![Lund Jensen: 28/5/2003, Polish, 25 caps / 1 goal](img/person_info-1.png)
![Lund Jensen, Player Personal: Other Nationality Danish, Favoured Club FC København, Favoured People Presnel Kimpembe, seven languages](img/person_info-2.png)

| on screen | raw bytes | parsed |
|---|---|---|
| `28/5/2003` | +20 `93 00 d3 07` | `dob` day 147 of 2003 |
| `Polish` | +24 `a1 00` | `nationality_id` 161 |
| Other Nationality `Danish` | +26 `8a 00` | `second_nationality_id` 138 |
| `25 caps / 1 goal` | +38 `19 01` | `international_caps` 25, `international_goals` 1 |
| Personality `Determined` | +52 `0b 0c 10 0f 0d 0f 0b 0a` | determination 16, the highest of the eight |
| Favoured Club `FC København` | relationship `03 01 58 01 00 00 01 64` | club tid 344 |
| Favoured People `Presnel Kimpembe` | relationship `01 03 6f 57 00 00 09 64` | person tid 22383 |
| Danish (Natural), English (Natural) | `1f 00 0a`, `07 00 0a` | Danish 10, English 10 |
| Norwegian (Fluent), Swedish (Fluent) | `15 00 08`, `1d 00 08` | 8, 8 |
| Polish (Good), Dutch (Good) | `11 00 05`, `06 00 05` | 5, 5 |
| German (Basic) | `0a 00 02` | 2 |
| (not shown) | `0e 00 00`, `17 00 00` | Italian 0, Spanish 0 |

Simon Adingra (tid 26552), record at 3,325,053:

![Adingra, Player Personal: 1/1/2002, no other nationality, French (Natural), Danish (Fluent), English (Good)](img/person_info-3.png)

| on screen | raw bytes | parsed |
|---|---|---|
| `1/1/2002` | +20 `00 00 d2 07` | day 0 of 2002 |
| Other Nationality `None` | +26 `ff ff` | `None` |
| French (Natural), Danish (Fluent), English (Good) | `03`, then `07 00 05`, `1f 00 07`, `09 00 0a` (stored English, Danish, French) | French 10, Danish 7, English 5 |
| Favoured Club / People `None` | `00 00` | no relationships |
| joined Frem | +46 `e3 00 ec 07` | `joined_date` 2028-08-15 |

The screen sorts languages by level and names the bands Natural (10), Fluent (7–8), Good
(5) and Basic (2). A level of 0 is not shown. Tested by `tests/test_people_evidence.py`.

## Quirks

> **Quirk:** a tid is a slot, not a person. The game gives a retired person's tid to a newgen:
> between `frem-2026-06-11` and `frem-2030-06-22`, 6,064 of the 32,966 tids changed occupant,
> and `dob` differed on every one. Key a person by `(tid, dob)` (`mart.dim_person`'s
> `person_id`), never by tid alone, or two careers splice into one.

> **Quirk:** the Player Relationships screen is not the relationship list. Adingra's screen
> shows a positive link with Adam Jakobsen and Røssner, but his list is empty. The list
> holds the Personal screen's Favoured Club and Favoured People, and more entries the screen
> doesn't show (Lund Jensen also lists Liverpool, Brøndby and three managers).
>
> ![Adingra, Player Relationships](img/person_info-4.png)

> **Quirk:** `type_flag` is not the player/staff split. It is 1 on every player, but also on
> 1,936 non-players. Decide by `sid` (`ffffffff` = not a player) and `id2`.

> **Dead end:** finding records by scanning for the "no nickname" `ffffffff` at +16, or for
> the staff `ffffffff` at +60, misses everyone with a nickname (1,583 people) and reads
> records out of alignment. The walk from the count frame reads all 32,966, with no empty
> slots.

## Output

`output/<label>/persons.json`: the 68-byte head of every person, in tid order, loaded into
`raw.person_records`. The languages and relationships are read by the walk but not emitted.
