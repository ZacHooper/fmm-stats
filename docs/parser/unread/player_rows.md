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
| +22 | u16 | `ffff` on most players; a small number on a few |
| +24 | 6 × u32 | 100 on most players |
| +48 | 6 × u32 | two player-table indexes, two 100s, then two indexes again |

- **The four indexes at +4 are not people that belong with the player.** Read as player-table
  indexes, a column holds every player exactly once; no attribute orders it (ability,
  reputation, age, height and club all rise as often as they fall); and they reshuffle
  almost completely between saves (under 1% unchanged in 17 days). Engine working state,
  most likely: random pairings the game draws each day.
- **The u16 at +20** correlates with nothing read so far (ability, reputation, age, morale,
  caps, height all |r| < 0.05) and is not the Club Squad screen's condition.

## Examples (truro-2026-11-16)

| player | tid | +20 | +22 | +48 (two indexes) |
|---|---|---|---|---|
| Ben Starkie | 4353 | 61 | `ffff` | 12777, 26491 |
| Omar Bogle | 6588 | 74 | `ffff` | 15075, 20135 |
| Luke Jephcott | 8820 | 67 | `ffff` | 17305, 24063 / 24146 |
| Harvey Greenslade | 25700 | 59 | `ffff` | 19204 (himself), 27654 / 27765 |
| Maxwell Kinsey-Wellings | 29417 | 53 | **87** | 6393, 29581 |
| Lewis Colwell (transfer-listed) | 31086 | 39 | **20** | 11642 / 11772, 33871 |

(Indexes are player-table rows: 19204 is Greenslade's own row.)

Kinsey-Wellings and Colwell are the only two of these with a number at +22; Colwell is
listed for transfer and has two interested clubs, Kinsey-Wellings neither.

## Tried

- The four columns as person tids (random people at unrelated clubs) and as sort orders
  (monotonic test above): neither.
- The +20 number against every player field read and against condition, morale and
  appearances on the 25 Jul Club Squad screen.

## Next

1. Find which players have +22 set (how many, and what they share).
2. Diff the +20 number over a match: a save before and after a game, for the players who
   played.
3. Table 6's one person (Kimika Forbes, tid 37304): what puts that row in a list of its own.

## Evidence that would help

A save the day before a match and one the day after; and any screen that shows a number per
player that drifts slowly (sharpness? happiness?).
