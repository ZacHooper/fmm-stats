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

### The complete register

Offsets are **record 0** on frem-2023-07-02 and drift per save; the count sits at `record0 - 2`
(u16) or `record0 - 4` (u32). Read the header, never these numbers.

| table | record 0 | hdr | declared | we read |
|---|---|---|---|---|
| player attributes | 3,996,823 | u32 | 26,505 | 26,518 — **13 over** |
| staff attributes | 6,064,225 | u32 | 4,642 | 4,150 |
| *unnamed, 7 B* | 6,245,275 | u32 | 1,971 | — |
| *unnamed, 7 B* | 6,259,084 | u32 | 560 | — |
| *unnamed, 7 B* | 6,263,016 | u32 | 816 | — |
| *unnamed, 99 B* | 6,268,740 | u32 | 622 | — |
| *round/leg names* | 6,330,330 | u32 | 273 | — |
| **clubs + national teams** | **6,340,458** | u32 | **11,331** | ~4,700 via a scan |
| competitions | 12,626,907 | u16 | 1,372 | 1,372 ✓ |
| nations | **12,776,737** | u16 | **251** | 227 |
| stadiums | 12,816,567 | u16 | 15,987 | 15,987 ✓ |
| cities | 13,492,220 | u16 | 10,956 | 10,956 ✓ |
| **awards** | **13,711,352** | u32 | **807** | — |
| currencies | 13,985,965 | u16 | 173 | 94 |
| *unnamed, 7 B* | 13,990,354 | u16 | 888 | — |
| languages | 13,996,580 | u16 | 124 | 77 |
| surname id-table | 37,878,967 | u32 | 32,148 | 28,624 |
| first-name id-table | 38,393,347 | u32 | 19,128 | 15,366 |
| **nickname id-table** | **38,699,407** | u32 | **9,480** | **never read** |

Plus the history slab (40,364,927, 265,423 rows): the same idea with different framing — a
u32 at `start - 12`, no sentinel — and `history.locate` already reads it.

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

**Nations — a range gate that excludes id 0.** The nation table declares **251** and
`scrape_nations` returns 227. Its header was missed at first because the locator's "first
record" was nation id **1** (Angola, 12,776,923): the real record 0 sits 188 bytes earlier at
**12,776,737** and is `[uid 5][id 0][7]'Algeria'`. `_nation_candidates` requires
`1 <= nid <= 4096`, so **Algeria is rejected by the gate and missing from the nation table
entirely.** 24 declared ids are absent in total; whether the other 23 are blank slots or
further misses is NOT yet established.

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

#### The NICKNAME id-table: 9,480 slots at 38,699,407 — and we have never read it

Found by chaining past the two name id-tables, which turn out to be **three** consecutive
blocks: surname (32,148) -> first-name (19,128) -> nickname (9,480), each
`[8xFF][count][16-byte records]`. `reference._discover_id_tables` returns only the two
LARGEST, so the third has never been opened.

It resolves through the same browse table, and the ground truth is not ambiguous:

| `common_name_id` | nickname | the name we currently show |
|---|---|---|
| 48 | **Tite** | Adenor Leonardo Bachi |
| 50 | **Renato Gaúcho** | Renato Portaluppi |
| 22 | **Míchel** | José Miguel González Martín del Campo |
| 40 | Adnan Hamad | Adnan Hamad Al-Abbasi |
| 311 | Javi Pérez | Javier Pérez Martínez |

**2,424 of 32,760 people carry one**, and we display every one of them under their full legal
name instead of the name the game shows.

This also corrects a claim in our own code. `staging.INFO_LAYOUT` says of `common_name_id`:
*"Only 0.1% of records set it (the rest are ffffffff), nowhere near the ~8% that carry a
nickname, so it is NOT the link `_scrape_nicknamed` follows."* The measured rate is
**2,424 / 32,760 = 7.4%**, which IS the ~8% that carry a nickname — and it is the same byte
range `_scrape_nicknamed` keys on (`+16`, the `NO_NICKNAME` sentinel). So both halves of that
comment are wrong: the field is the nickname link, and it now has a table to resolve against.

#### THE CLUB TABLE: 11,331 records at 6,340,458, `tid == slot index`

**The single biggest result of this work, and it came from chaining, not searching.** TODO #17
recorded that clubs were the one table with no locatable structure — the candidate scan's
accepted records sprawled across one 6.4 MB run whose first entry was junk, so there was no
"record 0" to look behind. That was true only because nobody had walked the chain into the
6.33–12.63 MB gap.

```
6,340,446   8 x FF                      <- sentinel
6,340,454   u32 = 11331                 <- declared count
6,340,458   [tid 0][uid 0xFFFFFFFB][7]'Algeria'[00][7]'Algeria'[00][3]'ALG' ...
```

