# How the parser works

**Read this first if you are changing `fmparser/`.** Not the history of how the save was
decoded — that is spread across `docs/` by subsystem — but the shape the parser has, and the
one idea it is organised around:

> **A locator shape tells you how to FIND a record. A declared layout tells you how to READ
> it. Everything else is small.**

Those two halves fail differently, are tested differently, and are the reason the same bug
kept recurring in different modules. Keeping them apart is what this document is for.

---

## Part 1 — the seven locator shapes

**First, the model underneath them.** Every table in the save answers three independent
questions, and the seven shapes below are combinations of the answers, not seven kinds of data:

| question | answers | in `core` |
|---|---|---|
| how do rows relate? | an **array** (fixed or variable stride), or a **linked list** (each row holds the next row's index) | `TableDef` / `TaggedTableDef` walk arrays; `LinkedTableDef` reads a linked pool |
| how is a row encoded? | **packed** (fields at offsets) or **tagged** (key-value fields) | `Record` / `TaggedRecord` |
| how is the start found and the end proved? | a declared count, a capacity with empty slots, a terminator, a length chain, an archive member, or a search by key | the locator each table supplies |

So A is an array with a declared count; B the one true linked list; C an array with a
capacity; D is where an array or a tagged row is STORED, not a structure; E an array of
variable stride; G an array with no count that ends at a marker; and F is an array whose start
and stride we have not mapped, found row by row through its key -- migrating an F table is
research into its bounds, not a refactor. (G is new, split out of B, which used to cover both
the linked list and the marker-ended arrays; the letters A-F keep their old meanings otherwise,
so older notes still read correctly.)

A 64 MB `.fms` is not one format. It is several, and the boundary between them is structural,
not thematic: a 20-byte fixed grid of cities and a 20-byte fixed grid of match slots are the
same *kind of thing* to a parser, while the competition table sitting between them is not.

Four **regimes** describe the file (see [`savefile-map.md`](savefile-map.md)). Seven
**shapes** describe the code, because a survey of every locator in `fmparser/` found several
that do not fit the four regimes.

| shape | how you find it | the validator that bounds it | used by |
|---|---|---|---|
| **A. Count-framed** | `[≥8 × 0xFF][count][record 0]` — the table declares its own size | `id == slot index`, on every declared record; for a tagged block, all `count` fields read strictly | competition table; ~20 tables carry the frame ([`table-framing.md`](table-framing.md)); the data dictionary's 667 rule files (`[u32 n][n tagged fields]`); training (`[u32 count]` + 61 B rows, `tid == row`, a fixed gap after the progress pool); club records (`[u16 count]` straight after the history pool, one variable-length row per club); **our matches** (`[u8 count]`, one `5,102 + 17 n` byte row per match, seeded from any row and walked back to the count) |
| **B. Linked list** | each row holds the NEXT row's index (`FFFFFFFF` ends a chain); the rows it has not moved name the pool's base | the forest check on every row: no row reached twice, no pointer out of the pool, and every row on a chain from a head (`core.forest`) | career-history pool |
| **C. Preallocated grid** | ships full of empty-sentinel rows and grows; the slot count is a *bound*, not a headcount | a residue class mod stride, plus the grid's own dense-from-0 invariant | match slots (3,975), player progress (62,400 × 70 B, seeded from its unused-row template and walked both ways), the record blocks inside each club-records row (25,368 empty rows on day one), contract grid (32,961 × 83 B), **staff attributes (4,642 × 39 B, `id2 == slot`)** |
| **D. Archive member** | zstd container with a directory at the tail | the directory names the member and its length | `fix_man`, `stadium`, `comp_<id>.dat` ×147 |
| **E. Seeded chain** | variable-length records, **no count and no index** | this record's length field lands exactly on the next one, `min_chain` times | stadiums, languages, currencies |
| **F. Key search, no table** | find *N* copies of a record by key bytes; disambiguate | the info spine, or recency | none: both records once read this way are table rows (below) |
| **G. Terminated array** | rows one after another with **no count**; the array ends at a marker, a delimiter or a filler wall | landing exactly on that end | squad snapshot |

The rest of this part is one section per shape: what it looks like in the bytes, how to find
it, and **the way it fails** — because every one of these has cost real debugging time, and the
failure mode is the part that does not survive in code comments.

---

### A. Count-framed — the only self-describing structure in the save

```
ff ff ff ff ff ff ff ff   <- >= 8 sentinel bytes
5c 05 00 00               <- record count (u32 for fixed grids, u16 for string tables)
00 00 ...                 <- record 0, whose id reads 0
```

**How you find it.** Where the table follows another one directly, start at that table's end:
the save is written front to back, so the round names, clubs, competitions and nations sit
back to back, and `tables/clubs.py`'s `locate_clubs` is just "after the round-name table's
span, skip the 0xFF run, read the count" (`after_frame`), `locate_competitions` the same after
the clubs. No content signature, no tuned range. Otherwise `core.find_framed_count(mm, start,
hi)`, and then you *must* validate: the
sentinel alone occurs **566,078 times** in one save, so the frame is a candidate generator and
nothing else. The validator is that the declared records satisfy `id == slot index` —
`tables.competitions.COMP_TABLE` asserts `cid == i` on every slot and raises `CompTableError` with
the slot number if it ever fails.

**Two details that are measured, not defensive:**

- Test for a run of **`>= 8`** sentinel bytes, never `== 8`. The record *preceding* the frame
  can itself end in `0xFF`, and an exact-length test misses those frames.
  Not every frame has eight: the club and competition tables' frames are six (`FF x 6`
  after the table before them), which is why they are located from that table's end rather
  than by a sentinel search.
