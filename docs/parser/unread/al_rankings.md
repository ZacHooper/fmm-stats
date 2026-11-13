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
- From row 3,748 (37,096,912) the rows change character: the sort key moves to the third
  column, the middle one holds a free value (21,310, 24,788 …), and 12,729 rows have tid −1.
- **The run breaks at 8-byte gaps** (two u32 that read as neither tid nor value): at
  37,357,264, 37,692,168, 37,755,028, 37,843,988 and 37,956,540. The list after the first gap
  is **midfielders ranked**: Kimmich 45,200, Rice 44,600, Vitinha 44,200, Pedri 43,120. The
  later ones read with the columns rotated, so their row phase is not settled. 16,451 distinct
  tids in all.
- Values step in 200s at the top (40,600, 40,000, 38,600): a rating or reputation scale,
  maybe the scouting value the game ranks players by. Not checked against a screen.

## Next

1. Read the 8-byte gaps as list headers, settle each list's row phase, and name its top
   players: one list per position group, or per position?
2. Ask for an in-game screen that ranks players (e.g. a scouting search sorted by rating or
   value) to name the two values.
3. Compare across the four FMM27 saves; then check FMM22's 1.16 MB.
