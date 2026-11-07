# rounds  ([`fmparser/tables/rounds.py`](../../fmparser/tables/rounds.py))

The names the game gives a competition's stages, rounds and legs: "Third Round", "Semi Final",
"Second Leg", "Group D", "League Path". A count-framed table of 273 variable-length records,
`[>= 8 × ff][count u32]`, at ~6.3 MB, between [officials](officials.md) and the
[club table](clubs.md). Static: the same 273 records on every save of both careers. The
competitions' rules point here by id (`tables/comp_rules.py`); the table holds no
competition itself.

## Layout

```
header  [8 × ff][count u32 = 273]
record  [id u32][len u32][name, len bytes][00][14-byte trailer]
```

| field | type | meaning | how we know |
|---|---|---|---|
| `id` | u32 | the name id the rules use (`stnm`, `stgn`) | the rules resolve, below |
| `name` | len-prefixed, NUL-terminated | the English name | |
| `flag1`, `flag3` | u32 | 1 on all 273 | |
| `flag2`, `flag4` | u16 | 32 on all 273 | |
| `round_idx` | u16 | the **next** record's index (record `k` holds `k + 1`); `ffff` on the last | 273 of 273 |

Ids run 1–266 in table order with one gap (36), then eight large ids in ascending order
(2000016478 Champions Path, 2000016479 League Path, …, 2000152034 Main Path). Among them: 1
Replay, 3 First Leg, 4 Second Leg, 8 Third Round, 17 Quarter Final, 18 Semi Final, 20 Final,
73 Group Stage, 76–91 Group A–P, 108 Championship Group, 149–152 First–Fourth Qualifying
Round, 164/165 First/Second Knockout Round, 236 Preliminary Phase.

**How it is found.** Record 0 is `id 1, len 6, "Replay\0"`; `locate_rounds` finds that
signature and requires at least 8 `ff` in front of the count.

## Evidence

`frem-2030-06-22`, the Vejle 2-4 Frem report ([matches](matches.md), `img/matches-1.png`)
reads "3F Superliga / Preliminary Phase". The fixture's `stage_index` is 0; the Superliga's
rules (`comp_6.dat`) name stage 0 with `stnm` 236; record 236, at byte 6,310,022, is

`ec 00 00 00 | 11 00 00 00 | Preliminary Phase 00 | 01 00 00 00 20 00 01 00 00 00 20 00 eb 00`

id 236, length 17, the name, then the trailer with `round_idx` 235 (the record after it,
index 235).

Hedensted 1-8 Frem (`img/matches-7.png`) reads "Sydbank Pokalen / Third Round": the
fixture's `round_index` is 2, the Pokalen's rules (`comp_1301406.dat`) name round 2 with
`stnm` 8, and record 8 is "Third Round". Tested by `tests/test_matches_evidence.py`.

## Quirks

> **Quirk:** the screen composes a round's label from more than one record: a stage, a
> round and a leg ("Semi Final", then "First Leg"). Which records a match's label uses comes
> from the competition's rules and the fixture's `stage_index`/`round_index`
> ([fixtures](fixtures.md)), not from this table. The loader joins them in
> `int.rounds` / `int.stages`.

> **Quirk:** `round_idx` is a `next` pointer, not an id: every record points at the one
> after it and the last ends the chain. Ids and positions part at the gap (id 37 is record
> 35), so never look a name up by position.

## Output

`output/<label>/round_names.json`: `[{id, name}]`, sorted by id. Loads into
`raw.round_names`.
