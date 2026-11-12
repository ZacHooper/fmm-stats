# id_list  ([`fmparser/tables/id_list.py`](../../fmparser/tables/id_list.py))

An **unread list of ids** between the [currencies](currencies.md) and the
[languages](languages.md). Its extent is proved; what the ids name is not.

| | Truro (FMM27) | every FMM22 save |
|---|---|---|
| rows | 924 | 888 |

## Layout

```
[>= 8 x ff][count u16]
per row: [id u32][3 bytes]
```

The ids ascend with gaps from 1 to 3,221. The three bytes are `00 00 00` on every FMM22 row
and `ff ff 00` on every FMM27 one. The last FMM27 id is 2,000,254,886.

**How it is found.** The frame after the currencies; the locator refuses it unless the rows
end on the `0xFF` run in front of the languages' count.

## Evidence

The walk ends on the languages' frame on all eight saves measured, both games.

## Quirks

> **Dead end:** matching the ids against every id field of the person, club, competition,
> nation, stadium, city, staff, official and rule-file tables. Every dense id space up to
> 3,221 contains them; no field's distinct values come close to the list. Look instead for
> a table of about 888 (FMM22) / 924 (FMM27) entries.

## Output

`output/<label>/id_list.json`: `[{id}]`. Not loaded.