- **`tid` IS the slot index, and the table is dense: 11,331 of 11,331 tids resolve, zero gaps**
  (ids 0..11,330 against a declared 11,331).
- Ground truth is exact: `tid 346` = `'Boldklubben Frem' / 'Frem' / 'Frem'`, `tid 7296` =
  `'Boldklubben Frem Reserves'` — the two tids `careers.py` has always used.
- It runs from 6,340,458 to the competition table's own header at 12,626,905, so **the whole
  6.3 MB gap is this one table.**
- It holds more than clubs. Low tids are **national teams** in the club layout, alphabetically
  (`0 Algeria, 1 Angola, 2 Benin, 3 Botswana, 4 Burkina Faso, 5 Burundi, 6 Cameroon, …`) with
  descending negative uids (`0xFFFFFFFB, 0xFFFFFFFA, …`); real clubs start around tid 61
  (`'Asociación Atlética Argentinos Juniors'`); reserve sides sit high (`7296`); and the table
  **ends with U21 national teams** (`11328 'Tuvalu U21'`, `11329 'Montenegro U21'`,
  `11330 'Saint Barthélemy U21'`).

That last point resolves the other half of TODO #17 by construction: national teams are not
invisible records the club scan happens to miss, they are **rows 0..~200 of the club table**,
and the reason 153 low tids were resolving to `'Footballer of the Year'` and friends is that
the scan never found this table and was matching award records (13,711,352) instead.

**What is NOT yet done: the record's trailer.** The head is
`[tid u32][uid u32][len][long][00][len][short][00][len][code]`, and a **fixed** 491-byte
trailer walks the first 62 records exactly (the whole CAF national-team block) and then
breaks, so the trailer carries something variable-length. The extent, the count, the index
invariant and the anchor are all established; converting `_eval_club_candidate` into a pure
structural walk needs only that trailer decoded, and until then a tid-keyed scan bounded by
this table's declared extent is already strictly better than scanning 20 MB of REFDATA.

#### The award table: 807 records at 13,711,352

Found by chaining forward from the city table's declared end, and it matters beyond the
inventory: **these are the records leaking into the club index.** They use the club shape
(`[tid u32][uid u32]` then long/short/code strings), start at `tid 0, uid 102407,
'Footballer of the Year'` / `'World Footballer of the Year'`, and continue through
`'South American Footballer of the Year'`, `'African Footballer of the Year'`,
`"Players' Player of the Year"`, `"Players' Young Player"`. TODO #17 records that **153 low
tids currently resolve in our club index to award names** — this is the table they come from,
and it now has an exact, declared anchor instead of a region guess. The trailer is longer than
the club/comp trailer (an assumed 14 bytes ran the string reads off the end), so the record
shape still needs pinning before it can be walked.

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
`scripts/map_regions.py` splits it into three stretches with three different characters:

| stretch | what it is |
|---|---|
| 14.00 – 16.71 MB | **85% filler** (33% `0xFF`, 52% `0x00`) with sparse structure. 54,437 runs of >= 8 `FF` in 2.8 MB, and EVERY count candidate in it is a multiple of 256 (257, 513, 769, 1024, 1026 …) — i.e. ordinary data bytes read as a u16, not a header. Club tids appear but unevenly (tid 346 seventeen times, tid 61 two hundred), so it is not a per-club grid either. Unidentified, but not count-framed. |
| 16.72 – ~21 MB | the **tagged data dictionary** — `fmparser/tagged.py`, self-describing `[tag][0x01][type][value]` fields, an entirely different framing, already parsed. |
| ~21 – 39.76 MB | `map_regions` calls it "binary pages ~49B". Holds the **contract detail records** (`regions.CONTRACTREC_LO/HI`) and the **transfer-history record** at 36.36–36.94 MB, both already decoded by other means. The three name id-tables sit at 37.88–38.85 MB inside it and those ARE count-framed. |

The whole-file index detector finds **zero** index-keyed tables anywhere between 14 MB and
37.9 MB, which agrees.

So the count-framed tables cluster in exactly two bands — **3.99–6.33 MB** (the attribute
section) and **6.34–14.00 MB** (the reference section) — plus the **37.88–38.85 MB** name
id-table trio. That is the shape of the convention in this file, not a coverage gap waiting to
be filled.

**One lead worth keeping**: `u32 = 32,966` sits at 14,000,242, immediately where the language
table ends, followed by a repeating 14-byte `[6 x FF][8 bytes]` unit. 32,966 is
person-count-shaped (the info spine holds 32,849 person records, 77 of them empty), so this may
be a per-person table. But the unit stops being uniform after 386 records, so its extent is
UNPROVEN and it is not in the register.

## Three kinds of number sit in front of a table

Not every header number is a record count, and conflating them is how `60000` nearly entered
the register as a table of 60,000 names. The distinction was settled by the one test a single
save cannot run: **hold the number against a career's worth of saves and see whether it moves.**

