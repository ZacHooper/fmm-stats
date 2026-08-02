# Handoff: find complete results/fixtures via DATE search

Fresh-eyes task. We've been trying to recover **complete league results/standings** from an
FMM22 save (`21-22-end.fms`, ~64 MB). The known results region (48.1–49.5 MB) is only a
**partial** feed (White Group 91/306 fixtures), so standings can't be rebuilt from it. The
new idea: **use our managed club's known match dates as a search key** to find OTHER
structures in the file that store matches — especially two zones that light up on a date
search but we've never examined: **~36–38 MB and ~63–64 MB**.

## How dates are encoded (confirmed)
Two encodings seen so far:
1. **day-of-year + year, both u16 little-endian** — used by detailed matches AND the light
   results. Year: `e5 07`=2021, `e6 07`=2022, `e4 07`=2020. Example: 30 Apr 2022 = day 120 =
   bytes **`78 00 e6 07`**. (Confirmed: BUGS #12c decoded day 304/2021 = 31 Oct 2021.)
2. **day-of-month + month + year** (the tagged data dictionary / `datadict`) — separate
   `dyom`,`mont`,`year` fields; see docs/DATADICT.md. Less useful as a search key.

The **detailed-match header** (fmparser/matches.py) is `[home:u16][away:u16][day:u16]
[year:u16][att:u16]`, with the comp cid at `date_off-3`. That's your ground-truth layout.

## Search recipe (validated)
```python
import struct
pat = struct.pack('<HH', doy, year)      # e.g. day 120, 2022 -> b'\x78\x00\xe6\x07'
# mm.find(pat, p) in a loop; bucket hits by round(offset/1e6) to see MB zones
```
Observed zones for sample dates (hits per MB):
- **48–50 MB** = light results (partial). **55–57 MB** = detailed match stats.
- **36–38 MB** and **63–64 MB** = **UNEXPLORED** — real hits here, structure unknown. Start here.
- **1–4 MB** = player DOBs (same day-of-year) — **collisions, ignore.** Also 30–33 MB is noisy.
Pick dates with distinctive day-of-year (avoid doy that collide with many DOBs) and always
require the year u16 too, to cut false positives.

## Ground truth: Bucaspor 1928 FIRST-TEAM match dates (44 games; reserves 11320 excluded)
`day` = day-of-year u16 LE, `year` LE (e5 07=2021, e6 07=2022). Search key = `day`+`year`.
comp: 228=2.League White, 227=play-off, 117=Turkish Cup, 65=friendly. opp = club TID.

| date | doy | day (LE) | year (LE) | opp TID | comp | score |
|------|-----|----------|-----------|---------|------|-------|
| 2021-08-03 | 215 | d7 00 | e5 07 | 1633 | 65 | 1-1 |
| 2021-08-07 | 219 | db 00 | e5 07 | 1362 | 65 | 2-2 |
| 2021-08-14 | 226 | e2 00 | e5 07 | 6515 | 65 | 1-1 |
| 2021-08-21 | 233 | e9 00 | e5 07 | 1651 | 228 | 1-1 |
| 2021-08-25 | 237 | ed 00 | e5 07 | 6574 | 228 | 0-1 |
| 2021-08-28 | 240 | f0 00 | e5 07 | 1634 | 228 | 1-1 |
| 2021-09-04 | 247 | f7 00 | e5 07 | 1375 | 228 | 2-0 |
| 2021-09-11 | 254 | fe 00 | e5 07 | 1673 | 228 | 3-0 |
| 2021-09-18 | 261 | 05 01 | e5 07 | 1384 | 228 | 3-3 |
| 2021-09-25 | 268 | 0c 01 | e5 07 | 1672 | 228 | 1-1 |
| 2021-10-02 | 275 | 13 01 | e5 07 | 6504 | 228 | 0-1 |
| 2021-10-09 | 282 | 1a 01 | e5 07 | 6352 | 228 | 2-0 |
| 2021-10-16 | 289 | 21 01 | e5 07 | 1399 | 228 | 2-0 |
| 2021-10-23 | 296 | 28 01 | e5 07 | 6552 | 228 | 2-0 |
| 2021-10-28 | 301 | 2d 01 | e5 07 | 6616 | 117 | 5-0 |
| 2021-10-31 | 304 | 30 01 | e5 07 | 948  | 117 | 3-1 |
| 2021-11-04 | 308 | 34 01 | e5 07 | 2518 | 228 | 1-1 |
| 2021-11-07 | 311 | 37 01 | e5 07 | 1630 | 228 | 0-0 |
| 2021-11-13 | 317 | 3d 01 | e5 07 | 6470 | 228 | 1-3 |
| 2021-11-20 | 324 | 44 01 | e5 07 | 6353 | 228 | 2-0 |
| 2021-11-27 | 331 | 4b 01 | e5 07 | 6537 | 228 | 1-2 |
| 2021-12-04 | 338 | 52 01 | e5 07 | 1657 | 228 | 1-2 |
| 2021-12-11 | 345 | 59 01 | e5 07 | 1651 | 228 | 0-2 |
| 2021-12-18 | 352 | 60 01 | e5 07 | 6574 | 228 | 0-2 |
| 2022-01-08 | 8   | 08 00 | e6 07 | 1634 | 228 | 1-0 |
| 2022-01-15 | 15  | 0f 00 | e6 07 | 1375 | 228 | 0-4 |
| 2022-01-22 | 22  | 16 00 | e6 07 | 1673 | 228 | 3-0 |
| 2022-02-05 | 36  | 24 00 | e6 07 | 1384 | 228 | 0-1 |
| 2022-02-12 | 43  | 2b 00 | e6 07 | 1672 | 228 | 1-1 |
| 2022-02-19 | 50  | 32 00 | e6 07 | 6504 | 228 | 2-2 |
| 2022-03-05 | 64  | 40 00 | e6 07 | 6352 | 228 | 1-2 |
| 2022-03-12 | 71  | 47 00 | e6 07 | 1399 | 228 | 0-0 |
| 2022-03-19 | 78  | 4e 00 | e6 07 | 6552 | 228 | 1-1 |
| 2022-04-02 | 92  | 5c 00 | e6 07 | 2518 | 228 | 0-0 |
| 2022-04-09 | 99  | 63 00 | e6 07 | 1630 | 228 | 1-3 |
| 2022-04-13 | 103 | 67 00 | e6 07 | 6470 | 228 | 1-0 |
| 2022-04-26 | 116 | 74 00 | e6 07 | 959  | 65 | 1-2 |
| 2022-04-30 | 120 | 78 00 | e6 07 | 6353 | 228 | 3-3 |  ← the fully-decoded ground-truth match
| 2022-05-07 | 127 | 7f 00 | e6 07 | 6537 | 228 | 0-0 |
| 2022-05-14 | 134 | 86 00 | e6 07 | 1657 | 228 | 0-0 |
| 2022-05-21 | 141 | 8d 00 | e6 07 | 6470 | 227 | 2-1 |
| 2022-05-25 | 145 | 91 00 | e6 07 | 6470 | 227 | 1-0 |
| 2022-05-28 | 148 | 94 00 | e6 07 | 2518 | 227 | 1-1 |
| 2022-06-01 | 152 | 98 00 | e6 07 | 2518 | 227 | 2-1 |

Regenerate this table any time:
`python3 -c "from fmparser.save import Save; from fmparser import matches as M; ..."`
(iterate `M.extract_season(mm)`, keep games with 6567 and not 11320, compute
`date(y,mo,da).timetuple().tm_yday`).

## Suggested plan for the new agent
1. **Zoom into 36–38 MB and 63–64 MB.** For a distinctive date (e.g. `30 01 e5 07` = 31 Oct
   2021, or `78 00 e6 07` = 30 Apr 2022), find the hits there and hexdump ±64 bytes. Look
   for the two team TIDs (`a7 19`=6567 + the known opponent) and a score near the date.
2. **Anchor on full tuples.** Because you know teams+score+date+comp for all 44 games, search
   for combinations (e.g. `[opp][6567]` or `[6567][opp]` near the date) to pin a record
   layout unambiguously — the same ground-truth-anchored method that cracked the light
   results (the comp cid lives at record+10 there; see fmparser/lightresults.py).
3. **Goal:** determine whether 36–38 or 63–64 MB stores a MORE COMPLETE set of results (test
   with the White Group: do teams reach 34 games?). If so, that's the standings source.

## Environment / tools
- `from fmparser.save import Save` → `Save('21-22-end.fms').mm` (read-only mmap). Never write
  to the `.fms`.
- `fmparser/matches.py` (detailed matches, header layout), `fmparser/lightresults.py`
  (partial results, record layout with cid at +10), `fmparser/reference.py::resolve_club`
  (TID→name), `fmparser/staging.py::scrape_players` (valid club TID set).
- Known club TIDs: Bucaspor 6567, Karacabey 6353, Galatasaray 955, Alanyaspor 1693. White
  Group (comp 228) has 18 clubs (see opp column above for most of them).
- What's already mapped (don't re-derive): 48.1–49.5 MB partial results, 42.83–48.1 MB a
  ~375k-entry index (no dates found), 55–63 MB detailed match stats, hard padding boundary
  at 42.78–42.83 MB. See docs/BUGS.md #12b/#12c.
