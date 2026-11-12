# derbies  ([`fmparser/tables/derbies.py`](../../fmparser/tables/derbies.py))

Every **named rivalry**: Merseyside (Everton v Liverpool), Lombardo (Atalanta v AC Milan),
Hudson (New York City FC v New York Red Bulls), and Frem's own "Gammel Køge Landevej"
against Hvidovre. Stored between [unions](unions.md) and [regions](regions.md).

| | Truro (FMM27) | Frem (FMM22) |
|---|---|---|
| derbies | 1,681 | 1,377 |
| both clubs in the database | 753 | 610 |

## Layout

```
[>= 8 x ff][count u16]
per derby: [id u32 = slot][uid u32][len u32][name][terminator]  23-byte body
```

| offset (body) | field | type | meaning | how we know |
|---|---|---|---|---|
| +0 | `club_a_tid` | u32 | `ffffffff` when the club is not in the database | every other value is a club, both games |
| +4 | `club_b_tid` | u32 | | |
| +8 | | u8 | 0–200; Merseyside 180, Melbourne 150, Lanarkshire 95. Probably the rivalry's intensity | |
| +9, +11, +13 | | u16 | `ffff` on every Truro derby, filled on many Frem ones: career state | |
| +15..+22 | | 4 × u16 | 0–4 | |

**How it is found.** The frame after the unions' last record, whose record 0 has id 0.

## Evidence

Structural and cross-table (`tests/test_world_lists_evidence.py`): every derby's id is its
slot, every club field is a club or `ffffffff`, and derby 0 is Merseyside, Everton v
Liverpool, on both games. No screen yet.

## Quirks

> **Lead:** the three u16s at +9 change as a career goes on. Diff a derby across Frem saves
> before and after the two clubs meet, and compare with the club's rivals screen.

## Output

`output/<label>/derbies.json`: `[{id, uid, name, club_a_tid, club_b_tid}]`. Not loaded yet.
