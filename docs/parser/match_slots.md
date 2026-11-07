# match_slots  ([`fmparser/tables/match_slots.py`](../../fmparser/tables/match_slots.py))

A preallocated table of 25-byte slots, a few hundred of which hold a recent result between
two other clubs. What the game uses it for is not known. 3,975 slots on every Frem save and
3,943 on Bucaspor, at ~37.8–40.6 MB (it drifts). Not extracted: nothing in the store reads it.
The complete results list is [fixtures](fixtures.md).

## Layout

| offset | field | type | meaning | how we know |
|---|---|---|---|---|
| +0 | `away_tid` | u16 | one club; `ffff` (or 0) when the slot holds no match | |
| +2 | `home_tid` | u16 | the other club. **The names are wrong: no venue is stored** (Quirks) | `fix_man` |
| +4 | `away_goals` | u8 | the goals of the club at +0 | |
| +5 | `home_goals` | u8 | the goals of the club at +2 | |
| +6 | `day` | u16 | day of the year, 0-based | `fix_man` |
| +8 | | u8 | the match's year − 2021 (Quirks) | |
| +9, +11, +13, +15 | A, B, C, D | i16 | three independent numbers: `A − B == C − D` on every match slot | |
| +17 | | i16 | | |
| +19 | | u8 | | |
| +20 | `trailer_a` | u16 | 391 on most slots; else the same year code as +8 | |
| +22 | `trailer_b` | u16 | `ffff` | |
| +24 | | u8 | 3 on most slots | |

`C = A − k` and `D = B − k` with `k` the save's day of the year minus the match's (plus 365
for a match in the year before) on 152 of 178 match slots on `frem-2030-06-22`; `B ==
⌊3A/5⌋` on 134. What `A` counts is unknown.

**How it is found.** The 4 bytes `87 01 ff ff` at +20 occupy one residue class mod 25 far
more than any other; `locate` takes the longest run on that class, bridging gaps of up to
40 slots. The slot count is the extent, and it never changes within a career.

## Evidence

Screenshots pending.

## Quirks

> **Quirk:** the table holds no venue. Joined to the fixture list on the two clubs and the
> day, the club at +2 is the home side on 83 of 174 slots on `frem-2030-06-22`, 149 of 272
> on `frem-2026-06-11` and 326 of 652 on `bucaspor-2023-04-01`; the goals always follow
> their club. The module's `home_`/`away_` names come from an "away-first" reading of a
> few slots. Read the pair as unordered and take the venue from [fixtures](fixtures.md).

> **Quirk:** only a few hundred slots hold a match (178 on `frem-2030-06-22`, 275 on
> `frem-2026-06-11`); on the rest `+0..+5` are `ff`. About 2,900 slots carry a day either
> way and the last ~1,100 are blank. Our own clubs never appear (0 slots involve Frem or its
> reserves), and a round is never complete, so it is no source of results or tables.

> **Quirk:** `+8` is the match's calendar year − 2021 on 1,234 of 1,243 match slots on four
> saves (9 for 2030, 8 for 2029). It is not a competition: no byte of the slot equals the
> match's cid, tested on the matches whose cid is known from both clubs sharing a league.

> **Quirk:** a match can sit in more than one slot (seven twice and one three times on
> `frem-2030-06-22`), and a slot can be seasons stale.

> **Quirk:** the first slot overlaps the 16-byte table ending in front of it: its clubs read
> 0 and 10,000 (`00 00 10 27`). `scrape` drops slots with a null or repeated club.

> **Dead end:** there is no second match table in the main save. The signature `[club u16]
> [club u16][goals <= 12][goals <= 12][day 1..366]`, both clubs in one league, was swept at
> every byte offset: only this table's hits share a stride (25, all on grid). The other
> clusters fail alignment, including a constant `01 00 00 01` at ~36.4 MB that reads as the
> same 0-1 on day 256 against every opponent (the transfer band's 143-byte records).

## Output

None. `scrape` returns the slots that hold a match, for tests and audits
(`tests/test_match_slots.py`).
