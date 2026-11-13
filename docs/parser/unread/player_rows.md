# One 72-byte row per player (block tables 5 and 6)

Part of [the block after the club titles](end_block.md). FMM27, at block offset 15,504 on
truro-2026-11-16: `[u32 n][n × 72 B]`, ascending by tid; then table 6, `[u32 1][1 × 72 B]`,
the same shape for one more person.

| save | rows | table 6's person |
|---|---|---|
| 22 Jul, 25 Jul, 8 Aug | 36,343 | 37304 Kimika Forbes |
| 16 Nov | 36,345 | 37304 Kimika Forbes |

The rows run tid 401 to 44,958 and are 2.6 MB, the block's biggest table.

## Known

| offset | type | what |
|---|---|---|
| +0 | u32 | the player's tid, ascending |
| +4 | 4 × u32 | four player-table indexes (0–36,202); each column is a **random permutation** of the players |
| +20 | u16 | 0–190; changes slowly (86% unchanged over 17 days, 40% over three months) |
| +22 | u16 | set only on young players: every player aged 21 or under, part of the 22-year-olds, nobody older (born 18 Jul 2004 or later; 12,063 players on 16 Nov); 20–118; `ffff` otherwise |
| +24 | 6 × u32 | `ffff…` on 28,856 players, 100 on 7,389 (the whole Truro squad and its league), a few other values (74, 93, 57: percentages?) |
| +48 | 6 × u32 | two player-table indexes, two 100s, then two indexes again |

- **The four indexes at +4 are not people that belong with the player.** Read as player-table
  indexes, a column holds every player exactly once; no attribute orders it (ability,
  reputation, age, height and club all rise as often as they fall); and they reshuffle
  almost completely between saves (under 1% unchanged in 17 days). Engine working state,
  most likely: random pairings the game draws each day.
- **The u16 at +20** correlates with nothing read so far (ability, reputation, age, morale,
  caps, height all |r| < 0.05) and is not the Club Squad screen's condition.

## Examples (truro-2026-11-16): whole rows

| bytes | Ben Starkie | Omar Bogle | Maxwell Kinsey-Wellings | Lewis Colwell |
|---|---|---|---|---|
| +0 tid | 4353 | 6588 | 29417 | 31086 |
| +4 four indexes | 12789, 27004, 35446, 26491 | 15085, 20934, 33148, 21144 | 6421, 30424, 6393, 29581 | 11642, 34137, 11772, 33983 |
| +20 u16 | 61 | 74 | 53 | 39 |
| +22 u16 | `ffff` | `ffff` | **87** | **20** |
| +24 six u32 | 100 × 6 | 100 × 6 | 100 × 6 | 100 × 6 |
| +48 six u32 | 12777, 26491, 100, 100, 12777, 26491 | 15075, 20135, 100, 100, 15075, 20135 | 6393, 29581, 100, 100, 6393, 29581 | 11642, 33871, 100, 100, 11772, 33871 |

Kinsey-Wellings, raw: `e9 72 00 00 | 15 19 00 00 d8 76 00 00 f9 18 00 00 8d 73 00 00 | 35 00 |
57 00 | 64 00 00 00 × 6 | f9 18 00 00 8d 73 00 00 64 00 00 00 64 00 00 00 f9 18 00 00 8d 73 00 00`.

The +48 indexes are drawn from the four at +4 (Kinsey-Wellings's are his third and fourth,
Colwell's his first and third) or sit close to them, so +48 is part of the same working
state. Greenslade's +48 holds his own row (19204). The fields that look like player data
are +20 and +22. (A "Seckie" was asked for; no Truro player has that name, so Ben Starkie
stands in.)

## Lined up: Truro and its league (truro-2026-11-16)

`--` = `ff` (empty). The +4 and +48 indexes (working state) are left out.

| player | club | +20 | +22 | +24 (six u32) | +56/+60 |
|---|---|---|---|---|---|
| Ben Starkie | Truro | 61 | -- | 100 × 6 | 100/100 |
| Omar Bogle | Truro | 74 | -- | 100 × 6 | 100/100 |
| Will Dean | Truro | 71 | -- | 100 × 6 | 100/100 |
| Luke Jephcott | Truro | 67 | -- | 100 × 6 | 100/100 |
| Harvey Greenslade | Truro | 59 | -- | 100 × 6 | 100/100 |
| Josiah Aboh | Truro | 35 | **106** | 100 100 -- -- 100 100 | --/-- |
| Maxwell Kinsey-Wellings | Truro | 53 | **87** | 100 × 6 | 100/100 |
| Jack Nunn | Truro | 53 | **83** | 100 × 6 | 100/100 |
| Jack Matthews | Truro | 45 | **75** | 100 × 6 | 100/100 |
| Tylor Love-Holmes | Truro | 46 | **37** | 100 × 6 | 100/100 |
| Tom Tweedy | Truro | 66 | **22** | 100 × 6 | 100/100 |
| Luca Barrington | Torquay | 88 | **117** | 100 × 6 | 100/100 |
| Jordan Archer | Torquay | 87 | -- | 100 × 6 | 100/100 |
| Charlie Casper | Chesham | 65 | **118** | 100 × 6 | 100/100 |
| Harry Barbrook | Chelmsford | 58 | **95** | 100 × 6 | 100/100 |
| Andy Carroll | Dagenham & Redbridge | 67 | -- | 100 × 6 | 100/100 |
| Jet Dyer | Dagenham & Redbridge | 32 | **38** | 100 × 6 | 100/100 |
| Essa Jadama | Dover | 27 | **55** | 100 × 6 | 100/100 |
| Jaye Long | Slough | 33 | **66** | 100 × 6 | 100/100 |

## Tried

- The four columns as person tids (random people at unrelated clubs) and as sort orders
  (monotonic test above): neither.
- The +20 number against every player field read and against condition, morale and
  appearances on the 25 Jul Club Squad screen.

## Next

1. +22: what young-player number this is. Not ability or potential (|r| < 0.04). A screen
   that shows a number for youngsters only (development? a youth rating?) is the lead.
2. Diff the +20 number over a match: a save before and after a game, for the players who
   played.
3. Table 6's one person (Kimika Forbes, tid 37304): what puts that row in a list of its own.

## Evidence that would help

A save the day before a match and one the day after; and any screen that shows a number per
player that drifts slowly (sharpness? happiness?).
