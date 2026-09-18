# TODO — the one doc you read to resume

**Where the project is, and everything still open.** There is no second resume doc: if it
isn't here, it isn't outstanding. The other files in `docs/` are *reference* — record layouts,
rules, dead ends already measured — and you read them when a task sends you there, not to find
out what to do.

If you finish something, **delete its entry**. Do not tick it off, or this rots into a
changelog, which is what killed the last four handoff docs.

Item numbers are for conversation only — they are renumbered whenever entries are deleted, so
never cite one in code or a commit message.

Last reviewed **2026-09-17**, after PR #51 (record expansion + attribute decoder rebuild).

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
| the hunt for complete fixtures | [`date-search.md`](date-search.md) |
| the transfer-history record (decoded, not parsed) | [`transfer-history-record.md`](transfer-history-record.md) |
| how to deploy the site | [`DEPLOY.md`](DEPLOY.md) |
| known parser bugs and their history | [`BUGS.md`](BUGS.md) |

---

## Blocked / needs a decision from Zac

### 1. The R2 API token has never been rolled
Its access key and secret were pasted into a chat transcript. Cloudflare → R2 → Manage API
Tokens, then `rclone config update r2 access_key_id <NEW> secret_access_key <NEW>`. **This is
the only security item in this file.**

### 2. `mart.squad_current` still uses the spell model
`roster_vs_spells` exists specifically to judge whether to switch it to the roster. Nobody has
read it and decided. Until then the spell model stands, because it is the one that survives a
lapsed loan (a departed player's `club_tid` can point at us indefinitely).

---

## Parser / decode

### 3. The league standings record is decoded but not implemented
`staging.standings` still reads `source = 'lightresults_computed'` — the *approximate* table
inferred from partial fixture coverage. A **14-byte fixed record holding the exact final
position of every club in every loaded competition** was decoded on 2026-07-20 and never wired
up. Layout, validation and parser plan: [`standings-record.md`](standings-record.md). Strict
upgrade over what ships today.

### 4. Complete results/fixtures via a date search
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

### 9. Three records still read short or unread
All three are known gaps, not suspicions:

- **`parse_club_trailer` steps over 20 undecoded bytes** — width confirmed, content unread.
- **The Region table is unparsed**, as is the nation record's counted language list. A NEW,
  related table was found 2026-09-18 right after the nation table ends: a small (~7-entry)
  **continent/confederation name table** matching `nyongrand/fmm-editor`'s `ContinentName`
  class exactly (`[uid u32][Name][1 terminator][CodeName][Demonym][1 terminator]`, no 14-byte
  trailer) — `Africa`/`Asia`/`Europe`/`North America`/`Oceania`/`South America` at ids 0-5
  (matching the six FIFA confederations the competition record's own `continent` field uses,
  declared as `comp_trailer` +1..2 in `scripts/audit_records.py`) plus a synthetic `World` at
  id 6 with empty code/demonym. Unparsed; nothing currently
  reads it. Its own 6th entry ("World") is the coincidental candidate that a widened comp scan
  briefly picked up as a fake `cid=24931` competition (see #10) before comps moved to a pure
  structural walk that never scans this far at all.
- **`_nation_candidates` breaks its `nat_len` loop unconditionally**, dropping a candidate whose
  `name_len` search then fails. Confirmed 2026-09-18 as the live cause of a real, visible gap,
  not just a theoretical one: `lookups.scrape_nations()` is missing **Algeria** (nation_id 0,
  the very first real nation, sitting immediately before Angola/nation_id 1) from its output.
  Root cause is the same *class* of bug fixed today in the competition scraper's own name walk
  (see #10's terminator note): a **plausibility-sniffed** terminator
  skip is ambiguous exactly when the field that follows is short/edge-case, where an
  **unconditional, structural** skip (the actual rule — every name field gets exactly one
  terminator, full stop, regardless of what's in it) is not. Not yet fixed here; `lookups.py`
  wasn't touched this session.

### 10. The competition scraper — SOLVED (2026-09-18): a pure structural walk, gate-free
Found auditing `reference.py`'s competition scraper 2026-09-17, escalated into a full rewrite
2026-09-18. History, in order:

**2026-09-17** (candidate-scan-plus-gates era, since fully replaced — see below): the
`_MIN_COMP_REP = 500` reputation floor was made a tier-1 fill instead of a hard reject, and the
3-name walk was made to accept a length-0 short-name/code (both fixed the same underlying class
of bug the terminator fix below later generalised). These recovered `Danish Second Division
East`/`West`, `Greek Football League North`/`South`, the Greek/N.Irish/Welsh/Polish regional
divisions, and all 30 `<Nation> Reserves Group <N>` competitions including cid 1342 "Danish
Reserves Group 1" (Zac's own motivating example — `mart.py`'s comment calling it unnamed was
wrong; the name was always there, just unreachable by the walk).

**2026-09-18, round 1** (more gate fixes, same architecture): auditing every remaining gate
against real bytes (never trusting a skip "for a good reason") found four more real bugs, each
confirmed by name before fixing:
- The `type` byte was treated as a 5-value enum (`COMP_TYPES`) and anything else rejected. It
  isn't — at least ~20 real values exist (Carabao Cup, European Championship, Copa América,
  African Cup of Nations, national Super Cups, youth leagues among them), and the single
  clearest case, cid 13 "French Regional Divisions", sat in an otherwise dense 0-12 block and
  was STILL being dropped by this gate alone. **Retired entirely** — continent/nation/
  reputation/shape already did the real noise filtering; the type gate never added anything a
  noise candidate actually needed catching by.
- `continent` was hardcoded `== 2` (Europe-only). It's the real FIFA confederation enum
  (0=Africa, 1=Asia, 2=Europe, 3=N.America, 4=Oceania, 5=S.America), confirmed against 6 real
  confederation-level competitions (Copa Libertadores, Asian/African/Oceania/European/N.American
  Champions Leagues) that the retired type gate had ALSO been dropping, so the Europe-only bug
  never got a chance to matter for them until today. Widened to `<= 5`.
- A reputation **ceiling** (`> 1000` implausible) and a **short-name-longer-than-long-name**
  shape check were added after a full sweep found the British Virgin Islands nation-table
  record (`lookups.scrape_nations()` id 206) resolving as a fake comp `cid=63981` — nation,
  club and comp records share the exact same `[name][short][code]`-shaped candidate signature
  (`lookups.scrape_nations`'s own docstring says so), so a nation string can misread as a comp
  under a bogus id from neighbouring bytes that were never an id at all. Structurally excluded
  the whole nation-table region from the candidate scan (`_nation_table_bounds`, anchored on
  `scrape_nations`'s own offsets) rather than leaning on the incidental ceiling/shape gate that
  only caught the one collision that happened to look wrong — as a side effect this also
  removed 191 nation/demonym/continent-name/reserve-competition strings that had been silently
  polluting the CLUB table via the same shared-shape collision.

**2026-09-18, round 2** (the terminator bug, and the shift away from gates): the user pushed
back hard on continuing to add gates without reading the one failing record's actual bytes
first. Doing that surfaced the real, previously-hidden defect: `_eval_comp_candidate`'s 3-name
walk decided whether a terminator byte preceded a name's length field by GUESSING from
plausibility (if the raw u32 didn't look like a valid length, assume a terminator is in the
way and skip one byte) rather than knowing the real, unconditional rule — **exactly one
terminator byte follows the long name and the short name; the code name (last of the three)
has none before the trailer, always, regardless of what any of the three names contain**. The
guess is provably ambiguous exactly when a short/code name is genuinely EMPTY (allowed since
the 2026-09-17 fix) and its own preceding terminator happens to be `0x00`: four zero bytes
(imaginary terminator + the true zero-length field) reads identically to the zero-length field
alone, so the terminator is silently never skipped and the trailer misaligns by 1 byte. Found by
name: cid 172 "Welsh First Division", a real, clean top-flight-adjacent league (reputation 19)
with an empty code field, dropped for exactly this reason. Fixing the walk to consume the
terminator unconditionally (no guessing) recovered 134 more real competitions on this save with
**zero losses and zero changed records** elsewhere (verified candidate-for-candidate against the
old heuristic). Combined with raising the name-length cap 45→60 (`Northern Amateur Football
League Premier Division`, 51 chars, among 40+ real names the old cap silently dropped),
allowing a lowercase first letter (`cinch Premiership` — cinch is Scottish football's actual
sponsor, deliberately lowercase-branded) and widening the continent check to accept the
`0xFFFF` "no confederation" sentinel (used by genuinely global competitions like `Club World
Championship`/`Confederations Cup`/`World Cup`, not just type-9 friendlies as originally
assumed) recovered 75 more.

**2026-09-18, round 3 — the rewrite.** Chasing gate fixes one collision at a time (the BVI
nation-table hit, then a further collision with a newly-found continent-name table adjacent to
nations — see #9 — then a stray "Team of the Week" false anchor) was visibly the wrong shape of
work: every fix bought a few more real records at the cost of a new, narrower blind spot
elsewhere, because a plausibility gate can only ever be as good as the noise it happened to be
tuned against. The actual fix was structural and had been sitting in the bytes the whole time:
**the table announces its own start and size.** A run of `0xFF` filler is immediately followed
by a `u16` giving the table's own declared record count (`0x055c` = 1372 on this save, exactly
max real cid 1371 + 1), then record 0 begins. `_comp_table_anchor` locates this (confirmed, not
guessed, by walking to record 1 and checking its cid reads back as 1), and `_walk_comp_table`
then reads every one of the `count` records by pure arithmetic — name lengths, the terminator
rule above, and a variable trailing block (below) — with the walk's own loop index as cid the
ONE structural assertion (raises on mismatch rather than silently drifting). **No plausibility
gate at all.**

**The gate cascade is DELETED, not kept as a fallback** (2026-09-18, round 4 — the review pass).
It shipped for one day as a "same-save-family fallback for a save where the anchor can't be
found", and the review asked the obvious question: does that save exist? Measured on all 34
archived saves across BOTH careers, the anchor resolves and the walk reads every declared slot
exactly — Frem 1372 = 1272 named + 100 blank, Bucaspor 1371 = 1271 + 100, `cid == i` throughout
every one. So the fallback was dead code, and a dead fallback is not insurance: it is a second,
untested definition of what a competition record is, which is precisely what had been quietly
costing real records all along. Gone: `_eval_comp_candidate`, `CompCandidate`, all twelve
`COMP_REJECT_*` reasons, the two-tier reputation arbitration, `_MIN_COMP_REP`, and the comp half
of `RefdataDiagnosis`/`diagnose_refdata_scan`. `_walk_comp_table` now raises `CompTableError`
(with the slot, the offset and the declared count) instead of returning `None` for a caller to
fall back on — and it raises on an unreadable name or a short read too, which the shipped
version let escape as a bare `UnicodeDecodeError` past a `_build_refdata_index` that caught
neither. `COMP_TYPES` also lost `21: "continental_cup"`: `type_id` is the real field, the label
is a display convenience for the five values with sourced names, and 21 had been named off a
single chat observation.

The walk immediately explained every remaining "missing" cid without adding a single new gate:
of the 1372 declared records, exactly **1272 are real (named) and 100 are genuinely blank**
placeholder slots — `namelen` 0, a structured `2,000,000,000 + n` uid counter completely
distinct from real competitions' `200,000,000 + cid` range (96 in one contiguous block,
cid 1242-1337, plus 4 scattered one-off placeholders sitting right after individual nations'
own reserve-group blocks, e.g. cid 1341 right after Belgium's 3 reserve groups). These were
never a scanner defect; they're slots the game itself never populated, and the walk reads them
exactly as easily as a named record because it never depended on name-shaped content to find
the next one. `tests/test_refdata_scan.py` pins the exact split (1272/100/1372) plus every
competition a since-fixed bug used to drop.

One coincidental side effect surfaced and is now moot: widening the continent/name-length/shape
gates during round 2 briefly let a `cid=24931 'World'` resolve — the 7th entry of a genuinely
real but different table (the continent-name table right after nations, see #9), not a
competition at all. The pure walk never reaches that region (it stops at cid 1371, right where
the file's own count said it would), so this never had to be fixed as its own gate; it just
stopped being reachable.

Two gaps remain — one football-domain, one structural:

- **`is_competitive` (`competition NOT ILIKE '%friend%'`, in `mart.py`) conflates cup and
  league.** A real, already-decoded type byte exists per competition (`COMP_TYPES` for the ~6
  named values, `type_N` for the rest, surfaced as `mart.competitions.kind`) and every `comp_id`
  Frem's own matches reference resolves it with zero gaps — so this isn't a decode gap, it's
  that `scripts/derive_weight_set.py`, `scripts/export_attribute_lab.py`, and the main query in
  `scripts/attribute_stat_correlations.py` filter on `is_competitive` alone, pooling Sydbank
  Pokalen (16 games) into "league form". Fix: join `comp_id` to `mart.competitions.kind` instead
  of the string heuristic, and add `is_league`/`kind` to `mart.matches`/`mart.match_player_facts`.
- **The block after the 14-byte trailer is now DECLARED and its field ORDER corrected; the
  8-byte entries are still unnamed.** `docs/agent-context/fmm-editor-record-comparison.md`
  is updated to match (it used to say "we parse about half"); this region is very likely
  fmm-editor's **3-season Rank/Year history** (and possibly the **Qualifiers table**). Solved
  for WIDTH and ORDER: `[n_entries u32][n_entries × 8 bytes][21-byte fixed tail]` =
  `25 + 8 × n_entries`,
  now declared in `scripts/audit_records.py` as `comp_history_count`/`comp_history_entry`/
  `comp_history_tail`.

  **The order above is a CORRECTION of what this item previously claimed** (`[count][3 stat
  u32][entries][3 season u16][1 tail byte][2-byte pad]`), and of the first attempt to declare
  it as a contiguous 25-byte head with the entries after it. All three orderings give the
  identical record length, so the walk's arithmetic cannot separate them and neither could any
  amount of checking that the walk lands on `cid == i`. Only content can: on the 914 records
  across the archive that actually carry entries, the three-`u16` season triple reads as a
  plausible year (1990-2060) at `record_end − 9` on **686** of them and at `head + 16` on
  **zero**. So the entries come immediately after the count and the fixed tail ends the record.
  This is worth remembering as a method note — 1,348 of 1,372 records have `n_entries == 0`,
  where every candidate ordering coincides, so the majority of the data could not have
  distinguished them and a spot check would have confirmed whichever guess was made first.

  NOT solved for MEANING. The tail's three `u32`s pair with the three seasons as parallel
  arrays (exactly fmm-editor's Rank[3]/Year[3] shape) but do not resolve as club tids — 3F
  Superliga's read 505/526/507, which come back as 'Southend United'/'Wigan Athletic'/'St.
  Albans City' — so they are carried as UNKNOWN rather than named. The 8-byte entry is the same
  story with a tempting near-miss: `[u32 value][u16 season][u16]` holds for 21,440 of 25,758
  entries (every entry of 'European International League Division A/B' steps through seasons
  correctly) and fails for the other 4,318, where Major League Soccer's entries after the first
  read season 0. 83% is a guess, not a decode. An in-game competition-history screen for a
  competition whose entries break the pattern would settle it in one reading.

### 11. `mart.club_managers` isn't purely structural
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

## Quality

### 15. Every test skips silently and exits 0 without a save
So a clean clone runs the suite, sees green, and has tested nothing. The suite is save-dependent
by nature; the fix is to make absence *fail loudly* or report SKIPPED in a way CI can count, not
to pretend it passed.

---

## Football (the actual career)

### 16. Position write-ups still owed
Zac asked for the position-by-position read for **DM, CM, AML, AMC, AMR and ST**, plus a verdict
on the **4-1-2-2-1** question. GK/LB/RB/CB were delivered. **The earlier analysis is several
seasons stale** — it was written when Frem were in NordicBet Liga; they have been in the **3F
Superliga (tier 1, cid 2) since 2025** and the store now runs to **2027 / 2026-07-02**. Redo the
read against the current squad rather than resuming the old one.

### 17. Apply the pure-structural-walk fix to the club table and the audit tooling
The competition table's 2026-09-18 rewrite (#10) replaced a candidate-scan-plus-gates approach
with a pure structural walk once the table's own start and declared record count were found in
a hex dump — no plausibility gate needed at all, and it immediately explained every remaining
"missing" cid as a genuinely blank slot rather than a scanner defect. Two follow-ups this
opens, both explicitly requested along the way and not yet done:

- **The club table is still gate-based** (`_eval_club_candidate`). It shares the exact same
  candidate-scan architecture the comp table moved away from, and the review pass MEASURED the
  exposure rather than leaving it as a suspicion: with `_candidate_positions`' nation-table and
  name-table exclusions removed, the club scan admits **191 extra "clubs" on frem-2026-06-11**
  — 'Angola', 'Botswana', 'Egypt', 'Ghana', 'Sint Maarten', 'Réunion' and the rest of the
  nation table, each under a nonsense tid (393218, 1376257, …) — plus tid 4294967295 resolving
  to 'Rajagobal', the browse name table's own first entry. The exclusions cost zero real clubs,
  so they stay, but **a scan that needs whole regions fenced off to stop inventing records has
  not found its table's structure yet.** Note the club table still yields tid 4294967295 even
  WITH the exclusions, which is a live wrong record, not a hypothetical one. Worth checking
  whether the club table also declares its own start/count the same way (a preceding filler run
  + a count header) before assuming it needs a scan at all — that is all it took for comps.
- **The audit tooling's comp half is DONE** (2026-09-18, review pass) — recorded here because
  the generalisation is still owed. `scripts/audit_declared_scans.py` was printing comp tier
  counts and per-gate reject costs, including the line "fixing this gate alone would recover
  exactly this many", for a code path `_build_refdata_index` had already stopped calling: an
  audit describing a dead path, which is worse than no audit. It now reports the walk's own
  invariant instead (`named + blank == the count the table declares`) and classifies a
  cross-reference miss structurally — either the cid is past the end of the declared table
  (2 such on frem-2026-06-11: 64735 and 65280, dangling references out of club `league`
  fields) or the table itself declares that slot blank. `scripts/audit_coverage.py` claims the
  comp table MEASURED per record via a new `reference.comp_table_spans`, 149 KB that the old
  AUDITED window claim never covered at all. **Still owed: the general version** — a
  structural, business-logic-free anomaly check applied to every keyed table, asserting the
  resolved id set is CONTIGUOUS from 0 regardless of what any gate says. `audit_records.py`'s
  EXTENT check already does exactly this for `city` and `stadium`; competitions now satisfy it
  by construction; clubs are the table that still needs it, and cid not being sequential in the
  old comp output should have been this kind of flag and was checked nowhere.

---

## Housekeeping (safe to do any time)

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
