# Club records → player progress: competition record books

| | from | to | size |
|---|---|---|---|
| FMM22 | 48,166,114 | 48,353,050 | 186,936 B, the same on every save of a career |
| FMM27 | 53,149,976 | 53,353,068 | 203,092 B, the same on all three Truro saves |

After [club_records](../club_records.md), up to [player progress](../player_progress.md).

## Known

- **A count**: u32 162 on every Frem save; on Truro a u16 176 followed by different bytes.
- **It is the competitions' record books.** The first entry is cid 0, the Belgian Pro League A:
  its rows name Anderlecht, Club Brugge, Beerschot, Charleroi, Genk, Beveren, Kortrijk.
- **A 21-byte row**: `[holder club u16][f32 value][season u16][day u16][u16][ffff][u8][club
  u16][opp u16][for u8][against u8]`. That is the club records' team row without its cid and
  with the record's holder in front. The holder is always one of the two sides: one row is
  Charleroi 0–4 Genk with Genk as the holder (a record away win). Values 71.0, 87.0, 78.0 …
  read like points totals.
- After **16** such rows come **24-byte rows** (a 22-byte player row plus the holder), then
  long runs of 21-byte empty rows: `00 00 00 00 ff ff 00 00 87 01 ff ff 04 ff …` on FMM22
  (`82 00` on FMM27), the u16 391 / 130 repeating thousands of times, so not a cid.
- 186,936 / 162 is not a whole number: the books are not all one size, or there is a header.

## Next

1. Try the club records' layout per competition: `[cid][12 × team row][12 × player row]
   [12 × team row][12 × player row]`, with these row widths.
2. Check a book against a competition's Records screen (biggest win, record attendance).

## Evidence that would help

A competition's Records screen for a league we have matches in, with a save that day.
