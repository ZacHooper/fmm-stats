# officials  ([`fmparser/tables/officials.py`](../../fmparser/tables/officials.py))

The match officials: one 99-byte record per referee, with his six refereeing attributes and
the competitions he takes charge of. A count-framed grid, `[>= 8 × ff][count u32]`, at
~6.24 MB, directly in front of [rounds](rounds.md). 622 records on every Frem save, 1,109 on
Bucaspor. Each official is also a person in [person_info](person_info.md), which holds his
name, date of birth and nationality. Not extracted.

## Layout

| offset | field | type | meaning | how we know |
|---|---|---|---|---|
| +0 | `slot_id` | u32 | the record's index, 0..N−1 | dense on every record |
| +4 | `uid` | u32 | the person's uid | = the person record's uid, 622 of 622 |
| +8 | `tid` | u32 | the person's tid | |
| +12 | `ca` | u16 | current ability | |
| +14 | `pa` | u16 | potential ability | |
| +16 | `reputation` | u16 | | |
| +18 | `allowing_flow` | u8 | 1–20 | name unverified |
| +19 | `discipline` | u8 | 3–20 | name unverified |
| +20 | `important_matches` | u8 | 1–20 | name unverified |
| +21 | `pressure` | u8 | 1–20 | = the person record's `pressure`, 622 of 622 |
| +22 | `refereeing` | u8 | 3–20 | name unverified |
| +23 | `running_match` | u8 | 1–20 | name unverified |
| +24 | | 5 | small values; `00 00 00 00 00` on 486 | |
| +29 | `null_year` | u16 | 1900 on every record | |
| +31 | `competitions_raw` | 16 × u32 | the leagues he referees, by competition **uid**, packed from the front; `ffffffff` fills the rest | 1,103 of 1,332 entries are a loaded competition's uid |
| +95 | `day_of_year`, `year` | 2 × u16 | a date: in 2029 or 2030 for 365 officials, day 0 of 2021 for the other 257 (unverified: the last match he took?) | |

**How it is found.** From [rounds](rounds.md)' record 0 (`locate_rounds`), step back over
the `ff` run to the end of this table. The last record's `slot_id` gives the count, and the
`count u32` in front of record 0 must declare the same number.

**FMM27** stores the same 99-byte record (fmm-editor's FMM26 `Official` is 99 bytes): 671
records on both Truro saves, `slot_id` dense, `uid` and `pressure` equal to the person
record's on 671 of 671, the six attributes 1–20.

> **Lead:** `null_year` (+29) is the year of a date whose day is +27 (a u16 inside the
> unnamed 5 bytes): one Truro official reads day 181 of 2026, all 670 others day 0 of 1900.
> Rename it in its own change (officials are not extracted, so the extract is unaffected).

## Evidence

`frem-2030-06-22`, the Vejle 2-4 Frem report. The fixture's +72 holds 9727
([fixtures](fixtures.md)); record 244, at byte 6,263,993, is that person.

![Referee: Mikkel Redder (sympathetic)](img/officials-1.png)

| on screen | raw bytes | parsed |
|---|---|---|
| Mikkel Redder | `f4 00 00 00 7b b7 9d 01 ff 25 00 00` | `slot_id` 244, `uid` 27113339, `tid` 9727, named by the person table |
| (a 3F Superliga match) | +31 `06 00 00 00 ff ff ff ff …` | his one competition: uid 6, the 3F Superliga |

Hedensted 1-8 Frem names Sandi Putros, "(firm)": the fixture's +72 is 9547, record 241 at
byte 6,263,696 (`f1 00 00 00 a5 6a 9d 01 4b 25 00 00`). He too lists only uid 6, though the
match was a cup tie: the list is not every competition he takes.

Vendsyssel 0-2 Frem names Jakob A. Sundberg, "(firm)": the fixture's +72 is 10510, record
252.

Redder ("sympathetic") reads 17 at +18 and 5 at +19; Putros ("firm") 4 and 14; Sundberg
("firm") 11 and 16. The label follows which of `allowing_flow` and `discipline` is higher on
all three, but three referees prove no mapping.
Tested by `tests/test_matches_evidence.py`.

## Quirks

> **Quirk:** the competitions are uids, not cids (`raw.competitions.uid`), and they are his
> leagues, not every competition he takes: Putros lists only the Superliga and refereed a
> Pokalen tie. Mike Dean (tid 444) lists 11 and 12: the English Premier Division and the Sky
> Bet Championship.

> **Quirk:** the referee of a match is in the [fixtures](fixtures.md) record (+72, the
> official's tid), not in our [matches](matches.md) row, which holds no official's tid, uid
> or slot.

> **Quirk:** `ca` and `pa` are raw ability numbers. Nothing extracts them; if they ever reach
> the store they fall under the immersion rule (`[immersion] hide_ability`).

## Output

None: parsed, not extracted (TODO "Raw mirrors the save, one table per table").
`tests/test_rounds_officials.py` checks the count and Mike Dean's record.
