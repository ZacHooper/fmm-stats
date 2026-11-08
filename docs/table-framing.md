# The save frames its own tables: `[8×FF][count][records]`

**Found 2026-09-18**, working outward from the competition table. The competition scraper was
rewritten in PR 57 because the table turned out to announce its own start and size; this
document is what happened when that question was asked of every other table in the file.

Two things came out of it. First, the convention is general, not a competition-table quirk —
**20 tables declare their own record count** (19 found 2026-09-18, the person table
2026-09-20), and the count is exact every time. Second,
comparing each declared count against what our parser actually reads found **five defects**,
two of which were losing real data on every save ever built.

**Provenance of each claim**, because the sweeps differ in cost and therefore in coverage:
the declared-count audit and its `--confirm` invariant checks ran on **all 34 saves** (27
Frem, 7 Bucaspor) — **238/238, zero failures** (204/204 before the person table was added).
The tile-based table sweep also ran on all 34.
The index-based discovery sweep is much slower (~2–3 min/save, it derives a stride per
candidate), so the five newly-found tables are confirmed on **one save per career** plus the
34-save tile sweep for the four it can see; `--stable` is the full version and is worth
running before anything depends on a shape. Reproduce with:

```bash
uv run python scripts/audit/audit_table_headers.py            # per-table report + hex dumps
uv run python scripts/audit/audit_table_headers.py --confirm  # each declared count vs its own invariant
uv run python scripts/audit/discover_tables.py                # inventory of walkable tables
uv run python scripts/audit/discover_tables.py --stable       # only what recurs across saves
```

## The convention

```
... records of the previous table ...
FF FF FF FF FF FF FF FF        <- 8 bytes of 0xFF: the sentinel
5C 05                          <- the record count (u16 here, u32 elsewhere)
00 00 ...                      <- record 0 begins immediately
```

The count sits **flush against record 0** — read it as the 2 or 4 bytes ending at the
record's first byte, not at a fixed distance from the sentinel.

**The sentinel is 8 bytes, but test for `>= 8`, never `== 8`.** The record in front can end in
`0xFF` of its own, making the run 9 or 10. Measured: requiring exactly 8 drops the currency
table (run of 10) and the first-name id-table (run of 9) — 2 of the 9 tables we already know.

**Header width is not guessable.** The variable-length string-record tables use a u16; the
fixed-width grids and the name id-tables use a u32. Read both and let the table decide.

### The complete register

Offsets are **record 0** on frem-2023-07-02 and drift per save; the count sits at `record0 - 2`
(u16) or `record0 - 4` (u32). Read the header, never these numbers.

| table | record 0 | hdr | declared | we read |
|---|---|---|---|---|
| [player attributes](parser/player_attributes.md) | 3,996,823 | u32 | 26,505 | 26,505 ✓ |
| [staff attributes](parser/staff.md) | 6,064,225 | u32 | 4,642 | 4,642 ✓ |
| *unnamed, 7 B* | 6,245,275 | u32 | 1,971 | — |
| *unnamed, 7 B* | 6,259,084 | u32 | 560 | — |
| *unnamed, 7 B* | 6,263,016 | u32 | 816 | — |
| [officials](parser/officials.md) | 6,268,740 | u32 | 622 | 622 ✓ |
| [round/leg names](parser/rounds.md) | 6,330,330 | u32 | 273 | 273 ✓ |
| **[clubs + national teams](parser/clubs.md)** | **6,340,458** | u32 | **11,331** | 11,331 ✓ |
| competitions | 12,626,907 | u16 | 1,372 | 1,372 ✓ |
| [nations](parser/nations.md) | **12,776,737** | u16 | **251** | 251 ✓ |
| [stadiums](parser/stadiums.md) | 12,816,567 | u16 | 15,987 | 15,987 ✓ |
| [cities](parser/cities.md) | 13,492,220 | u16 | 10,956 | 10,956 ✓ |
| **awards** | **13,711,352** | u32 | **807** | — |
| [currencies](parser/currencies.md) | 13,985,965 | u16 | 173 | 173 ✓ |
| *unnamed, 7 B* | 13,990,354 | u16 | 888 | — |
| [languages](parser/languages.md) | 13,996,580 | u16 | 124 | 124 ✓ |
| **[person table](parser/person_info.md)** | **572,042** (after a `01` header byte) | u32 | **32,966** | 32,966 ✓ |
| [surname id-table](parser/names.md) | 37,878,967 | u32 | 32,148 | 32,148 ✓ |
| [first-name id-table](parser/names.md) | 38,393,347 | u32 | 19,128 | 19,128 ✓ |
| [nickname id-table](parser/names.md) | 38,699,407 | u32 | 9,480 | 9,480 ✓ |