- A string table's length prefix is **u32**, not one byte. `table-framing.md` renders these as
  `[7]'Algeria'` and the actual bytes are `07 00 00 00 'Algeria' 00`; a search written from
  that description returns zero hits. `primitives.pstring` reads it correctly.

**How it fails.** Silently and expensively: a walk that stops early returns a *short table*
that looks entirely valid, because every record it did read was correct. Comparing each
declared count against what the parser actually read found **five defects** in tables that had
passed every check we had, two of them losing real records on every save ever built. If a table
declares its count, assert `read == declared` — that assertion is free and it is the only thing
that catches this class.

---

### B. Linked list — the career-history pool

Each row holds the index of the NEXT row in its chain, with `FFFFFFFF` ending the chain, so
records are found by following pointers, not by position. A monotonic-looking `u32` column is
often such a pointer rather than a counter: on a fresh save the rows are contiguous, so row `k`
holds `k+1` and the two readings are indistinguishable — they only diverge once the game starts
appending into recycled slots.

`core.LinkedTableDef` reads such a pool: a `Record` for the row, the name of its pointer field,
an optional header record, and a locator returning `(base, count)`. It reads **every row**,
column-wise, and its invariant is `core.forest` over all of them: in-degree at most 1, no
pointer outside the pool, chain starts equal chain ends, and every row reached by walking
the chains from their starts. The last clause is what catches a cycle, which has no start
and no end and so passes the first three. **Following a chain, and what its rows mean
together, is not the parser's job**: the pool is emitted as stored and the loader walks it
(`load_duckdb.load_history`).

