# Player progress → training: a row per person of attribute changes

Between [player progress](../player_progress.md) and [training](../training.md), on both
games. Until now taken for padding.

| save | from | to | size |
|---|---|---|---|
| truro-2026-11-16 (FMM27) | 58,958,685 | 59,992,765 | 1,034,080 B = 44,960 × 23 |
| frem-2026-06-11 (FMM22) | 52,721,064 | 53,479,282 | 758,218 B = 32,966 × 23 |
| bucaspor-2023-04-01 (FMM22) | | | 789,176 B = 34,312 × 23 |

## Known

- **One 23-byte row per person**: the size is exactly the person count
  ([person_index](../person_index.md)) × 23 on every save of both games. No count in front.
- **Each byte is a signed change, by the look of it one per displayed attribute**: 23 is the
  number of attributes a player shows (7 technical, 7 mental, 4 physical, 5 goalkeeping). All
  zero on day-one saves (truro-2026-07-22, frem-2021-06-27).
- **Only the managed club's players have rows set**: 3 on truro-2026-08-08, 23 on 16 Nov, all
  Truro players; 31–55 on the Frem saves, 29 on Bucaspor.
- Read against the change in each Truro player's attributes between the 8 Aug and 16 Nov
  snapshots (`mart.fact_player_snapshot`), the columns line up for most players:

  | col | attribute | evidence (row → change 8 Aug to 16 Nov) |
  |---|---|---|
  | 0 | Crossing | tid 37088: +2 → Crossing +2 |
  | 1 | Dribbling | Law +2 → +2 |
  | 2 | Aerial | tid 31087 +1 → +1 |
  | 3 | Passing | tid 29941 |
  | 4 | Shooting | Greenslade +1 → +1 |
  | 5 | Tackling | tid 9274 +2 → +2; tid 31087 +2 → +2 |
  | 8 | Decisions | tid 29941 |
  | 10 | Leadership | Starkie +1 → +1 |
  | 11 | Movement | Riley-Lowe, tid 29649 |
  | 12 | Positioning | Oxlade-Chamberlain +2 → +2 |
  | 13 | Teamwork | Zac Bell, tid 37343 |
  | 14, 15, 16 | Pace, Stamina, Strength | Bogle −1, −1 → Pace −1, Stamina −1 |
  | 20–22 | goalkeeping (Throwing at 22) | the two keepers only; Stone +1 → Throwing +1 |

  Not every player agrees: the row is not the whole 8 Aug → 16 Nov change (Lavercombe's row
  is +1, +1 with no change between the snapshots, Rooney's −1, −1, −1 likewise). The window
  is probably the profile's "recent changes" (the arrows), shorter than three months.

## Next

1. Screenshot a Truro player's attributes with their change arrows on the day of a save, to
   pin the window and the column order (6, 7, 9, 17, 18, 19 are unplaced).
2. Then it is a small table: 23 i8 per person, keyed by tid.
