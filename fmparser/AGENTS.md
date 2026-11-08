# fmparser — how to develop the parser

Loaded when working under `fmparser/`. What the parser is, for a person: [`README.md`](README.md).
This file is the method and the feedback loop. The reference lives elsewhere:

- **one doc per table**, [`docs/parser/`](../docs/parser/): layout, evidence from an in-game
  screen, quirks, output. Read the table's doc before changing its module.
- **the whole file**, [`docs/parser/savefile-map.md`](../docs/parser/savefile-map.md): every
  table in file order, the gaps, the archive at the tail.
- **how the parser is organised**, [`docs/parser-architecture.md`](../docs/parser-architecture.md):
  *a locator shape tells you how to FIND a record, a declared layout tells you how to READ it*;
  the seven locator shapes, how each fails, and what the audit scripts can tell you.
- **count-framed tables**, [`docs/table-framing.md`](../docs/table-framing.md).

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
7. **Look in front of record 0: the save declares its own table sizes.**
   `[>= 8 × 0xFF][count][record 0]`. Compare each declared count with what the parser reads;
   test for `>= 8` FF, never `== 8`. As a search it needs a real validator (`id == slot index`
   on every declared record): the sentinel alone occurs hundreds of thousands of times. Read
   [`table-framing.md`](../docs/table-framing.md) first.
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

`--map` prints the per-byte schema of every declared record: generated from the parser's own
declarations, so it cannot go stale.

**When an in-game screen disagrees with the parse, suspect the parse.** One disagreement is a
lead, not noise: chase it before explaining it away. Read the screenshot itself, not notes
about it, and prefer a screen with a TOTAL line, which catches a dropped or extra row.

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
- **One declarative layout per record is the schema** (`core.Record`, `core.TableDef`): the
  parser reads from it and `audit_records.py` checks against it, so they cannot drift.
- **Carry what you cannot name, then go and name it**, from an upstream definition or repeated
  ground truth, never a guess.
- **Before calling something a bug, ask whether it is a choice.** Record a real data bug as a
  callout in the table's doc and a TODO entry, and fix it in its own change.
