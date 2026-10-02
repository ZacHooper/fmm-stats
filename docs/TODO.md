# TODO — the one doc you read to resume

**Where the project is, and everything still open.** If it isn't here, it isn't outstanding.
The other files in `docs/` are *reference* — record layouts, rules, dead ends already measured —
and you read them when a task sends you there.

When you finish something, **delete its entry**. Do not tick it off, and do not leave a
"CLOSED" note: what was learned goes into the reference doc the entry points at. Item numbers
are for conversation only and are renumbered freely; never cite one in code or a commit.

Last reviewed **2026-09-30**, after the framework goal closed: every table on `core`, and every record's padding measured by a table walk.

---

## Where the project is

Reverse-engineering **Football Manager Mobile 2022** `.fms` saves into a DuckDB store and a
static web app, to manage a career with real data. The repo has three functions, and this file
is organised around them:

| function | code | job |
|---|---|---|
| **Parser** | `fmparser/`, `extract.py` | get the data out of the save into JSON, table by table |
| **Stats** | `load_duckdb.py`, `fmstats/` | clean and join the data within a save and across saves |
| **Site** | `site/`, `scripts/export_data.py` | a human-friendly view of the mart |

**The parser is the focus.** Every table is on the `core` framework
([`parser-architecture.md`](parser-architecture.md)), and every record a table reads has its
padding measured. What is left is new bytes (every byte of the save processed), then, a much
longer tail, understanding the bytes already read -- and moving the joins out of extract.

| | |
|---|---|
| career | **Boldklubben Frem** (Denmark, `--career frem`, managed tid 346, reserves 7296) |
| store | `fm-frem.duckdb`, latest snapshot **2027-08-08** (published copy on R2; `fmq.py` reads it by default) |
| division | **3F Superliga** since 2025, after three straight promotions from 3. Division |
| tactic | **4-2-3-1**, rated with `frem_minmax_4231` |
| hold-out | **Bucaspor** (Turkey) is archived, and is the only cross-career parser regression test |

### Reading the data without getting it wrong

Live traps, each of which has produced numbers that looked fine and were not:

- **Score an attribute on the population that HAS it.** A keeper attribute sits at the display
  floor for an outfielder, so pooling made Communication read 92.4% when it scores 3.0% on
  actual keepers.
- **The decoder's ceiling is 94.8% exact / 98.7% ±1, not 100%** ([`ca-weighting.md`](ca-weighting.md)).
  Current state: 59.4% exact on Frem, 59.5% on the Bucaspor hold-out, for the nine outfield
  entangled attributes.
- **Joining a per-(season, phase) dimension on (season, club_tid) fans every fact out by the
  snapshot count.** Frem's 19 home games read as 95.
- **`any_value(x ORDER BY y)` does not order in DuckDB.** `max_by(x, y)` does.
- **`mart.club_attendance` is our-matches-only** — read `n_games` before trusting `avg_att`.
- **A tid is a slot, not a person** — check `DISTINCT dob` per tid before telling a story
  about one ([`agent-context/tid-recycling.md`](agent-context/tid-recycling.md)).

### Where to look

| you want | read / run |
|---|---|
| how the parser is organised, and how to hook up a table | [`parser-architecture.md`](parser-architecture.md) |
| where every byte of the file lives | [`savefile-map.md`](savefile-map.md) |
| which bytes no parser reads | `uv run python scripts/audit/audit_coverage.py` |
| the per-byte schema of every declared record | `uv run python scripts/audit/audit_records.py --map` |
| whether a region is text, records or compressed | `uv run python scripts/audit/entropy_profile.py <save.fms>` |
| count-framed tables, and the dead ends of that search | [`table-framing.md`](table-framing.md) |
| the compressed archive and the fixture list in it | [`save-archive.md`](save-archive.md) |
| the attribute decoder, and what is ruled out | [`attribute-model.md`](attribute-model.md) |
| deploying the site | [`DEPLOY.md`](DEPLOY.md) |

---

## Parser — coverage: every byte processed