Plus the [history pool](parser/history.md) (265,423 rows): a `[count u32]` with no sentinel.

**Confirmed adjacencies** (each found by walking one table's declared extent and reading what
follows): player attributes -> staff -> the three 7 B tables -> the 99 B table -> round/leg
names (273) -> **the club table (11,331)** -> competitions (1372) -> **nations (251)**;
stadiums -> cities -> awards (807); currencies -> the 888-record list -> languages; and
surname -> first-name -> **nickname** id-tables.

**Where the chain STOPS.** The language table's 124 records end at 14,000,242 followed by six
bytes and then a run of only **six** 0xFF — not an 8-byte sentinel. So the convention is not
universal even inside a section, and a chain walker must be able to halt rather than assume
the next block is always there.

**The blocks CHAIN.** Each fixed-width table's declared end is followed immediately by the
8-byte sentinel and the next table's count, so a section is a contiguous run of
`[8xFF][count][records]` blocks. That is how the award and 273-entry tables were found:
by walking forward from a table whose extent the declared count already gave us, rather than
by searching for anything. Verified end-to-end for player attributes -> staff -> the three
7 B tables -> the 99 B table -> 273-entry strings, and cities -> awards.

The history slab is the same idea with different framing and was already relying on it:
`history.locate` reads the exact row count from a **u32 at `start - 12`**, with no sentinel.

## What the audit found: declared vs. what we read

`scripts/audit/audit_table_headers.py` takes the first record of every table the parser locates,
looks back 128 bytes, and compares any count it finds against the records we actually got.

| table | declares | we read | |
|---|---|---|---|
| competitions | 1372 | 1372 | ✓ (1272 named + 100 blank slots) |
| cities | 10956 | 10956 | ✓ |
| stadiums | 15987 | 15987 | ✓ |
| [history pool](parser/history.md) | 265423 | 265423 | ✓ |
| languages | 124 | 124 | ✓ |
| currencies | 173 | 173 | ✓ |
| [surname id-table](parser/names.md) | 32148 | 32148 | ✓ |
| [first-name id-table](parser/names.md) | 19128 | 19128 | ✓ |
| [staff attributes](parser/staff.md) | 4642 | 4642 | ✓ |
| [player attributes](parser/player_attributes.md) | 26505 | 26505 | ✓ |
| nations | 251 | 251 | ✓ |
| browse names | (60000) | 45942 | not a count — see below |
| [person table](parser/person_info.md) | 32966 | 32966 | ✓ |
| clubs | 11331 | 11331 | ✓ |

`--confirm` re-checks each declared count against the **table's own invariant** rather than
against our parser, which is both cheaper and stronger evidence: **238/238 confirmed, zero
failures**, over all 34 saves — and exactly two declared counts per table per career, so the
tally doubles as the constant-across-a-career test.

> **ALL OF THE DEFECTS BELOW ARE FIXED as of 2026-09-20** (parser refactor, Phase 5). The
> write-ups are kept because they record *how* each one hid, which is the reusable part. What
> changed, in one line each: languages 77 -> 124 and currencies 94 -> 173 (one rejected record
> was truncating the rest of the chain); nations 227 -> 251 (three separate rejects, including
> the `0xFFFF` no-continent sentinel on 17 defunct states); the attribute table stops at its
> declared end instead of inventing 13 rows; and the **third name id-table** is now read, so
> 2,424 people have their real display names. One claim below is also CORRECTED rather than
> fixed — see "the staff grid" at the end.

