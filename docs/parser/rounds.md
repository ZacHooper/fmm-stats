# rounds  ([`fmparser/tables/rounds.py`](../../fmparser/tables/rounds.py))

The names the game gives a competition's stages, rounds and legs: "Third Round", "Semi Final",
"Second Leg", "Group D", "League Path", each with a short and a plural form. A count-framed
table of variable-length records, `[>= 8 × ff][count u32]`, between [officials](officials.md)
and the [club table](clubs.md): 288 on both Truro saves (FMM27); on FMM22 273 at ~6.3 MB,
static, the same 273 records on every save of both careers. The competitions' rules point
here by id (`tables/comp_rules.py`); the table holds no competition itself. FMM22's record
holds one name and a fixed trailer where FMM27 has the short and plural names (Layout, FMM22).

## Layout

```
header  [>= 8 × ff][count u32 = 288]
record  [id u32][name][ff][short_name][ff][plural_name][ff][next u16]      string = [len u32][bytes]
```

Each string is followed by a terminator byte, as fmm-editor's FMM26 records store a name and
its `Terminator`.

| field | type | meaning | how we know |
|---|---|---|---|
| `id` | u32 | the name id the rules use (`stnm`, `stgn`) | the rules resolve (Evidence, FMM22) |
| `name` | string, `ff`-terminated | the English name: First Leg, First Round, Knock-out Playoff | |
| `short_name` | string, `ff`-terminated | Leg 1, 1st Rnd, Knock-out Playoff | |
| `plural_name` | string, `ff`-terminated | First Legs, First Round, Knock-out Playoffs; empty on one record (2000049558 Fourth Placed Teams) | |
| `next` | u16 | the next record's index (record `k` holds `k + 1`); `ffff` ends the chain | `k + 1` on 287 of 288, `ffff` on the last |

The terminator is `ff` on all 864 strings. An empty string is data (`[00 00 00 00][ff]`), so
all three allow it: a walk that refused it stopped at record 270.

On FMM22 ids run 1–266 in table order with one gap (36), then eight large ids in ascending
order (2000016478 Champions Path, 2000016479 League Path, …, 2000152034 Main Path). Among
them: 1 Replay, 3 First Leg, 4 Second Leg, 8 Third Round, 17 Quarter Final, 18 Semi Final, 20
Final, 73 Group Stage, 76–91 Group A–P, 108 Championship Group, 149–152 First–Fourth
Qualifying Round, 164/165 First/Second Knockout Round, 236 Preliminary Phase.

**How it is found.** Record 0 is `id 1, len 6, "Replay"` and its terminator byte;
`locate_rounds` finds that signature (either version's terminator) and requires at least 8
`ff` in front of the count.

### FMM22

```
header  [8 × ff][count u32 = 273]
record  [id u32][len u32][name, len bytes][00][14-byte trailer]
```

One string, `00`-terminated, then a fixed 14-byte trailer in place of the short and plural
names:

| field | type | meaning | how we know |
|---|---|---|---|
| `flag1`, `flag3` | u32 | 1 on all 273 | |
| `flag2`, `flag4` | u16 | 32 on all 273 | |
| `next` | u16 | as FMM27 | 273 of 273 |

The FMM27 reading also reads this trailer: `[01 00 00 00][20][00]` twice is two one-space
strings, `00`-terminated, where FMM27 has the short and plural names; the FMM22 declaration
keeps its `flag1..4` names, so its extract is unchanged.

## Evidence

`truro-2026-07-25`. No in-game screen is tied to a record yet; what holds is the walk: the
locator finds the frame and all 288 records read to the declared count, `next` = `k + 1` on
287 of 288 and `ffff` on the last, `ff` on all 864 terminators. The walk is tested by
`tests/test_reference_fmm27_evidence.py`.

### FMM22

`frem-2030-06-22`, the Vejle 2-4 Frem report ([matches](matches.md), `img/matches-1.png`)
reads "3F Superliga / Preliminary Phase". The fixture's `stage_index` is 0; the Superliga's
rules (`comp_6.dat`) name stage 0 with `stnm` 236; record 236, at byte 6,310,022, is

`ec 00 00 00 | 11 00 00 00 | Preliminary Phase 00 | 01 00 00 00 20 00 01 00 00 00 20 00 eb 00`

id 236, length 17, the name, then the trailer with `next` 235 (the record after it,
index 235).

Hedensted 1-8 Frem (`img/matches-7.png`) reads "Sydbank Pokalen / Third Round": the
fixture's `round_index` is 2, the Pokalen's rules (`comp_1301406.dat`) name round 2 with
`stnm` 8, and record 8 is "Third Round".

The cup's own Fixtures screens head each leg the same way: "Quarter Final Second Leg -
Saturday 15th December 2029", "Semi Final First Leg", "Semi Final Second Leg"
(`img/rounds-1..3.png`, [fixtures](fixtures.md)). Each leg is one `stage_key`; the round name
(17 Quarter Final, 18 Semi Final) comes from the rules and the leg (3 First Leg, 4 Second Leg)
from the tie's date order.

Frem's Club Fixtures list ([fixtures](fixtures.md), `img/fixtures-1..5.png`) labels all 50
matches. Every label `site.matches` builds from these names matches the screen: the Pokalen's
Third Round, Fourth Round, Quarter Final and Semi Final; the Superliga's Preliminary Phase
and Championship Group; the Champions Cup's Group D and First Knockout Round. The group letter
and the leg are not in this table: the letter is the group's place among its stage's
`stage_key`s and the leg the tie's date order (`int.matches`, `site.matches`). Tested by `tests/test_matches_evidence.py`.

## Quirks

> **Quirk:** the screen composes a round's label from more than one record: a stage, a
> round and a leg ("Semi Final", then "First Leg"). Which records a match's label uses comes
> from the competition's rules and the fixture's `stage_index`/`round_index`
> ([fixtures](fixtures.md)), not from this table. The loader joins them in
> `int.rounds` / `int.stages`.

> **Quirk:** `next` is a pointer, not an id: every record points at the one
> after it and the last ends the chain. Ids and positions part at the gap (on FMM22 id 37 is
> record 35), so never look a name up by position.

## Output

`output/<label>/round_names.json`: `[{id, name, short_name, plural_name}]`, sorted by id;
on FMM22 `[{id, name}]`. Loads into `raw.round_names`.
