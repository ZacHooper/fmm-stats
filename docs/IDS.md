# ID map — what identifiers exist and how they link

The save is a web of entities joined by IDs. This is the inventory of every ID we've
found, what it keys, and which joins are solved vs open. Use it to anchor future digging.

## Entities & their IDs

### Player  (info record, ~whole file; the identity spine)
| id | size | notes |
|----|------|-------|
| **TID** | u32 | primary player key, used in matches, snapshot, everywhere |
| **UID** | u32 | global unique id |
| **SID** | u16 (stored in 4 bytes) | → the global **attribute** record. `ffffffff` = staff (no player record) |
| **history head** | u32 | at `P-38` in that same attribute record → the player's career-history chain. See below |
| firstNameID / lastNameID | u32 | → name string table — **UNRESOLVED** (not a flat index) |
| nationality_id | u16 | 173 = Turkey |
| club_tid | u16 | → **Club**.TID |

### Club  (club record, ~7–13 MB)
| id | size | notes |
|----|------|-------|
| **TID** | u32 | primary club key. Big clubs have low TIDs |
| **UID** | u32 | |
| nation | u16 | first field after the 3 name strings |

Known anchors (found by name): Galatasaray **955**, Fenerbahçe **954**, Beşiktaş **951**,
Trabzonspor **961**, Liverpool **356**, Bucaspor **6567**, Karacabey **6353**.

### Competition  (comp record, ~13 MB)
| id | size | notes |
|----|------|-------|
| **cid** | u16 | primary comp key. 228 = Turkish 2. League White Group |
| **uid** | u32 | 463485 for cid 228; reserve leagues ~2e8 |
| type / nation | u8 | bytes after the name strings (league/cup/reserve/friendly; 173) |
| **compref** | u16, `0x40xx` | the id used in **fixtures/results** — a THIRD, compact comp id. NOT equal to cid. e.g. one confirmed Super-League result had compref `16512` (0x4080) |

### Nation
`nation_id` u16 — 173 Turkey. Others seen: 145, 158, 159, 175, 177 (loaded/scattered).

## TID RECYCLING — a tid is a SLOT, not a person (measured 2026-08-19)

**FM reuses a retired person's tid for a newgen.** This is not rare: **829 identity changes in
`fm-frem.duckdb` and 1,503 in `fm-buca.duckdb`** across the snapshots we hold. Any analysis keyed
on tid alone will silently splice two different people into one career.

**What a swap looks like** (means over 829 frem changes):

| | outgoing | incoming |
| --- | --- | --- |
| mean age | **41.3** | **16.9** (68% are exactly 16) |
| free agents (club 65535) | 789/829 (95%) | 25/829 (3%) |
| has attributes | 29/829 (3.5%) | 829/829 (100%) |

The outgoing side is usually a **dormant record** — a long-retired name carrying no attributes, no
positions and no club (e.g. tid 3733 was *Tab Ramos*, b. 1966, free agent, no attribute record at
all, before becoming 16-year-old Hervé Buur). Outgoing ages are bimodal: ~32–41 (just retired) and
~53–67 (legends/managers). Swaps arrive in **off-season bursts** (frem: 202 at 2022-06-26, 296 at
2023-06-26, 128 at 2023-07-01) — the newgen intake. Mid-season snapshots see almost none.

**NOTHING about the previous occupant carries over.** Measured over the 1,098 swaps where the
outgoing identity was a real player with attributes:

| inherited? | match rate | chance level | verdict |
| --- | --- | --- | --- |
| primary position (fam>=15) | 12.4% | ~10% (13 positions) | **no** |
| goalkeeper vs outfield | 79.5% | ~79% (GKs are 12%) | **no** — GK->ST/DR/DMC is common |
| preferred foot | 65.1% | **65.3%** | **no** — dead on chance |
| nationality | 17.7% | — | **no** |

Beware the tempting coincidence: De Clercq (AMC:20, ST:14) -> Nordberg (AMC:20, ST:15) looks like
inheritance and is not. The tid is simply a free slot.

### Use `(tid, dob)` as the person key — never `tid` alone

**`dob` separates every single recycled slot: 2,332 identity changes across both stores, 0
collisions, 0 nulls (100%).** Name works too but is mutable and non-unique; dob is neither.

This matters beyond dedup: keying on tid alone forces a choice between the two people, so a
**player who retires out of our own squad loses his history the moment a newgen takes his slot**.
`(tid, dob)` keeps both as distinct persons, so retired players' match stats, injuries and
attribute history stay queryable instead of being overwritten or discarded.

**IMPLEMENTED (2026-08-19), phases 1-2.** The loader materialises the bridge — no re-extraction
needed, since `dob` is already in every `players` slice:

- `staging.persons(person_id, tid, dob, name, first_seen, last_seen, slices)`
- `staging.person_slices(season, phase, tid, person_id)` — the join bridge for every fact table
- `person_id` is the stable VARCHAR `'<tid>-<dob>'` (`'<tid>-?'` when dob is unknown — 28 tids
  appear in match stats but in no `players` slice at all). Rebuilt wholesale by
  `load_duckdb.rebuild_persons()` after each load; cheap and idempotent.

`dashboard/db.py` helpers: `current_person_ids(tids)`, `person_history(tid)` (every identity that
has held a tid), and **`keep_current_person(df)`** — drops rows of any frame with season/phase/tid
columns that belonged to a previous occupant. It no-ops when no tid in the frame was ever
recycled, which is the common case. `_identity_snapshots` is now dob-based, with the old name
match kept as a fallback for stores built before the bridge.