### Three that lost real data

Nations (a gate that excluded id 0, Algeria), languages (an empty `OtherName` read as the end)
and currencies (a `uid <= 4096` gate): each lost real records on every save until it was walked
by its declared count. What each one teaches is a callout in the table's doc:
[nations](parser/nations.md), [languages](parser/languages.md),
[currencies](parser/currencies.md). **An empty length-prefixed string is data, not a
terminator, and a uid is an identifier, not a range.**

### The people tables

The staff table is a dense array indexed by `id2`, the name id-tables are three chained
count-framed tables (surnames, first names, nicknames), the attribute table stops at its
declared count, and the person table declares its count behind a `01` header byte. Each is
walked by declaration now: [staff](parser/staff.md), [names](parser/names.md),
[player_attributes](parser/player_attributes.md), [person_info](parser/person_info.md).

### Two clean negatives

`browse_names`' `u32 = 60000` is a **capacity, not a count**: both id-tables' highest ordinal
is 45,941, exactly matching the walk's 45,942 entries. The second negative — that
`info_spine`'s 25-byte gap holds nothing count-shaped — is still true of the GAP, and was
still the wrong conclusion about the table; see above.

## Using the convention to FIND tables

The sentinel alone is useless as a locator. Measured funnel on frem-2023-07-02:

| stage | survivors |
|---|---|
| an 8-byte `FF` sentinel anywhere in the file | 566,078 |
| + a plausible count flush against it | 245,929 |
| + `count × stride` landing exactly on the next sentinel | 39 |
| + the same `(count, stride)` in all 27 saves of the career | 24 |
| + sharing a section's drift with ≥1 other table | 12 |

Two traps, both paid for:

**Never key cross-save stability on the offset.** A first attempt did and found **zero**
stable candidates in either career, because every section drifts per save — 23,584 bytes
across Frem's 27 saves for the attribute section, 84,317 for the reference section. The
shape travels; the address does not.

**Shared drift proves section membership, not table validity.** Tables in one section move
together, so a candidate whose drift value is shared by nothing else is arithmetic. But 5 of
the 12 survivors above are still false positives — the award records at ~13.71 MB, where the
bytes are plainly length-prefixed strings (`Players' Team of the Year`, `Player of the
Month`) and `count × stride` is a coincidence.

### The detector that actually works: the index invariant

`scripts/audit/discover_tables.py` prefers a much stronger test. If a table is a dense array whose
first field IS the slot index, then with `count` from the header the stride can be **derived**
(where do ids 1 and 2 sit?) and then `id == k` checked for **every declared record**. A
full-table index check is not something noise survives, and it needs no idea what the rest of
the record holds.

It also found a table the tile test could not: the 622-record, 99-byte table at ~6.27 MB has
a **64-byte `FF` block inside every record**, so it contains sentinels of its own — which
both hid it from the tile test and made it re-detect part-way in as a phantom "132 × 99B"
whose count was read out of a day-of-year field. Hence overlap suppression: accept the
strongest evidence first, drop anything starting inside an accepted span.

### What neither detector can find

Absence from the inventory is **not** evidence a table has no header:

- **Variable-length tables.** Competitions, stadiums, languages and currencies are
  length-prefixed-string records. They all have real, exact headers and neither detector sees
  them, because there is no stride to find. Walking those needs a record parser.
- **Gappy indexes.** The 888-record list at ~13.99 MB has strictly ascending but gappy ids
  (1..3221, with 2,333 absent), so the index test rejects it; only the tile test finds it.
- **Anything not framed by the sentinel convention** — the history slab, for one.

## Inventory: walkable tables nothing here parses yet

The next job is to work through these **one at a time**. Offsets are from
frem-2023-07-02 and **drift per save** — locate by walking the sentinels, never by these
numbers.

