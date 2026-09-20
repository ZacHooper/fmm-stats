# How the parser works

**Read this first if you are changing `fmparser/`.** Not the history of how the save was
decoded — that is spread across `docs/` by subsystem — but the shape the parser has, and the
one idea it is organised around:

> **A locator shape tells you how to FIND a record. A declared layout tells you how to READ
> it. Everything else is small.**

Those two halves fail differently, are tested differently, and are the reason the same bug
kept recurring in different modules. Keeping them apart is what this document is for.

---

## Part 1 — the six locator shapes

A 64 MB `.fms` is not one format. It is several, and the boundary between them is structural,
not thematic: a 20-byte fixed grid of cities and a 20-byte fixed grid of match slots are the
same *kind of thing* to a parser, while the competition table sitting between them is not.

Four **regimes** describe the file (see [`savefile-map.md`](savefile-map.md)). Six **shapes**
describe the code, because a survey of every locator in `fmparser/` found seven that do not
fit the four — enough that a four-walker design would have had to special-case its way back to
six.

| shape | how you find it | the validator that bounds it | used by |
|---|---|---|---|
| **A. Count-framed** | `[≥8 × 0xFF][count][record 0]` — the table declares its own size | `id == slot index`, on every declared record | competition table; ~20 tables carry the frame ([`table-framing.md`](table-framing.md)) |
| **B. Pointer / delimiter / marker** | career data; there is never a count | a chain that lands exactly on the next record, or a filler wall | history slab, our matches, squad snapshot, tagged region, club records |
| **C. Preallocated grid** | ships full of empty-sentinel rows and grows; the slot count is a *bound*, not a headcount | a residue class mod stride, plus the grid's own dense-from-0 invariant | match slots (3,975), club records (25,368 empty rows on day one), contract grid (32,961 × 83 B) |
| **D. Archive member** | zstd container with a directory at the tail | the directory names the member and its length | `fix_man`, `stadium`, `comp_<id>.dat` ×147 |
| **E. Seeded chain** | variable-length records, **no count and no index** | this record's length field lands exactly on the next one, `min_chain` times | stadiums, languages, currencies |
| **F. Key search, no table** | find *N* copies of a record by key bytes; disambiguate | the info spine, or recency | contract status, `attr_record`, staff attributes, injuries |

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

**How you find it.** `records.find_framed_count(mm, start, hi)`. Then you *must* validate: the
sentinel alone occurs **566,078 times** in one save, so the frame is a candidate generator and
nothing else. The validator is that the declared records satisfy `id == slot index` —
`reference._walk_comp_table` asserts `cid == i` on every slot and raises `CompTableError` with
the slot number if it ever fails.

**Two details that are measured, not defensive:**

- Test for a run of **`>= 8`** sentinel bytes, never `== 8`. The record *preceding* the frame
  can itself end in `0xFF`, and an exact-length test misses those frames.
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

### B. Pointer / delimiter / marker — the career half

Career data has no counts. What it has instead:

**Linked lists.** A monotonic-looking `u32` column is often a **next-row pointer**, not a
counter, with `FFFFFFFF` ending the chain. On a fresh save the rows are contiguous, so row `k`
holds `k+1` and the two readings are indistinguishable — they only diverge once the game starts
appending into recycled slots. Tell them apart with the **in-degree test**: build the pointer
graph and check `max in-degree == 1` and `#(in-degree-0 rows) == #(FFFFFFFF rows)`. If that
holds, it is a forest of chains, record starts are the in-degree-0 rows, and no delimiter
heuristic is needed. This is `history.py`; the detail is in
[`agent-context/history-chain-pointers.md`](agent-context/history-chain-pointers.md).

**Filler walls.** Long runs of `00`/`ff` separate sections cleanly, which is what
`scripts/map_regions.py` exploits and how `clubrecords.region()` bounds itself: start at the
end of the history slab (a structure that knows its own extent), end at the first 4 KB run of
zeros. That change alone took the club-records scan from 26.4 s to 2.3 s, byte-identically,
because it stopped scanning 60 MB to find records that live in 0.5 MB.

**Markers.** `attributes.CLUB_MARKER` locates the squad snapshot; `matches.find_match_region`
finds our own games.

**How it fails.** *Drift.* Every window in `regions.py` was tuned on one career and is wrong
for the other — Frem's contract-expiry records sit at ~29–31 M, nowhere near the Bucaspor
`CONTRACT_LO = 54 M`. A constant fallback is worse than no fallback, because it produces a
plausible short answer instead of an error. Locate by an embedded key plus a validating
signature, and validate every hit against the info spine.

---

### C. Preallocated grid — the shape that surprised us

These tables **ship full**. On a day-one save, the club-records region already contains 25,368
twenty-one-byte rows of empty sentinels, and the stride-70 pool is 100% empty — falling to
92.5% by 2026 as the career fills it in. They also **grow**, by exact multiples of the record
size. Preallocation and append are not alternatives here; the file does both.

**Consequences that matter:**

- **A row count is not a headcount.** The slot count is stable across every save of a career
  (match slots: 3,975 for Frem, 3,943 for Bucaspor) whether the career is one day or five years
  old. A walk that returns a *different* count between saves of one career is wrong, and
  `tests/test_match_slots.py` asserts exactly that.
- **Day one is a real test case, not an edge case.** A walk that depends on rows existing
  finds nothing on `frem-2021-07-01` and everything on `frem-2026-06-11`. That save is in
  `scripts/assert_identical.py`'s four for this reason.

