# formations  ([`fmparser/tables/formations.py`](../../fmparser/tables/formations.py))

**The game's 21 stock formations, each with the position of its 11 slots.** The list a
staff record's formation fields index ([staff](staff.md)), and the layout the managed club's
saved tactics ([alt_managed_club](unread/alt_managed_club.md)) and the tactic in each of
[our matches](matches.md) are stored in. Both games, the same 21. `extract.py` writes
`formations.json` (the names, which the loader reads) and `formation_catalog.json` (index,
name, the 11 position codes).

| save | from | to |
|---|---|---|
| truro-2026-11-16 (FMM27) | 27,855,891 | 27,882,393 |
| frem-2026-06-11 (FMM22) | 20,596,961 | 20,623,463 |

Between the [season-year blocks](unread/rf_season_years.md) and the
[team selections](team_selections.md), whose count follows the last record.

## Layout

21 × 1,262 B, no count:

| offset | field | type | meaning |
|---|---|---|---|
| +0 | | u32 | 0x07f4b976 on every record (`76 b9 f4 07`), saved tactics too |
| +4 | `name` | 32 B | NUL-padded: `3-4-3`, `3-4-3 DM`, `4-4-2 Diamond` … |
| +36 | `positions` | 11 × u16 | slot 0 the goalkeeper, then the outfield slots in the tactic's order |
| +58 | | 1,204 B | not read: the codes again, eleven `01` bytes, `[u16][u16]` grids (positions in each phase, by the look of it) |

FMM27's order: 3-4-3, 3-4-3 DM, 4-1-2-2-1, 4-1-4-1, 4-2-1-3, 4-2-2-2, 4-2-3-1, 4-2-3-1 DM,
4-2-4, 4-3-1-2, 4-3-2-1, 4-3-3, 4-4-1-1, 4-4-2, 4-4-2 Diamond, 4-5-1, 5-1-2-2, 5-2-1-2,
5-2-2-1, 5-3-2, 5-4-1. FMM22 opens with 4-4-2.

### Position codes

A row bit in bits 0-6 and one lane bit in bits 7-11:

| row bit | row | | lane bit | lane |
|---|---|---|---|---|
| 0x01 | goalkeeper | | 0x800 | right flank (pinned below) |
| 0x04 | defence | | 0x400 | inside right? |
| 0x08 | defensive midfield / wing-back | | 0x200 | centre |
| 0x10 | midfield | | 0x100 | inside left? |
| 0x20 | attacking midfield | | 0x080 | left flank (pinned below) |
| 0x40 | attack | | | |

So 4-4-2 is GK `0001`, back four `0804 0084 0404 0104`, midfield `0810 0090 0410 0110`,
strikers `0440 0140`; a back three is `0404 0204 0104`, wing-backs `0808 0088`.

**Which side is which is pinned only for the flanks.** In Truro's
[team selection](team_selections.md), Love-Holmes (a right-back) stands in the `0804` slot of
their 4-1-2-1-2 and Law (a left-back) in `0084`. The inside lanes (`0400`, `0100`) are read
by symmetry, not yet against a screen.

## Evidence

truro-2026-11-16: the 21 names, and the 4-4-2 Diamond's eleven codes, which Truro's saved
4-1-2-1-2 carries code for code (`tests/test_team_selections_evidence.py`).

## Next

Screenshot a team's lineup on the pitch for a formation with a back three and one with
inside-left/right players, to pin the inside lanes; then name the positions in the loader.
