# unions  ([`fmparser/tables/unions.py`](../../fmparser/tables/unions.py))

The six **nation unions**: European Union, European Economic Area, the African, Caribbean
and Pacific group, the Overseas Territories Act, the Turkic states and EFTA. Probably what
work-permit and foreign-player rules are written against; the nations' work-permit rules
themselves are in the [rule files](rule_files.md#work-permits), and name no union. Stored between
[awards](awards.md) and [derbies](derbies.md).

## Layout

```
[>= 8 x ff][count u16 = 6]
per union: [id u16 = slot + 1][len u32][name][terminator]
```

Six on both games, ids 1–6. Two names changed for FMM27 ("Organisation of African,
Caribbean and Pacific States", "Organization of Turkic States"). The terminator is `00` on
FMM22, `ff` on FMM27.

**How it is found.** The frame after the awards' last record, whose record 0 has id 1.

## Evidence

The names, on every FMM22 and FMM27 save measured; the walk ends on the derbies' frame
(`tests/test_world_lists_evidence.py`).

## Quirks

> **Lead:** which nations belong to which union is not here. Look for a union id in the
> nation record.

## Output

`output/<label>/unions.json`: `[{id, name}]`. Not loaded yet.