**How you find one.** By a **residue class mod stride**: take a constant that appears in every
populated row, collect its offsets, and find the residue class mod the stride that holds the
longest contiguous run. `matchslots.locate` does this. Note the discipline in its signature —
`bridge_slots` spans the 7% of slots carrying no trailer, and it bounds a **gap**, not the
table, so widening it cannot change the row count.

**How it fails.** A tuned bound silently becomes the answer. A miss counter or a plausibility
window makes the row count a function of the constant rather than of the table — which is how
the city walk dropped 31 real cities and invented 3 while reading Parken and Copenhagen
perfectly. Its real invariant is `id == slot index`, and once that was the bound, the tuned
number was not needed anywhere.

---

### D. Archive member — the last ~1.3 MB

The tail of the save is a **zstd archive** (`sicomps`): 159 named members, 6.6 MB decompressed,
with a directory. Its `fix_man.dat` is the world fixture list — 26,954 rows across 1,751 clubs.

> **Not on this branch yet.** The reader (`fmparser/archive.py`) and its two documents,
> `save-archive.md` and `archive-coverage.md`, arrive with the archive PR. The shape is
> described here because it is part of the file whether or not we have merged the code that
> reads it, and Phase 4 of the refactor wires `fix_man` into `extract.py`.

**The rule that found it, which generalises past this shape:** **rank an unknown region by
BLOCK ENTROPY, never by printable fraction.** This region was ranked the best remaining target
for being "25.8% printable" when uniform random bytes are **37.1% printable by construction** —
it was *less* printable than noise. Four hunts died there before anyone measured entropy.
`scripts/entropy_profile.py` does it: filler reads ~1.4 bits/byte, ordinary records 3–6, dense
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

---

### F. Key search, no table

Sometimes there is no table concept to find. You search the file for *N* copies of a record
keyed on a tid/uid/sid and then have to decide which copy is the live one.

- `attributes.attr_record` disambiguates **by recency** — reserve players otherwise read stale
  attributes, and a frozen row is the tell
  ([`agent-context/reserve-marker-stale-attrs.md`](agent-context/reserve-marker-stale-attrs.md)).
- `staff.scrape_staff_attributes` cannot use a grid walk at all: the staff records are
  **multi-segment**, so a stride walk is provably impossible and each is found by its `id2`
  link from the person record.

**How it fails.** By picking the wrong copy, which produces *correct-looking* values for the
wrong point in time. Validate every hit against the info spine, exactly as the scrapers in
`staging.py` do.

### Two non-conformers that are defects, not shapes

- `lightresults` locates and walks the **same region** `clubrecords` owns, with its own
  independent locator, and `extract.py` calls both. One region, two locators.
- `staging.scrape_attributes` and `scrape_contracts` have **no locator at all** — just a
  window constant from `regions.py`.

Both are Phase 3 of the refactor. Do not model them.

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
| `fmparser/primitives.py` | the byte readers — `u8/u16/u32/i16/i32/f32`, `ymd`, `pstring`, `tag4`. Pure `(buffer, offset) -> value`. |
| `fmparser/schema.py` | `Field(offset, width, name, kind, group, alias, note)`, `Record(name, span, fields, stride, anchor)`, `UNKNOWN`, and `validate()`. |
| `fmparser/records.py` | `read / read_at_anchor / read_into / read_fields / read_group / walk / columns`. **No locating.** |

Run **`uv run python tests/test_layouts.py`** — no save file, milliseconds — and
**`uv run python scripts/audit_records.py --map`**, which prints the per-byte schema. *That
printout is the record documentation.* It is generated rather than retyped, so it cannot go
stale, which is the only reason to trust it.

### Offsets are relative to the RECORD START

Always — never to whatever internal landmark the locator happened to find. The player
attribute record is *found* by its SID marker and this project has always described its fields
relative to that marker (`P-38`, `P+28`) while the record itself begins 42 bytes earlier. Both
spellings are legitimate and mixing them is a bug the repo has already had. `Record.anchor`
reconciles them: declare in record coordinates, and call
`records.read_at_anchor(mm, rec, marker_offset)`, which does the subtraction exactly once.

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

**Meaning.** Sentinel collapsing (`uid == 0` blanks the whole person block — 77 records with
joined dates in 1290 and 2570), banding (a hidden byte → Attacking / Normal / Defensive),
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

---

## Part 3 — the checks, and what each one can actually tell you

| command | what it establishes | needs a save? |
|---|---|---|
| `tests/test_layouts.py` | every declared layout is internally sound — covered, non-overlapping, widths match kinds | no |
| `scripts/audit_records.py` | **STRIDE / COVERAGE / EXTENT** against a real save | yes |
| `scripts/audit_records.py --map` | the generated per-byte record documentation | yes |
| `scripts/audit_table_headers.py --confirm` | declared count == records read, for every framed table | yes |
| `scripts/assert_identical.py` | the extract still produces the same *bytes* | yes, 4 |
| `scripts/audit_coverage.py` | whole-file byte accounting in tiers | yes |

**Before you call a record decoded, prove the EXTENT, not just the fields.** Ground truth on
the fields you read says nothing about the fields you did not. Both of this project's worst
decoding bugs passed every check that existed at the time:

- **STRIDE** — the modal gap between consecutive records *is* the stride you claim, and the
  rest are multiples of it (skipped records, not noise).
- **COVERAGE** — every byte in `[0, span)` is named or declared `PAD`.
- **EXTENT** — a keyed table is dense from id 0. A gap means the walk dropped a row; an
  overshoot means it invented one.

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

0. **Profile by block entropy** — `scripts/entropy_profile.py`. Above 7.9 bits/byte is
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