On `frem-2027-08-08` (61.7 MB): 38.3% filler, 41.7% read, 0.8% declared, **19.1% unclaimed**
(`audit_coverage.py`). The gaps, largest first, with what is known about each:

### 3. The unclaimed regions of the career half
- **54.21–59.27 M** (5.1 MB) — around our match region. Unexamined. One populated
  player-list block sits in this stretch on older saves (`Jeppe Corfitzen` at 56,336,372 on
  `frem-2026-06-11`), so start with #4's structure.
- **53.99–54.14 M** — straight after the training table (0.16 MB). Unexamined.
- **Straight after the club-records table** (46.66 M on `frem-2027-08-08`): `[count u32]` =
  162 on every save, then variable-length rows carrying 21-byte matches shaped like the club
  team records (`[f32 value][year][day]…[club][opp][for][against]`). Likely the competitions'
  own record books. Walk it from its count, as the club records were.
- **34.12–38.53 M** — the transfer band ([`transfer-history-record.md`](transfer-history-record.md):
  decoded, not parsed).
- **13.96–16.68 M** — 85% filler, no count headers; and **13.68–13.96 M** before it.
- A **stride-65 per-season table** (`[flag u8][value u16][tid u16][year u16]`) right after the
  550-byte `0xFF` wall that ends our matches; settle whether it is `table-framing.md`'s
  per-season series near 44.6 MB.

Numbers drift per save; re-run `audit_coverage.py` before starting on one.

### 4. Player lists: what is still unread
`tables/player_lists.py` reads all 66 lists, identified against the game's screens on
`frem-2027-06-15`: 0–30 the World Best XI pool of each season, 31–61 the Manager's Best
Eleven pool of each season (every player who played for the manager, loanees included; it
follows the manager, not the club), 62/64 and 63/65 the World and Manager's All-Time pools.
Each entry is a **scrapbook entry**: the player's Scrapbook Profile as of its date
(Nuamah's and Mikkel Andersson's 2022 entries verified field by field). Every entry is in the
store (`raw.player_scrapbook`); `int.scrapbook_entries` picks each player's latest in our club lists, and `int.managed_squad` says who is ours. Open:
- **Which copy of each All-Time pair is live**: 63 carries this season's "New Entry" dates,
  65 last season's. Confirm across a season boundary.