Guarded so far: the Development attribute-history chart, `player_role_series`,
`squad_role_series`, `primary_position_map`, plus injuries/loans via `_identity_snapshots`.
Effect on frem: Nordberg's chart loses De Clercq's row (the false "Creativity 10 -> 8" regression),
and **Louka Pingel drops 6 attribute rows to 1** — his history was a retired GOALKEEPER's
(Stefaan Thieren). 46 of 48 of our players are untouched.

**Still TODO (phase 3):** `match_stats_rows` / `enrich_match_rows` / `player_match_totals` are
unguarded, but currently splice **0 tids** in either career (a recycled slot's predecessor almost
never played for us) — latent, not live. And retention: a retired player is still *dropped* from
the current tid's view rather than surfaced as his own person. Apply `keep_current_person` to any
NEW cross-save per-player join.

Frem's own youth intake, all on recycled tids:
`Roos Demyttenaere->Noyan Adelgaard`, `Tab Ramos->Hervé Buur`, `Thomas De Clercq->Johan Nordberg`
(all 2022-07-01), `Stefaan Thieren->Louka Pingel` (2023-07-01). Two of those four outgoing
identities WERE real players with attributes — De Clercq (AMC, rep 1750) and Thieren (a
**goalkeeper**, rep 3000) — so the "outgoing is always a harmless shell" assumption is false even
in a sample of four.

## PLAYER → CAREER HISTORY — the `P-38` link (solved 2026-08-19)

**The career-history table contains no player id at all.** Earlier sessions searched every
history row (and ±64 B around it) for tid/sid/uid as u16 and u32 and found nothing, and a
record's position is referenced nowhere else in the file. The link is real but it runs the
**other way**: the player's ATTRIBUTE record points at his history.

Anchored on `P`, the attribute-record pointer that `staging.scrape_attributes` already
computes (it scans a 78-byte grid for a structurally valid record and reads the SID at
`P-42`):

```
P-42  u32   SID                     <- already used, keys the attribute record
P-38  u32   HISTORY CHAIN HEAD      <- NEW: 0-based row index into the history slab
P      ...  15 position bytes, feet, CA/PA, reputation, attributes
```

So the full join is **`player.tid → info.sid → attribute record → P-38 → history row`**.

**Evidence (denmark-24-start.fms).** Of the 26,518 attribute records, 25,627 hold a value
inside the slab, and **25,627 of 25,627 are valid chain heads — rows with in-degree 0 in
the pointer graph — and all are distinct.** No heuristic scores that well by accident. The
~891 out-of-range values are players with no history yet (newgens).

**Why this matters.** Linking used to be positional: records are sid-ordered, so a banded
DP walked the sid-sorted player list guessing which records were interleaved staff. That is
now dead code — the pointer is exact, needs no ordering assumption, and works for players
whose records were relocated into recycled slots (where sid-ordering does not hold at all).

**Gotcha — do not re-derive `P` by hand.** `P` is the position `scrape_attributes` locks
onto, not the start of the record. Read the head via that scraper's `P`, or you will be off
by a multiple of 78 and silently return a *neighbouring* player's career — which, in a
youth-intake cohort of near-identical records, looks entirely plausible.

## Joins
- player.SID → attribute record  ✅ solved (staging + record sweep)
- player.SID → **career-history chain**  ✅ solved 2026-08-19 (`u32 @ P-38`, see § PLAYER → CAREER HISTORY)
- player.club_tid → club.TID  ✅ solved
- match/result: home_tid, away_tid, **comp** ✅ for OUR detailed matches (`[FF×8][home][away][cid]`)
- **club → league (whole DB)  ⚠️ OPEN** — the blocker. See below.
- nameID → player name  ❌ open (only own club, via snapshot inline names)

## The club→league problem (open)
- Top leagues (Super League, Premier League) ARE simulated but store only **light
  results** (teams, score, date, table position — no clickable detail). Only the
  managed club's games have the detailed `[FF×8]…` records.
- The light-result record IS decodable — one confirmed: `[..00 FF..][home:u16][away:u16]
  [scoreH:u16][scoreA:u16][compref:u16(0x40xx)]` → `1693 (Alanyaspor) 1-0 1368
  (Başakşehir), compref 16512`. But a reliable whole-file sweep isn't cracked: the
  `00 FF` anchor is too common (false positives), records are scattered, and the layout
  isn't consistent across all hits.
- **compref (0x40xx)** is the most promising league key — but we can't yet (a) sweep
  light-results reliably, nor (b) map compref ↔ cid ↔ league name.

## Sources useful for digging
- **Tagged schema region (~13–20 MB)** — a self-describing data dictionary: field names
  stored reversed (`comp`, `level`, `cash`, `ntms`, `team`, `id`, `stdt`…). Reveals
  record layouts. See `fmparser/tagged.py`, BUGS #13.
- **Known club names → TIDs** — the strongest anchor (used to find the clubs above).
- `data/rough-guide.md` — community hex guide.
- **Ground truth**: our own matches (exact home/away/score/comp/date) and the
  screenshots in `data/screenshots/` (e.g. a Super-League results day with positions).

## Reliable grouping without club→league
CA is a universal cross-league scale. Every club has players with CA, so
**mean-CA-per-club** ranks all clubs globally *now*, without needing league labels —
the pragmatic route to "what level is my team".
