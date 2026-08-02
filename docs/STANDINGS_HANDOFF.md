# League Standings Record — discovery & parser plan

Discovered 2026-07-20 while reverse-engineering the light-results region in the
visualizer. This is a **new on-disk structure** that stores the exact final
league position of every club in every loaded competition. It is a strict upgrade
over the approximate standings currently computed in `fmparser/lightresults.py`
(`league_table`, which infers points from partial fixture coverage).

## The record (14 bytes, fixed)

Anchored on the doubled competition id. Byte layout from the record start:

| off | type | field            | notes                                   |
|-----|------|------------------|-----------------------------------------|
| +0  | u16  | year A           | **always 2020** (0x07E4) — invariant tag, NOT the live season |
| +2  | u16  | team TID         | club id (same space as light-result home/away) |
| +4  | u8   | marker           | **always 0x01**                         |
| +5  | u16  | comp cid         | competition id                          |
| +7  | u16  | comp cid (repeat)| **always == +5** — this doubling is the signature |
| +9  | u8   | league position  | **1..N, unique per club** ★             |
| +10 | u16  | year B           | **always 2021** (0x07E5) — invariant tag |
| +12 | u16  | team count (N)   | == number of clubs in the comp          |

Records are bracketed by `FF` runs and stored in **team-id order** (not position
order). Position 1 = champion, position N = bottom.

## How it was validated

- **510 records** across **26 competitions**, all invariants held: marker always
  0x01, cid always doubled, years always (2020, 2021), `pos <= C`.
- Anchoring on marker+doubled-cid ONLY (no year gate): **24/26 comps** are a perfect
  `1..N` permutation with `count == N`. The other 2 (cid 576/577, Greek Super League 2
  North/South) are a **grouped competition**: positions run 1..17 *within each group*
  while `count` stores 34 (the whole competition) — a real structural case, not an error.
- **Ground truth**: Turkish Super League reads Trabzonspor #1, Galatasaray #2,
  Fenerbahçe, Beşiktaş at the top — the real giants (Trabzonspor won 2021-22 IRL).
  Managed club **Bucaspor is stored 3/18** in the Turkish 2. League White Group
  (cid 228) — consistent with their play-off qualification.

## Sample offsets (21-22-end.fms) — select the START byte, apply "League Standings Record"

- Turkish Super League (118): `0x02E2EBC1` (Trabzonspor 1/20), `0x02E2CE87` (Galatasaray 2/20)
- Turkish 2. League White (228): `0x02EF63B7` (Bucaspor **3/18**), `0x02E4F926` (Amed 1/18)
- Vanarama National League (70): `0x02E018BD` (Stockport 1/23)
- The empty pre-region fa-buffer: `0x02D8FD88 .. 0x02DE3D18` (21,498 × `00×8 ff ff fa ff×5`)

## Open questions

1. **The two years (2020/2021)** are invariant across all records. Either a fixed
   "season slot" tag or the record models the *just-completed* season. The stored
   positions match the current sim (Trabzonspor champion), so despite the 2020/2021
   bytes these look like the **live** final table, not DB history. Needs confirming.
2. **First-block year artifact** — the FIRST block in the region (Aldershot,
   `0x02DE3D20`) has `year A` = `1060` instead of `2020` (the only such record out of
   511). A robust parser MUST anchor on doubled-cid + marker and NOT gate on the year,
   or it drops this record (cid 70 then reads 22/23 teams). RESOLVED: with no year gate,
   24/26 comps are perfect; the remaining 2 are the Greek grouped comp (see above).
3. **comp_detail mis-names some cids** (e.g. cid 8 resolves to "Botswana" but its
   members are English League Two clubs — Mansfield, Bradford City...). Standings
   parsing must trust the cid + member nationality, same caveat as `lightresults`.
4. **No P/W/D/L/GF/GA/points in this record** — position only. The full stat columns
   may live in the records that surround each block (the `e4 07 ...` rows above each
   standings record look like a different per-club structure — unexplored).

## Parser plan (`fmparser/standings.py` — proposed)

- `scan_standings(mm, lo, hi)` — anchor on `marker==0x01 && u16(i)==u16(i+2)` with
  plausible cid; do NOT gate on the year (to catch the first block). Return
  `[{team, cid, position, count, off}]`.
- `tables(mm)` -> `{cid: [team_tid ordered by position]}` — the authoritative final
  table per competition.
- **Integration with `lightresults`**: this replaces `league_table()`'s approximate
  ordering. Keep `sweep()` for fixtures/scores, but source *standings and final
  position* from here. `club_leagues()` / `leagues()` membership can be
  cross-checked (or replaced) by the standings' authoritative member set — every
  club with a record for a cid is definitively in that comp.
- This is a **large change to how light results are processed**: today standings are
  derived; after this they are read directly, and the derived path becomes a
  fallback/validation only.
- Add a ground-truth test: assert Bucaspor 3/18 in cid 228, Trabzonspor 1/20 in 118.

## The light-results region is PER-CLUB BLOCKS (major structural finding)

The region is NOT interspersed fixtures — it is a sequence of **per-club blocks, ordered
by club TID**. Each block contains, on a ~21-byte slot grid:

1. A run of empty/header slots — empties look like `e4 07 ff ff ff ff 00 00 00 00 ff...`;
   headers carry `... cid year 00 00 87 01 ff ff 04` (a section/round marker; `87 01`=391
   and `04` meanings still unknown).
2. The club's **standings record** (14 bytes, above).
3. ~260 bytes of `FF` padding.
4. The club's **HOME fixtures** — standard 21-byte light-result records
   (`[home][away][sH][sA][pad][flags][cid][year][day][tail]`), where `home` == this club.

