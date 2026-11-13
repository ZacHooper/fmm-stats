# After loans, 2: ranked player lists

Between the [loans](../loans.md) and the [transfer band](../savefile-map.md#the-transfer-band),
the second of two sub-tables there on FMM27, after the
[position-masked headers](al_position_lists.md).

| save | from | to | size |
|---|---|---|---|
| truro-2026-11-16 | 37,051,936 | 38,133,604 | 1.08 MB: 90,139 × 12 B |

## Known

- **12-byte rows `[person tid u32][value u32][value u32 or −1]`**, running straight into the
  transfer band's `[u32 65,000]`. The last three rows are zero.
- Rows 0–58: placeholders `[0][0][id]`, the ids ascending (6,930, 6,931 …).
- **Rows 59–1,658 rank the world's goalkeepers**, sorted on the larger value, descending:
  Courtois 40,600, Alisson 40,000, Kobel 39,800, Oblak 38,600, Raya 38,600 … down to
  19,200. Where the third value is set it is the higher one (Joan García 36,400 / 37,400).
- Rows 1,659–3,747: a second list from 19,200 down to 3,000 (Julian Fuest, Darío Ramos,
  Owen Foster …): goalkeepers again by the look of it, a lower tier.
- From row 3,748 (about 37,096,900) the reading drifts by 4 bytes: tids land in the middle
  column. So a new list with its own small header starts there; the rest, about 86,000 rows,
  is not split yet. 16,451 distinct tids in all.
- Values step in 200s at the top (40,600, 40,000, 38,600): a rating or reputation scale,
  maybe the scouting value the game ranks players by. Not checked against a screen.

## Next

1. Find the list headers inside the run (where the 4-byte drift starts) and count the lists:
   one per position group, or per position?
2. Ask for an in-game screen that ranks players (e.g. a scouting search sorted by rating or
   value) to name the two values.
3. Compare across the four FMM27 saves; then check FMM22's 1.16 MB.
