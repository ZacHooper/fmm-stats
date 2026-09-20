# Whole-file map: `frem-2026-06-11.fms` (63,936,873 bytes)

**2026-09-20.** Every row below was measured **live against this save** in one session, either
by calling the named parser function or by the structural test named in the `how` column. No
offset is carried over from another save, and nothing is cited from an unmerged branch.

This supersedes the map drafted in PR #59, which mixed offsets from two different saves in one
ordered table and inherited several rows from PR #58's `frem-2023-07-02` measurements. Four of
its rows are corrected here — see "What changed" at the end.

## Read this first: the drift boundary

The single most useful fact about this file's layout is **where it moves**:

| anchor | `frem-2021-07-01` | `frem-2026-06-29` | drift over 5 years |
|---|---|---|---|
| tagged datadict end | 20,206,373 | 20,294,619 | **+88 KB** |
| match-slot table start | 37,009,585 | 40,393,355 | **+3.38 MB**, and it oscillates |

Everything below ~20 MB is near-static: a reference-half offset taken from any save of the
same career is good to about ±100 KB, which is close enough to seek to and then confirm with
the table's own header. Everything above ~34 MB moves by megabytes and **does not move
monotonically** — it sawtooths, because the seasonal transfer band (35.4–38.4 MB) fills by
~2.5 MB each season and is wiped every July. So a career-half offset from another save is not
approximately right; it is wrong in a direction that depends on where you are in the season.

Practical rule: **locate reference-half tables by their declared count header, and career-half
structures by their own invariant.** Never by a remembered offset.

## The map

`live` = a parser function called against this save. `hdr` = found by its declared count
preceded by a run of ≥8 `0xFF` (see [`table-framing.md`](table-framing.md)). `struct` = found
by a structural test described in the notes.

