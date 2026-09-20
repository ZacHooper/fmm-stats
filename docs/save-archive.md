# The save ends in a zstd archive: `sicomps`, 159 named members

**Found 2026-09-20**, opening `savefile-map.md`'s densest unexplored gap. That map and
[`TODO.md`](TODO.md) both described the 1.93 MB after the squad snapshot as *"by far the
most TEXT-dense unparsed span in the file"* (71% non-filler, 25.8% printable) and ranked it
the best remaining target on exactly that basis.

**It is not text.** 95 of 256 byte values are printable, so **uniform random bytes are
37.1% printable by chance** — which is what that span measures once the filler at its front
is excluded. Block entropy across it is a flat **7.99 bits/byte**, and the reason is that
every byte of it is compressed: `28 b5 2f fd`, the **Zstandard** magic number, occurs 181
times there and **nowhere else in the file**.

That single fact turns the file's last megabyte from an unparsed region into a **named
archive with a directory**, and the directory names twelve subsystems plus one file per
competition. The biggest member, `fix_man.dat`, is **the world fixture list with scores** —
the thing [`TODO.md`](TODO.md) §4 has been hunting through four separate dead ends.

**Correct the measurement, not just the conclusion.** Printable-fraction was the wrong
statistic to rank gaps by: it cannot separate "text" from "compressed", and it ranked this
region first for a reason that was false. Entropy separates them in one pass.

## The container

```
... the last uncompressed structure ...
02 01 'fmf.' 08 00 00 [u32 ?]      <- 13-byte record header opening the archive
00 00 00 00 11 00 00 00 00 00 00 00 03   <- a further 13 constant bytes, UNNAMED
[u32 stored_size][zstd frame]      <- member 0, one or more frames
[u32 stored_size][zstd frame]      <- member 1
...
02 01 'fmf.' 08 00 00 [u32 n]      <- the DIRECTORY's own header; n IS its frame size
[zstd frame]                       <- the directory, ending on the file's last byte
```

Both 13-byte runs are byte-identical across both careers except for the u32.

`'fmf.'` and `'tad.'` are `.fmf` and `.dat` **stored reversed**, the same convention the
tagged data dictionary uses for its field names (`fmparser/tagged.py`, where `b"  di"` is
`id`). Every member's *decompressed* payload opens with its own 6-byte
`[0x03][0x01]['tad.']` header, so the extension travels with the content.

### The directory

```
[u32 len]['sicomps'][u32 0][u32 1][u32 len]['rgman'][u32 count]
then `count` x
[u32 len][name][u32 len][ext][u64 offset][u64 stored][u64 unpacked][u64 ?][u64 ?]
```

- `offset` is relative to member 0's length prefix; `stored` **includes** the 4-byte length
  prefixes; `unpacked` is the exact decompressed size.
- The two trailing u64s are `0xFFFFFFF1886E0900` on **every entry of every save measured**.
  Constant, so not a per-member timestamp. **Unnamed.**
- `'sicomps'`, the `0` and `1` after it, and the leading `'rgman'` (which is also entry 0's
  name) are **unnamed**. So is the `[08][00][00]` in the 13-byte record header.
- The u32 in the header that **opens** the archive is *not* the member area, and it took the
  second career to say so: it is 17 more than the members' stored total on both Frem saves
  measured (464,097 v 464,080; 1,299,014 v 1,298,997) and **495 LESS** on
  bucaspor-2023-05-20 (1,365,725 v 1,366,220). Two saves agreeing was a coincidence.
  **Unnamed.** On the *directory's* header the same u32 IS that frame's size, exactly, on
  all 34 saves — which is what `locate` checks.

### Extent, proven by the archive's own invariants

`scripts/audit_archive.py` runs four checks per save and **34/34 saves pass** (27 Frem,
7 Bucaspor) in under 5 seconds:

| check | invariant |
|---|---|
| CHAIN | walking `[u32 stored][frame]` from the **first zstd magic in the file** lands exactly on a `.fmf` header whose declared size ends on the **last byte of the file** |
| COUNT | reading the declared number of entries consumes the directory to within 4 bytes |
| TILING | entries tile `[0, member_area)` with no gap and no overlap; `sum(stored) == member_area` exactly |
| UNPACKED | every member's concatenated frames decompress to **exactly** its declared size |

No offset and no window is involved, which is what makes this survive the megabyte-scale
drift of the career half. `fmparser/archive.py` is the reader; `tests/test_archive.py`
guards it.

