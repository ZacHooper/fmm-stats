# The save ends in a zstd archive: `sicomps`, 159 named members

**Found 2026-09-20**, opening the densest unexplored gap in
[`savefile-map.md`](savefile-map.md). Two documents ranked the 1.93 MB after the squad
snapshot as the best remaining target, on two DIFFERENT statistics, and only one of them was
the bad one:

- [`TODO.md`](TODO.md) called it *"by far the most TEXT-dense unparsed span in the file"*,
  citing **25.8% printable**. That is the flawed reading.
- `savefile-map.md` called it *"the densest unknown in the file"* on **71% non-filler**,
  which is a fair measure of "there is something here" and says nothing about what.

The distinction matters because the fix is not "distrust the map" — it is "never rank by
printable fraction".

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
| `comp_man` | 194 KB | 211 KB | 232 KB | 212 KB | **the master competition stages calendar & roll of honour** — see below |
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

The 147 `comp_<id>.dat` ids are **not our `cid` space — they are the competition `uid`**. The
competition record in the main save holds its uid immediately before its name, and
`fmparser/clubs_comps.py` already reads it into `staging.competitions.uid`: `cid 2` 3F
Superliga is `comp_6.dat`, `cid 256` European Champions Cup `comp_1301394.dat`, `cid 258`
EURO Cup `comp_1301396.dat`, `cid 263` Sydbank Pokalen `comp_1301406.dat`. See the next
section for what the members hold.

## `comp_<uid>.dat` — each competition's rules: stages, rounds and their names

Decoded 2026-09-28; parsed by `fmparser/tables/comp_rules.py`, loaded as
`staging.competition_rounds`. Each member is a declared 54-byte `HEADER` record
(`season_year` +20, `base_year` +48, `n_fields` +50; the rest declared UNKNOWN, see
`audit_records.py --map`) followed by a **tagged tree** in the data dictionary's wire format,
read strictly by `fmparser/datadict.py`'s `read_tree` -- the same type table the dictionary
scan uses, not a second copy:

    [54-byte HEADER][n tagged fields, n = HEADER.n_fields]
    field     = [tag x4][0x01][type][value]  |  [0x01][type][value]  (tagless list element)
    0x0a container [u32 m][m fields]   0x0b list [u32 n][n fields]   0x1a string [u32 len][bytes]
    0x0f a pair of u32                 0x00 empty    others fixed width (1/2/4/8 bytes)

