# staff  ([`fmparser/tables/staff.py`](../../fmparser/tables/staff.py))

Every staff member's coaching attributes, reputations and a manager's three formations
(preferred, attacking, defensive). A count-framed table of fixed 39-byte records,
`[8 × 0xFF][count u32]`, directly after [player_attributes](player_attributes.md), with
`id2 == slot index`. The count is a fixed pool per career: 4,642 on Frem, 5,697 on Bucaspor.
A person reaches his record through `id2` ([person_info](person_info.md) +64). The module
also reads the formation catalog (`formation_catalog`), the 21 shapes the formation fields
index.

## Layout

| offset | field | type | meaning | how we know |
|---|---|---|---|---|
| +0 | `id2` | u32 | equals the slot index | all 4,642 slots |
| +4 | `ca`, `pa` | 2 × u16 | ability; never shown (the immersion rule) | |
| +8 | `home_reputation` | u16 | | |
| +10 | `current_reputation` | u16 | | |
| +12 | `world_reputation` | u16 | sets the profile's Reputation: below 3,000 Regional, below 5,800 National, else Continental (`reputation_tier`) | seven managers |
| +14 | `attacking_intent` | u8 | hidden 1–20; sets the profile's Style: ≤ 7 Defensive, 8–13 Normal, ≥ 14 Attacking (`style`) | fourteen managers, both band edges |
| +15 | `financial_control` | u8 | 1–20 | seven managers |
| +16 | `outfield_coaching` | u8 | | |
| +17 | `goalkeeping_coaching` | u8 | 1–20, but 51–99 on 43 records (Quirks) | |
| +19 | `discipline` | u8 | | |
| +21 | `judging_ability` | u8 | | |
| +22 | `judging_potential` | u8 | | |
| +23 | `people_management` | u8 | | |
| +25 | `motivating` | u8 | | |
| +29 | `tactical_knowledge` | u8 | | |
| +30 | `youth_coaching` | u8 | | |
| +18, +20, +24, +26, +27, +28 | `hidden_s18` … `hidden_s28` | u8 | hidden 1–20, not identified; `hidden_s27` reads 1–4 on 96% of staff, the most distinctive of the six | |
| +31 | `formation_preferred` | u8 | index into the formation catalog (0 = 4-4-2, 5 = 4-2-3-1, 17 = 5-2-1-2) | seven managers |
| +32 | `formation_attacking` | u8 | | |
| +33 | `formation_defensive` | u8 | | |
| +34 | | 5 × u8 | unnamed; values 0–19, near-unique per person, identical across saves | |

The formation catalog: 21 templates of 1,262 bytes, found by the marker `76 b9 f4 07` (the
name is ASCII at +20 of each). `formations.json` lists the names in catalog order.

## Evidence

The seven Danish Superliga managers' profiles of 25 Nov 2024, against `frem-2024-11-22`:
preferred formation, reputation tier and all ten coaching attributes exact for 7 of 7, and
the eight personality values on their [person_info](person_info.md) records byte for byte.
Seven more managers' Style was predicted from `attacking_intent` on `frem-2026-07-02`
before reading it in game, chosen to sit on the band edges: Peter Pedersen at 8 reads
Normal and Jon Dahl Tomasson at 14 reads Attacking. All seven matched. Both sets are the data in
`tests/test_staff_records.py`.

| manager (2024) | Style on screen | `attacking_intent` | Formation on screen | `formation_preferred` |
|---|---|---|---|---|
| Radoslav Látal (OB) | Defensive | 7 | 4-2-3-1 | 5 |
| Jesse Marsch (FCM) | Normal | 13 | 4-4-2 | 0 |
| Jess Thorup (FCK) | Attacking | 15 | 4-1-2-2-1 | 2 |

On `frem-2030-06-22`, Frem's Tom Little (Adingra's Training Report names him Assistant
Manager) has `id2` 3137, record at byte 6,157,665:

```
41 0c 00 00  6e 00 b4 00  f8 11 f8 11 fc 08  03 06 03 02 0e 0f 0d 0a 0a 05 0a 0c 13 08 12 04 08  11 11 11  0e 0a 11 07 02
```

`attacking_intent` 3 (Defensive), formations 17 / 17 / 17 (5-2-1-2), world reputation
2,300 (Regional). His profile screenshot will confirm these.

## Quirks

> **Quirk:** Style is derived, not stored. The record's 39-byte extent leaves no room for a
> three-valued field, and the bands on `attacking_intent` predicted fourteen managers'
> Style. `corr(attacking_intent, world_reputation)` is +0.12 on `frem-2030-06-22`, so it is not
> quality in disguise.

> **Quirk:** the club record's staff array lists the coaches but not the manager. The manager
> is the club's staff member missing from it ([clubs](clubs.md)); Frem has none in the list
> because we manage it.

> **Quirk:** 43 records read 51–99 at +17 (`goalkeeping_coaching`): retired goalkeepers
> such as Ben Foster and Tom Heaton, most of them free agents. `_process_staff` drops any
> record with an attribute outside 1–20, so these 43 are missing from `staff_records.json`
> although the extract promises every record. Open in TODO as "Staff records with
> goalkeeping coaching above 20 are dropped".

> **Dead end:** formation and Style are not in the person record or anywhere near it. Exact,
> nibble and single-bit searches for 16 managers' Style, and for 9 managers' formations as an
> index, a name or an 11-slot position vector, found nothing within ±20,000 bytes. They are
> in this separate table, reached by `id2`.

> **Dead end:** Job Status and the manager Rank are not located.

## Output

`output/<label>/staff_records.json`: one row per record in table order (the derived
`reputation_tier` and `style` are left out), loaded into `raw.staff_records`.
`output/<label>/formations.json`: the 21 catalog names, loaded into `raw.formations`.
