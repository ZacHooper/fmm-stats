# After the season stats, 3: inline-named records

The last of three sub-tables between the [player season stats](../player_season_stats.md) and
the [career-history pool](../history.md), after the [grouped tid rows](sst_tid_groups.md).
FMM27 only.

| save | from | to | size |
|---|---|---|---|
| truro-2026-11-16 | 45,971,166 | 46,029,088 | 58 KB |

## Known

- **About 1,020 records, each with its first name and surname typed in** as length-prefixed
  strings, about 52–59 bytes apart: `… ff ff ff ff [u32 len]"Mark" [u32 0][u32 len]"Smith" 01
  00 ea 07 ff …`. Others: "Phillip Foose", "Cecilia Tenconi" (followed by `01 d7 07`: 2007, a
  birth year by the look of it), "Carrie Scrimgeour", "Cathy Jessup". On 16 Nov the first is
  at +139,012 from the season stats' end and the last at +196,896.
- Where exactly the year sits is not settled: the bytes after the surname differ between
  records. The names are typed into the record, not ids into the name tables, so these are
  people the database does not ship.

## Next

Check whether the names appear in the browse-name table at all, and look for a tid or club in
each record: they may be generated non-player people (journalists, agents, board members) or
FMM27's women's players.