**How you find one.** From its own pointers. A row the game has not moved points at the row
after it, so two neighbouring such rows fix the pool's base arithmetically; every candidate
base is checked against the count in front of it and the forest check, most-named first
(`tables/history.py`'s `locate_history`). No window and no threshold: one unmoved pair is
enough, and the acceptance test is exact. The count must also HOLD the pairs that named the
base: a one-record frame is trivially a forest, and on a save whose real pool was corrupted
one such frame was accepted in its place until that rule went in. Break the pool on purpose
and the locator must return nothing, not a lookalike.

**How it fails.** *Reading the pointer as a counter.* It works perfectly on a fresh save and
nowhere else: splitting records where the `+1` sequence breaks shatters each player whose
history was appended into recycled slots into 3-4 fake players. *Framing the row wrong.* For
years the history row was read 8 bytes late, as `[club, fee, next][stats]`, which made a
row's stats look like they belonged to the season on the PREVIOUS row and needed a reading
rule to undo. The row is `[stats][club, fee, next]`: record 0's stats were the 8 bytes taken
for a header, and the old rule read record 0's season off the far end of the pool.

---

### C. Preallocated grid — the shape that surprised us

These tables **ship full**. On a day-one save, the club-records table's 2,114 team blocks
already hold 25,368 twenty-one-byte rows of empty sentinels, and the stride-70 pool is 100% empty — falling to
92.5% by 2026 as the career fills it in. They also **grow**, by exact multiples of the record
size. Preallocation and append are not alternatives here; the file does both.

**Consequences that matter:**

- **A row count is not a headcount.** The slot count is stable across every save of a career
  (match slots: 3,975 for Frem, 3,943 for Bucaspor) whether the career is one day or five years
  old. A walk that returns a *different* count between saves of one career is wrong, and
  `tests/test_match_slots.py` asserts exactly that.
- **Day one is a real test case, not an edge case.** A walk that depends on rows existing
  finds nothing on `frem-2021-07-01` and everything on `frem-2026-06-11`. That save is in
  `tests/assert_identical.py`'s four for this reason.

**How you find one.** By a **residue class mod stride**: take a constant that appears in every
populated row, collect its offsets, and find the residue class mod the stride that holds the
longest contiguous run. `matchslots.locate` does this. Note the discipline in its signature —
`bridge_slots` spans the 7% of slots carrying no trailer, and it bounds a **gap**, not the
table, so widening it cannot change the row count.

**A grid can sit inside a framed table.** The club records are a shape A table -- a u16
count, then one row per club, `[club_tid][n][n league lists][4 blocks of 12 slots]` -- and
each block is a preallocated grid whose slots fill in place, independently of each other
(`core.FixedList`, `tables/club_records.py`). Read as a free-standing grid, by a sweep for
12 plausible rows agreeing on one club, the same bytes gave the right values and the wrong
table: a block with any unwritten slot failed the 12-row test and was dropped whole (a
club's whole current season, for every club not yet at 12 records), and a player block,
which has no club id of its own, went to the nearest team block's club. Walked from the
count, the club is the row's key and an empty slot is `comp_cid` / `player_tid` = all-FF.

**How it fails.** A tuned bound silently becomes the answer. A miss counter or a plausibility
window makes the row count a function of the constant rather than of the table — which is how
the city walk dropped 31 real cities and invented 3 while reading Parken and Copenhagen
perfectly. Its real invariant is `id == slot index`, and once that was the bound, the tuned
number was not needed anywhere.

---

### D. Archive member — the last ~1.3 MB

The tail of the save is a **zstd archive** (`sicomps`): 159 named members, 6.6 MB decompressed,
with a directory. Its `fix_man.dat` is the world fixture list — 26,954 rows across 1,751 clubs.

See [`save-archive.md`](save-archive.md) for the container and
[`archive-coverage.md`](archive-coverage.md) for what each member is worth against what we
already parse. The reader is `fmparser/core/archive.py`; it needs `uv sync --extra archive`.

**The rule that found it, which generalises past this shape:** **rank an unknown region by
BLOCK ENTROPY, never by printable fraction.** This region was ranked the best remaining target
for being "25.8% printable" when uniform random bytes are **37.1% printable by construction** —
it was *less* printable than noise. Four hunts died there before anyone measured entropy.
`scripts/audit/entropy_profile.py` does it: filler reads ~1.4 bits/byte, ordinary records 3–6, dense
records and strings 6–7.5, and **anything above 7.9 is compressed**, where no stride search
will ever bite.

**How it fails.** Not by mis-parsing — the directory is authoritative — but by **scope**.
`fix_man` is a *two-calendar-year rolling window* of matches already played, so it enriches the
snapshot it came from and can never supply history. A 2026 save knows nothing about 2021. That
single fact turns almost every "can the archive replace our parser?" answer from *replace* into
*augment*.

---

### E. Seeded chain — variable-length, no count, no index

Stadiums, languages and currencies are variable-length records with no framing and no ids to
check against. The only structure available is that **a record's length fields land exactly on
the start of the next record**, so `min_chain` consecutive successful parses is a signature
noise does not produce. `lookups._walk` implements it.

**How it fails, and it is the subtle one.** The seed is merely *the first place the signature
matched*, which is not the first record. For languages that is wherever `Name == OtherName`
first happens to hold — seeding there would silently drop ids 0–6 and every count downstream
would be short by six with nothing to notice it. `_walk` therefore **rewinds**: it steps back
looking for a record that ends exactly where the current one starts, and repeats until it
cannot. A bad seed shifts the whole table and nothing complains.

**The player lists are the same shape, walked both ways** (`tables/player_lists.py`). 66
lists of `[100 scrapbook entries][14-byte trailer]`, each entry eight
length-prefixed strings and a 168-byte tail, with no count in front and a large unrelated
pool behind. The seed is an unused list -- 100 template entries whose tails carry `14 01 00 0a 00` at exactly 200-byte
gaps -- and from it the walk goes forward list by list, and BACKWARD by reading each
entry's strings from their end: a string of length n ends n bytes after a u32 holding n, so
the strings that end at a given byte have exactly one start. Both walks stop where a list no
longer parses, and the region must come out as 66 lists (31 world, 31 club, 4 more) on
every save. Extract hands every entry over as stored (`player_scrapbook.json`); which of
them are our squad's is the store's question (`staging.squad_scrapbook`: a player in our
squad arrays, his latest entry in lists 31-61, used for the entangled attributes while it
is at most a year old). The managed squad used to be found by key
search -- clusters of our club marker -- and on the early saves the cluster sat on lists
62-65, stale copies whose attributes match the stored ones less often (1,589 vs 1,754) than
our current season list's.

---

### F. Key search, no table

Sometimes there is no table concept to find. You search the file for *N* copies of a record
keyed on a tid/uid/sid and then have to decide which copy is the live one.

- `staff.scrape_staff_attributes` **used to be listed here and no longer belongs.** It was
  held to be shape F because the staff records were "multi-segment, so a stride walk is
  provably impossible". They are not. That conclusion came from measuring the gaps between
  ground-truth managers (19,929 and 8,541 bytes) against the **player** record's 78-byte
  stride; the staff record is **39** bytes, and those gaps are exactly 511 and 219 records of
  it. Read at the right stride, `id2 == slot index` on every declared slot — 4642/4642 on
  Frem, 5697/5697 on Bucaspor — so it is **shape C**, a preallocated grid, and the lookup is
  now arithmetic. Corrected 2026-09-20.

  Keep the failure in mind when reading any other "provably impossible" in these notes: the
  measurement was right, the stride it was compared against was not, and at 78 bytes the ids
  come out `0, 2, 4, ...`, which is exactly what a phase reset looks like.
- **Contract status** was the other one: a 40-byte record found by searching the file for
  `87 00` and keeping the hits whose `[tid][uid]` matched the person table. Every hit is a
  row of the **training table** (shape A, `[count u32][61 B rows]`, `tid == row`): the gaps
  between hits are all multiples of 61, and the search had been finding that table one row
  at a time. `87` is the row's `contracted` byte (+37; `00` on a free agent and on staff), and
  the squad status is +39. `training.scrape_squad_status` reads it from the table, identical
  to the search on all 31 saves of both careers, and the 29 bytes the old record declared as
  padding are the row's training columns.

**How it fails.** By picking the wrong copy, which produces *correct-looking* values for the
wrong point in time. Validate every hit against the info spine, exactly as the scrapers in
`staging.py` do.

### G. Terminated array — no count, ends at a marker

Rows sit one after another, but nothing declares how many: the array ends where a marker, a
delimiter or a filler wall says it does. Career data is mostly like this.

**Filler walls.** Long runs of `00`/`ff` separate sections cleanly, and a region between a
structure that knows its own extent and the next wall is a far smaller search than the file.
Before assuming a region needs one, look in front of its first record for a count (shape
A): the club-records region was bounded this way until the u16 in front of it turned out to
be the club count.

**Our matches were read as this shape, and were not it.** The old `matches.py` found each
game by a delimiter cluster (`21 22 55 15 0a 00 00 00`, repeated) and scanned forward from it
for a header. The cluster is the per-starter tactic items at the END of the previous row, so
the season's first match -- which has no previous row -- was never found: one match short on
every save, both careers, for the life of the parser. The table has a u8 count in front of
row 0 and rows whose length the row declares (`tables/matches.py`); see shape A.

**How it fails.** *Drift.* Every window in `regions.py` was tuned on one career and is wrong
for the other — Frem's contract-expiry records sit at ~29–31 M, nowhere near the Bucaspor
`CONTRACT_LO = 54 M`. A constant fallback is worse than no fallback, because it produces a
plausible short answer instead of an error. Locate by an embedded key plus a validating
signature, validate every hit against the info spine, and prove the end by landing on it.

### Two non-conformers, and what measuring them showed

**`lightresults` is not a shape of its own — it is a shape G sweep, reading shape C's record at a
15-byte shift.** Measured 2026-09-20 on `frem-2026-06-11`: of the 5,830 "fixtures" a
whole-region sweep returns, 5,183 (88.9%) sit at exactly `club_team_record + 15`, and the
alignment is field for field —

| light | club_team_record |
|---|---|
| `+0` home_tid | `+15` club_tid |
| `+2` away_tid | `+17` opponent_tid |
| `+4` scoreH | `+19` score_for |
| `+5` scoreA | `+20` score_against |
| `+10` comp_cid | the **next** row's `+4` (stride 21, so `+15+10 == +21+4`) |

So a "fixture" there is one club's record-setting match plus the competition of the following
category's row. Region agreement is 98.9% on `frem-2026-06-11` and 96.7% on
`bucaspor-2023-03-25`; the 1–3% outside come from clusters the year-marker scan opens in the
name tables and the transfer band, and are suspected false positives. The sweep has since
been deleted; the club-records table is read from its own count.

**The two window-bounded scrapers were measured before being replaced, and the measurement
said not to.** `ATTR_LO/HI` (3.8–6.6 MB) and `CONTRACTREC_LO/HI` (16–40 MB) return counts
identical to a whole-file scan on three saves across both careers. The one apparent exception
argues *for* the window: without it, `frem-2021-07-01` gains a contract record at 12.646 MB
that reads wage 0 and an expiry six months before the save's own date — and 12.646 MB is
inside the competition table. It is a coincidental `[tid][0x01]…[plausible year]` in an
unrelated structure, and the window is what excludes it.

The distinction that matters: **these two are not fallbacks.** Nothing falls through to them
when a locator fails, because there is no locator to fail. That is what separated them from
`SNAPSHOT_LO/HI`, `LIGHT_LO/HI` and `MATCH_LO`, all three of which *were* fallbacks and are
gone — see below.

### A constant fallback is worse than no fallback

Four locators used to answer with a hand-tuned window when they found nothing, so a blind
locator produced a plausible short result instead of an error. All four now raise or report:

| locator | the window it fell back to | why it was wrong |
|---|---|---|
| `attributes.snapshot_bounds` | `SNAPSHOT_LO/HI` 62.3–63.2 MB | the *default career's* snapshot; any other career got an empty read |
| `rule_files.find_region` | `TAGGED_LO/HI` — **and cached it** | one blind lookup served to every later caller for the life of the process |
| `matches.extract_season` (retired) | `MATCH_LO` = 55 MB | 55 MB is *inside* Frem's own match region (~53.8 MB), so it dropped the start of that career |
| `lightresults.build` | `LIGHT_LO/HI` 47.0–50.5 MB | Bucaspor-tuned; and measured across all 34 archived saves the locator never once returned empty, so this was dead code with a failure mode attached |

The match table is not located on a save whose table is empty (after the July rollover, or on
a career's first day), and that is correct there, not a locator failure. What tells the two
apart is an independent table: the extract requires the match table to hold exactly our clubs'
games in the world fixture list since the rollover (`matches.check_against_fixtures`), which
agrees match for match on every save measured.

---

## Part 2 — reading a record, once it is found

### The declared-layout rule

> **One declarative layout per record is the schema.** The parser reads FROM it; the audit
> checks AGAINST it. Neither can drift from the other, because there is only one of them.

That rule predates this refactor — `staging.INFO_LAYOUT` and `matchslots.LAYOUT` already worked
this way. What was missing was one *dialect*: there were three, and the third
(`scripts/audit_records.LAYOUTS`) dropped the field's `kind`. That is not cosmetic. It is why
nothing in the repo could catch a field whose **declared width disagrees with its kind** —
`staging._read` ignores `width` outright for `DATE` and `HEX4`, so `(20, 2, "dob", DATE)` would
declare two bytes, read four, and pass every check we had.

The modules:

| module | what it holds |
|---|---|
| `fmparser/core/primitives.py` | the byte readers — `u8/u16/u32/i16/i32/f32`, `ymd`, `tag4`. Pure `(buffer, offset) -> value`. |
| `fmparser/core/types.py` | how a value is ENCODED: the packed kinds (`U8` .. `PAD`, `UNKNOWN`), the variable-length segments whose length the bytes declare (`PString`, `CountedList`), `FixedList` (`[n x item]`, n fixed by the layout, the item a `Record` or a `Struct` -- a fixed-width element that holds a list of its own), and the tagged format (`read_tree`). |
| `fmparser/core/schema.py` | what a record MEANS: `Record` + `Field` (packed), `TaggedRecord` + `Tag` (tagged), `validate()` / `validate_tagged()`. |
| `fmparser/core/table.py` | where the rows are and how to walk them: `TableDef` (packed), `TaggedTableDef` (tagged), `LinkedTableDef` (a linked pool, with `forest` / `follow`); `record_instances` lists every record a walk reads. |

**31 packed records are declared**, and `scripts/audit/audit_records.py` audits every one of
them straight from `core.REGISTRY` — every `Record` registers itself on import, so the audit
holds no layout, and no list, of its own. (A hand-kept list had silently left five records
unaudited.) That
inversion was not cosmetic: while the audit owned the competition trailer's layout, it
declared `nation` as a u16 at `+3` and both parsers read `trailer[3]` alone, which is right
only because all 227 nation ids in the save happen to fit in a byte.

Run **`uv run python tests/test_layouts.py`** — no save file, milliseconds — and
**`uv run python scripts/audit/audit_records.py --map`**, which prints the per-byte schema. *That
printout is the record documentation.* It is generated rather than retyped, so it cannot go
stale, which is the only reason to trust it.

### Offsets are relative to the RECORD START

Always — never to whatever internal landmark the locator happened to find. The player
attribute record is *found* by its SID marker and this project has always described its fields
relative to that marker (`P-38`, `P+28`) while the record itself begins 42 bytes earlier. Both
spellings are legitimate and mixing them is a bug the repo has already had. `Record.anchor`
reconciles them: declare in record coordinates, and call
`rec.read_at_anchor(mm, marker_offset)`, which does the subtraction exactly once.

### Declared UNKNOWN is not the same as undeclared

A byte you have decided you cannot name is **covered and visible**. A byte that is neither
named nor declared is **a byte you are stepping over by accident**, and the audit's job is to
tell those apart. The player record decoded perfectly for four years while missing its last 13
bytes.

**Carry what you cannot name — then go and name it.** The player record's nine hidden
attributes were carried unnamed for years and are now named from `fmm-editor`'s `Player.cs`.
The staff record's six are still `hidden_s*`, named *by offset*, because fmm-editor has no
`Staff.cs` — there is no upstream order to borrow and no ground truth of our own. Guessing a
name is how `-140` became a Style candidate; sourcing one and checking it twice is not
guessing.

### What is deliberately NOT declarable

**Meaning.** Sentinel collapsing (`0xFFFF` second nationality -> none), banding (a hidden byte → Attacking / Normal / Defensive),
composites (an attribute modelled from CA), and the **four money conventions** — wage units
×520, fees in thousands, an f32 of whole GBP, a u32 of whole GBP. Which money convention
applies is a property of the record, not of the byte width, so a shared `money()` helper would
let a call site be wrong by a factor of 520 and still return a plausible number. Each record
converts its own, next to the evidence.

**Plausibility windows.** `1 <= ln <= 120` for a stadium name, `0 < cid < 20000`, a DOB year
gate. These look like validation and they are **locating** — separately measured evidence about
one table's extent. Centralised, a table's row count becomes a function of a shared constant.

**Counted and nested structures.** The competition record is
`[names][trailer 14][count 4][entry 8 × n][tail 21]`; the person record continues past its
68-byte head into counted language and relationship lists. Only the fixed-width parts are
declared, and `Record.span` is the extent of *the declared part*, not of the record.
`is_head=True` says so. There is no DSL for the rest, on purpose: a schema that could express
it would be a programming language, and every argument currently visible in a comment would
stop being visible.

### Packed and tagged: one system

Two encodings occur in the save. PACKED records are bytes at fixed offsets. TAGGED records --
the data dictionary's rule files, the archive's `comp_<uid>.dat` members -- are
`[tag][01][type][value]` fields in any order, with optional tags and a type code that can
vary with the value (`ntms` is a u8 for 12 teams, a u16 for 255). Each layer of `core` holds
both, so a tagged table is hooked up exactly the way a packed one is:

| layer | packed (e.g. cities) | tagged (e.g. rule files) |
|---|---|---|
| encoding (`types.py`) | kinds `U16`, `F32`, ...; variable-length segments `PString`, `CountedList` | `read_tree`: one field, strict |
| record (`schema.py`) | `Record` of `Field(offset, width, name, kind)`; every byte named or `UNKNOWN` | `TaggedRecord` of `Tag(tag, name, kind)`; every tag read or listed `unread` |
| table (`table.py`) | `TableDef(name, segments, locator)`; locator -> `(base, count)` | `TaggedTableDef(name, locator, schema)`; locator -> `[(offset, n)]`, one per row |
| walk | the engine steps by stride / segment | the engine reads exactly n fields per row, then the row's schema |

```python
CITIES_TABLE = TableDef(name="cities", locator=locate_cities, segments=(CITY,))
COMP_RULES_TABLE = TaggedTableDef(name="comp_rules", locator=locate_comp_rules, schema=FILE)
RULE_FILES_TABLE = TaggedTableDef(name="rule_files", locator=locate_rule_files,
                                  schema=schema_for)     # one schema per row kind
```

`schema` is one `TaggedRecord`, or a function `block -> TaggedRecord` where rows come in
several kinds (the rule files: a competition's, a nation's three, a stageless one). A row
that does not read to its declared count raises `TaggedTableError` -- never a shorter row. A
row declaring 0 fields is a stub: located, not scraped.

**Hooking up a new table.** The first two steps are the same for both; the rest differ only
in which class you reach for.

1. **Find it** -- entropy profile, then look in front of record 0 for the count (Part 1). A
   packed table's frame is `[>=8 x FF][count]`; a tagged block's is `[u32 n][tag 01 type]`.
2. **Write the locator.** Packed: `(base, count)`, or a list of such runs where the table is
   stored as several arrays (the world fixture list). Tagged: `[(offset of first field, n)]`.
   Where the table asserts something of every row (`id == slot`), declare it as the
   `invariant` rather than writing a loop that breaks on it: the walk stops at the first row
   that fails it. The engine only finds and reads a table; looking a row up by id is a join
   on the scraped rows, not a second way into the bytes.
   For a region of count-framed blocks, `core.scan_tagged_blocks(mm, lo, hi)` is the whole
   locator shape -- one forward pass, a candidate taken only if all n fields read -- and your
   locator keeps the blocks that are yours (the rule files keep those with `ftye` + `file`).
3. **Declare the record.** Packed: a `Field` per byte range. A variable-length row is a
   sequence of segments -- `Record`s for the fixed stretches, `PString` for a
   length-prefixed string, `CountedList(name, count, item)` for `[count][count x item]`,
   `FixedList(name, item, n)` for n preallocated slots, whose item may be a
   `Struct(name, *segments)` when each element holds a list itself (a match's two team
   blocks: `FixedList("teams", Struct(head, FixedList(players, 20), tail), 2)`) --
   and the walk steps through them in order (`tables/nations.py`: three strings and three
   counted lists between fixed stretches; `tables/matches.py`: a counted event list, 50 event
   slots and two team blocks of 20 player slots). Tagged: a `Tag` per tag you
   read, and `unread=` for every other tag seen. Build `unread` from the saves, not by
   hand: declare the tags you know, run `TABLE.coverage(mm)` over every save, and its
   `undeclared` counts are the list to add. Nested containers are `Nested(RECORD)`, lists of
   containers `ListOf(RECORD)`, and each nested record is declared the same way.
4. **Define the table** -- `TableDef(...)` / `TaggedTableDef(...)` -- and read it with
   `TABLE.scrape(mm)`; register it in `tables/__init__.py`'s `TABLES`. A record stored in
   front of the rows -- a table's own header (`comp_man.dat`'s), or the header before each
   tagged row (every `comp_<uid>.dat`'s) -- is the table's `header=`, so the audit measures it
   with the rows. An archive table names its member (`member="fix_man.dat"`), or a family of
   them (`member="comp_<uid>.dat"`, `archive.member_names`).
5. **Audit it.** Nothing to add: every `Record` and `TaggedRecord` registers itself, and
   `audit_records.py` audits every registered schema of both kinds (byte coverage for packed,
   tag coverage for tagged), and measures every `PAD` span on every record a table walk
   reaches, headers included. A registered record no walk reaches is listed as "not
   measured": that is either a table missing its `header=` or a record read some other way,
   and both are bugs. `audit_records.py --map` prints both.
6. **Test it** -- extent and coverage on every save, plus ground truth for what you read
   (`tests/test_rule_files.py`: 3F Superliga has 12 teams).

`tests/test_layouts.py` checks every registered schema of both kinds is sound, and the
`TaggedTableDef` engine's strictness, with no save. `audit_records.py <save>`,
`tests/test_comp_rules.py` and `tests/test_rule_files.py` fail on an undeclared tag.

---

## Part 3 — the checks, and what each one can actually tell you

| command | what it establishes | needs a save? |
|---|---|---|
| `tests/test_layouts.py` | every declared layout is internally sound — covered, non-overlapping, widths match kinds; every tagged schema declares each tag once | no |
| `scripts/audit/audit_records.py` | **STRIDE / COVERAGE / EXTENT / PADDING** against a real save | yes |
| `scripts/audit/audit_records.py --map` | the generated per-byte record documentation | yes |
| `scripts/audit/audit_table_headers.py --confirm` | declared count == records read, for every framed table | yes |
| `tests/assert_identical.py` | the extract still produces the same *bytes* | yes, 4 |
| `scripts/audit/audit_coverage.py` | whole-file byte accounting in tiers | yes |

**Before you call a record decoded, prove the EXTENT, not just the fields.** Ground truth on
the fields you read says nothing about the fields you did not. Both of this project's worst
decoding bugs passed every check that existed at the time:

- **STRIDE** — the modal gap between consecutive records *is* the stride you claim, and the
  rest are multiples of it (skipped records, not noise).
- **COVERAGE** — every byte in `[0, span)` is named or declared `UNKNOWN`.
- **EXTENT** — a keyed table is dense from id 0. A gap means the walk dropped a row; an
  overshoot means it invented one.
- **PADDING** — every span declared `PAD` reads the same bytes on every record a table walk
  reads (`core.record_instances`). `PAD` means filler; an undecoded span that varies is data
  and is declared `UNKNOWN` with kind `RAW`. The first run of this check found 35 `PAD`
  spans that were data, besides two bytes of every career-history row.

`audit_coverage.py`'s tiers are worth reading as a *ranking of how much you actually know*:
**MEASURED** (read record by record) > **AUDITED** (candidates enumerated) > **DECLARED**
(inside a `regions.py` window). A window-bounded scraper can only ever claim DECLARED, so
retiring a window in favour of a structural locator shows up directly as DECLARED falling and
MEASURED rising. If only one of those moves, the window did not really go away.

**Bytes, not values, for `assert_identical.py`.** `extract.py`'s `dump()` passes no
`sort_keys`, so **key order is part of the output**, and `load_duckdb.py` reads some of these
files positionally. A reader that emits the same values in a different order writes a different
file, and that is the failure a generic reader introduces most easily. It is caught on purpose.

---

## Part 4 — when FMM26 arrives

This is the payoff, and it is the reason the layouts are data rather than code.

[`agent-context/fmm-editor-record-comparison.md`](agent-context/fmm-editor-record-comparison.md)
is a field-by-field map of our parsers against the FMM26 database layouts published in
`nyongrand/fmm-editor`. **Read it before decoding any new field — it names the record you are
in.** The known divergences are documented there; the one worth internalising is that FMM22's
`NationalCaps`/`NationalGoals` are `u8` where FMM26 has `i16`, which shifts everything from
+40 onward two bytes earlier in our file. That shift is what makes the *rest* of the record
land on offsets we had already verified independently — which is the check that the alignment
is right, not a fudge to make it fit.

So the porting story is: **a layout change, validated by `tests/test_layouts.py` with no save
file at all, then `audit_records.py` against one real save.** The locators are the part that
will need real work, because they depend on file structure rather than record structure — and
Part 1 is what tells you which kind of locator you are re-deriving.

---

## The method, when you are adding something new

Region-first, then structural. This order has repeatedly turned multi-hour hunts into quick
finds, and every step of it exists because skipping it cost someone a day:

0. **Profile by block entropy** — `scripts/audit/entropy_profile.py`. Above 7.9 bits/byte is
   compressed and no stride search will bite. **Never rank a region by printable fraction.**
1. **Map the file into filler-delimited sections** — `scripts/map_regions.py`. Cross-check
   `fmparser/regions.py`, whose windows are Bucaspor-tuned and often wrong elsewhere.
2. **Find records structurally, never by absolute offset** — an embedded key plus a validating
   signature, every hit validated against the info spine.
3. **Identify an unknown field with ground truth + contrast** — read real values off a
   screenshot, then find the offset that matches per player, *or* the offset that is constant
   within a group and differs between groups (how contract expiry fell: 6/2022 players vs
   6/2023 players). **Money and dates display ROUNDED** — value `1923` shows as "£2K" — so
   search a ±few-% band, never the exact number.
4. **When value-matching fails everywhere, DIFF TWO SAVES.** The definitive tool, and the only
   one that finds fields not stored adjacent to a player id.
5. **Bound the table by its own invariant, never a tuned constant** — then declare the layout
   in the same commit you add the field to the parser.

Encodings cheat-sheet: money = raw currency shown rounded; dates = `[day-of-year u16][year
u16]`; seasons coded `1971 + n`; 4-byte tags are stored **reversed**; string length prefixes
are **u32**.