### Index-validated (strong evidence: `id == slot index` on every declared record)

| offset | records | stride | notes |
|---|---|---|---|
| ~6,268,740 | 622 | 99 B | ids 0..621, ending exactly on the next sentinel (which introduces a 273-entry string table). Layout measured below. |
| ~6,245,275 | 1,971 | 7 B | `[id u32 == index][3 bytes, 1..255]`, 56 distinct tails |
| ~6,263,016 | 816 | 7 B | same shape, 17 distinct tails |
| ~6,259,084 | 560 | 7 B | same shape, 25 distinct tails |

All four sit in the **attribute section**, immediately behind the staff attribute grid, and
drift with it. All four are present in **both careers** with the same record shape, which is
the check that makes them tables rather than coincidences:

| table | Frem | Bucaspor |
|---|---|---|
| 99 B | 622 | 1,109 |
| 7 B (first) | 1,971 | 2,603 |
| 7 B (second) | 816 | 796 |
| 7 B (third) | 560 | **560** |

So **560 is career-invariant** — a fixed enumeration — while the other three scale with the
database. That difference is itself a clue for the naming pass.

#### The nickname id-table

Read now: [names](parser/names.md).

#### The club table: 11,331 records at 6,340,458, `tid == slot index`

Found by chaining from the round-name table's declared end, and it runs to the competition
table's own header: the whole 6.3 MB gap is this one table. National teams and U21 sides are
rows of it. Documented in [`docs/parser/clubs.md`](parser/clubs.md).

#### The award table: 807 records at 13,711,352

Found by chaining forward from the city table's declared end, and it matters beyond the
inventory: **these are the records leaking into the club index.** They use the club shape
(`[tid u32][uid u32]` then long/short/code strings), start at `tid 0, uid 102407,
'Footballer of the Year'` / `'World Footballer of the Year'`, and continue through
`'South American Footballer of the Year'`, `'African Footballer of the Year'`,
`"Players' Player of the Year"`, `"Players' Young Player"`. TODO #16 records that **153 low
tids currently resolve in our club index to award names** — this is the table they come from,
and it now has an exact, declared anchor instead of a region guess. The trailer is longer than
the club/comp trailer (an assumed 14 bytes ran the string reads off the end), so the record
shape still needs pinning before it can be walked.

#### The 622 × 99 B table

The match officials, decoded in [`docs/parser/officials.md`](parser/officials.md).

### Tile-only (weaker: fixed-width fit, no index field to confirm)

| offset | records | stride | notes |
|---|---|---|---|
| ~13,990,354 | 888 | 7 B | `[id u32][00 00 00]`, ids strictly ascending 1..3221 with 2,333 gaps. Tail always zero. Ends flush against the sentinel that introduces the **language** table. Count 888 in *both* careers. |
| ~13,712,779 .. ~13,730,600 | 8 / 9 / 18 / 24 / 111 | 12 / 174 / 5 / 4 / 4 B | **False positives** — all of them sit INSIDE the 807-record award table at 13,711,352 (above), whose records are length-prefixed strings. Listed so the next pass doesn't rediscover them as tables. |
| ~6,520,193 .. ~6,922,426 | 8–14 | 27–61 B | In the club-name region. Contain repeating groups whose second `u16` is `0x07E7` (2023) — a lead, unverified, and the apparent strides do not hold beyond the first few records. |
| ~34,325,563 .. ~34,517,491 | 10–20 | 4–10 B | Unexamined. |
| ~53,828,461 .. ~55,032,659 | 10–79 | 3–7 B | Unexamined; inside/near the match region. |

The small candidates (count < ~100, stride < 8) are where the exact-division test is weakest
— `span % count == 0` is nearly free to satisfy — so treat every one of them as a place to
look, not as a table.

## The 14.0 -> 37.9 MB stretch is NOT more count-framed tables

The obvious next place to look, since the register jumps 23.9 MB from the language table to the
surname id-table. It was checked, and the answer is no — recorded here so it is not re-checked.
Split by its filler runs, it falls into three stretches with three different characters:

