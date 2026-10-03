# fmparser — reverse-engineering the save format

Loaded when working under `fmparser/`. Read this before changing the parser or hunting a new field.

## How the parser works — [`docs/parser-architecture.md`](docs/parser-architecture.md)
**The one doc to read before changing `fmparser/`.** It carries the idea the parser is
organised around — *a locator shape tells you how to FIND a record, a declared layout tells
you how to READ it* — as the **seven-shape locator table** (count-framed / linked list /
preallocated grid / archive member / seeded chain / key search / terminated array), one section per shape with
how you find it, the invariant that bounds it, and **how it fails**. Then the declared-layout
rule (`core/types.py` / `core/schema.py` / `core/table.py`), what is deliberately *not* declarable,
what each audit script can actually tell you, and what porting to FMM26 will involve.
The method section below is the field guide; that doc is the map.

**Two commands are the feedback loop for any parser change, and they are cheap:**
```bash
uv run python tests/run_tests.py            # the suite, in parallel, ~20 s; exit 2 means NOTHING ran
                                            # (--store adds test_fmq, over the published copy)
uv run python tests/assert_identical.py   # 4 saves x 23 files, per-file SHA-256, ~35s
```
`assert_identical.py` is the **acceptance gate**: a restructuring commit must leave the
extracted JSON byte-identical, and `extract.py` dumps with no `sort_keys`, so **key order is
part of the test** — a reader that returns the right values in the wrong order fails, which is
correct, because `load_duckdb.py` reads some files positionally. When a change SHOULD alter
output, re-record in the same commit and say why:
`tests/assert_identical.py --record --note '<why>'`. The baseline is gitignored (`.oracle/`)
because it is keyed to your local saves. Before trusting a green run, remember its own rule: a
gate that has never failed is not evidence — break something on purpose once.

## Reverse-engineering method: ALWAYS region-first, then structural
When locating a **new field** in the save, do NOT start by guessing byte offsets. Follow this order —
it has repeatedly turned multi-hour hunts into quick finds. (Which *kind* of locator you are
building is [`docs/parser-architecture.md`](docs/parser-architecture.md) Part 1; this is how
you find it in the first place.)

0. **Profile it by BLOCK ENTROPY first** — `uv run python scripts/audit/entropy_profile.py <save.fms>`.
   Filler reads ~1.4 bits/byte, ordinary records 3–6, dense records/strings 6–7.5, and **>7.9 is
   COMPRESSED** — no stride search will ever bite there. This is not optional book-keeping: the
   file's last 1.3 MB was ranked the best remaining target for being "25.8% printable" when
   uniform random bytes are **37.1% printable by construction**, and it cost four hunts. Never
   rank an unknown region by printable fraction.
1. **Audit coverage and unmapped sections first** — `uv run python scripts/audit/audit_coverage.py [save.fms]`.
   The save is audited by declared table bounds and split by long runs of `00`/`ff` filler; this
   shows you *where* to look and exposes regions we haven't mapped. Cross-check against `docs/savefile-map.md`.
2. **Find records structurally, never by absolute offset** — every window in `regions.py` **drifts** per
   save and per career (e.g. Frem's contract-expiry records sit at ~29–31M, nowhere near the Bucaspor
   `CONTRACT_LO=54M`). Locate a record by an embedded key (tid / uid / sid) plus a validating signature
   (a marker byte, a plausible year, an in-range value) and **validate every hit against the info spine**,
   exactly like the scrapers in `fmparser/staging.py`.
3. **Identify an unknown field with ground truth + contrast** — read the real values off an in-game
   screenshot for several players, then either (a) find the offset whose per-player value matches, or
   (b) find the offset that is *constant within a group and differs between groups* (how contract expiry
   was cracked: 6/2022 players vs 6/2023 players). **Money and dates are DISPLAYED ROUNDED** (value `1923`
   shows as "£2K"), so search a ±few-% band, not the exact number.
4. **When value-matching fails everywhere, DIFF TWO SAVES** — the definitive tool. Take two snapshots
   where the value changed for some players and find the field that changed iff the value did. Fields not
   stored adjacent to a player id (wages appear to live in a positional finance table) only fall to this.
5. **A monotonic-looking `u32` column may be a POINTER, not a counter.** Big tables here are
   **linked lists**, not arrays: the field holds the *next row's index*, with `FFFFFFFF` = end of
   chain. On a fresh save the rows are contiguous so row `k` holds `k+1` and the field is
   indistinguishable from a counter — the two readings only diverge once the game starts appending
   into recycled slots. Tell them apart with the **in-degree test**: build the pointer graph and
   check `max in-degree == 1` and `#(in-degree-0 rows) == #(FFFFFFFF rows)`. If that holds it is a
   forest of chains, record starts are the in-degree-0 rows, and you need no delimiter heuristics
   at all. If fields look like they belong to the NEXT or PREVIOUS row, suspect the FRAMING before
   writing a reading rule: career history was read for years as "season+stats from row `k-1`,
   club+fee from row `k`", and the truth was that the row starts 8 bytes earlier —
   `[stats][club, fee, next]`, one complete season line per record. Always confirm a whole
   record against ground truth — an in-game TOTAL line is the cheapest check, since an
   off-by-one either double-counts a row or drops one.
6. **If a table has no id in it, look for the pointer running the OTHER way.** Career history holds
   no tid/sid/uid anywhere; the *attribute* record points at it (`u32 @ P-38`). Before concluding a
   join is unsolvable, search the file for the target's row index / offset as a u32 — one hit outside
   the table is the link. See `docs/IDS.md`.