### Size, and how it behaves

| | day one 2021 | 2023-06-26 | 2026-06-11 | Bucaspor 2023-05-20 |
|---|---|---|---|---|
| members | 159 | 159 | 159 | **161** |
| stored | 464 KB | 1.12 MB | 1.30 MB | 1.37 MB |
| unpacked | **3.58 MB** | 6.50 MB | 6.58 MB | 7.09 MB |

So the archive holds **5x more data than it occupies**, it grows with the career, and its
twelve named members are **identical in both careers** — the cross-career check that makes
this the format's shape rather than Frem's. Only the competition count differs (147 Frem,
149 Bucaspor).

## The members

Twelve named subsystems plus `comp_<id>.dat`, one per loaded competition. Sizes are
decompressed bytes, measured on four saves:

| member | 2021 | 2023 | 2026 | Bucaspor | what is established |
|---|---|---|---|---|---|
| **`fix_man`** | 1.00 MB | 2.95 MB | 2.52 MB | 2.77 MB | **the fixture list with scores** — see below |
| `comp_man` | 194 KB | 211 KB | 232 KB | 212 KB | unexamined |
| `stadium` | 132 KB | 134 KB | 133 KB | 134 KB | opens `[u16 3][u32 15984]` then 8-byte pairs; 15,984 is one short of the reference stadium table's declared 15,987. Unexamined beyond that |
| `comp_hosts` | 22 KB | 25 KB | 31 KB | 25 KB | unexamined |
| `friend_man` | 23 KB | 15 KB | 17 KB | 25 KB | unexamined; friendlies |
| `rule_group` | 57 KB | 64 KB | 67 KB | 63 KB | carries the only plain-text strings in the archive: engine log lines such as `15/6/2025: Promoted seeding for Denmark (13th) - id=0 EURO Cup old_seed=2 new_seed=1`, plus `wwclub_split_year` / `wwclub_single_year` |
| `rgman` | 5.4 KB | 18 KB | 21 KB | 18 KB | a 20-byte grid `[u32 index][u32 value][16 x FF]` |
| `reserves` | 1,500 B | 1,500 B | 1,500 B | 1,753 B | constant within a career |
| `national_teams` | 56 B | 464 B | 371 B | 236 B | unexamined |
| `discipline` | 254 B | 254 B | 254 B | 254 B | **byte-identical on every save of both careers** — a static enumeration, not career state |
| `fifa_rankings` | 14 B | 14 B | 14 B | 14 B | a date and one u16. Despite the name it holds no ranking table |
| `squad_man` | 225 B | 97 B | 17 B | 17 B | shrinks to a stub; nothing in it by 2026 |

The 147 `comp_<id>.dat` ids are **not our `cid` space**: they run `1, 2, 6, 7, 8, 11 … 100101
… 2000099928`, and `reference.comp_refs` resolves exactly **1 of 147**. The tagged data
dictionary's `DBID` values overlap 54 of them and its `comp` values 92, so a mapping
probably exists but **none is established here** — treat the id as opaque until it is.

## `fix_man.dat` — the fixture list, and exactly how far it is decoded

This is the biggest single result in the archive and the reason to open it first, so it is
reported with its limits attached.

### What is proven

**STRIDE 92.** A gap histogram of the `[u8][0x14][4 x FF]` record opener gives 26,951 of
26,953 gaps at exactly 92 on frem-2026-06-11.

**SEGMENTS that tile exactly.** The hits fall into **more than one residue class mod 92**,
so the member is not one grid but a series of them. Splitting on the residue change, every
segment satisfies `record_count x 92 == segment_span` **exactly**, on six saves across both
careers:

| save | size | segments | records per segment |
|---|---|---|---|
| frem-2021-07-01 | 1.00 MB | 2 | 209 / 114 |
| frem-2023-06-26 | 2.95 MB | 2 | 7,873 / 18,704 |
| frem-2026-06-11 | 2.52 MB | 2 | 7,721 / 19,232 |
| frem-2026-07-02 | 3.12 MB | 2 | 7,817 / 19,232 |
| bucaspor-2023-05-20 | 2.77 MB | 2 | 8,839 / 20,632 |
| bucaspor-2024-03-16 | 2.59 MB | **7** | 4,454 / 50 / 29 / 18 / 145 / 68 / 20,645 |

On frem-2026-06-11 the two segments carry **year 2026 (7,721 records)** and **year 2025
(19,232)** — the segment split is the calendar year, and the counts match the year field
exactly. The 38 KB between the two segments is **not identified**.

