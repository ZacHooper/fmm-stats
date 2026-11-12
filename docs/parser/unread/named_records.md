# Nicknames → history

| | from | to | size |
|---|---|---|---|
| FMM22 | 41,113,898 | 42,630,093 | 1.52 MB, 82% zero |
| FMM27 | 42,654,960 | 44,791,485 | 2.14 MB, 95% zero |

After the [nickname id-table](../names.md), up to the [career-history pool](../history.md).

## Known

- **Most of it is dense small numbers** (on both games), e.g. FMM22 opening `1b 04 07 00 c5 00
  02 01 01 02 00 00 03 0e 00 00 00 00 06 00 00 00 2a …`. The same on 25 Jul and 8 Aug (94%).
- **FMM27 ends in 1,020 inline-named records**, about 52–59 bytes apart, the first at
  44,733,559 on truro-2026-08-08: `… ff ff ff ff [u32 len]"Mark" [u32 0][u32 len]"Smith" 01 00
  ea 07 ff …`. Others: "Phillip Foose", "Cecilia Tenconi" (followed by `01 d7 07`: 2007, a birth
  year by the look of it), "Carrie Scrimgeour", "Cathy Jessup". Where exactly the year sits is
  not settled: the bytes after the surname differ between records. The names are typed into the record,
  not ids into the name tables, so these are people the database does not ship.
- Near the end on Truro sit counts of 3,125 (Truro's own tid) and 10,000, about 174 KB before
  the history pool.
- **FMM22's tail is different**: rows of two u32 and a u16 nation id (`8b`, `a3`, `a7` …).

## Next

1. Check whether the inline names appear in the browse-name table at all, and look for a tid
   or club in each record: they may be generated non-player people (journalists, agents, board
   members) or FMM27's women's players.
2. Frame the dense-number part: try one row per person or per club, as elsewhere.