- **Unread bytes**: which of the three "1 Jan 2021" dates (+4/+12/+16) is the profile's loan
  end and what the other two are; +22..+27; attribute-block indices 9 and 35; the u32 at
  +83; +95 (4 bytes), +103 (5), +117 (3); the 46 bytes at +122; the trailer's first byte and
  11 more bytes. The profile's up/down arrows beside some attributes (a change since an
  earlier value) are somewhere unread: compare two profiles of one player. Squad number is not stored (the
  profile's card is live: current club and number).
- **Kits on the Best Eleven screens** are drawn from the snapshot's registration club's kit
  record (Nuamah in FC Nordsjaelland's, a goalkeeper in the club's goalkeeper kit), not from
  the snapshot: its `colour_1`/`colour_2` are the team he played FOR (Frem, for every
  loanee). The kit STYLE is the first of the two unread flag bytes before each of the club
  record's six kits (`tables/clubs.py` `_kit_fields`): Liverpool's plain home kit is 01,
  Frem's red/blue stripes 31, Barcelona 30, Newcastle 25, FC Nordsjaelland 0c, Frem's
  goalkeeper kit 0d, ff an unused kit. Name the ids from kits whose design is known; the
  second byte (00/01/02) is unread.
- **Training table: the unread bytes and codes** (`tables/training.py`, `mart.training_focus`).
  Read and loaded: Focus Role, Focus Pos, attribute focus, intensity, for every player on
  every snapshot. Still open:
  - the 12 role names marked `inferred` in `seeds/roles.csv` (2, 8, 11, 18, 20, 22, 23,
    24, 27-29, 31). The
    quickest proof is to set a dozen players' Focus Role to each, save, and read the ids;
    `docs/role-ids.csv` names famous players holding each role for checking on profiles.
  - attribute-focus codes 0, 2, 4, 10, 12, 13, 15 (13 is the AI's most common, 5,067 players).
  - intensity 0 and 1: only 3 (High) and 2 (Normal) are read off the screen.
  - the Progress bar: a green fill, or a full yellow bar when the player is unlikely to improve
    further. Not the stored `pa - ca` (0 on yellow and near-empty bars alike); the green-fill
    rows are the ones with `+17` and `+41` non-zero. Diff two saves a few weeks apart.
  - `+8` u8, `+9`/`+13` u32 (money-like; `+9` round), `+31..36`, `+38`, `+40..48` and the
    three dates at `+49/+53/+57`. The row also carries the squad status (`+37` contracted,
    `+39` status), so it is a per-person status row as much as a training one.
  - surfacing it: each squad player's training focus on the site's Squad page.
- **Competition teams of the year are not snapshots**: the game shows only the current
  season's, and a player opens his live profile, so there is nothing stored per year to find.
- **Surface the World Best XI pools**: every season's pool is in `raw.player_scrapbook`
  (lists 0-30, 62/64); nothing reads it yet.

### 4a. Player progress: what is still unread
`tables/player_progress.py` hands every used row to `raw.player_progress` (the six lines
and the raw status included); the mart draws injury and loan spells from the bits. Open: the six
u16 skill lines at +4 (which line is which on the Player Progress graph), status bits 3 (8)
and 6 (64), and the 23 u16 at +24 (17 filled for an outfield player, 6 for a goalkeeper --
the week's attribute values?). Named, the table could give every squad player's weekly
development, not just injuries and loans.

### 5. Reference-half tables not yet read
- The unnamed count-framed tables in [`table-framing.md`'s register](table-framing.md#the-complete-register).
- The **Region** table, the unnamed bytes of the nation record (`NATION_TEAM`, `NATION_END`),
  and the ~7-entry
  **continent** table right after the nations (`[uid u32][Name][01][CodeName][Demonym][01]`,
  Africa..South America at ids 0–5, `World` at 6).
- The club record's unnamed stretches (`tables/clubs.py`): 20 bytes in `CLUB_STANDING`, 74 at
  the end of `CLUB_STAFF`, the `[u32 8][8 B]` block at +167, and the 9-byte tail items.
- The person record's unnamed bytes (`PERSON_MID`, three of each relationship's eight), and
  what its language `level` of 255 means.

### 6. Archive members and framing not yet read
[`save-archive.md`](save-archive.md) is the reference.
- `comp_hosts.dat` (31 KB, 4-year host cycles) and `rule_group.dat` (plain-text engine logs).
- `comp_<uid>.dat` beyond the stage list: prize money (`przm`, `wnpz`), qualification and
  seeding (`strq`, `advs`, `rank`), TV and scheduling (`tvds`, `drdt`).
- The archive's own framing: the two u64s ending each directory entry, `'sicomps'` and the byte
  after it, the `[08][00][00]` and u32 in the record header, the 13 bytes before member 0.
- **Which competition a fixture belongs to.** A `fix_man` fixture names its stage
  (`stage_key`, an index into `comp_man.dat`'s 78-byte stage grid) but no readable
  competition. The link was searched for on the 182 stage instances of our own matches (13
  competitions, every save) and found nowhere decoded: no fixture field and no stage-record
  field is constant within a competition and distinct between them, a stage's key sits in its
  own `comp_<uid>.dat` 42 times in 182 (6% background in the others), and `rgman.dat` /
  `rule_group.dat` hold the uid beside the key 14 and 16 times. Until it is found, the store
  labels a stage from our own match in it or from its teams' shared league
  (`dim_match.competition_source`). First place to look: the stage record's unread `+1..+30`.

### 7. The data dictionary's state between the rule files
The 667 rule files (`fmparser/tables/rule_files.py`) read 99.2% of their span and are identical
in every save of a career. The 26,878 bytes BETWEEN them are the part that changes (26 of 666
separators change from frem-2027-07-02 to frem-2027-08-08): the separator before each group
(`ffffffff`-led u16 entries ending `01`) and the 41-byte dated record before each nation's
merged `_rules`. Diff two saves.

---

## Parser — understanding: naming what is read

### 8. Decode the competition rules
Entry, advancement, promotion and relegation (`strq`, `advs`, `relr`, `prmr`) for every
competition in the dictionary, not just the ~70 the archive loads. Every configured archive
member names its dictionary file (`file`), so the two join. `docs/DATADICT.md` (deleted; last
at commit 7cc46b6) holds guesses at many tag meanings — hypotheses to test, not facts.

### 9. The standings record
A 14-byte record with the exact final position of every club in every loaded competition,
decoded but never parsed ([`standings-record.md`](standings-record.md)). The rebuilt league
tables (#13) make it less urgent for Denmark, but it is the direct way to settle Spain.

### 10. Unnamed fields in records we already read
- **Staff** `+34..+38`: five catalog indices. The six hidden staff attributes stay named by
  offset (fmm-editor has no `Staff.cs`); `hidden_s27` is the one to identify next — 85% of
  staff read 1–4, distinctive enough for a small ground-truth set.
- **Match event type `0x0e`**: 2 events, both reserve fixtures.
- **`att_avg` / `att_min` / `att_max`** in the club record: read correctly, but the names from
  fmm-editor fail every check (a 12,500 ceiling, multiples of 100, Barcelona's max below its
  avg). Not attendance — `mart.club_attendance` is. Carried in `raw.club_details` only.
- **Origin clubs**: 3,936 of 22,624 origin tids resolve to no club in `raw.clubs` —
  probably youth/academy or defunct clubs in another structure.
- **Career history** (`tables/history.py`): the history lines' `yellows` / `reds` are in `raw.player_history_seasons` but not yet in
  `mart.player_career_seasons` -- add them after the next publish, since the published store
  lacks the columns and the mart re-binds against it.
- **Drop the `mart.our_clubs` fallback**: the published store (rebuilt 2026-09-30) carries
  `career_managed_tid`, so the fallback in `OUR_CLUBS` (`fmstats/mart.py`) -- the club in the
  most named-competition matches -- has nothing left to serve. Remove it.
- **Surface Player of the Match**: `raw.matches.player_of_match` is the game's own pick,
  in the store since 2026-09-30; nothing reads it yet. Add it to `mart.matches`.
- **The match record** (`tables/matches.py`): the event's last 8 bytes (two u32, never a tid
  of the match), the player slot's 33 unnamed bytes (+54..61 two more u32; +2 equals the
  opponent's score on the goalkeeper's slot), the team head and tail (75 and 46 bytes), the
  body head's +19..51 and +67..77 (one u8 reads 90-96 on detailed matches: the final whistle's
  minute?), and our tactic in the tail: +0..32 small bitfields (team instructions?), eleven
  per-starter 8-byte items at +1196 (4 flag bytes and a value -- 10/9/6/5 -- that tracks the
  position: probably role or duty), a u16 coordinate grid at +220..1182 that changes with
  the back line, and team-looking u16 values after +1295. The positions at +102 are a second
  copy of +69, byte-identical on all 1,027 matches measured. A tactics screenshot for one
  match would settle the per-starter items.
- **The `RAW` spans the PADDING check uncovered** in the world fixture (11), the official
  (+24..28), the contract (+17..35, +40..82) and the competition history tail (4) records;
  the competition stage record (`comp_man_stage` +1..29, +50..55, and +72/+76, the second
  halves of the FourCCs at +70/+74); the competition rules header (+8..19, +26..29 an f32,
  +30..47).

### 10a. Every player's current-season stats by competition type (minor)
The Player History screen's "This Season" panel splits the current season into Non
Competitive / League / Cup / Continental / International, each with Pld, Gls, Ast, Yel, Red,
PoM and average rating, for ANY player -- so the save holds it per player, in a region not yet
identified. We have nothing like it: `mart.player_seasons` is built from our own match
reports, so it covers only games Frem played in, and no friendlies, internationals or PoM.
Use: proper league records (top scorers, cards, player of the match) for every league, not
just the games we watched. Find it with a screenshot and a save from the SAME in-game day:
Frederik Karlsen on 26 Sep 2027 read Non Competitive 2 apps / 1 ast / 7.50, League 4 apps /
1 yel / 7.00, Continental 2 apps / 7.50 -- take a second player with different numbers to
rule out coincidence, then search for the values next to his tid.

### 11. Read the season rollover from the game, not from `careers.py`
A save's campaign depends on the day its career's new season starts: Denmark 30 June, Turkey
20 June, measured from the managed club's record and set per career as `Career.rollover`. A
new career needs it measured again. The game holds it -- most likely each nation's calendar in
the data dictionary's rule files (#7, #8) -- so decode it there. The fixture list does not
change at the rollover, and no fixed-offset season field exists in the first 14 MB.

---

## Parser ↔ stats: decoupling

### 12. Extract dumps tables; the store models them
**Plan: [`plans/2026-10-01-data-layers.md`](plans/2026-10-01-data-layers.md)** -- 18 steps, one PR
each. Extract hands over every table as the save stores it (header dates, dead outputs, whole
reference tables, then contracts, names and person records, and a file-order cursor); the store
renames `staging` to `raw` and models it as raw → stg → int → mart, ending in the `dim_*` /
`fact_*` tables of [`data-model/`](data-model/README.md), and the site's marts move onto them.
Every step is gated row-for-row against a store built from `main`. Person identity (#14),
history reclamation (#15) and extra-time minutes (#16) block steps of it.

### 12a. After the plan: raw mirrors the save, one table per table
Low priority; do it once the data-layers plan is finished. Raw is still not one table per save
table:
- **Split by the loader.** `nations.json` becomes four raw tables (nations, ranking
  history, coefficients, languages), `clubs.json` five (`clubs`, `club_details`,
  `club_squad`, `club_staff`, `club_affiliates`) and the Club History table three
  (`club_records`, `player_records`, `club_league_history`). Fix: keep each as one raw table
  with its lists as `LIST(STRUCT)` columns, and unnest in stg.
- **Derived by the loader.** `raw.player_history` and `raw.player_history_seasons` are both
  walked from the history pool in `load_history`, and the fee codes are renamed there
  (`'stay'`/`'loan'`/`'free'`). The summary is only each chain's first and last line plus the
  head offset. Fix: `raw.history_rows` holds the pool as stored, an int model walks the
  chains from `history_head` (recursive CTE), and the summary becomes a view or goes.
- **Cut down by extract.** `competition_team_counts` is one field of each rule file, and
  `competition_rounds` flattens each `comp_<uid>.dat` member. Fix: dump `rule_files` and
  `comp_rules` whole.
- **Parsed but never extracted.** `officials` (match officials), `comp_honours` (roll of
  honour) and `comp_stages` (stages calendar) from `comp_man.dat`, and `match_slots`. Each needs
  an extract step, a raw table and a stg model.
- **Not parsed.** The transfer band's 143-byte records are decoded on paper
  ([`transfer-history-record.md`](transfer-history-record.md)) but have no parser module, and
  the save wipes them each July (#3).

---

## Stats

### 13. League tables outside Denmark
`mart.league_tables` rebuilds tables from the fixture list. Against each club's own
`last_league_pos` (the first snapshot of the next season), measured 2026-09-29:
Denmark 40/40 tables exact, Germany 23/26, England 85/121, Belgium 14/21, **Spain 0/48** (51 of
588 clubs agree — worse than chance, so a systematic error, not tie-breaks). Settle it on one
Spanish season against an in-game table before quoting any non-Danish table.
**`raw.club_league_history` is that table**: the game's own final position for every club
in every league season (`tables/club_records.py`; `year` is the season's start year). Check
the rebuilt tables against it, league by league, then consider serving finished seasons from
it directly.

### 14. Person identity across snapshots
- **`player_spells` holds a second, wrong name for some people** (Jonathan Bech also "Jose
  Almeida"); `mart.at_club_spells` is clean. Likely a recycled tid resolved at the wrong
  snapshot.
- **`is_staff` flipping to true empties a player's history** in that snapshot (tids 9231,
  9430). Both are in [`agent-context/tid-recycling.md`](agent-context/tid-recycling.md).

### 15. History lost to the pool's reclamation
The career-history pool is fixed-size; 25.2% of sids have a SHORTER chain in 2026 than on day one
([`table-framing.md`](table-framing.md)). Quantify it in the store (how many people have their
richest history in an older snapshot), and if material, union history across snapshots in
`fmstats/mart.py` — which also fixes the mart-only R2 object, where `player_career_seasons`
reads the newest snapshot only.

### 16. Match facts
- **Goals exceed shots** on 260 of 11,161 player-match rows (`goals > shotA`). Probably
  penalties or deflections; until settled, no conversion rate from these columns.
- **Extra-time minutes**: `mart.match_player_facts.minutes` caps at 90, so a full 120 reads
  90 and an extra-time substitute goes negative (Lucas Lodberg, 2023-02-22: −15). The flag exists
  (`extra_time` in `mart.match_stages`, for competitions we play); carry it to the minutes.

### 16a. Retire the stuck-loan workarounds
`raw.players.loaned_in` is now true only for a player in our squad arrays whose own record
names another club, so it clears when a loan ends. The mart and exporter still carry code for
the flag that never cleared: the "SET-ONLY" notes and the `ever_loaned_in` run exclusion in
`fmstats/mart.py` (`mart.at_club_spells`, "SECOND GHOST"), and the loan note in
`scripts/export_data.py`. Remove them one at a time on a rebuilt store, each gated by
`validate_mart.py` and a no-op `git diff site/api`.

### 17. Views that hide their confidence
- **`mart.player_origin`**: `eligible=False` cannot be told from *unknown* when the origin club
  does not resolve (#10). Add the distinction; until then treat it as "ask Zac".
- **`mart.club_managers`**: a sole structural hit and a `home_reputation` fallback look the
  same. Expose the candidate count.

### 18. Models
- **Refit the transfer-value model** with `current_reputation` and `world_reputation` (parsed,
  unused; `fmstats/value_model.py` fits on `reputation` alone).
- **Attribute decoder** ([`attribute-model.md`](attribute-model.md) — read its "ruled out"
  section first): the misses are bias, not noise (`|mean signed error|` vs exact rate −0.91),
  and good players are under-predicted (83.6% exact at true 4–6, 22.4% at 16–20). Re-test two
  near-misses on the larger store: feet for Dribbling, height/weight for Shooting.
- **Retrain on time-aligned rows.** Our squad's "exact" attributes and value are scrapbook
  entries (`tables/player_lists.py`), dated by `scrapbook_date`, and a
  player who has not played this season carries one up to two years old. Both fits pair an
  entry with the CURRENT save's record bytes, CA and reputation
  (`scripts/fit_attribute_model.py` joins `raw.players` to `player_attributes_exact` on
  `(season, phase, tid)`; `scripts/fit_value_model.py` likewise), so some rows ask a 2024
  entry to predict a 2026 player -- and the same stale entry is repeated in every
  store snapshot until he plays again. Train only on rows whose entry is fresh relative to
  the save (written at the last monthly update, ~31 days before `phase`), or pair each
  distinct entry with the store snapshot nearest its date, once per entry. Re-score on the held-out players
  (`scripts/holdout_score.py`) before and after; expect a small change, but it is a flaw in the
  labels, and the 94.8% label ceiling (`docs/ca-weighting.md`) was measured on the same rows.
- **Goalkeepers** (7 at Frem) stay on frozen coefficients; they need more careers, not more
  snapshots.

### 19. Scripts that fail at import
`scripts/derive_weight_set.py` and `scripts/attribute_stat_correlations.py` import the deleted
`dashboard/db.py`. Port onto `fmstats` (`store.open_store()`, `scout.effective_table`,
`stats.player_output`). The `attribute-profiles` skill calls scripts deleted in #82/#73
(`export_attribute_lab.py`, `check_rating_parity.py`, `import_weight_set.py`): restore them
from git or rewrite the skill.

### 20. Mart candidates left out on size
Squad moves between consecutive snapshots (on `mart.club_roster`, scoped to clubs we have
played), and `pos_index` as a column on `mart.player_position_fit`.

---

## Site

### 21. One primary-position rule
`mart.player_primary_position` is the rule, but `scripts/_export_db.py` (the depth chart:
highest tactic rating) and `site/js/data.js` `playerRoles()` (most familiar, first row on a
tie) each carry their own. Switch both to the view in one diff and review `git diff site/api`.

---

## Docs

### 22. Rewrite the docs around the three functions
`CLAUDE.md`, `docs/` and `docs/agent-context/` grew with the project and describe parts of it
that no longer exist. The goal is docs that explain the three functions (parser, stats, site)
to a newcomer and an agent — `parser-architecture.md` is the model for the parser.
- **CLAUDE.md** still describes the Streamlit dashboard ("Streamlit stays", the
  `developing-with-streamlit` skill), `regions.py`, `staging.scrape_*`, and
  `canonicalise_names.py`. Its reverse-engineering method section would sit better in
  `parser-architecture.md`.
- **~38 dead code paths** are cited across `docs/`, `CLAUDE.md` and the skills —
  `dashboard/*`, pre-`core` parser modules (`fmparser/staging.py`, `regions.py`, `places.py`,
  `lookups.py`, `staff.py`, `attributes.py`, `lightresults.py`, `mapregions.py`, `tagged.py`,
  ...) and deleted scripts (`map_regions.py`, `audit_archive.py`, `canonicalise_names.py`, ...).
  Find them with a loop over `grep -rhoE "(fmparser|scripts|tests|dashboard)/[A-Za-z0-9_/]+\.py"`
  and a `test -e`.
- **`docs/agent-context/`**: retire the superseded notes (`light-results-rolling-buffer`,
  `master-schedule-plan`), fold duplicates into the reference docs, fix the stale commit SHAs
  in `fm-parser-project.md` and `day1-league-membership.md`, and re-sync `MEMORY.md`.
- **Old TODO numbers** are still cited as live work in `table-framing.md`, `date-search.md`
  and `agent-context/light-results-rolling-buffer.md`.

---

## Other

- **Roll the R2 API token** — its key and secret were pasted into a chat transcript.
  Cloudflare → R2 → Manage API Tokens, then
  `rclone config update r2 access_key_id <NEW> secret_access_key <NEW>`.
- **Position write-ups** for DM, CM, AML, AMC, AMR and ST, plus a verdict on 4-1-2-2-1, against
  the current Superliga squad.
- **Save housekeeping** (needs Zac): every manifest save is now named `<career>-<header date>`
  in R2 and the manifest, so on the local machine delete `~/fm-saves/*/` copies under the old
  names, the stale `output/` dirs and the pre-rewrite git backup, and rebuild the stores
  (`scripts/rebuild.py`; an old store's `raw.extracts` still names the old labels, and
  `export_manifest.py` from it would put them back). The four `unfiled/` saves are dated by
  their headers: `frem/denmark-mid-22` 2021-10-02, `bucaspor/22-23-start` and
  `bucaspor/fm_save3` 2022-06-20 (check whether they are the same save),
  `bucaspor/fm_save1-24-mid` 2023-11-08; register or delete them.
- **`careers.py` hardcodes `reserve_tid`** — the club record's `main_club_tid` could derive it.
- **`tests/test_attribute_model.py` skips without a repo-local store** — open it through
  `fmstats.store.open_store()` as `tests/test_fmq.py` does.
- **Loader speed**: `orjson` for the JSON decode and flattened row construction in `load_core`
  measured ~2.9 s → ~1.6 s per snapshot.