| kind | evidence | examples |
|---|---|---|
| **True count** | equals the records actually present | competitions 1,372; cities 10,956; stadiums 15,987; languages 124; currencies 173 |
| **Per-database pool** | fixed for a career, DIFFERENT between careers, 100% initialised | the **history slab**: 265,423 rows in all 28 Frem saves, **295,648** in Bucaspor |
| **Engine-wide capacity** | identical across careers, larger than actual usage | the **browse name table**: `60,000` in both careers, holding 45,942 (Frem) / 45,834 (Bucaspor) names — 76.5% utilised |

### The history slab's 265,423 is a POOL, not a growing count

This is the one worth internalising. `history.locate`'s docstring calls it "the exact row
count", which is true of the physical rows — but it is **byte-identical in all 28 Frem saves,
from the day-one 2021-07-01 save to 2026-07-02**, five in-game years and 25 snapshots apart,
while the career history it holds grows the whole time. And every one of the 265,423 rows is
non-zero even on day one.

So it is a **fixed pool allocated when the database is built, fully initialised, and recycled
rather than grown** — which is exactly what
[`history-chain-pointers.md`](agent-context/history-chain-pointers.md) describes from the other
side (chains running through recycled slots). The practical consequence: **that number can
never tell you how much history exists**, only how many slots the pool has. It is safe as a
walk bound and worthless as a measure.

Bucaspor's 295,648 confirms it is per-database rather than a hard-coded engine constant.

**One unresolved lead** in the same header: the `u32` at `start - 8` DOES vary across saves
(2,069 on the day-one save, then 67,635, 564, and 52 for most of the career, 56 at the end).
It is not monotonic, so it is not a usage counter; a free-list head into the recycled pool would
fit, but that is a guess and has not been tested.

## The convention does NOT extend to the career half of the file (39 MB +)

Checked because the register stops at 38.85 MB and the file runs to ~61 MB. The tables up
there — the history slab, the club history record tables, our own matches, the squad snapshot —
are located by other mechanisms, and that is not an oversight in the search:

| region | framing |
|---|---|
| history slab, 39.8–44.6 MB | **Counted, but a DIFFERENT framing**: `u32 @ start - 12`, no sentinel, not 4-byte aligned. `history.locate` already reads it. The only counted table outside the two reference bands. |
| just after the slab, 44.6 MB | a per-season series — `[f32][…][u16 year]`, 7.0 in 2021, 10.0 in 2022 — FF-padded, no count. |
| club history record tables, ~46.8 MB | The first row sits **immediately** after an 8-byte FF run with **no count between them**: the 4 bytes where a count would be read `3F 80 00 00`, i.e. float32 `1.0` — data, not a header. The FF run here is filler that happens to be 8 long. |
| our matches, ~55.4 MB | **No count and no capacity.** Checked twice: the nearest 8-byte sentinel is 1,250 bytes before the first anchor with unrelated values, and the 64 bytes immediately in front of the anchor are *near-constant across saves* (only two value sets over 10 saves) while the match count swings from 9 to 57 — so they track something else entirely. They read as `u16` pairs (8/15, 8/27, 13/31), i.e. tail data from the preceding match record rather than a header. Matches are found by the `regions.DELIM_UNIT` delimiter cluster. |
| squad snapshot, 51–61 MB | located by `regions.CLUB_MARKER`. |

The cross-save sweep agrees: across all 34 saves there is **not one** count-framed table above
39 MB that survives both stability filters (the single candidate, a Bucaspor `10 x 3 B`, has a
drift value shared by nothing else — a coincidence in a different place each save).

**So the convention is a property of the STATIC REFERENCE DATABASE, not of the save.** The
reference half (roughly 4–14 MB: attributes, staff, clubs, competitions, nations, stadiums,
cities, languages, currencies, awards, and the name id-tables at 37.9 MB) is shipped as counted
arrays, because its sizes are fixed when the database is built. The career half (39–61 MB:
history, club records, matches, the snapshot) is written by the running game and is located by
pointers, delimiters and markers instead — which is exactly why `history.py` needed the
in-degree test, `matches.py` needs a delimiter cluster, and neither could have been found by
looking in front of record 0.

That is the useful closing shape of this work: **look for a count header when the data is
reference data, and expect pointers or delimiters when it is career data.**

## Why the yield is low, and where the rest are

The detectors' own harvest was ~91 KB of a 60.7 MB file, which looked thin until chaining
added the 6.3 MB club table. The reason the *detectors* find little is structural rather than
a tuning problem: **they only see sentinel-framed tables of FIXED-WIDTH records** — and the
lesson is that **chaining forward from a known table's declared end beats any detector**,
because the declared count makes each table's extent known and therefore makes the next
table's header findable with no search at all. The file's bulk lives in regions with different framing entirely — the
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