| stretch | what it is |
|---|---|
| 14.00 – 16.71 MB | **85% filler** (33% `0xFF`, 52% `0x00`) with sparse structure. 54,437 runs of >= 8 `FF` in 2.8 MB, and EVERY count candidate in it is a multiple of 256 (257, 513, 769, 1024, 1026 …) — i.e. ordinary data bytes read as a u16, not a header. Club tids appear but unevenly (tid 346 seventeen times, tid 61 two hundred), so it is not a per-club grid either. Unidentified, but not count-framed. |
| 16.72 – ~21 MB | the **tagged data dictionary** — 667 rule files `[u32 n][n tagged fields]`, count-framed but not by the FF sentinel; parsed by `fmparser/tables/rule_files.py` (a `TaggedTableDef`). |
| ~21 – 39.76 MB | `map_regions` calls it "binary pages ~49B". Holds the **contract detail records** (`regions.CONTRACTREC_LO/HI`) and the **transfer-history record** at 36.36–36.94 MB, both already decoded by other means. The three name id-tables sit at 37.88–38.85 MB inside it and those ARE count-framed. |

The whole-file index detector finds **zero** index-keyed tables anywhere between 14 MB and
37.9 MB, which agrees.

So the count-framed tables cluster in exactly two bands — **3.99–6.33 MB** (the attribute
section) and **6.34–14.00 MB** (the reference section) — plus the **37.88–38.85 MB** name
id-table trio. That is the shape of the convention in this file, not a coverage gap waiting to
be filled.

