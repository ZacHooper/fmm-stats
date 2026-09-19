# Whole-file map: `frem-2026-06-11.fms` (63,936,873 bytes)

**2026-09-19.** A single reference save, walked start to end, with every section and table this
project currently knows about — named or not, decoded or not. Chosen because it's the save
today's exact history-slab/club-records/matches work already used, and the one
`tests/test_club_records.py` and `tests/test_match_slots.py` hold ground truth against.

**Read the provenance column before trusting an offset.** Three different standards are mixed
here on purpose, because that's honestly the state of the knowledge:

| tag | means |
|---|---|
| **live** | Located this session, on this branch, by calling the real parser function against this exact save. Exact. |
| **branch** | An existing, already-merged function on this branch, called live against this save (same standard as **live**, distinguished only because it predates today's work). |
| **PR58** | From `docs/table-framing.md` on the **unmerged** `docs/table-framing` branch — real work, not on `main` or this branch yet, and **measured on `frem-2023-07-02`, a different save**. Treat every PR58 offset as approximate for this file; the reference database is known to drift on the order of 10⁵–10⁶ bytes between saves three years apart. |
| **const** | A hard-coded constant in `fmparser/regions.py`, not re-derived this session. Known to drift per save/career — see that file's own comments. |
| **gap** | Not identified by anything currently in the codebase. |

## The map

| start | end | size | what | status | provenance |
|---|---|---|---|---|---|
| 0 | 515,797 | 0.516 MB | **browse name table** — 45,942 flat `[len][utf8]` entries, nation-grouped | named, decoded | live (`reference._name_table_bounds`) |
| 515,797 | ~3,800,000 | ~3.28 MB | filler + unexamined | unnamed | gap |
| 3,800,000 | 6,600,000 | 2.80 MB | **global attribute section** (player attributes, staff attributes, plus several small sub-tables below) | mixed | const (`regions.ATTR_LO/HI`), refined below |
| — player attributes sub-table | | | 26,505 declared records (PR58), all player CA/attributes, keyed by sid | named, decoded | PR58 (offset from 2023-07-02: record0 ≈ 3,996,823) |
| 6,006,370 | 6,287,369 | 0.28 MB | **staff attributes + the small unnamed tables that chain after it** (staff grid, three 7-byte index tables, one 99-byte table, a 273-entry round/leg-names string table) | staff: named; three 7B tables, 99B table: **unnamed**; round/leg names: unnamed | live window (`staff._discover_window`); internal sub-table breakdown is PR58 only (not re-split on this save) |
| 6,340,458† | 12,626,905† | ~6.29 MB | **club + national-team table**, `tid == slot index`, 11,331 declared records — the single biggest table in the file, spans this whole stretch | **named, decoded**, still gate-based in code (TODO #17) | PR58 (†offsets from 2023-07-02) |
| 12,607,199 | — | (1,372 records) | **competition table anchor** — pure structural walk, no gates (TODO #10, already merged) | named, decoded | live (`reference._comp_table_anchor`) |
| 12,756,279 | 12,795,841 | 0.04 MB | **nation table** (251 declared per PR58; 227 read here — the known `nat_len` gap, TODO #9) | named, decoded (partially) | live (`reference._nation_table_bounds`) |
| 12,796,123 | 13,471,710 | 0.68 MB | **stadium table**, 15,987 records | named, decoded | live (`places.scrape_stadiums`, offset span) |
| 13,471,776 | 13,690,876 | 0.22 MB | **city table**, 10,956 records | named, decoded | live (`places.scrape_cities`, offset span) |
| ~13,711,352‡ | — | (807 records) | **award table** ("Footballer of the Year" etc.) — shares the club/comp record shape, is what makes 153 low club-tids resolve to award names (TODO #17) | named, undecoded beyond identification | PR58 (‡2023-07-02 offset) |
| 13,965,521 | — | (173 declared, 94 read) | **currency table** — the known `uid > 4096` gap (TODO-adjacent, table-framing) | named, decoded (partially) | live (`lookups.scrape_currencies`, first-record offset) |
| 13,976,136 | — | (124 declared, 77 read) | **language table** — the known empty-`OtherName` gap | named, decoded (partially) | live (`lookups.scrape_languages`, first-record offset) |
| ~13,990,354† | — | (888 records) | unnamed 7-byte gappy id-list, ids 1..3221 with gaps | **unnamed** | PR58 |
| 16,000,000 | 40,000,000 | 24 MB | **contract-detail records window** (unwindowed scan in practice; wage/expiry records, `[tid][0x01][wage u16][…][expiry date]`) | named, decoded | const (`regions.CONTRACTREC_LO/HI`) |
| 16,692,615 | 20,321,452 | 3.63 MB | **tagged data dictionary** — self-describing `[tag][0x01][type][value]` fields (config/rules, e.g. fixture rules) | named, decoded | live (`tagged.find_tagged_region`) |
| ~36,360,000–36,940,000† | | 0.58 MB | **transfer-history record** — decoded, not wired into `extract.py` (`docs/transfer-history-record.md`) | named, decoded | PR58 offset / existing doc |
| 40,042,185 | 40,141,560 | 0.10 MB | **away-first match-slot table** (`matchslots.py`) — exactly 3,975 slots on every Frem save, a genuine fixed pool | named, decoded | live (`matchslots.locate`) |
| 40,141,778 | ~40,470,000 | ~0.33 MB | **surname id-table**, walked 28,624 of 32,148 declared (the walk stops at the first free slot; declared count is exact per PR58) | named, decoded (partially) | live (`reference._discover_id_tables`) |
| 40,656,158 | ~40,962,000 | ~0.31 MB | **first-name id-table**, walked 15,366 of 19,128 declared | named, decoded (partially) | live (`reference._discover_id_tables`) |
| ~40,962,000 | 42,630,105 | ~1.67 MB | **nickname id-table** (9,480 declared, never opened — `_discover_id_tables` only returns the two largest tables) sits somewhere in here structurally, exact position not re-derived on this save | **known to exist, unnamed in code** (TODO: nicknames never resolved — 2,424 people show under the wrong name) | PR58 (position inferred, not measured, for this save) |
| **42,630,105** | **46,876,873** | **4.25 MB** | **player-history slab** — 265,423 rows, exact on every save regardless of career length; pointer-forest structure, recycled not grown | named, decoded | **live, today** (exact parameter-free forest proof) |
| 46,876,873 | 46,877,082 | 209 B | fixed handoff gap, exact on 3 saves tested | — | **live, today** |
| **46,877,082** | ~48,163,009 | ~1.29 MB | **club-records** (Team Records + Player Records per club) — append-and-shift, grows every season, NOT a fixed pool (refuted a 2-save coincidence with a 3rd save) | named, decoded | **live, today** |
| ~48,163,009 | 52,721,064 | ~4.56 MB | **trailing per-club "empty slot" table**, stride 70, `e4 07` (year 2020) empty sentinel — also append-and-shift, shares one growing envelope with club-records above it | **unnamed** | **live, today** |
| 52,721,064 | 52,744,230 | 23,166 B | genuine `0x00` filler | — | **live, today** |
| 52,744,230 | ~55,839,667 | ~3.10 MB | **unidentified** — not investigated this session | **unnamed** | gap |
| ~55,839,667 | ~56,173,268 | ~0.33 MB | **our matches** — rich per-match stat blocks (home XI + away XI, 54-byte player blocks), delimiter-clustered; append-and-shift **within a season**, wiped at season start | named, decoded | **live, today** + existing `matches.py` |
| 56,173,268 → +550 B | | 550 B | exact `0xFF` wall, identical regardless of match count (9/43/59 matches all show it) | — | **live, today** |
| 56,314,027 | (grows one record/season) | 65 B/record | **per-season table**, `[flag u8][value u16][tid u16][year u16]`, tid constant at our own club, one record per season since 2021 | **unnamed** | **live, today** |
| ~56,314,300 | 61,896,648 | ~5.58 MB | **unidentified** — not investigated this session (map_regions.py's coarse skeleton lumps this into the same catch-all "binary pages" bucket as everything from 16.7M onward, so its own label carries no information here) | **unnamed** | gap |
| **61,896,648** | **62,002,727** | **0.11 MB** | **squad snapshot** — full names + all 23 attributes + feet, managed club only | named, decoded | live (`attributes.snapshot_bounds`) |
| 62,002,727 | 63,936,873 | ~1.93 MB | unexamined tail — `map_regions.py`'s coarse skeleton calls the whole 53.5–63.9M stretch `inline_names` (662 player records, first at ~56.3M) but that label is now known to be too broad: it's spanning the matches region, the per-season table, and the real snapshot all at once | unnamed | gap (superseded coarse label) |

## What this map makes obvious

- **The reference database (roughly 0–41M) is comprehensively named**, even where individual
  fields inside a table aren't fully decoded (nations, currencies, languages). The one real gap
  in this half is the nickname id-table, which is *known to exist* but has never been opened by
  code — a one-line fix (return three tables from `_discover_id_tables`, not two) rather than a
  research problem.
- **The career half (41M onward) is far patchier.** Two genuinely fixed pools now confirmed
  (history slab, matchslots), two append-and-shift structures now proven (club-records, our
  matches), and **two entirely uncharacterized gaps totaling ~8.7 MB** (52.74M–55.84M and
  56.3M–61.9M) — more than a tenth of the whole file, sitting between structures we understand
  well on either side.
- **`map_regions.py`'s coarse skeleton is not a substitute for this.** Its top-level split
  labels almost the entire 16.7–52.7M stretch a single generic `"binary pages~49B"` blob and the
  53.5–63.9M stretch a single `inline_names` blob — both spans this map now shows hold at least
  four and three genuinely distinct structures respectively. Useful as a first-pass filter for
  where zero-runs are, useless as a description of what's actually there.

## Reproducing this map

Every `live`/`branch` row was produced by calling the named function directly against
`~/fm-saves/frem/frem-2026-06-11.fms` (fetch via `rclone copy r2:fmm-stats/saves/frem/frem-2026-06-11.fms.gz .`
then `gunzip`). No new script was shipped; each call is a one-liner against the existing
`fmparser` modules named in the table. Re-run against a different save to see how much drifts —
per `career-region-sizing.md`, expect the reference-half offsets to move by the low hundreds of
thousands of bytes per year of career, and the two proven-fixed structures (history slab,
matchslots) to keep their row counts exactly.