The `n` fields end at the trailer `XSvC`/`EdBr`/`EdDt`/`SubF` (`SubF` is the source path, e.g.
`.\europe\`); binary runtime state follows and is not read. **147/147 members parse to their
declared count on every save tested in both careers**; 74 declare 0 fields (loaded, not
configured). The `stgs` list is the stage structure, and it is what `fix_man` indexes:

| field | meaning | fix_man |
|---|---|---|
| stage `id` | FourCC code: `leag` `cham` `prom` `rele` `bppr` (League Path) `chpr` (Champions Path) `play` `grou` `cup ` … | |
| stage `indx` | stage index | **+76 `stage_index`** |
| stage `type` | 0 knockout, 1 league, 2 groups, 6 play-off feeder | |
| stage `ntms`, `ngps` | teams, number of groups | |
| stage `stnm` | stage name id (League Path, Preliminary Phase, Championship Group, Group Stage) | |
| `rnds[k]` | round `k` of the stage | **+77 `round_index`** |
| round `stnm`, `ntms`, `nmlg` | round name id, teams, **legs per tie** | |

A name id is either `stnm`'s scalar value or the `stgn` child of an `stnm` container (both
occur), and resolves through the **round-name catalog** in the main save (273 records,
`fmparser/tables/rounds.py`, loaded as `staging.round_names`): 17 Quarter Final, 18 Semi
Final, 20 Final, 73 Group Stage, 76–91 Group A–P, 108 Championship Group, 149–152 First–
Fourth Qualifying Round, 164/165 First/Second Knockout Round, 236 Preliminary Phase,
2000016479 League Path, 2000016478 Champions Path.

**Ground truth**: the in-game Club Fixtures screens for 2026/27 and 2027/28 — EURO Cup League
Path Third Qualifying Round (stage 0, round 0), Playoff (stage 2), Group D, First Knockout
Round (stage 4, round 0); Champions Cup League Path Third Qualifying Round (stage 1, round 1)
and Playoff (round 2); 3F Superliga Preliminary Phase (stage 0) and Championship Group (stage
1); Sydbank Pokalen Third Round (round 2). All reproduce, in `tests/test_comp_rules.py` from
the save and `tests/validate_mart.py` from `mart.match_stages`.

**The fixture record still carries no competition.** None of the members' uids occurs anywhere
in `fix_man.dat`, no unnamed fixture byte is constant within a stage and distinct between
competitions, and `comp_man`'s tail blocks are a day-by-day calendar of stage keys, not a
competition map. The link runs through the matches the store holds: a match's `comp_id` →
`staging.competitions.uid` → rules, and its fixture's `stage_key` then labels that stage for
every club. A knockout round is one `stage_key`; **a group stage is one `stage_key` per group**,
consecutive, so the letter is the group's place among its siblings (`mart.match_stages`).

## `comp_man.dat` — master stages calendar and roll of honour

Decoded 2026-09-21. A prior investigation reported "stride 78, exact tiling coincidence; record 133
lands mid-way through tagged tags `mmus`/`solc`". Both halves of that reading were misunderstandings:
`comp_man.dat` **is a strict 78-byte grid preceded by a 36-byte header and followed by an auxiliary tail**:

1. **36-byte Header:** byte `+10` is a `u32` declaring the exact count of 78-byte records
   (`n_stages` = 2,157 on day one `frem-2021-07-01`, 2,316 on `frem-2026-06-11`, 2,181 on
   `frem-2026-07-02`, 2,269 on `bucaspor-2023-05-20`).
2. **78-byte Stage Calendar Grid:** runs from offset 36 to `36 + n_stages * 78` (e.g. byte 180,684
   on 2026). Record index `k` in this grid corresponds directly to `stage_key == k` in `fix_man.dat`.
   `mmus` (`summ`) and `solc` (`clos`) in record 133 are not stray tagged dictionary fields —
   record 133 is the **Superliga Championship Split**, and those are 4-byte FourCC status tags sitting
   at bytes `+70` and `+74` of the 78-byte record.
   - `+46/+48`: validity year bounds (u16)
   - `+58`: format mode (1=league/group, 2/4=knockout)
   - `+64`: default kickoff time (e.g. 1500 for 3pm, 1930 for 7:30pm)
   - `+66`: calendar scheduling week `0..60` across the season (August to May)
   - `+70`: team/match capacity or FourCC
   - `+74`: scheduling priority / leg ordinal or FourCC
3. **Auxiliary Tail (~25 KB – 54 KB):**
   - **Part 1 (0..29,850 B):** 1,152 tournament scheduling blocks (`[u32 count][u32 id, u16 year] * count`).
   - **Part 2 (29,850..51,740 B):** **The 55-byte Roll of Honour Grid** (398 records on 2026).
     Every completed competition season has a 55-byte record carrying the true `comp_cid`:
     `[u16 start][u16 end][u16 format][u16 base 1900][u32 comp_cid][u32 season][u32 winner_tid][u32 runner_up_tid][u32 third_place_tid][u32 fourth_place_tid]`.
     Verified: Premier Division (`cid 5`, 2025 winner Chelsea 431, runner-up Liverpool 471, 3rd Man City 473);
     FA Cup (`cid 275`, 2025 winner Liverpool 471, runner-up Tottenham 518).

Parsed by `fmparser/compman.py` (`HEADER`, `STAGE`, `HONOUR`).

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
| +6 | **home goals**, u8 | match goals (0xFF = unplayed) |
| +7 | **home extra goals**, u8 | extra time / aggregate goals (0xFF = none) |
| +8 | **home penalties**, u8 | penalty shoot-out score (0xFF = none; e.g. Leicester v Liverpool 23 Sep 2025: 0-0 pens 2-3) |
| +11 | **away goals**, u8 | match goals (0xFF = unplayed) |
| +12 | **away extra goals**, u8 | extra time / aggregate goals (0xFF = none) |
| +13 | **away penalties**, u8 | penalty shoot-out score (0xFF = none) |
| +31 | **stage key**, u32 | index into `comp_man.dat`'s 78-byte stage calendar grid (409 distinct values on 2026) |
| +35 | **seq_id**, u16 | per-fixture sequence id within stage |
| +41 | **home club tid**, u32 | 282/285 against ground truth; HOME-FIRST |
| +47 | **away club tid**, u32 | 282/285 |
| +53 | **day of year = `u16 & 0x1FF`** | `& 0x1FF` never exceeds 366 in 26,954 records, twice over; 1-indexed (see `fixtures.DAY_BASE`) |
| +55 | **year**, u16 | 2025 / 2026 only on a 2026 save |
| +57 | **day2**, u16 | secondary date day-of-year |
| +59 | **year2**, u16 | secondary date year |
| +66 | **season_year**, u16 | season year (2024/2025; 0 on unplayed/friendlies) |
| +76 | **stage_index**, u8 | stage index within competition (corresponds to `stgs` in `comp_<id>.dat`) |
| +77 | **round_index**, u8 | round index within stage (corresponds to `rnds` in `comp_<id>.dat`) |
| +78 | **round**, u8 | matchday counter WITHIN competition; 255 = none / friendly |
| +83 | **subr**, u8 | stage classification (corresponds to `subr` in `comp_<id>.dat`) |

**Ground truth**: every `mart.club_matches` row for the managed club, in both careers, on
five saves. **CORRECTED 2026-09-21: the date needs a `-1`** — the day-of-year field is
one-indexed and the decoder treated it as zero-indexed, so every date read a day late. The
original check joined rows ON the date, which cannot expose a uniform shift; re-measuring by
(opponent, score) instead shows 51/51 and 60/60 rows needing exactly -1 across both careers.
The counts below stand; the dates behind them did not until `fixtures.DAY_BASE` landed.

On those same five saves, **282 of 285 in-window rows match exactly on date, home tid, away tid and both
scores; 3 disagree, all on the score only; 0 disagree on clubs or date.** Rows outside the
window are simply absent — on frem-2026-06-11, **51/51** of our 2025 and 2026 matches are
present and **0/143** of 2021-2024 are, which is what the two-year year field already says.

**This table is home-first.** `fmparser/matchslots.py`'s 25-byte table is away-first and
gets the orientation wrong on one of every repeated club pair (3/3 measured). This one got
venue right on all 282.

### The goals block (`+2..+15`) decoded

The goals block carries normal goals, extra time/aggregate goals, and penalty shootouts:
- Plain matches (97.9%): `+6` and `+11` hold the full score; `+7/+8` and `+12/+13` read `0xFF`.
- Penalty shootouts: regular score at `+6/+11`, penalty shootout scores at `+8/+13` (verified against Leicester 0-0 Liverpool on 2025-09-23: `+8=2`, `+13=3`).
- Two-legged ties / extra time: extra goals read at `+7/+12`.

Parsed by `fmparser/fixtures.py` (`FIXTURE`).

### What is NOT established about `fix_man`
- **No competition field is identified**, and 2026-09-28 looked for one against the
  competition uids and found none (see `comp_<uid>.dat` above). A fixture's competition comes
  from a match the store holds in the same `stage_key`, which labels every fixture of a stage
  we played in (`mart.match_stages`).
- **The goals at +6/+11 are the 90-minute score.** Extra-time goals sit at +7/+12 and are not
  emitted; `mart.match_stages` takes the store's full-time score where it holds the match and
  flags `extra_time` (3 of our matches to date).
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