| start | end | size | what | class | how |
|---|---|---|---|---|---|
| 299 | 515,797 | 0.52 MB | **browse name table** — 45,942 names; the `60,000` in front is a capacity, not a count | static | live (`reference._name_table_bounds`) |
| 515,797 | ~572,037 | 0.06 MB | filler + a short run of unnamed records | — | — |
| **572,037** | ~3,988,960 | **3.42 MB** | **the PERSON table (info spine)** — declares **32,966** (Frem) / **34,312** (Bucaspor), career-constant, so a **fixed pool**. Records are variable-length (68 B head + counted lists) and `staging.scrape_players` finds them by sentinel sweep, reading 32,874 — **92 short of declared**. The extent is now anchored at the front; the walk is not solved | **preallocated pool** | hdr (2026-09-20) |
| 3,988,968 | 6,056,358 | 2.07 MB | **player attributes** — 26,505 × 78 B | static | hdr |
| 6,056,370 | 6,237,408 | 0.18 MB | **staff attributes** — 4,642 × 39 B, `id2 == slot index` | static | hdr |
| 6,237,408 | 6,332,591 | 0.09 MB | the chained small tables: three 7 B index tables (1,971 / 560 / 816), the 622 × 99 B person-shaped record, the 273-entry round/leg-name strings | static, **unnamed** | chain (PR #58) |
| 6,332,603 | ~12,607,190 | 6.27 MB | **club + national team table** — 11,331 records, `tid == slot index`, dense. Low tids are national teams; U21 sides are the last rows | static | hdr |
| 12,607,199 | ~12,756,285 | 0.15 MB | **competitions** — 1,372 | static | hdr + live (`_comp_table_anchor`) |
| 12,756,293 | ~12,796,115 | 0.04 MB | **nations** — declared 251, we read 227 (Algeria is id 0, cut by a `1 <= nid` gate) | static | hdr + live |
| 12,796,123 | 13,471,770 | 0.68 MB | **stadiums** — 15,987 ✓ | static | hdr + live |
| 13,471,776 | 13,690,902 | 0.22 MB | **cities** — 10,956 ✓ | static | hdr + live |
| 13,690,908 | ~13,965,510 | 0.27 MB | **awards** — 807 records, club-record shape; plus the 888-record 7 B id list | static, partly unnamed | hdr |
| 13,965,521 | ~13,976,130 | 0.01 MB | **currencies** — declared 173, we read 94 (`uid > 4096` gate) | static | hdr + live |
| 13,976,136 | ~13,978,480 | 0.002 MB | **languages** — declared 124, we read 77 (zero-length `OtherName`) | static | hdr + live |
| 13,978,474 | 16,692,615 | 2.71 MB | **UNIDENTIFIED** (`00` 52% / `ff` 31% / other 18%); checked and *not* count-framed | — | — |
| 16,692,615 | 20,321,452 | 3.63 MB | **tagged data dictionary** — self-describing `[tag][01][type][value]` | static-ish | live (`tagged.find_tagged_region`) |
| 20,321,452 | 29,171,689 | **8.85 MB** | **FILLER — 97% `0xFF`, 1% `00`, 2% other.** Not a research target | — | struct |
| **29,171,689** | **31,907,618** | **2.74 MB** | **contract grid** — dense **83-byte** records, **32,961 slots**, 26,754 populated. One slot per person (the info spine holds ~32,885) | **preallocated, stable all career** | struct (stride-83 run) |
| 31,907,618 | 35,439,434 | 3.53 MB | **UNIDENTIFIED** (`00` 53% / `ff` 31% / other 17%) | — | — |
| **35,439,434** | **38,404,968** | **2.97 MB** | **seasonal transfer band** — 6,362 × 143 B transfer-history records (`tid@+48`, `wage@+53`, `expiry@+61`). The records are **0.91 MB, 31% of the span**; what the other 69% holds is not established, only that it collapses with them | **wiped every July; the span's collapse IS the file's July shrink** | struct (residue class mod 143) |
| 38,404,968 | 40,042,185 | 1.64 MB | **UNIDENTIFIED** (`00` 34% / `ff` 33% / other 32%) | — | — |
| 40,042,185 | 40,141,560 | 99,375 B | **away-first match-slot table** — 3,975 × 25 B | **fixed pool** | live (`matchslots.locate`) |
| 40,141,778 | 40,656,146 | 0.51 MB | **surname id-table** — declared 32,148, walked 28,624 | static | hdr |
| 40,656,158 | 40,962,206 | 0.31 MB | **first-name id-table** — declared 19,128, walked 15,366 | static | hdr |
| 40,962,218 | 41,113,898 | **0.15 MB** | **nickname id-table** — 9,480 × 16 B, **never opened by code** | static | chained past #2 |
| 41,113,898 | 42,630,105 | 1.52 MB | **UNIDENTIFIED**, 82% zero — mostly padding | — | — |
| 42,630,105 | 46,876,873 | 4.25 MB | **player-history slab** — 265,423 rows × 16 B, pointer forest | **fixed pool** | live (`history.locate`) |
| 46,876,873 | 48,165,854 | 1.29 MB | **club-records** — 21 B team rows / 22 B player rows, 12-row category blocks | **preallocated grid + 212 B per new block** | struct (empty-row extent) |
| 48,165,854 | 52,721,064 | 4.56 MB | **trailing stride-70 empty-slot pool** — 65,072 slots, `e4 07` (year 2020) empty sentinel | **preallocated, being consumed** | struct (residue class mod 70) |
| 52,721,064 | 55,839,667 | 3.12 MB | **UNIDENTIFIED**, 65% zero — five `0x00` runs of 52–193 KB | — | — |
| 55,839,667 | 56,223,268 | 0.38 MB | **our matches** — 60 blocks, home XI + away XI, 54 B player blocks | **wiped every July; appends in-season** | live (`matches.find_match_region`) |
| 56,313,477 | 56,314,027 | **550 B** | exact `0xFF` wall, identical regardless of match count | — | struct |
| 56,314,027 | — | 65 B/rec | **per-season table** — `[flag u8][value u16][tid u16][year u16]`, one record per season, tid constant at our club | grows 1/season | struct |
| ~56,314,300 | ~61,253,092 | 4.94 MB | **UNIDENTIFIED** (`00` 29% / `ff` 53% / other 18%). One small player-list block sits at 56,336,372 (`Jeppe Corfitzen` / `FC København` / `Res Group 1`), so the structure below starts earlier than its first EMPTY slot | — | — |
| **~61,253,092** | **62,631,781** | **1.38 MB** | **player-list blocks** — blocks of **100 slots x 200 B** (+14 B per block); 52 blocks are entirely empty on this save, carrying an identical template with `e5 07` = the career's start year. Populated slots hold a variable-length player record: a ~160 B binary core then `[full name][first][last][""][last][club short name][competition name]`. Contents are squad lists (ours) and world/scouting lists (De Bruyne/Man City, Courtois/R. Madrid, Frendrup/Genoa). **The squad snapshot is five of these blocks**, not a structure of its own. Start is the first POPULATED block; the first empty slot is at 61,381,262 | preallocated, partly consumed | struct (stride-200 run) |
| *61,896,648* | *62,002,727* | *0.11 MB* | ↳ *of which:* **squad snapshot** — the managed club's own list blocks | — | live (`attributes.snapshot_bounds`) |
| 62,631,781 | 62,635,766 | 3,985 B | **UNNAMED dated table** — 14 B units `[u32 FFFFFFFF][u16 9][u16 day-of-year][u16 year][u32 ?]`, dates a fortnight ahead of the save. Both careers | — | struct |
| **62,635,766** | **63,936,873** | **1.30 MB** | **the `sicomps` ARCHIVE** — 159 zstd members with a directory; 6.58 MB decompressed. Holds `fix_man.dat`, **the world fixture list with scores**. See [`save-archive.md`](save-archive.md) | grows with the career | live (`archive.locate`) |

## Behaviour classes, which matter more than the offsets

Four kinds of structure live in this file, and the class tells you how to parse it:

| class | members | consequence |
|---|---|---|
| **static reference data** | everything 0–20 MB plus the three name id-tables | Count-framed (`[≥8×FF][count][record 0]`). Walk it by the declared count; the count is exact. |
| **fixed pool** | history slab (265,423 rows), match-slot table (3,975 slots) | Allocated once at career creation, never resized, recycled internally. The count is a **bound**, never a measure of how much data exists. |
| **preallocated grid that also grows** | contract grid (32,961 × 83 B), club-records, the stride-70 pool | Ships full of empty-sentinel rows and fills up. Club-records additionally gains 212 B per new season block. On a day-one save these read as *empty*, not missing. |
| **seasonal, wiped each July** | transfer band (35.4–38.4 MB), our matches | Whatever is in them at the end of June is gone in July. A late-June save each year is the only way to keep a season's transfers or matches. |

## The July rollover, measured

The career half does not drift smoothly; it sawtooths, and the whole sawtooth is one event.
`frem-2026-06-29` -> `frem-2026-07-02` loses **3,004,689 bytes**. Anchor-matching one save into
the other -- take a 48-byte non-filler sample every 64 KB, find its unique match in the other
save, watch the offset delta -- localises every byte of that:

| where | delta | what |
|---|---|---|
| below 34.59 MB | −8,952 | datadict edits, nothing structural |
| **34.59 – 39.55 MB** | **−2,541,720** | the transfer band |
| 39.55 – 55.6 MB | (carries −2,550,551) | everything downstream just slides |
| **55.6 – 59.8 MB** | **−383,862** | our matches, exactly the region's own size |
| tail | −59,274 | |

**The transfer band accounts for its step on its own.** Across that pair its extent goes
**3.32 MB -> 0.79 MB** (6,877 records -> 1,720) — a 2.53 MB collapse against a 2.54 MB measured
deletion. Matches go 60 anchors -> 0 over the same pair.

The wipe is a discrete event on rollover day and **the date moves year to year**:
`2023-06-30` 44 match anchors -> `2023-07-01` 0; `2024-06-28` 59 -> `2024-06-30` 0;
`2026-06-29` 60 -> `2026-07-02` 0. So a save taken even two days late has already lost the
season. The reference-half floor the band resets to is stable across five years
(17.96 / 17.55 / 17.69 / 17.83 / 17.66 MB measured from the datadict's end to the first name
id-table), so nothing accumulates here between seasons.

**Limit of the method, stated because it bounds the claim above:** the anchor probe separates
"this sample is not in the other save" from "it moved", not "deleted" from "rewritten". Inside
34.59–39.55 MB every sample is absent, so the deletion cannot be localised more finely than
that span by this means.

## Gaps, ranked by what's worth looking at

Size alone is misleading — filler fraction matters more. Ranked by *unexplained non-filler
bytes*:

| span | size | other% | ≈ real bytes | note |
|---|---|---|---|---|
| **0.57 – 3.99M** | 3.42 MB | 45% | **1.55 MB** | **Partly resolved 2026-09-20**: this is the PERSON table and it declares **32,966** records at a header at 572,037 (34,312 on Bucaspor) — see [`table-framing.md`](table-framing.md). It is still the biggest unexplained block by bytes, because the records are variable-length and nothing walks them; what remains is a per-record parser, not a search |
| ~~62.00 – 63.94M~~ | ~~1.93 MB~~ | ~~71%~~ | ~~1.37 MB~~ | **RESOLVED 2026-09-20 — and it was ranked here for a reason that was false.** 0.63 MB is the tail of the player-list blocks; 1.30 MB is the `sicomps` **zstd archive**. "71% other / 25.8% printable" is not text density: 95/256 = **37.1% of uniform random bytes are printable**, so compressed data scores exactly this. See [`save-archive.md`](save-archive.md) |
| 56.31 – 61.38M | 5.07 MB | 18% | **~0.9 MB** | shrank by the player-list blocks, which start at 61,381,262 |
| 52.72 – 55.84M | 3.12 MB | 31% | **0.97 MB** | sits between the stride-70 pool and our matches |
| 31.91 – 35.44M | 3.53 MB | 17% | **0.59 MB** | sits in front of the transfer band |
| 38.40 – 40.04M | 1.64 MB | 32% | **0.52 MB** | between the transfer band and the match-slot table |
| 13.98 – 16.69M | 2.71 MB | 18% | **0.49 MB** | already checked: not count-framed |
| 41.11 – 42.63M | 1.52 MB | 18% | **0.27 MB** | 82% zero — mostly padding |
| **20.32 – 29.17M** | **8.85 MB** | **2%** | **0.18 MB** | **97% `0xFF`. Padding, not a target.** |

Two corrections matter more than any row. The biggest-looking hole in the file (20.32–29.17M)
is empty space. And **ranking by printable fraction is the wrong statistic** — it put the tail
first on the strength of a number that uniform random bytes produce by construction. **Rank by
BLOCK ENTROPY instead**: it separates text from compressed data in one pass, and it would have
found the archive immediately. With the tail resolved, **0.52–3.99M is now the clear leader**:
the most unexplained bytes in the file, though the info spine accounts for some of them.

## What changed versus the PR #59 map

1. **The `16,000,000–40,000,000` "contract-detail records window" row is gone.** That was a
   *scan window*, not a structure, and counting it as mapped concealed three separate gaps.
   The real content in that 24 MB is three islands — the datadict (3.63 MB), the contract grid
   (2.74 MB) and the transfer band (4.28 MB) — with 8.85 MB of pure `0xFF` padding and ~3.9 MB
   of genuine unknown around them.
2. **The nickname id-table is 0.15 MB, not ~1.67 MB.** 9,480 × 16 B = 151,680 B. The PR gave
   it the whole span to the history slab with its position "inferred, not measured"; measured,
   it ends at 41,113,898 and leaves a separate 1.52 MB gap behind it.
3. **The matches-wall row was internally inconsistent** — it put the wall at
   `56,173,268 + 550` while the next row began at `56,314,027`, which do not meet. Measured,
   the run starts at 56,313,477 and ends exactly at 56,314,027.
4. **Row ordering no longer mixes saves.** The PR listed the competition anchor (12,607,199,
   from the 2026 save) *before* the club table's end (12,626,905, from the 2023 save), which
   reads as an overlap that doesn't exist.

Two rows are also newly classified rather than merely located: the **contract grid** (a
preallocated 83-byte-per-person table, which replaces a 24 MB byte-by-byte scan with a bounded
walk) and the **stride-70 pool**, which on a day-one save carries the empty sentinel in
**100%** of its slots and is down to ~92.5% by 2026 — the signature of a preallocated pool
being consumed, not of an append-and-shift structure.

## Reproducing this

Every `hdr` row is found by searching for the table's declared count immediately preceded by a
run of ≥8 `0xFF`; every `live` row by calling the named function. The structural rows:

- **contract grid** — scan for `[tid u32][0x01][wage u16][6×00][doy u16][year u16]`, keep hits
  whose gaps are exact multiples of 83; the run's extent divided by 83 is the slot count.
- **transfer band** — the same signature, but every hit in 34–39 MB lands on **one residue
  class mod 143**, at `+48` of the 143-byte transfer record.
- **stride-70 pool** — occurrences of `e4 07` sharing one residue class mod 70, from
  club-records' end to the `0x00` wall.
- **club-records extent** — the 17-byte empty-row signature
  `ff ff e4 07 00 00 87 01 ff ff 04 ff ff ff ff ff ff`; its last occurrence + 21 is the end.
- **drift class** — re-run any two saves and compare; the reference half moves in tens of KB,
  the career half in megabytes.
- **player-list blocks** — occurrences of `14 01 00 0a 00` (inside every empty 200-byte slot)
  whose gaps are exactly 200; the runs come in lengths of exactly 100, separated by 214.
- **the archive** — the FIRST `28 b5 2f fd` (zstd magic) in the file; walk `[u32 stored][frame]`
  from four bytes before it. `uv run python scripts/audit_archive.py` reproduces the whole
  thing, 34/34 saves.

## The tail was mis-ranked, and the reason generalises

The 2026-09-19 map put `62.00–63.94M` second on the gap table because it measured 71%
non-filler and 25.8% printable, and called it "by far the most TEXT-dense unparsed span in
the file". **95 of 256 byte values are printable, so uniform random bytes measure 37.1%
printable.** Compressed data therefore scores high on exactly the statistic that was being
used to mean "text". Block entropy tells them apart at a glance — that span reads a flat
**7.99 bits/byte** — and the four-byte grep that follows from it
([`save-archive.md`](save-archive.md)) resolved the region in one step.

Practical rule for the next pass: **profile the whole file by 4 KB block entropy before
ranking anything.** Filler is ~1.4 bits, ordinary records are 3–6, and anything at 7.9+ is
compressed or encrypted and will not yield to a stride search at all.