### Fields verified against ground truth

Offsets are from the record's first byte (the `[u8][0x14]` opener):

| offset | field | evidence |
|---|---|---|
| +41 | **home club tid**, u32 | 282/285 |
| +47 | **away club tid**, u32 | 282/285 |
| +53 | **day of year = `u16 & 0x1FF`** | `& 0x1FF` never exceeds 366 in 26,954 records, twice over; a random 9-bit mask would overflow ~29% of the time |
| +55 | **year**, u16 | 2025 / 2026 only on a 2026 save |
| +6 | home goals, u8 | 282/285 — **but see the caveat** |
| +11 | away goals, u8 | 282/285 — **but see the caveat** |
| +78 | a round / matchday counter, u32 | sequential 0,1,2… within a competition. Not verified |

**Ground truth**: every `mart.club_matches` row for the managed club, in both careers, on
five saves. **282 of 285 in-window rows match exactly on date, home tid, away tid and both
scores; 3 disagree, all on the score only; 0 disagree on clubs or date.** Rows outside the
window are simply absent — on frem-2026-06-11, **51/51** of our 2025 and 2026 matches are
present and **0/143** of 2021-2024 are, which is what the two-year year field already says.

**This table is home-first.** `fmparser/matchslots.py`'s 25-byte table is away-first and
gets the orientation wrong on one of every repeated club pair (3/3 measured). This one got
venue right on all 282.

### Why the scores are NOT a finished decode

`+6` and `+11` are not fixed fields. The ten bytes after the opener are a **variable-shape
block**, and the one Frem mismatch shows it directly:

```
plain (works):  01 14 ff ff ff ff  02 ff ff ff ff  01 ff ff ff ff   -> 2-1
Frem 2023-02-22: 01 14 ff ff ff ff  00 00 ff 00 ff  00 01 ff 01 ff  -> reads 0-0, store says 0-1
```

So `+6/+11` is a reading that happens to be right whenever the block takes its plain shape.
**Do not ship it as a field** until the block's shape rule is understood — most likely it
carries extra time / penalties / aggregate. The other two mismatches are the *same*
Bucaspor fixture (2023-02-04, Bucaspor 6567 v 6378) on two different saves, where the
record takes the plain shape and reads 2-1 while the store reads 1-1. **That one needs a
screenshot**: neither side is ground truth, since the store's score is itself parsed.

### What is NOT established about `fix_man`
- **No competition field is identified.** Every fixture's competition is still unknown from
  the record alone, exactly as for the 25-byte table.
- **~70 of the 92 bytes are unnamed.** There is no `LAYOUTS` entry for this record yet and
  `scripts/audit_records.py` does not cover it.
- The 38 KB between segments, and the segment ordering (2026 before 2025), are unexplained.
- Whether a fixture can appear twice, as it does in `clubrecords.py` and the 25-byte table.

## Using it

```bash
uv sync --extra archive          # zstd is not in the stdlib before Python 3.14
uv run python scripts/audit_archive.py                      # all saves
uv run python scripts/audit_archive.py <save.fms>           # one save + the listing
uv run python tests/test_archive.py
```

```python
from fmparser import archive as A
name, ents = A.directory(mm)          # ('sicomps', [Entry(...), ...])
blob = A.extract(mm, "fix_man.dat")   # decompressed, header included
```

`uv sync --extra archive` replaces the environment, so pair it with `--extra dashboard` if
you want Streamlit at the same time.

## Method notes worth carrying

- **Rank gaps by ENTROPY, not by printable fraction.** Compressed data is 37% printable by
  construction. This region was ranked first for a reason that was false, and the same
  statistic would mis-rank any other compressed region in any other save format.
- **A magic number is worth one grep before any structural work.** Four bytes settled what
  a gap histogram, a stride search and a residue-class test could never have reached,
  because there is no stride in a zstd frame to find.
- **`discover_tables.py` and `audit_table_headers.py` could not have found this**, and
  their own docs say so: the count-framing convention is a property of the static reference
  database. The archive is at the far end of the career half and is framed by a length
  prefix and a magic number instead.
- **An archive that names its own members is worth more than a decoded record.** The
  directory turned 1.3 MB of noise into twelve named subsystems in a single step, and it
  names things — `fix_man`, `discipline`, `comp_hosts` — that tell you what to look for
  before you read a byte of them.