**One lead worth keeping**: `u32 = 32,966` sits at 14,000,242, immediately where the language
table ends, followed by a repeating 14-byte `[6 x FF][8 bytes]` unit. 32,966 is
person-count-shaped (the info spine's declared count), so this may
be a per-person table. But the unit stops being uniform after 386 records, so its extent is
UNPROVEN and it is not in the register.

## Three kinds of number sit in front of a table

Not every header number is a record count, and conflating them is how `60000` nearly entered
the register as a table of 60,000 names. The distinction was settled by the one test a single
save cannot run: **hold the number against a career's worth of saves and see whether it moves.**

| kind | evidence | examples |
|---|---|---|
| **True count** | equals the records actually present | competitions 1,372; cities 10,956; stadiums 15,987; languages 124; currencies 173 |
| **Per-database pool** | fixed for a career, DIFFERENT between careers, 100% initialised | the **history slab**: 265,423 rows in all 27 Frem saves, **295,648** in Bucaspor |
| **Engine-wide capacity** | identical across careers, larger than actual usage | the **browse name table**: `60,000` in both careers, holding 45,942 (Frem) / 45,834 (Bucaspor) names — 76.5% utilised |

### The history pool's 265,423 is a pool, not a count

It is identical on every save of a career and every record is always on a chain, so it bounds
a walk and says nothing about how much history exists. How the game recycles it is in
[history](parser/history.md).

## The convention does NOT extend to the career half of the file (39 MB +)

Checked because the register stops at 38.85 MB and the file runs to ~61 MB. The tables up
there — the history slab, the club history record tables, our own matches, the squad snapshot —
are located by other mechanisms, and that is not an oversight in the search:

| region | framing |
|---|---|
| history slab, 39.8–44.6 MB | **Counted, but a DIFFERENT framing**: `u32 @ start - 12`, no sentinel, not 4-byte aligned. `history.locate` already reads it. The only counted table outside the two reference bands. |
| just after the slab, 44.6 MB | a per-season series — `[f32][…][u16 year]`, 7.0 in 2021, 10.0 in 2022 — FF-padded, no count. |
| club history record tables, ~46.8 MB | The first row sits **immediately** after an 8-byte FF run with **no count between them**: the 4 bytes where a count would be read `3F 80 00 00`, i.e. float32 `1.0` — data, not a header. The FF run here is filler that happens to be 8 long. |
| [our matches](parser/matches.md), ~55.7 MB | **Counted, u8, no sentinel**: the byte in front of row 0 is the match count on every save, both careers. Row 0 starts with `[home u16][away u16][cid u16][day u16][n events u8]`. |
| squad snapshot, 51–61 MB | located by `regions.CLUB_MARKER`. |

The cross-save sweep agrees: across all 34 saves there is **not one** count-framed table above
39 MB that survives both stability filters (the single candidate, a Bucaspor `10 x 3 B`, has a
drift value shared by nothing else — a coincidence in a different place each save).

**So the convention is a property of the STATIC REFERENCE DATABASE, not of the save.** The
reference half (roughly 4–14 MB: attributes, staff, clubs, competitions, nations, stadiums,
cities, languages, currencies, awards, and the name id-tables at 37.9 MB) is shipped as counted
arrays, because its sizes are fixed when the database is built. The career half (39–61 MB:
history, club records, matches, the snapshot) is written by the running game and mostly lacks
the FF-sentinel frame -- which is why `history.py` needed the in-degree test. It is NOT
uncounted: the club records carry a bare u16 count and our matches a bare u8, each directly in
front of row 0 with no sentinel, and both were missed for years because the search required
the sentinel.

That is the useful closing shape of this work: **look for a count header when the data is
reference data, and for a BARE count in front of row 0 when it is career data** -- then check
it against a walk that proves its own extent.

## Why the yield is low, and where the rest are

The detectors' own harvest was ~91 KB of a 60.7 MB file, which looked thin until chaining
added the 6.3 MB club table. The reason the *detectors* find little is structural rather than
a tuning problem: **they only see sentinel-framed tables of FIXED-WIDTH records** — and the
lesson is that **chaining forward from a known table's declared end beats any detector**,
because the declared count makes each table's extent known and therefore makes the next
table's header findable with no search at all. The file's bulk lives in regions with different framing entirely — the
~47 MB of per-club Club History record tables
([`docs/parser/club_records.md`](parser/club_records.md)), the tagged data dictionary
(`fmparser/tables/rule_files.py`, count-framed tagged blocks with no FF sentinel), the match
region, and the history slab. None of those is a sentinel-framed grid, so none of them should
be expected here.

The nearest untapped seam is the **variable-length** tables, and it was probed rather than
assumed. A string-walk detector — consume `count x k` length-prefixed UTF-8 strings from
record 0 and check where the walk lands — gives a clean result for records holding ONE string:

| table | k | walk ends | lands |
|---|---|---|---|
| currencies (173) | 1 | 13,990,340 | 8-byte sentinel at **+4** — exact |
| stadiums (15,987) | 1 | 13,492,153 | 67 bytes before the city table's own sentinel |

and fails for the two tables whose records hold several:

| table | why |
|---|---|
| competitions (1372) | 3 strings per record, but 100 slots are blank and many short/code fields are empty, so the true string count is not `count x k` for any k |
| languages (124) | 2 strings per record, except the 47 records whose `OtherName` is empty |

**The failure mode is the same bug class this whole document is about**: a zero-length
length-prefixed string is invisible to a greedy string walker, exactly as it was invisible to
`_language_at` and to the old competition reader. So a string-density detector cannot bound a
variable-length table without already knowing the record shape — which is the thing it was
supposed to avoid needing.

That makes the next goal concrete rather than open-ended: walking the variable-length tables
needs a per-record parser, so they should be taken **one at a time**, and each one's header
gives a free, exact termination check the moment its record shape is right.

## Method notes worth carrying

- **A table can declare its own size, and twenty here do.** Before writing a walk bounded by a
  plausibility gate or a miss counter, look at the bytes in front of record 0.
- **Compare the declared count to what you read.** That single comparison found 4 defects in
  tables that had passed every check we had, including two losing real records on every save.
- **Anchor on the table's base, not on the first record your walk reaches.** The staff grid
  looked header-less purely because our entry point was 9 slots in.
- **Round numbers are suspicious.** `60000` in front of the browse table is a capacity; the
  id-tables' own ordinals prove the real length is 45,942.