7. **LOOK IN FRONT OF RECORD 0 — the save declares its own table sizes.** The framing is
   `[8 bytes of 0xFF][record count][record 0]`, and **20 tables use it**, exactly (u16 for the
   variable-length string-record tables, u32 for the fixed-width grids). Comparing each declared
   count against what the parser reads found five defects in tables that passed every check we
   had, two of them losing real records on every save ever built. Test for a run of `>= 8` FF,
   never `== 8` (the preceding record can end in FF). It also works as a SEARCH strategy, but
   only with a real validator behind it — the sentinel alone occurs 566,078 times in one save;
   derive a candidate stride from the count and then require `id == slot index` on every
   declared record. Read [`docs/table-framing.md`](docs/table-framing.md) before walking any new
   table, and note what it says you CANNOT find that way.
8. **Encodings cheat-sheet:** money = raw currency (`2000` = £2K) but shown rounded; dates =
   `[day-of-year u16][year u16]` (see DOB in `staging.scrape_players`); seasons coded `1971 + n`.
   **Contract-detail record** (`staging.scrape_contracts`, section ~16–40M, `[tid u32][0x01][wage
   u16][6×00][expiry day-of-year u16][expiry year u16]`): **wage £/yr = `u16@+5` × ~520** (validated
   £15.5K–£17.75M, ±2%; the squad status is on the training row, `tables/training.py`), and
   **expiry = full date @+13** (some Danish deals expire 31 Dec, not 30 Jun — keep the day, not just
   the year).

### Before you call a record decoded: prove the EXTENT, not just the fields
Ground truth on the fields you read says nothing about the fields you didn't. The player record
decoded perfectly for four years while missing its last 13 bytes; the city walk had Parken and
Copenhagen exact while dropping 31 real cities and inventing 3. Both passed every check we had.
Run **`uv run python scripts/audit/audit_records.py [save.fms]`**:

- **STRIDE** — the modal gap between consecutive records IS the stride you claim, and the rest
  are multiples of it (skipped records, not noise). This is what settled the staff record at 39
  bytes and left Style nowhere to hide.
- **COVERAGE** — every byte in `[0, stride)` is a named field or declared `UNKNOWN` in the
  record's `Record` declaration (the audit reads every registered `Record`, so there is no
  second list to update). **A byte that is neither is a byte you are stepping over by
  accident.**
- **EXTENT** — a keyed table is dense from id 0. A gap means the walk dropped a row; an
  overshoot means it invented one.

**Never validate a field by JOINING ON IT.** A check that matches candidate rows *on* the
date and then reports "282 of 285 agree on date" cannot fail when every date is uniformly
wrong — a shift makes fewer rows join, and a high agreement rate among the rows that did join
still reads as a pass. That is exactly how `fix_man`'s dates shipped a day late: the day-of-
year is 1-indexed and `ymd_from` is 0-indexed, and the validation was measuring agreement
among rows it had already filtered for agreement. **Join on something else (an id, a score)
and let the field under test come out as OUTPUT**; re-measured that way it was 51/51 and 60/60
rows needing exactly −1, across both careers, in one run.

**Adjacent bytes are not one field until you show they are.** This has now cost two decodes.
The staff record was measured against the PLAYER record's 78-byte stride, so `id2` read 0, 2,
4, … and the write-up concluded "multi-segment, a grid walk is provably impossible" — it is a
dense 39-byte array. The fixture record's `+78..81` were read as one u32, which offered only
"u8 plus padding" or "u32", and both look wrong — `+78` is a round counter and `+79`/`+80`/
`+81` are three separate small columns. In both cases every measurement was correct and the
grouping was the error. Non-zero neighbours argue against PADDING, never against a narrow
field.

Two rules follow, and the recent bugs all break them:
- **Bound a table walk by the table's own invariant, never a tuned constant.** A miss counter or
  a plausibility window makes the row count a function of the constant. The city table's real
  invariant is `id == slot index`.
- **One declarative layout per record is the schema.** `staging.INFO_LAYOUT` is a table of
  `(offset, width, name, kind)` with `UNKNOWN` rows as first-class entries: `_decode_info` reads
  FROM it and `scripts/audit/audit_records.py` checks AGAINST it, so the parser and its audit cannot
  drift. **`uv run python scripts/audit/audit_records.py --map` prints the per-byte schema** — that is
  the record documentation, generated rather than retyped, so it cannot go stale.
- **Bound a record by its own invariant, not a plausibility window.** The person table was
  once read by a sentinel sweep that produced 77 "empty slots" with joined dates in 1290 and
  2570 — misaligned reads, not data. Walked from its count frame with `tid == slot index`, all
  32,966 records are real people and none needs a date window or a range test.
- **Carry what you cannot name — then go and name it.** A byte identified as an attribute but
  not labelled is still data, so both records' hidden attributes are carried. The PLAYER nine
  are now NAMED from `nyongrand/fmm-editor`'s `Player.cs` (`jumping`, `consistency`,
  `big_match`, `injury_prone`, `versatility`, `set_pieces`, `penalty`, `work_rate`, `flair`) —
  the order is confirmed by seven independently-verified anchors plus the fact that the 18
  slots FMM22 fills are exactly the ability-independent attributes and the 16 it leaves are
  exactly the technical/GK values it computes from CA. The STAFF six stay `hidden_s*`, named by
  OFFSET, because fmm-editor has **no `Staff.cs`** — it stops at the `Unknown6b` link that
  leads there, so there is no upstream order to borrow and no ground truth of our own.
  Nothing derives from any of the fifteen and none is surfaced. Guessing a name is how `-140`
  became a Style candidate; sourcing one and checking it twice is not guessing.
