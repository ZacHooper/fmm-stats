# fmparser — how to develop the parser

Loaded when working under `fmparser/`. What the parser is, for a person: [`README.md`](README.md).
This file is how to change it: the feedback loop, how a table is found, how a record is read,
and the method for decoding something new. The reference lives elsewhere:

- **one doc per table**, [`docs/parser/`](../docs/parser/): layout, evidence from an in-game
  screen, quirks, output. Read the table's doc before changing its module.
- **the whole file**, [`docs/parser/savefile-map.md`](../docs/parser/savefile-map.md): every
  table in file order, the gaps, the tables nothing reads yet, the archive at the tail.

The one idea the parser is organised around: **a locator tells you how to FIND a table, a
declared layout tells you how to READ its records.** The two fail differently and are tested
differently; keep them apart.

## The feedback loop

Two commands, both cheap:
```bash
uv run python tests/run_tests.py            # the suite, in parallel, ~20 s; exit 2 means NOTHING ran
                                            # (--store adds test_fmq, over the published copy)
uv run python tests/assert_identical.py     # 4 saves x every extract file, per-file SHA-256
```
`assert_identical.py` is the **acceptance gate**: a restructuring commit must leave the
extracted JSON byte-identical, and `extract.py` dumps with no `sort_keys`, so **key order is
part of the test** (`load_duckdb.py` reads some files positionally). When a change SHOULD alter
output, re-record in the same commit and say why:
`tests/assert_identical.py --record --note '<why>'`. The baseline is gitignored (`.oracle/`)
because it is keyed to your local saves. A gate that has never failed is not evidence: break
something on purpose once.

**A comment-only change must leave the extract byte-identical.** Diff `output/<label>/` before
and after.

**Evidence tests** (`tests/test_*_evidence.py` with `tests/fixtures/*_evidence.json`) pin what
an in-game screen shows to the raw bytes and to the parsed field. Pin bytes, not only parsed
values: a list checked only through the parser is the parser checking itself.

What each check can tell you:

| command | establishes | needs a save |
|---|---|---|
| `tests/test_layouts.py` | every declared layout is sound: covered, non-overlapping, widths match kinds; every tagged schema declares each tag once | no |
| `scripts/audit/audit_records.py` | STRIDE / COVERAGE / EXTENT / PADDING of every registered record (below) | yes |
| `scripts/audit/audit_records.py --map` | the per-byte schema of every record, generated from the declarations: the record documentation that cannot go stale | yes |
| `scripts/audit/audit_table_headers.py --confirm` | each declared count against the table's own invariant, across `~/fm-saves` | yes |
| `scripts/audit/discover_tables.py` | count-framed fixed-width tables, found by `id == slot index` on every declared record | yes, slow |
| `scripts/audit/audit_coverage.py` | which bytes no table claims | yes |
| `scripts/audit/entropy_profile.py` | block entropy along the file | yes |
| `tests/assert_identical.py` | the extract's bytes are unchanged | yes, 4 |

## Finding a table: the locator shapes

Every table answers three questions, and the shapes are combinations of the answers:

