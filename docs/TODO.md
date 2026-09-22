# TODO — the one doc you read to resume

**Where the project is, and everything still open.** There is no second resume doc: if it
isn't here, it isn't outstanding. The other files in `docs/` are *reference* — record layouts,
rules, dead ends already measured — and you read them when a task sends you there, not to find
out what to do.

If you finish something, **delete its entry**. Do not tick it off, or this rots into a
changelog, which is what killed the last four handoff docs.

Item numbers are for conversation only — they are renumbered whenever entries are deleted, so
never cite one in code or a commit message.

Last reviewed **2026-09-20**, after the tail archive was opened (#4) and the **parser refactor
landed in full** — records are declared once and read from the declaration, the six locator
shapes are written up in [`parser-architecture.md`](parser-architecture.md), the world fixture
list is extracted, and all seven self-declared-count defects (#17) are fixed. Every
restructuring commit was held byte-identical by `scripts/assert_identical.py`; the four commits
that changed output say so and re-recorded in the same commit.

---

## Where the project is

Reverse-engineering **Football Manager Mobile 2022** `.fms` saves into a DuckDB store, a static
web app and a Streamlit dashboard, to manage a career with real data.

| | |
|---|---|
| career | **Boldklubben Frem** (Denmark, `--career frem`, managed tid 346, reserves 7296) |
| store | **25 snapshots**, `fm-frem.duckdb`, latest **2027 / 2026-07-02** |
| division | **3F Superliga — tier 1, `club_league` cid 2 — since season 2025** |
| how they got there | 3. Division → 2. Division → NordicBet Liga → Superliga, three straight promotions |
| tactic | `frem_attacking_ss` (strikerless SS), the dashboard default |
| hold-out | **Bucaspor** (Turkey) is archived, and is the only cross-career parser regression test |

The squad was built to win the fourth tier. Expect the level gap to be the dominant story.

**Infrastructure is done and not a source of open work.** Storage tiers (git / R2 / local-only)
are settled, the store is disposable (`scripts/rebuild.py --career frem`), the web app is live
at <https://fmm-stats.zac-g-hooper.workers.dev>, remote-agent SQL over R2 works, and squad
registration shipped. House rules live in [`CLAUDE.md`](../CLAUDE.md) — read them there, they
are not repeated here.

### Reading the data without getting it wrong

Five things have produced numbers that looked fine and were not. All are live traps, not history:

- **Score an attribute on the population that HAS it.** A keeper attribute sits at the display
  floor for an outfielder, so pooling made Communication read 92.4% when it scores 3.0% on
  actual keepers.
- **The decoder's ceiling is 94.8% exact / 98.7% ±1, not 100%** — measured on attributes read
  straight from a byte, where a disagreement is the two sources disagreeing rather than a decode
  error ([`ca-weighting.md`](ca-weighting.md)). Quote accuracy against that, never against 100%.
  Current state: **59.4% exact on Frem, 59.5% on the Bucaspor hold-out**, for the nine outfield
  entangled attributes; frozen was 46.3%.
- **Joining a per-(season, _phase_) dimension on (season, club_tid) fans every fact out by the
  snapshot count.** Frem's 19 home games read as 95.
- **`any_value(x ORDER BY y)` does not order in DuckDB.** `max_by(x, y)` is the one that works.
- **`mart.club_attendance` is our-matches-only** — every club but us has one or two home games a
  season, so read `n_games` before trusting `avg_att`. (`staging.club_details.att_*` is NOT
  attendance — see below.)

### Where to look

| you want | read |
|---|---|
| the attribute decoder, and what is already ruled out | [`attribute-model.md`](attribute-model.md) |
| what CA is made of, per position | [`ca-weighting.md`](ca-weighting.md) |
| record layouts from the 2026-09 expansion | [`record-expansion.md`](record-expansion.md) |
| the per-byte schema of any record we walk | `uv run python scripts/audit_records.py --map` |
| which BYTES of the save no parser reads | `uv run python scripts/audit_coverage.py` |
| the standings record, decoded but unimplemented | [`standings-record.md`](standings-record.md) |
| **the compressed archive at the end of the file, and the fixture list in it** | [**`save-archive.md`**](save-archive.md) |
| where every byte of the file lives | [`savefile-map.md`](savefile-map.md) |
| whether a region is text, records or COMPRESSED | `uv run python scripts/entropy_profile.py <save.fms>` |
| the hunt for complete fixtures (history; now superseded by the archive) | [`date-search.md`](date-search.md) |
| the transfer-history record (decoded, not parsed) | [`transfer-history-record.md`](transfer-history-record.md) |
| how to deploy the site | [`DEPLOY.md`](DEPLOY.md) |
| known parser bugs and their history | [`BUGS.md`](BUGS.md) |

---

## Blocked / needs a decision from Zac

### 1. The R2 API token has never been rolled
Its access key and secret were pasted into a chat transcript. Cloudflare → R2 → Manage API
Tokens, then `rclone config update r2 access_key_id <NEW> secret_access_key <NEW>`. **This is
the only security item in this file.**

---

## Parser / decode

### 3. The league standings record is decoded but not implemented
`staging.standings` still reads `source = 'lightresults_computed'` — the *approximate* table
inferred from partial fixture coverage. A **14-byte fixed record holding the exact final
position of every club in every loaded competition** was decoded on 2026-07-20 and never wired
up. Layout, validation and parser plan: [`standings-record.md`](standings-record.md). Strict
upgrade over what ships today.

**Before doing that work, know what already ships.** `mart.clubs.last_league_pos` /
`last_league_cid` carry **each club's exact finishing position in its last completed league**,
straight from the club record — no parser work needed, and `staging.standings` is not involved.
Verified 2026-09-21: a perfect `1..12` permutation of the Danish top flight in all 25 Frem
snapshots, and it tracks Frem's real ladder exactly (2.Div 15th → 3.Div 1st → 2.Div 1st →
NordicBet 1st → Superliga 6th → Superliga 3rd).

The one rule for using it: **it updates at the JULY ROLLOVER and describes the season that just
ENDED**, so the final table of season S is carried by the first snapshot of season S+1, not by
the last snapshot of S. On 2026-06-29 it still reads the 2024/25 table; on 2026-07-02 it reads
2025/26. What it does NOT carry is points, W/D/L or goals — only the position. That is still
the gap the 14-byte record would close, alongside non-final (in-season) tables.



**Re-scoped 2026-09-17.** The light-results region turned out to be the **club records**
tables (`fmparser/clubrecords.py`), so the complete results are not there and never were, and
neither the rolling-buffer story nor the "partial decode" framing survives. 28 results read
off in-game screenshots (`tests/fixtures/light_results_truth.json`) are recovered 9/28, and
those 9 are precisely the ones that happen to BE club records. Two fixtures
(Southampton 3-0 Aston Villa, Liverpool 0-1 Newcastle) have their two club tids nowhere
adjacent in the file, so any remaining structure does not store a fixture as a tid pair.
**Updated 2026-09-17 (second pass).** The "cid-less list at ~49.36 MB" **does not exist** —
it is an unset table, every field `0xff`. Six more hypotheses were tested and killed with
measurements (uid-keyed records, slot-index round-robin columns, bare score arrays, the
datadict's `fxds`/`mtdy` scheduling records, a two-save append diff); all are tabulated in
[`light-results-record.md`](light-results-record.md) so they are not re-run.

**CLOSED 2026-09-18 — the ~2,600 clubless-but-dated slots hold NO match data.** This entry
called them "the majority of the table's real content and never examined"; they have now been
examined and there is nothing in them. On `frem-2026-06-11` all **2,598** of those slots carry
`away_tid == home_tid == 0xFFFF` **and** `away_goals == home_goals == 255` — both club fields
and both score fields at their sentinels. They are date-only shells: a `day`, the A/B/k group,
and nothing else. So the table's real match content IS the 275 fixture rows, and the "populated
total 2,874" figure counts shells, not content. Do not re-open this as a source of results.

**CLOSED 2026-09-18 — the datadict's `fxds` is a schedule TEMPLATE, not fixtures.** Previously
recorded as "tested and killed" without a reason; here is the reason, so it stays killed. Its
996 records carry `id_1`/`id_2` values like 2,003,398,260 and 1,937,006,962 — 4-byte tag-shaped
constants, not club tids — and their dates read `dyow`/`dyom`/`mont` with **year 2000/2001**,
i.e. "this round is played on this day-of-week in this month" rules with a placeholder year, not
this career's dated fixtures. The dictionary describes competition STRUCTURE; the realised
programme is not in it.

**Where the unparsed bytes actually are** (frem-2026-06-11, 63.9 MB) — updated 2026-09-20,
and the tail row that used to head this table is gone because the tail is now read:

| span | size | note |
|---|---|---|
| 51,149,000 – 55,839,667 | 4.69 MB | before our match region. Still unexamined |
| 56,223,268 – ~61,253,092 | 5.03 MB | between matches and the first player-list block. Still unexamined, but 0.6 MB smaller than this table used to claim |
| ~~62,002,727 – 63,936,873~~ | ~~1.93 MB~~ | **RESOLVED** — 0.63 MB of player-list blocks + the 1.30 MB `sicomps` archive |

(Our own match region is 55.84–56.22 MB and the squad snapshot 61.90–62.00 MB on that save;
both are parsed. Everything else in the 51–64 MB tail is not.) The 14.0–16.7 MB region (2.7 MB,
85% filler) is the other unidentified area — see #17.

**And a shorter path to most of what "results" is for:** #3's standings record is already decoded
and gives the exact final position of every club in every loaded competition. That is a strict
upgrade over today's `lightresults_computed` approximation and needs wiring, not decoding.

**The 25-byte AWAY-FIRST record is now DECODED as far as its shape goes** —
`fmparser/matchslots.py`, guarded by `tests/test_match_slots.py`. Stride 25 (two independent
measurements), self-locating by a constant at +20, **3,975 slots on every Frem save across four
seasons and 3,943 on Bucaspor** (a preallocated table, which is the invariant that bounds the
walk), all 25 bytes named or declared UNKNOWN, and three fixtures verified against the game.

**It is NOT the fixture list, and it is not ~7% populated either** — that figure only counts
slots with a resolvable CLUB PAIR (a "fixture"; 275 on `frem-2026-06-11`). Checking the `day`
field independently of the club filter shows the table is **72-74% populated**, and the total
stays essentially constant while the mix shifts: fixture-count + clubless-but-dated count is
**2,874** on `frem-2023-07-02` and `frem-2024-06-30`, **2,873** on `frem-2026-06-11` and
`frem-2026-07-02` — four saves spanning 2023-2026, fixture count anywhere from 100 to 275, same
populated total every time. The remaining ~1,101-1,102 slots are genuinely inert (day=0, every
carried field zero). Reads as a fixed-size calendar of ~2,874 slots that fill in progressively
as matches are played, not a fixture list that's mostly empty — **the ~2,600 clubless-but-dated
slots are the majority of the table's real content and have never been examined.**

**Checked for a World Cup** (`frem-2023-01-06`, days after the real Qatar final, and
`frem-2026-07-02`, taken DURING the real 2026 tournament window): zero fixture rows resolve to
a nation in either save (100 fixture rows in the WC-window save, correctly down from 275 three
weeks earlier as domestic leagues broke for it). National teams do exist as their own club-style
records (86 found, e.g. Qatar tid 1,632,698,368) but their tids are 4+ orders of magnitude
bigger than this record's 16-bit `away_tid`/`home_tid` fields can hold (max 65,535) — a national
team is structurally unable to appear here, independent of the calendar.

**No `cid`/competition field is stored in the record — reconfirmed 2026-09-17 with the right
test, after the reputation-floor/empty-CODE fix raised the obvious question of whether one of
the 8 UNKNOWN bytes was secretly a now-more-resolvable cid.** "Does this byte resolve to *some*
valid competition" says yes almost everywhere — worthless, since 678 real cids packed densely
into 0..1400 make that near-guaranteed by chance. The test that actually settles it: on the
242/275 fixtures where both clubs share a league (so the correct cid is known independently of
the row), does any of the 25 bytes, read as u8 or u16, EQUAL that known cid? Every offset hits
0-2%, not the ~100% a real field would show (`tests/test_match_slots.py`'s new "NO CID FIELD"
check pins this). So the fix changed which already-inferred leagues resolve (`frem-2026-06-11`'s
275 fixtures span 349 distinct clubs across 47 `league_cid`s via each club's own DEFAULT
league membership looked up separately, ALL 47 of which now resolve, 20 only because of the
fix), not whether a hidden cid exists — it doesn't, and this table structurally cannot answer
the question for the other 33 fixtures. 242/275 pair two clubs from the same inferred league;
the other 33 can't be ordinary league fixtures by construction, and their real competition (cup
/ friendly / playoff) is unrecoverable from this record, full stop — not blocked by any decode
bug, so no future fix to `reference.py` can unlock it. Four were checked against Zac's own
in-game fixture screens and all four decoded
EXACTLY on **date**, but only two of the four also had the score read correctly the first time
— the other two were corrected after further checking (below), so treat any score quoted for a
cross-league row as unverified until it's been checked twice, not once:

| row | day → date | screenshot says |
|---|---|---|
| Forest 3-0 Maidstone | 13 → 2026-01-14 | FA Cup Third Round **Replay** (score OK) |
| Burnley 1-2 Arsenal | 199 → 2025-07-19 | pre-season **Friendly** (score OK) |
| Sevilla 1-3 Gladbach | 146 → 2026-05-27 | continental cup **Final**, neutral (was misread the other way round) |
| Nürnberg 2-3 Düsseldorf | 140 → 2026-05-21 | promotion **Playoff**, 1st leg, Düsseldorf won away (was misread as Nürnberg winning at home) |

A fifth cross-league row (Logroñés 0-3 A. Madrid, day 201) couldn't be found in-game — **now
solved** by the `k` formula below: its `k` is `naive + 4×365`, i.e. this really is a match, just
roughly four seasons stale in a slot that was never overwritten. It won't be on Atlético's
current fixture screen because it isn't from the current season at all — not a wrong
year-guess, as the old day≥181 heuristic made it look.

**Orientation is NOT reliable on a repeated club pair.** Three `(away_tid, home_tid)` pairs
recur with a different day and score each time — first read as possible reschedules, but
ground truth says all three are ordinary fixtures where the real venue genuinely differed (two
are legs of a two-legged playoff with real alternating venues; Merthyr/Bradford confirmed
directly). The table gets it wrong for exactly **one of the two rows, every time (3/3)**:
Palace/Stoke (day 142 wrong, day 138 right), Sint-Truidense/Beerschot (day 128 wrong, day 121
right), Merthyr/Bradford (day 114 wrong, day 359 right). It isn't even one consistent bug: on
Palace/Stoke the club **identities** are swapped between the away/home slots; on
Nürnberg/Düsseldorf above, the identities are correct but the **goals** are swapped between the
two clubs instead. Two distinct failure modes, both invisible from the bytes alone. **Every
single-occurrence row checked against a screenshot has been exactly right** — this is specific
to a club pair appearing more than once, not a flaw in away-first generally.

**Ruled out as a competition-type flag**, tested against the four confirmed rows plus the three
known league fixtures: `+8` (5 on 226/242 same-league rows AND 17/20 cross-league rows) and
`trailer_a` (the cup replay and a same-day plain-league game are both 5; another plain-league
game is 391). Neither separates cup/friendly/playoff from league. (Unaffected by the
orientation bug above — these are raw per-offset byte values, not which club they're read as.)

**`k` is SOLVED** — this was sitting unmerged in `light-results-record.md` from before
`matchslots.py` existed, so it's now folded into the module docstring rather than re-treated as
open. **`k = (save's own day-of-year) − (match day)`, wrapping `+365` for a previous-year
match** — exact or +365-exact on 251/275 rows (91%) on `frem-2026-06-11` (save day-of-year
161). This is the real date rule; prefer it over guessing a year from `day` alone. The ~9% that
miss are mostly off by a few days (a refresh-lag artifact, not a broken formula) except for a
handful that are further whole multiples of ~365 off — stale slots, as with the Madrid row
above. `B` isn't independent either: **`B == floor(3A/5)` on 223/275 (81%)** — of the four i16
fields, only ONE number is truly free.

The Sevilla-Gladbach final is also stored TWICE, 500 bytes (20 slots) apart, identical
tid/score/day, different `trailer_a` — the same multi-copy pattern as `clubrecords.py`.

**No ID field exists.** Checked every `UNKNOWN` byte for uniqueness across the 275 fixture rows
(262 genuinely distinct matches): the best candidate, `+9` (A), has only 94 distinct values —
reused ~3× on average. A is a date-derived number (via `k`), not a key; there's no sequential
match id to find here.

**Immediately before the table, no gap**: content density stays ~0.6 for at least 80KB back.
A DIFFERENT 16-byte-stride table runs for 9,692 records (~155KB) right up to this table's
start — `00 05 [u16 ~10000] [u16 ~10000] [i16 -1500..1087] ff ff ff 00 00 [u8] [2-byte trailer,
usually 5c-a1]`. The two ~10000 fields read as a percentage ×100 (100.00% default, real values
cluster 8500-9700). Not identified beyond that. "Manager" (ASCII) appears ~190 bytes after this
table's END, not before.

The 497-record chained region at 6.127-6.260 MB has now been swept: 91 signature hits but
only 67% share a stride, so it fails the alignment control and is not a match table. A
whole-file sweep at every byte offset found **no second gridded match signature anywhere** —
the 25-byte table is the only one (654 stray hits of the same trailer constant at 46.88-48.35M
were checked and decode as non-football garbage, not a second table).

[`date-search.md`](date-search.md) — the results we hold are **our matches only**, confirmed by
`mart.competitions`: we carry exactly **32** Superliga fixtures per season, which is one club's
full league programme, not the division's ~200. Two zones that light up on a date search
(~36–38 MB, ~63–64 MB) have never been examined.

**Possibly superseded by #3**: if the standings record gives exact final tables, complete
fixtures may no longer be needed. Decide that before spending time here.

### 4b. Career-half region sizing: two real fixed pools, two false ones — next region to check is open
**2026-09-18/19.** Following PR #58's proof that the *reference* database announces its own
table sizes, the same question was asked of the *career* half, tested against five saves: three
spanning the whole career (2023/2024/2026) plus two more from the same season (2022-08-27,
2023-06-26). Full writeup, exact numbers and the reusable method:
[`career-region-sizing.md`](career-region-sizing.md).

**Proven, exact, 3/3**: the player-history slab is a genuine fixed-size pool — 265,423 rows on
every save regardless of career length, proven with a parameter-free pointer-forest check (not
`history.locate()`'s sampled score), and it hands off to club-records exactly **209 bytes**
after its own end, every time.

**Refuted by the 3rd save**: club-records plus the trailing empty-slot table looked like a
second fixed pool after two saves measured the same span to the byte (4,558,055). A third save
broke that. Tracking one real club (Southampton, tid 504) across all three saves instead showed
its footprint grows by exactly 212 bytes when it earns a new season block — real insertion, not
space claimed from a reservation. This part of the file is ordinary append-and-shift, not a pool.

**Same pattern, a third region: "our matches."** Looked briefly like it might be a fixed
container too (`matches.find_match_region()` returning 0 valid anchors on two of five saves
looked like it could be a locator bug). It isn't — those two saves are effectively at a season
boundary and the region genuinely resets to empty there, confirmed by comparing two saves from
inside the *same* season (9 matches vs 43 matches, footprint scaling ~proportionally, not
constant). What IS exact: a **550-byte `0xFF` wall** right after the last real match, identical
across all three match-bearing saves regardless of match count (9/43/59). But that wall isn't
headroom for more matches — reading past it lands in a completely different, independently
growing **stride-65 per-season table** (`[flag u8][value u16][tid u16][year u16]`, one entry per
season), unnamed and not yet checked against `table-framing.md`'s similarly-shaped per-season
series near 44.6 MB (same table found twice, a sibling, or coincidence — open).

**Four follow-ups, none started:**
- Ship the exact (no-sampling) history-slab locator as a real function next to
  `history.locate()`, the way `scripts/audit_table_headers.py --confirm` sits next to the
  reference-table locators — the sampled version is fine for finding a candidate but should not
  be the thing a "fixed pool, proven" claim rests on.
- **Live bug**: `fmparser/mapregions.py`'s `sub_regions()` calls
  `lightresults.find_light_region()` (singular) but the real function is `find_light_regions()`
  (plural) — a silent `AttributeError` swallowed by a bare `except: pass`, so
  `scripts/map_regions.py` has never once printed a `light_results` sub-region for any save.
  One-line fix.
- **The matches season-reset is documented here but not coded anywhere.** `matches.py` has no
  comment or test asserting the region resets at season boundaries; anyone hitting the
  0-valid-anchors case cold would still read it as a bug today.
- **Name the stride-65 per-season table** and settle whether it's the same structure as
  `table-framing.md`'s "per-season series" near 44.6 MB or a genuine sibling.

Next step per the user: apply the same method (exact structural proof + multi-save cross-check,
never trust two saves) to the rest of the still-unidentified career-half regions, to work out
which are genuine fixed pools and which just look that way.

**2026-09-19 addendum — the whole file mapped, and two real gaps found.**
[`savefile-map.md`](savefile-map.md) walks `frem-2026-06-11.fms` start to end with every known
section, live-verified on this branch wherever possible. Two genuinely uncharacterised stretches
fell out of it, ~8.7 MB combined:
- **52.74M–55.84M** (~3.10 MB) — sits between the trailing club-records empty-slot table's
  filler wall and where our matches begin. Not investigated at all.
- **56.3M–~61.25M** (~4.94 MB) — sits between the per-season table found after matches (§4
  above) and the first **player-list block**. `map_regions.py` calls this whole span
  `inline_names`, which the map now shows is wrong. **Trimmed 2026-09-20**: the last 0.63 MB
  of what this bullet used to claim is the head of the player-list block region
  (~61.25M–62.63M), of which `attributes.snapshot_bounds`'s 0.11 MB squad snapshot is five
  blocks. One stray populated block also sits at 56,336,372 (`Jeppe Corfitzen` / `FC
  København` / `Res Group 1`), so the same structure reaches into this gap and is the first
  thing to chase in it.

**Also surfaced, and worth fixing before doing much more work on this branch: PR #58 is not
merged.** This branch (`claude/pr-58-learnings-8xx4fi`) was cut from `main`, and PR #58 lives on
its own unmerged branch (`docs/table-framing`) — `docs/table-framing.md`,
`scripts/audit_table_headers.py` and `scripts/discover_tables.py` simply don't exist here. The
club table, award table, and a handful of small attribute-section sub-tables in
`savefile-map.md` are cited from that branch at `frem-2023-07-02` offsets, unverified on this
save. Reconcile the branches (merge #58, or rebase this one onto it) before treating those rows
as anything more than a lead.

### 4c. The `sicomps` archive: remaining unparsed members
**New 2026-09-20.** The file's last 1.0–1.6 MB is a **named zstd archive** with a directory —
159 members on Frem, 161 on Bucaspor, 6.6 MB decompressed. `fmparser/archive.py` reads it.
`fix_man.dat` (fixtures and scores) and `comp_man.dat` (stages calendar and Roll of Honour)
are parsed and wired (`fmparser/fixtures.py`, `fmparser/compman.py`).
[`save-archive.md`](save-archive.md) is the reference.

The remaining open members in the archive:

- **`comp_hosts.dat`** (31 KB) — variable-length, 4-year host cycles (`0x07d2, 0x07d6, ...`).
- **The 147 `comp_<id>.dat` ids are not our `cid` space.** `reference.comp_refs` resolves
  1 of 147. The datadict's `DBID` values overlap 54 of them and its `comp` values 92, so a
  mapping probably exists; **none is established.** Settle this before building anything on a
  per-competition member, because without it you cannot say which competition a file is.
- **`rule_group.dat`** carries plain-text engine logs (`15/6/2025: Promoted seeding for Denmark
  (13th) - id=0 EURO Cup old_seed=2 new_seed=1`) — the only prose in the archive.
- **Three members are static**: `discipline.dat` is byte-identical on every save of both
  careers, `fifa_rankings.dat` is 14 bytes and holds no rankings, `squad_man.dat` decays to a
  17-byte stub. Recorded so nobody re-opens them expecting career state.
- **Unnamed fields**: the two u64s ending every directory entry (constant
  `0xFFFFFFF1886E0900`), `'sicomps'` and the `0`/`1` after it, the `[08][00][00]` in the
  13-byte record header, the u32 that follows it, and the 13 constant bytes before member 0.

### 4d. Player-list blocks — named, not decoded
**New 2026-09-20.** ~1.38 MB at ~61.25M–62.63M is a run of blocks of **100 slots x 200 B**
(+14 B per block), most slots holding an identical empty template with `e5 07` = the career's
start year. Populated slots carry a variable-length player record — a ~160 B binary core then
`[full name][first][last][""][last][club short name][competition name]`. The lists are squad
lists (ours) and world/scouting lists (De Bruyne/Man City, Courtois/R. Madrid).

**`attributes.snapshot_bounds` finds exactly five of these blocks — our own squad — and the
other ~55 have never been opened.** Open: what the 160-byte core holds beyond the 23
attributes `attributes.py` already reads, what selects which players appear in the world
lists, and whether the blocks carry a header naming the list. Reproduce with occurrences of
`14 01 00 0a 00` at gaps of exactly 200; runs come in lengths of exactly 100.

### 5. `att_avg` / `att_min` / `att_max` are misnamed — curiosity only
The bytes are read correctly (`league_id` lands exactly at p+158 right beside them), but the
NAMES come from fmm-editor's `Club.cs` and were never checked against the game. They fail every
check: a hard worldwide ceiling of 12,500 with 99 clubs exactly on it; always multiples of 100,
only 66 distinct values of `att_avg` worldwide; and **Barcelona reads max 9,500 BELOW avg
9,600**, which no genuine min/avg/max triple can do (6.8% of clubs violate the ordering). No
single scale reconciles them with in-game figures — ×10 matches Frem's ~11k exactly but gives
FCK 36k against an in-game ~30k and puts 25% of clubs above their own stadium capacity.

**Deliberately NOT surfaced in `mart.clubs`**; carried in `staging.club_details` only.

**Superseded in practice.** `staging.matches.attendance` is the real figure and is exposed as
`mart.club_attendance`: FCK 32,875 against a reported ~30k, Frem climbing 2,086 (2022, lower
divisions) → 10,924 (2026, Superliga) against Zac's ~11k. Capacity correlates **+0.93** with it;
`att_avg` correlates **−0.31**. So this is now curiosity, and low priority. If anyone picks it
up, the method is ground truth rather than more inference (CLAUDE.md §3), and note they are NOT
static as first claimed: 506 of 5,208 clubs move `att_avg` across snapshots — Frem and FCK just
happen not to.

### 6. One match-event type byte is unnamed
`?0e` (byte 14): 2 events, both in reserve fixtures, minutes 38 and 59. `mart.match_events`
carries it verbatim rather than dropping it. `0x07`/`0x08` were named `shootout_goal` /
`shootout_miss` on 2026-09-17 — see `fmparser/matches.py` for the arithmetic that settled the
direction.

### 6b. The save's own in-game date is not located — partial search, results kept

**Not blocking anything.** `phase` is supplied by hand at import (`archive_save.py --phase`)
precisely because a 0-match save has no match to date it from, and that works. This is about
removing the hand-entry, and the hunt was cut short on 2026-09-20; what follows is what was
ruled out, so the next attempt starts further along.

Ruled out: **it is not a fixed-offset field in any header.** Diffing `frem-2025-06-10` against
`frem-2026-06-11` and requiring a `[day u16][year u16]` pair that reads as each save's own
date at the SAME offset in both eliminates every candidate in the first 1 MB, and then in the
whole file bar one.

The one survivor is **offset 38,184,473** — `99 00 e8 07` on a 2024 save, i.e. day 153, year
2024. Two cautions before trusting it: it sits inside the big 16–40M binary section rather
than any header, and the pattern **repeats roughly every 32 bytes**, which smells like a
per-row date column in some table (a contract or registration grid) that happens to be
uniformly stamped with the save date, rather than a single authoritative field. Checking it
means reading the same offset across three or four saves and confirming it tracks each one's
date exactly.

Cheaper alternative worth trying first: the fixture list now gives a **lower bound for free**
— the current-year segment of `fix_man` ends at the last played day, which on the saves
measured is the save's own day-of-year or one before it. That does not date a day-one save
(323 rows, none of them this season), but it would cross-check every other import.

### 7. Staff record: five catalog indices plus six hidden attributes
Bytes `+34..+38` are five undecoded catalog indices, declared `UNKNOWN` in
`scripts/audit_records.py`'s `LAYOUTS` so the audit passes honestly. The record's stride and
coverage are proven; only these are unnamed.

The six hidden staff attributes stay named by OFFSET (`hidden_s18 … hidden_s28`) on purpose:
fmm-editor has **no `Staff.cs`** — its `People.cs` stops at the `Unknown6b` u32 that links here
— so there is no upstream order to borrow and no ground truth of our own. **`hidden_s27` is the
one to identify next**: 85% of staff read 1–4 against ~10 for the other five, the only one
distinctive enough for a small ground-truth set.

### 8. 17% of origin clubs do not resolve, and the capital rule silently under-reports
**3,936 of 22,624** origin clubs come back as `#<tid>` in `mart.player_origin.origin_club`, so
the capital-province rule **cannot be evaluated** for that share of the pool — and
`eligible=False` is currently indistinguishable from *unknown*. Confirmed live: Samuel
Clemmensen (tid 8834) read `#65192`; Zac identified it in-game as FC Fredericia (genuinely
ineligible), but the data could not say so. These ids are **not** in `staging.clubs`, so they
are probably youth/academy or defunct-club records in another structure.

Two things to do: find where they resolve, and until then make `player_origin` distinguish
*ineligible* from *unknown*. **Treat `eligible=False` on a `#<tid>` origin as "ask Zac", not
"no".**

### 9. Two records still read short or unread
Both are known gaps, not suspicions (a third, the nation walk, was fixed 2026-09-20):

- **parse_club_trailer steps over 20 undecoded bytes** — width confirmed, content unread.
- **The Region table is unparsed**, as is the nation record's counted language list. A NEW,
  related table was found 2026-09-18 right after the nation table ends: a small (~7-entry)
  **continent/confederation name table** matching `nyongrand/fmm-editor`'s `ContinentName`
  class exactly (`[uid u32][Name][1 terminator][CodeName][Demonym][1 terminator]`, no 14-byte
  trailer) — `Africa`/`Asia`/`Europe`/`North America`/`Oceania`/`South America` at ids 0-5
  (matching the six FIFA confederations the competition record's own `continent` field uses,
  declared as `comp_trailer` +1..2 in `scripts/audit_records.py`) plus a synthetic `World` at
  id 6 with empty code/demonym. Unparsed; nothing currently
  reads it. Its own 6th entry ("World") is the coincidental candidate that a widened comp scan
  briefly picked up as a fake `cid=24931` competition before comps moved to a pure
  structural walk that never scans this far at all.

### 10. `mart.club_managers` isn't purely structural
It keeps a `home_reputation` tiebreak and exposes no candidate count, so a sole structural hit
and a reputation fallback are indistinguishable to anything reading the view. A scout report
quoting the opposition manager cannot tell how confident to be.

---

## Models

### 12. Refit the transfer-value model with the new reputation fields
`current_reputation` and `world_reputation` are parsed (PR #51) and currently unused —
`fmparser/value_model.py` still fits on `reputation` alone. This was the one workstream from the
parser expansion that never got done, and reputation is exactly what a value model wants. Zac
called it out as important for transfer value.

### 13. Attribute decoder — two measured leads, and two hints
Both leads are from [`attribute-model.md`](attribute-model.md); neither is speculative.

- **Bias is almost the whole story.** `|mean signed error|` correlates **−0.91** with the
  exact-match rate across the 14. The misses are systematic, not noisy — an intercept problem,
  which is the most fixable kind.
- **We under-predict good players.** Exact falls 83.6% (true 4–6) → 22.4% (true 16–20) with the
  bias going +0.10 → −1.01. Worst precisely where scouting cares most.

Two features that lost at n=80 but lost *narrowly*, worth one re-test now the store is 25
snapshots: **feet for Dribbling** (48→54%) and **height/weight for Shooting** (63→66%).

**Read the reference doc's "already ruled out" section first** — height, the CA constraint, the
CA surprise, a non-linear link and `blend_w` are all tested and dead. Do not re-run them.

### 14. Goalkeeper attributes cannot be modelled at this sample size
Frem has **7 goalkeepers**. The five keeper attributes are deliberately **not refitted**
(`--min-players`, default 20) and keep the frozen coefficients, because refitting made the
Bucaspor hold-out worse. Needs more GK ground truth before it can move — which realistically
means more careers, not more snapshots (the learning curve is flat in rows and only bends in
players).

---

## Football (the actual career)

### 15. Position write-ups still owed
Zac asked for the position-by-position read for **DM, CM, AML, AMC, AMR and ST**, plus a verdict
on the **4-1-2-2-1** question. GK/LB/RB/CB were delivered. **The earlier analysis is several
seasons stale** — it was written when Frem were in NordicBet Liga; they have been in the **3F
Superliga (tier 1, cid 2) since 2025** and the store now runs to **2027 / 2026-07-02**. Redo the
read against the current squad rather than resuming the old one.

### 16. Table discovery: the save frames its own tables, and the inventory needs naming
**Full write-up: [`table-framing.md`](table-framing.md).** Measured on all 34 saves across both
careers; reproduce with `scripts/audit_table_headers.py` (+ `--confirm`) and
`scripts/discover_tables.py` (+ `--stable`).

The competition table's self-declared count (#10) turned out to be a **general convention**:
`[8 bytes of 0xFF][record count][record 0]`, used by nine tables, exact every time. Asking each
table "what does your header say, versus what do we read?" found four defects. **Nothing here
is fixed yet** — the audit is committed, the fixes are not.

**The four that were losing real data on every save are FIXED (2026-09-20, refactor Phase 5).**
Languages 77 -> 124, currencies 94 -> 173, nations 227 -> 251, and the third name id-table is
read at last, so 2,424 people carry their real display names instead of their full legal ones
(`Tite`, not 'Adenor Leonardo Bachi'). The attribute table now stops at its declared end rather
than inventing 13 rows, and the staff grid is read by arithmetic. The diagnoses, and the way
each one hid, are kept in [`table-framing.md`](table-framing.md) — the reusable lesson is that
**a rejected record does not cost one record**: in a chained table it truncates everything
after it, and in a keyed table it punches a hole that still looks like a clean table.

Two patterns did nearly all the damage and are worth recognising on sight:

- **The `0xFFFF` / out-of-band sentinel read as an out-of-range value.** A plausibility gate
  (`nation_id <= 4096`, `continent_id <= 6`, `uid <= 4096`) rejects the value the save uses to
  mean "none". It cost 17 defunct nations, 5 regional languages and 79 currencies across three
  tables. `primitives.NO_ID16` / `NO_ID32` exist to be checked against.
- **A stride borrowed from the neighbouring table.** The staff record was measured against the
  player record's 78 bytes instead of its own 39, and the resulting nonsense (`id2` reading
  0, 2, 4, …) was written up as "the table is multi-segment, a grid walk is provably
  impossible". It is a dense array.

**The next goal: name the tables in the inventory, one at a time.** `discover_tables.py`
validates a table by deriving its stride from the header's count and then checking
`id == slot index` on **every** declared record. That found five tables nothing parses, and
**chaining forward from a declared end found two more** — each fixed-width table's end is
followed immediately by the sentinel and the next table's count, so a section is a contiguous
run of blocks. Full register with offsets in
[`table-framing.md`](table-framing.md#the-complete-register). The unnamed ones:

| offset (frem-2023-07-02, DRIFTS) | Frem | Bucaspor | stride | evidence |
|---|---|---|---|---|
| ~6,268,740 | 622 | 1,109 | 99 B | INDEX. Record has a 64-byte `FF` block inside it; `[id][u32][u32][u16 ~115][u16 ~145][u16 ~5750][8 small bytes][u16 1900][u32][u32][64×FF][u16 day][u16 2023]` |
| ~6,245,275 | 1,971 | 2,603 | 7 B | INDEX. `[id u32 == index][3 bytes 1..255]` |
| ~6,263,016 | 816 | 796 | 7 B | INDEX. same shape |
| ~6,259,084 | 560 | **560** | 7 B | INDEX. same shape; count is career-INVARIANT, so a fixed enumeration |
| ~13,711,352 | 807 | — | variable | **THE AWARD TABLE** — club-shaped `[tid][uid][3 strings]`, `tid 0` = 'Footballer of the Year'. This is where the 153 award names polluting the club index (#17) come from, now with a declared anchor. Trailer length still unpinned. |
| ~6,330,330 | 273 | — | variable | `[id u32][len][string]`, id 1 = 'Replay' |
| ~13,990,354 | 888 | **888** | 7 B | TILE only. `[id u32][00 00 00]`, ids strictly ascending 1..3221 with 2,333 gaps; ends flush against the sentinel that introduces the LANGUAGE table |

All four INDEX tables sit in the attribute section behind the staff grid and drift with it.

**A header number is not always a count.** Three kinds, separated by holding the number against
a whole career of saves (see [`table-framing.md`](table-framing.md)): a **true count** (the
reference tables), a **per-database pool** (the history slab — 265,423 in ALL 28 Frem saves over
five in-game years, 295,648 in Bucaspor, 100% initialised on day one), and an **engine-wide
capacity** (the browse name table's `60,000`, identical in both careers, 76.5% utilised).
`history.locate`'s docstring calling 265,423 "the exact row count" is true of the physical rows
but invites the wrong inference: **it is a fixed allocation and can never indicate how much
history exists.** Worth a docstring fix. An unresolved lead sits beside it — the `u32` at
`start-8` varies across saves (2,069 / 67,635 / 564 / 52 / 56), is not monotonic so not a usage
counter, and would fit a free-list head into the recycled pool. Untested.

### The history pool: reclamation means older snapshots hold history newer ones lost
Measured 2026-09-18, full detail in [`table-framing.md`](table-framing.md). The slab is a fixed
per-database pool (265,423 rows Frem / 295,648 Bucaspor), a perfect forest with **100% of rows
reachable** in every save, whose singleton chains are the free reserve (27,319 on day one ->
~10,000 and stable, so exhaustion is not a risk). Churn is monotonic: `untouched` decays
0.81 -> 0.38 over five years.

**The finding that matters:** of 24,145 sids present in both the day-one and the 2026 save,
**6,077 (25.2%) have a SHORTER history chain in 2026** — 68,998 rows, the worst going 39 rows
down to 5. Median age of that group in 2021 was 31 (~36 by 2026) versus 22 for the 72% that
gained rows, and max chain length across the whole pool falls 39 -> 31 -> 26. So rows are
reclaimed from players whose careers end.

Open, in order:
1. **Settle the mechanism with a RELIABLE retirement signal.** `club_tid` cannot do it (97.6% of
   the shortened group vs 97.7% of the lengthened group still "have a club" — the lapsed-loan
   trap). Try absence from later `mart.player_snapshots` / match stats instead.
2. **Quantify the loss in the STORE, not the save**: per person, compare career-history row
   counts across snapshots and count how many have their richest history in an OLDER snapshot.
3. **If material, union history across snapshots in `fmparser/mart.py`.** We keep every
   snapshot's extract, so the data is recoverable — nothing currently unions it.
4. Cheap standing check per import: singleton-chain count, to confirm the reserve is not
   shrinking toward exhaustion.

Refuted while doing this, so nobody retries it: the `u32` at slab `start-8` is **not** a
free-list head — the rows it points at have in-degree 1, i.e. ordinary mid-chain rows.

**Do not look for count headers above 39 MB either** — checked 2026-09-18. The history slab is
counted but on different framing (`u32 @ start-12`, no sentinel, already read by
`history.locate`); the club-history rows sit straight after an 8-byte FF run with NO count (the
bytes there are float32 `1.0`); our matches have no sentinel within 1,250 bytes of the first
anchor and are found by `regions.DELIM_UNIT`; the snapshot is found by `CLUB_MARKER`. Across all
34 saves, zero count-framed tables above 39 MB survive both stability filters. **The convention
belongs to the static reference database (~4–14 MB plus the name id-tables), not to the career
half of the file** — reference data ships as counted arrays, career data is pointer- and
delimiter-located.

**Do not re-check 14.0 -> 37.9 MB for count-framed tables** — that 23.9 MB jump in the register
looks like the obvious next place and it was checked (2026-09-18): 14.0–16.7 MB is 85% filler
with no headers (every count candidate is a multiple of 256, i.e. data bytes), 16.7–21 MB is the
tagged data dictionary on completely different framing, and 21–39.8 MB is the contract/transfer
record pages. The convention lives in two bands only, 3.99–6.33 MB and 6.34–14.0 MB, plus the
name id-table trio at 37.9 MB.

**2026-09-20 — a TWENTIETH table, and this doc's own advice caught it.** The person table
(info spine) **does** declare a count; the earlier pass concluded "no header found" because it
looked near the first record the sentinel SWEEP reaches instead of at the table's base — the
exact mistake the staff grid had already taught once. It is the first run of >= 8 `0xFF` below
1 MB, just past the browse table's zero filler:

| career | record 0 | declared | `staging.scrape_players` reads |
|---|---|---|---|
| Frem | 572,041 | **32,966** | 32,874 (**92 short**) |
| Bucaspor | 575,721 | **34,312** | 34,010 (**302 short**) |

`--confirm` is now **238/238 across all 34 saves** and shows the count is **career-constant
and career-specific** — a per-database pool, like the history slab, so 32,966 is a bound and
not a headcount. It also makes the old lead below less mysterious: the `u32 = 32,966` at
14,000,242 is the same number in a second place.

**Open, and do not treat the shortfall as 92 lost people until it is settled:** whether record
0 is at 572,041 (where the count is flush, but the bytes decode as a placeholder) or 572,042
(where they decode as a real person); how much of the shortfall is the 77 known `uid == 0`
empty slots and tid-keyed collapse rather than loss; and a real structural walk, which needs a
per-record parser because the record is variable-length (68 B head + counted lists).

One unproven lead is kept in the doc (a 14-byte unit at 14,000,242 that stops being uniform
after 386 rows).

Read `table-framing.md` before extending the sweep — it records what the detectors CANNOT find
(variable-length tables have real headers and are invisible; competitions, stadiums, languages
and currencies are all in that class), the two cross-save filters and why offset-keying finds
nothing, and the remaining tile-only candidates including the ones already identified as false
positives in the award-record region so the next pass does not rediscover them.

---

## Housekeeping (safe to do any time)

- **Move `fmparser/archive.py` to `fmparser/core/archive.py`**:
  `archive.py` is the Shape D container/filesystem driver for the embedded Zstandard archive (`sicomps`). It is not a table parser — it sits at the same structural abstraction layer as `schema.py`, `table.py`, and `primitives.py`. Relocate to `fmparser/core/archive.py`, update `fmparser/tables/` imports, and keep `fmparser/core/` self-contained.

- **DuckDB Loader optimizations (`load_duckdb.py`)**: Profiling on full snapshots (e.g. `2026-mid` at ~2.9s) identified two simple wins when loader throughput becomes worth tuning:
  1. *JSON decoding with `orjson`*: Standard library `json.load()` accounts for 1.1s–1.3s (45%) of total snapshot load time parsing ~20 JSON files (~33 MB `players.json`). Replacing with `orjson.loads(f.read())` in `load_duckdb.py` cuts JSON parsing to ~0.45s (~0.7s–0.8s saved per snapshot). `orjson` is added to `pyproject.toml` dependencies under `uv` without affecting stdlib-only extractors.
  2. *Flattening generator expressions in `load_core`*: ~0.9s–1.0s (35%) is spent constructing row tuples via nested generator expressions (`*(_int(v.get(c)) for c in PLAYER_HIDDEN_COLS)`, `SRC_COLS`, `PERSON_COLS`), resulting in >11M method dispatches per snapshot. Pre-compiling accessor lists outside row loops saves ~0.4s–0.5s per snapshot.
  Together, these cut load time from ~2.9s to ~1.6s–1.7s per snapshot (~40-45% load speedup).

- **Two pairs of saves in `~/fm-saves/frem` are byte-identical duplicates** (md5, whole file):
  `frem-2024-05-25.fms` == `frem-2024-06-02.fms`, and `frem-2024-06-03.fms` ==
  `frem-2024-06-28.fms`. Noticed 2026-09-20 while hashing the archive across all 34 saves —
  two of the "34" are the same file twice, so any cross-save count in this repo that says 27
  Frem saves is really 25 distinct ones. Decide which name is right and drop the other (and
  its `.gz`, its R2 object, and its manifest row — `canonicalise_names.py` lists the five
  places a save's identity lives).

- **~308 MB of stale `output/` dirs** from old experiments (`frem-patched-test`,
  `multi-region-test`, `frem-22-start`, pre-rename leftovers). All regenerable.
  Careful: `rebuild.py --skip-existing` reuses these, and a stale-FORMAT extract used to load
  silently — now guarded by `_extract_is_current`, but deleting them is still tidier.
- **`~/fm-parser-git-backup-20260820.tar`** (302 MB) and `/tmp/oldgit` — the pre-history-rewrite
  backup, safe to delete now the rebuild is verified.
- **4 saves in `unfiled/`** with no in-game date, so no canonical name:
  `frem/unfiled/denmark-mid-22.fms`, `bucaspor/unfiled/{22-23-start, fm_save1-24-mid,
  fm_save3}.fms`. Needs Zac's in-game dates to file them.
- **`careers.py` hardcodes `reserve_tid`** — `main_club_tid` from the club record could replace
  it, making a new career one field shorter to register.
- **Stale commit SHAs** cited in `agent-context/fm-parser-project.md` and
  `day1-league-membership.md` (`aac6cbe`, `0b9a679`, `9c89633`, `d0f60af`) — invalidated by the
  history rewrite. Cosmetic.
- **The Cloudflare Pages project does not exist** — the site is deployed as a Worker instead
  (see [`DEPLOY.md`](DEPLOY.md)). Preview locally with `uv run python -m http.server -d site 8000`.