Verified invariant: for every club checked, the first home fixture sits **~274 bytes after**
the standings record start (Bucaspor/Galatasaray/Trabzonspor/Adana = 274, Aldershot = 295).
This gap is a reliable structural anchor.

Consequences:
- **Each match is stored under its HOME club's block.** A club has ~0 records where it is the
  away side in its own block; its away games live in the opponents' blocks. To reconstruct a
  club's full fixture list, gather home games from its block + away games from others'.
- **Exactly one standings record per club** (0/511 have more than one) — domestic league only.
  No cup, European, or group-stage tables in this structure. `count` = domestic league size.
- This is the basis for a cleaner parser: walk block-by-block (standings → home fixtures)
  instead of the current linear `sweep()` + dedup. Every home game appears once per block, so
  the flag-family duplication (0x40/0xC0/0x41 copies) can be collapsed by taking the home
  club's block as the source of truth.

## Light fixtures are MULTI-VARIANT (do not apply one fixed layout)

Investigated via Bucaspor's block cross-checked against the rich match data (which has
exact dates). Findings:

- **Twin copies 516 bytes apart are NOT identical.** The same fixture (e.g. Akhisar 0-3)
  appears at `0x651D` (`yr=2021 day=21` → 2022-01-22, correct) and `0x6532`
  (`yr=2020 day=330`, different payload). Dedup must NOT assume copies match beyond
  (home,away,cid,score).
- **The year field is a base-offset, not a literal year.** `date(yr, day)` works for some
  records (Pendikspor yr=2021 day=260 → 2021-09-18 ✓) but others need `date(yr+1, day)`
  (Akhisar yr=2021 day=21 → 2022-01-22 ✓). The `2020` values are NOT real 2020 matches.
- **The day field is a real day-of-year but mis-paired across a variant boundary.** In part
  of the block each record's `+14` day equals the NEXT record's true date (330/133/49 are
  all real day-of-years, attached to the wrong fixture). This is the tell that one fixed
  layout is being applied across two different record variants.
- **League and cup interleave** (cid 228 and cid 117 records sit in the same block).
- The managed club's block is the WORST place to decode dates (its games live in the rich
  54-byte format, matches.py); light structure is really for non-managed clubs.

Parser stance: from light, trust **teams + score + cid** and the **standings** record.
Do NOT emit per-match dates from light until the variant boundaries + date offset are pinned
against a club with independent date truth. Prior-season vs current-season records must be
separated by the year field before anything else.

## The fixtures are a fixed-width GRID (confirmed universal)

Every club's fixture block reads as a clean **21-byte-stride table** with aligned columns
(home@+0, away@+2, scoreH@+4, scoreA@+5, flags@+8, cid@+10, year@+12, day@+14,
term FF FF @+18, copyidx@+20). Verified on Bucaspor, Galatasaray, Trabzonspor, Aldershot.
Parser should read it as a strided table (anchor block start, step 21), NOT pattern-search.

- **The `day` column is NOT the row's date.** Across every club the same day value appears
  on consecutive rows for different opponents (Galatasaray day 112 on both the Trabzonspor
  and Giresunspor rows; Trabzonspor day 240 on the Galatasaray and Sivasspor rows). A club
  can't play two teams the same day, so the date field is structurally shifted/shared — not
  a Bucaspor quirk. Trust **teams + score + cid** per row; do NOT emit per-row dates.
- **Blocks are not league-only**: European (e.g. cid 505) and cup (cid 117) fixtures are
  interleaved in the same grid alongside the domestic league (cid 118/228/etc).
- Fixtures appear in duplicate rows with different flag-family bytes (@+8/+9), sometimes
  adjacent, sometimes in a twin block 516 bytes away; the copies can disagree on year/day.

## Second table after the fixtures (likely club finances — NEW lead)

Between a club's fixtures grid and the next club's block sits a distinct **22-byte-row table**
(`ff ff ff ff` row delimiter, `e5 07`/`e4 07` year marker at row start). A row decodes as:
`[year u16][u32 ~21000][pad][u32 money?][pad][u32 ~16000][FF FF FF FF]`. The middle u32
swings wildly by row (45M / 49M / 477M) — the signature of currency, so this is probably a
per-club **finance/aggregate table** (one row per season). Unconfirmed; own investigation.

## Full W/D/L/GF/GA/Pts — stored, but MANAGED-CLUB ONLY

The position-only standings record (above) has no W/D/L/points. Those exact columns ARE
stored, but a file-wide search found them for the **managed club only** (Bucaspor), as a
per-competition summary near the match region (~57.5 MB), e.g. `0x036F297D`:

```
team(2) year(2) ff ff  08 00  ff 00  cid(2)  02  P(1) W(1) L(1) D(1)  GF(u16) GA(u16) Pts(u16)
6567    2021                   228         34   14   6   14    45      29      56
```

Field order is **P, W, L, D, GF, GA, Pts** (verified: `3·W+D == Pts`, `W+D+L == P`, and the
values match Bucaspor's true league line computed from the rich match data). Empty slots
below carry a `b3 07` (0x07B3) marker.

Consequence: exact full-table stats are recoverable for YOUR club only. For all other clubs
only the league POSITION is on disk (position-only record); their W/D/L/Pts are not stored in
any table we have found (the game likely recomputes them from a complete results set — the
light list holds only ~1/3, so we cannot reproduce them yet).

## Region bounds

Standings records live within the light-results window
(`regions.LIGHT_LO..LIGHT_HI`), interleaved per-club with the fixture lists. On
21-22-end they span roughly `0x02DE3D20 .. 0x02F0xxxx`.