| question | answers | in `core` |
|---|---|---|
| how do rows relate? | an array (fixed or variable stride), or a linked list (each row holds the next row's index) | `TableDef`, `TaggedTableDef`; `LinkedTableDef` |
| how is a row encoded? | packed (fields at offsets) or tagged (`[tag][01][type][value]` fields in any order) | `Record`, `TaggedRecord` |
| how is the start found and the end proved? | a declared count, a capacity, a terminator, a length chain, an archive member, a search by key | the locator each table supplies |

| shape | found by | bounded by | tables |
|---|---|---|---|
| **A. Count-framed** | a count in front of record 0; usually start at the previous table's end | `id == slot index` on every declared record, or the walk landing on the next frame | most: the reference half, rule files, club records, training, our matches |
| **B. Linked list** | its own pointers: an unmoved pair (row k → k+1) fixes the base | the forest check on every row (`core.forest`) | history |
| **C. Preallocated grid** | a residue class mod stride, or a template row | the grid's dense-from-0 invariant; the slot count is a bound, not a headcount | match slots, player progress, contracts, staff, the record blocks inside each club-records row |
| **D. Archive member** | the zstd archive's directory (`core/archive.py`) | the directory's lengths | fixtures, comp_stages, comp_honours, comp_rules |
| **E. Seeded chain** | a seed record, then each record's lengths landing on the next | the walk failing to parse, both ways | player lists, browse names |
| **F. Key search** | *N* copies of a keyed record; pick the live one | validation of every hit against the person table | none now |
| **G. Terminated array** | a marker or filler wall at the end | landing exactly on it | none now |

### A. Count-framed

```
ff ff ff ff ff ff ff ff   <- >= 8 bytes of 0xFF
5c 05 00 00               <- the count, flush against record 0 (u16 or u32: the table decides)
00 00 ...                 <- record 0, whose id reads 0
```

- **Start at the previous table's end** where one table follows another: skip the `0xFF`
  run, read the count (`tables/clubs.py`'s `after_frame`). The reference half is a chain of
  such blocks: player attributes → staff → coaches, scouts, physios → officials → round names →
  clubs → competitions → nations; stadiums → cities → awards; currencies → an 888-row list →
  languages; and the three name id-tables. No signature and no range is needed.
- **As a search, the frame is only a candidate generator**: `frem-2030-06-22` has 536,739
  runs of >= 8 `0xFF`. `core.find_framed_count` finds candidates; `id == slot index` on every
  declared record is what accepts one (`scripts/audit/discover_tables.py`).
- **Test for `>= 8` `0xFF`, never `== 8`**: the record in front can end in `0xFF` of its own
  (the currency table's run is 10).
- **The count's width is not guessable.** u16 in front of the string tables (competitions,
  nations, stadiums, cities, currencies, languages), u32 in front of the grids, clubs, round
  names and id-tables. Read both and let the walk decide.
- **Three kinds of number sit in front of a table.** A count equals the rows present
  (competitions 1,372). A per-career pool is fixed for a career and differs between careers
  (the history pool: 265,423 Frem, 295,648 Bucaspor). A capacity is the same across careers
  and larger than the use (`60,000` before the browse names, which hold 45,942; `65,000`
  before the [transfer band](../docs/parser/savefile-map.md#the-transfer-band)). Hold the
  number against a career's saves before calling it a count.
- **The career half counts too, without the sentinel**: a bare u8 in front of our matches, a
  u16 in front of club records, a u32 in front of training and the history pool. Look for a
  bare count when the data is the running game's.
- **Assert `read == declared`.** A walk that stops early returns a short table in which every
  row is right; only the declared count catches it.

> **Dead end:** a greedy walk over length-prefixed strings. An empty string (a language
> with no other name, a blank competition slot) is data, not a terminator, and the walk loses
> the rest of the table. A string table needs its record parser; the declared count then
> checks it for free.

> **Dead end:** keying a cross-save search on the offset. Every section drifts per save; the
> `(count, stride)` shape travels, the address doesn't.

### B. Linked list

Each row holds its chain's next row; `FFFFFFFF` ends a chain. `core.LinkedTableDef` reads
every row column-wise and checks `core.forest`: in-degree at most 1, no pointer out of the
pool, as many chain starts as ends, every row reached from a start (which is what catches a
cycle). Following a chain, and what its rows mean together, is the loader's job
(`load_duckdb.load_history`), not the parser's.

> **Quirk:** on a fresh save every row points at the next, so the pointer reads like a
> counter. Splitting at breaks in `+1` works there and nowhere else. If fields seem to belong
> to the neighbouring row, the row is framed wrong.

The locator must also refuse: break the pool on purpose and it returns nothing, not a
lookalike (a one-row frame is trivially a forest; the count must hold the pairs that named
the base).

### C. Preallocated grid

Ships full of empty rows and fills in place; some also grow. A day-one save is a real test
case: a walk that depends on rows existing finds nothing there. The slot count is stable
across a career (match slots: 3,975 Frem, 3,943 Bucaspor); a walk whose count changes
between saves of one career is wrong. A grid can sit inside a framed table: each club-records
row holds four blocks of 12 slots (`core.FixedList`), and walked from the count an empty slot
is just all-`FF`.

> **Dead end:** a tuned bound. A miss counter or a plausibility window makes the row count a
> function of the constant, and every row it does read is right. Bound it by `id == slot index`.

### D. Archive member

The save's last ~1.3 MB is a zstd archive; its directory is authoritative
([the archive](../docs/parser/savefile-map.md#the-archive)). It is current state:
`fix_man.dat` is a two-calendar-year window, so it enriches its snapshot and never supplies
history.

### E. Seeded chain

No count and no index; a record's lengths land exactly on the next record. The seed is only
the first place the signature matched, not the first record, so the walk must also go
backward until it can't, or it silently drops the table's first rows. The player lists walk both ways from an unused list
(`tables/player_lists.py`), and must come out as 66 lists on every save.

### F and G

No table uses them now. A key search fails by picking the wrong copy, with values right for
another point in time; a terminated array by drift.

> **Dead end:** a constant fallback. A locator that answers with a hand-tuned window when it
> finds nothing returns a plausible short table instead of an error, and every window tuned
> on one career was wrong for the other. A locator raises or reports; an empty table is
> correct only where an independent table says so (the match table after the rollover,
> `matches.check_against_fixtures`).

## Reading a record

> **One declarative layout per record is the schema.** The parser reads from it; the audit
> checks against it.

| module | holds |
|---|---|
| `core/primitives.py` | byte readers, `(buffer, offset) -> value`: `u8 … f32`, `ymd`, `tag4`, `pstring` (u32 length prefix) |
| `core/types.py` | how a value is encoded: the packed kinds (`U8` … `PAD`, `UNKNOWN`), `PString`, `CountedList`, `FixedList`, `Struct`, and the tagged reader `read_tree` |
| `core/schema.py` | what a record means: `Record` + `Field` (packed), `TaggedRecord` + `Tag` (tagged) |
| `core/table.py` | where rows are and how to walk them: `TableDef`, `TaggedTableDef`, `LinkedTableDef`; `record_instances` lists every record a walk reads |

- **Offsets are relative to the record start**, never to the landmark the locator found. Where
  a record is found by an inner marker, declare in record coordinates and call
  `Record.read_at_anchor(mm, marker)`.
- **Declared `UNKNOWN` is not undeclared.** A byte you can't name yet is covered and visible;
  a byte that is neither is one you are stepping over by accident (the player record read
  right for years while missing its last 13 bytes). `PAD` means filler: the PADDING audit
  checks every `PAD` span reads the same on every record, and an undecoded span that varies
  is `UNKNOWN` with kind `RAW`.
- **Not declarable, on purpose:** meaning (sentinels to None, banding, modelled values);
  plausibility windows, which are locating evidence about one table; and money, whose
  convention belongs to the record, not the width: wage units × 10 a week
  ([contracts](../docs/parser/contracts.md)), fees in £000s ([history](../docs/parser/history.md)),
  an f32 of pounds ([club_records](../docs/parser/club_records.md)), a u32 of pounds (the
  transfer band). A shared `money()` would be wrong by a factor of 520 and still plausible.
- **Packed and tagged are one system.** Each `core` layer holds both, so a tagged table (the
  rule files, each `comp_<uid>.dat`) is hooked up like a packed one. A tagged row that
  doesn't read to its declared field count raises `TaggedTableError`, never a shorter row.

**Hooking up a new table:**

1. **Find it**: entropy profile, then the count in front of record 0. A packed frame is
   `[>= 8 × FF][count]`; a tagged block's is `[u32 n][tag 01 type]`.
2. **Write the locator**, returning `(base, count)` (or several runs), or for a tagged table
   `[(offset of first field, n)]`. Declare a per-row assertion as the table's `invariant`, so
   the walk stops at the first row that fails it. For a region of tagged blocks,
   `core.scan_tagged_blocks(mm, lo, hi)` is the whole locator; keep the blocks that are yours.
3. **Declare the record.** Packed: a `Field` per byte range; a variable-length row is a
   sequence of segments (`Record`, `PString`, `CountedList`, `FixedList` of a `Record` or a
   `Struct`; `tables/nations.py`, `tables/matches.py`). Tagged: a `Tag` per tag you read and
   `unread=` for the rest, built from `TABLE.coverage(mm)`'s `undeclared` over every save.
4. **Define the table** (`TableDef` / `TaggedTableDef`), register it in `tables/__init__.py`'s
   `TABLES`, and give a record stored in front of the rows as the table's `header=`. An
   archive table names its member (`member="fix_man.dat"`, or `"comp_<uid>.dat"`).
5. **Audit it**: nothing to add. Every `Record` and `TaggedRecord` registers itself and
   `audit_records.py` audits them all; a registered record no walk reaches is listed as "not
   measured", which is a bug either way.
6. **Test it**: extent and coverage on every save, an evidence test for what you read, and an
   `extract.py` step.

**Another game's layouts.** `nyongrand/fmm-editor` (C#, `FMMLibrary/`) reads the FMM26
pre-game database field by field, and the save embeds the same layouts, so once a record is
located its field order is no longer guesswork. It is not a drop-in: it reads standalone
`.dat` files front to back, and our records still have to be located. Clone it when needed
(`git clone --depth 1 https://github.com/nyongrand/fmm-editor`). Each table doc says where
FMM22 departs from it; the one to remember is that FMM22's international caps and goals are
u8 where FMM26 has i16, so the person record from +40 on sits two bytes earlier than
fmm-editor says.

## Reverse-engineering method: region first, then structural

When locating a **new field**, do not start by guessing byte offsets. In this order:

0. **Profile by block entropy**: `uv run python scripts/audit/entropy_profile.py <save.fms>`.
   Filler reads ~1.4 bits/byte, records 3–6, dense records and strings 6–7.5, and **> 7.9 is
   compressed**: no stride search will bite there. Never rank a region by printable fraction
   (uniform random bytes are 37.1% printable).
1. **Audit coverage**: `uv run python scripts/audit/audit_coverage.py [save.fms]` shows which
   bytes no table claims. Cross-check against the [savefile map](../docs/parser/savefile-map.md).
2. **Find records structurally, never by absolute offset.** Everything drifts per save and per
   career. Locate a record by an embedded key (tid / uid / sid) plus a validating signature, and
   validate every hit against a table you trust.
3. **Identify a field with ground truth and contrast.** Read real values off an in-game screen
   for several rows, then find the offset whose value matches, or the offset that is constant
   within a group and differs between groups. **Money and dates are displayed rounded**: search
   a ±few-% band, not the exact number.
4. **When value-matching fails, diff two saves**: find the field that changed iff the value did.
5. **A monotonic-looking u32 may be a pointer.** Big tables are often linked lists: the field
   holds the next row's index, `FFFFFFFF` ends a chain. Tell a pointer from a counter with the
   **in-degree test**: max in-degree 1 and as many in-degree-0 rows as `FFFFFFFF` rows. If
   fields look like they belong to the next or previous row, suspect the **framing** before
   writing a reading rule, and confirm a whole record against an in-game TOTAL line.
6. **If a table holds no id, look for the pointer running the other way.** Search the file for
   the target's row index or offset as a u32; one hit outside the table is the link (how the
   [history](../docs/parser/history.md) pool joins the attribute record).
7. **Look in front of record 0: the save declares its own table sizes**
   ([shape A](#a-count-framed)). Compare each declared count with what the parser reads.
8. **Run the cross-career check early.** Bucaspor (Turkey) is the only generalisation test the
   parser has; an offset from one Danish save is a hypothesis until it holds there too.

### Before you call a record decoded: prove the extent, not just the fields

Ground truth on the fields you read says nothing about the fields you didn't. Run
**`uv run python scripts/audit/audit_records.py [save.fms]`**:

- **STRIDE**: the modal gap between records is the stride you claim, the rest multiples of it.
- **COVERAGE**: every byte of the stride is a named field or a declared `UNKNOWN` in the
  record's `Record` declaration. A byte that is neither is one you are stepping over by
  accident.
- **EXTENT**: a keyed table is dense from id 0. A gap means the walk dropped a row; an
  overshoot means it invented one.
- **PADDING**: every `PAD` span reads the same bytes on every record a walk reaches.

**When an in-game screen disagrees with the parse, suspect the parse.** One disagreement is a
lead, not noise: chase it before explaining it away. Read the screenshot itself, not notes
about it, and prefer a screen with a TOTAL line, which catches a dropped or extra row.

**A gate true for only some records loses the rest without an error.** An equality test
against a sentinel, or a range literal, where a structural check belongs makes the output
smaller, not wrong: scanning for the "no nickname" `ffffffff` missed everyone with a nickname.
A range in this parser is a claim about the data; measure it on both careers.

**Never validate a field by joining on it.** A check that matches rows *on* the date and then
reports "282 of 285 agree on date" cannot fail when every date is uniformly wrong. Join on
something else (an id, a score) and let the field under test come out as output.

**Adjacent bytes are not one field until you show they are.** Non-zero neighbours argue against
padding, never against a narrow field. A field's name is a claim too: check what the screen
calls it.

**Unknown bytes next to a known field are worth a look on every screen.** Corners, offsides,
the sending-off minute, the referee and a competition's holders all turned up that way.

Rules that follow:
- **Bound a walk by the table's own invariant**, never a tuned constant: a miss counter or a
  plausibility window makes the row count a function of the constant.
- **Carry what you cannot name, then go and name it**, from an upstream definition or repeated
  ground truth, never a guess.
- **Before calling something a bug, ask whether it is a choice.** Record a real data bug as a
  callout in the table's doc and a TODO entry, and fix it in its own change.
