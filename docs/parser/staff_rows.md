# staff_rows  ([`fmparser/tables/staff_rows.py`](../../fmparser/tables/staff_rows.py))

**One 8-byte row per member of staff**, straight after the [per-person rows](person_index.md).
The second link of the chain of counted tables that runs from the languages to the
[rule files](rule_files.md); the next link is the [club rows](club_rows.md). Its extent is
proved; no field is named yet, so `extract.py` walks it and writes no file.

| | Truro (FMM27) | Frem (FMM22) | Bucaspor (FMM22) |
|---|---|---|---|
| rows (= staff records) | 6,212 × 8 B | 4,642 × 8 B | 5,697 × 8 B |

## Layout

`[count u16]` with no `0xFF` frame, flush against the per-person rows' end, then the rows,
row k = [staff](staff.md) id2 k. The same 8 bytes on both games.

| offset | type | what is seen |
|---|---|---|
| +0 | u16 | 0 to ~830. On Frem's last row (the user's) 0 / 202 / 424 / 829 on the 2021 / 2023 / 2026 / 2030 saves |
| +2 | u16 | 0 on ~99% of rows |
| +4 | u8 | 0 on ~97% of rows |
| +5 | u16 | at most 3 × `+7` on 938 of the 943 non-zero rows of frem-2026-06-11 |
| +7 | u8 | 0 to 49 |

**A lead, not a reading.** On frem-2026-06-11 the non-zero rows are managers', employed or
not, and `+5 ≤ 3 × +7` is the shape of a league record, points and games: Elche's manager
reads 100 and 42 (the Segunda has 42 rounds), Vejle's 69 and 32 (the Superliga, 32). It does
not match the user: 67 and 32, where Frem's 2025/26 line in [club_seasons](club_seasons.md)
is 53 points from 32 games. A Manager Profile screen from the same day as a save would settle
it.

## How it is found

`locate_staff_rows`: the u16 where the per-person rows end must equal the staff count, and
`count × 8` bytes later must sit a u16 equal to the [club](clubs.md) count. Both hold on all
eight saves.

> **Quirk: the counts are u16.** The person_index count reads as a u32, but this block's
> rows start two bytes after its count: the first row's first bytes are the "high half"
> a u32 reading would see. The last row's +0 on Frem (`a8 01`, 424) sits right before the
> club count `43 2c`.

## Evidence

[`tests/test_person_chain_evidence.py`](../../tests/test_person_chain_evidence.py): the start
and count on four saves of both games, the bytes at the block's end, and the landing on the
club count.

### FMM22

Identical layout; 4,642 rows on Frem, 5,697 on Bucaspor.
