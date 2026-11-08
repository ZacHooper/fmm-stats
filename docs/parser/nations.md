# nations  ([`fmparser/tables/nations.py`](../../fmparser/tables/nations.py))

Every nation: names, continent, capital and national stadium, its national team's world
ranking, its ranking history, its continental coefficients and the languages spoken there.
A count-framed table of 251 variable-length records in the reference block (~12.75 MB),
`[8 × 0xFF][count u16 = 251]`, in id order from 0, walked by declaration with
`id == slot index`. The walk ends exactly on the continent table's own count frame.

## Layout

| segment | field | type | meaning | how we know |
|---|---|---|---|---|
| `NATION_HEAD` | `uid` | u32 | database id; a national team's club record carries `-uid` ([clubs](clubs.md)) | all 251 |
| | `id` | u16 | the nation id everything else points at; equals the slot index | the walk's invariant |
| strings | `name`, `nationality`, `code` | `[len u32][utf-8]`, the first two NUL-terminated | `Denmark`, `Danish`, `DEN` | |
| `NATION_TAIL` | `continent_id` | u16 | 0 Africa … 5 South America; `0xFFFF` on defunct states | Denmark 2 = Europe (Team Information) |
| | `capital_city_id` | u16 → [cities](cities.md) | Denmark → 58, Copenhagen | |
| | `national_stadium_id` | u16 → [stadiums](stadiums.md) | Denmark → 177, Parken | |
| `NATION_TEAM` (23 B) +11 | `rival_nation_id` | u16 | `0xFFFF` = none | Denmark → Sweden, England → Scotland, Sweden → Norway |
| +18 | `is_ranked` | u8 | | Denmark 1 |
| +19 | `world_ranking` | u16 | current world ranking | Denmark 22nd (Team Information) |
| +21 | `ranking_points` | u16 | world ranking points | Denmark 1,699 |
| +0..+17 | | 18 B | unnamed (`NATION_TEAM` declares them `UNKNOWN`) | |
| `ranking_history` | | `[u16 n][n × u16]` | past world rankings; 0 entries on an unranked nation. Order **unverified**: the module docstring says oldest first, but Denmark's last entry is 24 while it is 22nd today | |
| `NATION_GAP` | | u16 = 0 | | |
| `coefficients` | | `[u8 n][n × f32]` | continental coefficients by season, oldest first; 11 entries | Coefficients screen (below) |
| `NATION_GAP2` | | u8 = 0 | | |
| `languages` | | `[u8 n][n × (language_id u16, proficiency u8)]` | languages spoken, proficiency 0–100 → [languages](languages.md) | Denmark: Danish 100 |
| `NATION_END` | | 11 B | unnamed | |

`scrape_nations` turns `rival_nation_id` outside 1–4096 into `None`, `is_ranked` into a bool,
and rounds coefficients to 4 places.

## Evidence

`frem-2030-06-22`, League Standards → Coefficients. Denmark's record starts at byte
12,759,310; its coefficient list at 12,759,427:

![League Standards - Coefficients: Denmark 7.400, 8.375, 76.400](img/nations-1.png)

```
0b                       n = 11
00 00 84 40  4.125       slot 0
00 00 08 41  8.5         slot 1
cd cc ec 40  7.4         slot 2   <- first season column on screen
00 00 06 41  8.375       slot 3   <- second season column
00 00 e0 40  7.0         …
33 33 c3 40  6.1
9a 99 31 41  11.1
9a 99 31 41  11.1
cd cc ec 40  7.4
9a 99 a9 40  5.3
00 00 00 00  0.0         slot 10, the season not yet played
```

| on screen (Denmark) | parsed |
|---|---|
| `7.400` | `coefficients[2]` = 7.4 |
| `8.375` | `coefficients[3]` = 8.375 |
| `76.400` (the total) | `sum(coefficients)` = 76.4 |

The same holds for every row on the screen: Italy 19.429 / 19.286 / 184.571, Holland 16.000 /
8.100 / 99.900, Austria 8.500 / 10.300 / 76.100. Capital and national stadium check against the
real world: Denmark → city 58 (Copenhagen's coordinates) and stadium 177 (Parken, 38,065).

Denmark's Team Information screen. `NATION_TAIL` at byte 12,759,346, `NATION_TEAM` at
12,759,352:

![Denmark: Parken 38,065, Europe, Denmark U21, 22nd (1,699 pts)](img/nations-2.png)

| on screen | raw bytes | parsed |
|---|---|---|
| Continent `Europe` | tail +0 `02 00` | `continent_id` 2 |
| Stadium `Parken`, 38,065 | tail +4 `b1 00` | `national_stadium_id` 177 → [stadiums](stadiums.md) |
| World Ranking `22nd (1,699 pts)` | team +18 `01`, +19 `16 00`, +21 `a3 06` | `is_ranked` true, `world_ranking` 22, `ranking_points` 1,699 |
| Youth Squad `Denmark U21` | (the club table) | Denmark U21 (tid 11236) has `main_club_tid` 547, the Denmark national team ([clubs](clubs.md)) |

Tested by `tests/test_world_evidence.py`.

## Quirks

> **Quirk:** the Coefficients screen's two season columns are slots 2 and 3 of the list,
> whatever seasons the header names, and its total is the sum of all eleven. Use the total
> and the trend; don't map a slot to the season the game prints beside it.

> **Quirk:** coefficients exist for Europe's 55 nations and for most of Africa and Asia (132
> nations carry 11 entries); the rest carry none.

> **Quirk:** `NATION_TEAM` +1..+8 read `ff 7f d4 00 00 00 ff 7f` on 250 of 251 nations. The
> one exception, in both careers (Frem 2023 and 2030, Bucaspor 2023), is Denmark, `fe 7f 00 70 00 70 fe 7f`, which as RGB555 is
> white, red, red, white: Denmark's colours. A lead, not a decode: why only one nation carries
> its own is unknown.

> **Quirk:** `continent_id` is `0xFFFF` on 23 defunct or unaffiliated states (C.I.S.,
> Czechoslovakia, E. Germany, U.S.S.R., W. Germany, …). A gate that requires a real continent
> drops them, and a gate that requires `id ≥ 1` drops Algeria, id 0. Walk by declaration.

> **Quirk:** Russia reads `is_ranked` true, `world_ranking` 0 and 1,463 points on both
> careers. A rank of 0 is neither first nor unranked; the game's suspension is the likely
> reason (unverified).

> **Quirk:** the ranking history's length is not a constant: 11 entries on `bucaspor-2022-06-19`,
> 24 from 2023 on. Read the count; a hard-coded 24 returns nothing on an early save.

## Output

`output/<label>/nations.json`, `{id: nation}` with each record's byte `offset`. The loader
splits it into `raw.nations`, `raw.nation_ranking_history`, `raw.nation_coefficients` and
`raw.nation_languages`.
