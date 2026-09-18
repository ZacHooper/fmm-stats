# The save frames its own tables: `[8×FF][count][records]`

**Found 2026-09-18**, working outward from the competition table. The competition scraper was
rewritten in PR 57 because the table turned out to announce its own start and size; this
document is what happened when that question was asked of every other table in the file.

Two things came out of it. First, the convention is general, not a competition-table quirk —
**nine tables declare their own record count**, and the count is exact every time. Second,
comparing each declared count against what our parser actually reads found **four defects**,
two of which were losing real data on every save ever built.

**Provenance of each claim**, because the sweeps differ in cost and therefore in coverage:
the declared-count audit and its `--confirm` invariant checks ran on **all 34 saves** (27
Frem, 7 Bucaspor) — 204/204, zero failures. The tile-based table sweep also ran on all 34.
The index-based discovery sweep is much slower (~2–3 min/save, it derives a stride per
candidate), so the five newly-found tables are confirmed on **one save per career** plus the
34-save tile sweep for the four it can see; `--stable` is the full version and is worth
running before anything depends on a shape. Reproduce with:

```bash
uv run python scripts/audit_table_headers.py            # per-table report + hex dumps
uv run python scripts/audit_table_headers.py --confirm  # each declared count vs its own invariant
uv run python scripts/discover_tables.py                # inventory of walkable tables
uv run python scripts/discover_tables.py --stable       # only what recurs across saves
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

| table | header | declared |
|---|---|---|
| competitions | u16 | 1372 |
| cities | u16 | 10956 |
| stadiums | u16 | 15987 |
| languages | u16 | 124 |
| currencies | u16 | 173 |
| player attributes | u32 | 26505 |
| staff attributes | u32 | 4642 |
| surname id-table | u32 | 32148 |
| first-name id-table | u32 | 19128 |

The history slab is the same idea with different framing and was already relying on it:
`history.locate` reads the exact row count from a **u32 at `start - 12`**, with no sentinel.

## What the audit found: declared vs. what we read

`scripts/audit_table_headers.py` takes the first record of every table the parser locates,
looks back 128 bytes, and compares any count it finds against the records we actually got.

| table | declares | we read | |
|---|---|---|---|
| competitions | 1372 | 1372 | ✓ (1272 named + 100 blank slots) |
| cities | 10956 | 10956 | ✓ |
| stadiums | 15987 | 15987 | ✓ |
| history slab | 265423 | 265423 | ✓ already used |
| **languages** | **124** | 77 | **47 short** |
| **currencies** | **173** | 94 | **79 short** |
| **surname id-table** | **32148** | 28624 | 3,524 short |
| **first-name id-table** | **19128** | 15366 | 3,762 short |
| **staff attributes** | **4642** | 4150 | 492 short |
| **player attributes** | **26505** | 26518 | **13 over** |
| nations | — | 227 | no header at the located start |
| browse names | (60000) | 45942 | not a count — see below |
| info spine | — | 32760 | no header found |
| clubs | — | — | no located table at all |

`--confirm` re-checks each declared count against the **table's own invariant** rather than
against our parser, which is both cheaper and stronger evidence: **204/204 confirmed, zero
failures**, over all 34 saves.

### The two that lose real data

**Languages — an empty name field.** `lookups._language_at` stops at slot 77, 'Malayalam',
whose `OtherName` is zero-length; `_string` requires `1 <= ln`. A walk that tolerates a
zero-length string reaches **exactly 124** and stops. Among the 47 lost: Berber (Tamazight)
and the game's own UI locales (Latin American, Brazilian, Chinese Simplified/Traditional,
English US), which carry uid 1,000,000+.

This is the *same failure* the competition table had — cid 172 'Welsh First Division' with an
empty code field — found independently one table over. **An empty length-prefixed string is
data, not a terminator.**

**Currencies — a uid range gate.** `lookups._currency_at` rejects `uid > 4096`. Slot 94 is
'Macao Pataca', uid 51535. A walk without the gate reaches **exactly 173**, then hits filler.
Lost: West African CFA franc, Central African CFA Franc, Nigerian Naira, Bolivian Boliviano,
Guatemalan Quetzal, Honduran Lempira, Nicaraguan Córdoba and 72 more.

This is the **fourth uid range gate in this codebase to cut a table short** — see
`reference.py` on the other three (`uid >= 1000` skipping every top division, the
400,000,000 club ceiling, `_CLUB_UID_FILL_LO/HI`). A uid is an identifier, not a range.

Both counts are **identical across both careers** (124 and 173 on all 34 saves) and both
parsers read the same 77 and 94 everywhere, so this has been a constant, silent loss.

### The three that are structural, not data loss

**Staff attributes are a dense array indexed by `id2`** — `id2 == slot index` on **4642 of
4642**. `scrape_staff_attributes` reads 4150 because it is driven by the id2 values the info
spine hands it, which is legitimate for its current purpose. Its first record sits 9 slots
(351 bytes) into the table, which is why the header looked absent until the locator was
anchored on the table's own base rather than on the first record the walk happened to reach.

**The two name id-tables** are walked by an `id == slot index` invariant that breaks at the
first free slot (`id = 0xFFFFFFFF`); 3,523 such slots are scattered through the surname
table. The declared counts are exact — the last declared slot reads `id=32147,
ordinal=45941`, the final browse entry. Nothing downstream depends on the walked count today
(`resolve_name` indexes directly), so this is latent rather than live; the size heuristic
that orients first names vs surnames would be more robust reading the declared counts.

**Player attributes** over-read by 13. All 26,505 declared slots pass the position check, and
the 13 extras are off-grid, past the table's end, and obvious garbage (height 54,539 cm).
**Zero of the 13 join the info spine**, so none ever surfaces. The declared count would
replace the scan-and-skip loop with pure arithmetic.

### Two clean negatives

`browse_names`' `u32 = 60000` is a **capacity, not a count**: both id-tables' highest ordinal
is 45,941, exactly matching the walk's 45,942 entries. And `info_spine`'s 25-byte gap holds
nothing count-shaped.

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

`scripts/discover_tables.py` prefers a much stronger test. If a table is a dense array whose
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

#### The 622 × 99 B table, measured

The richest of the five and the obvious place to start. Every field below was checked across
all 622 records, not read off one hex dump:

```
+0   u32   id == slot index                      (622/622)
+4   u32   ?                                     e.g. 103812
+8   u32   ?                                     e.g. 442
+12  u16   20..191     -- CA-shaped
+14  u16   50..192     -- PA-shaped, and >= +12 on every record
+16  u16   ?           -- e.g. 5750, reputation-shaped
+18  6xu8  1..20       -- six attributes on the displayed scale
+24  5xu8  always 0
+29  u16   1900        -- the "null date" year staging.INFO_LAYOUT already documents
+31  16xu32  a PREFIX-PACKED REFERENCE ARRAY, 0xFFFFFFFF = empty slot
+95  u16   day-of-year 0..328
+97  u16   year, only 2021 / 2022 / 2023
```

The array is the interesting part. **The filled slots form a contiguous prefix in 622 of 622
records** (0 filled in 6 records, then 1 in 291, 2 in 118, 3 in 88, 4 in 74, 5 in 30, 6 in 10,
7 in 5 — never more than 7 of the 16), which is why the record looked like it had a
variable-length FF pad: the pad always ENDS at +95 and starts wherever the entries stop.

Its 1,332 filled entries hold 169 distinct values in three bands — 463 under 1,000, 709
between 1k and 400M, and 160 in the 1.9–2.1bn range that `reference._CLUB_UID_FILL_LO/HI`
uses for club uids. That looks like a uid space, **but none of the 50 distinct values above
400M resolves against our club index**, so the target is genuinely unidentified. Treat that
as unresolved rather than as a refutation: the club index is itself known to be incomplete
(TODO #17), so a miss there is weak evidence either way. Settling which id space this array
points into is the first question for the naming pass.

Taken together — CA/PA, a reputation, six 1–20 attributes, a date in the career's own years,
and a short list of references — this reads as a *person-with-a-list* record. It is NOT named
here, and the shape is suggestive rather than conclusive.

### Tile-only (weaker: fixed-width fit, no index field to confirm)

| offset | records | stride | notes |
|---|---|---|---|
| ~13,990,354 | 888 | 7 B | `[id u32][00 00 00]`, ids strictly ascending 1..3221 with 2,333 gaps. Tail always zero. Ends flush against the sentinel that introduces the **language** table. Count 888 in *both* careers. |
| ~13,712,779 .. ~13,730,600 | 8 / 9 / 18 / 24 / 111 | 12 / 174 / 5 / 4 / 4 B | **False positives.** This is the award-record region; the bytes are length-prefixed strings. Listed so the next pass doesn't rediscover them as tables. |
| ~6,520,193 .. ~6,922,426 | 8–14 | 27–61 B | In the club-name region. Contain repeating groups whose second `u16` is `0x07E7` (2023) — a lead, unverified, and the apparent strides do not hold beyond the first few records. |
| ~34,325,563 .. ~34,517,491 | 10–20 | 4–10 B | Unexamined. |
| ~53,828,461 .. ~55,032,659 | 10–79 | 3–7 B | Unexamined; inside/near the match region. |

The small candidates (count < ~100, stride < 8) are where the exact-division test is weakest
— `span % count == 0` is nearly free to satisfy — so treat every one of them as a place to
look, not as a table.

## Why the yield is low, and where the rest are

Five new tables totalling ~91 KB out of a 60.7 MB file is a thin harvest, and the reason is
structural rather than a tuning problem: **the detectors only see sentinel-framed tables of
FIXED-WIDTH records.** The file's bulk lives in regions with different framing entirely — the
~47 MB of per-club Club History record tables
([`light-results-record.md`](light-results-record.md)), the tagged data dictionary
(`fmparser/tagged.py`, self-describing and walked a completely different way), the match
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

- **A table can declare its own size, and nine here do.** Before writing a walk bounded by a
  plausibility gate or a miss counter, look at the bytes in front of record 0.
- **Compare the declared count to what you read.** That single comparison found 4 defects in
  tables that had passed every check we had, including two losing real records on every save.
- **Anchor on the table's base, not on the first record your walk reaches.** The staff grid
  looked header-less purely because our entry point was 9 slots in.
- **Round numbers are suspicious.** `60000` in front of the browse table is a capacity; the
  id-tables' own ordinals prove the real length is 45,942.
