# TODO — the one doc you read to resume

**Where the project is, and everything still open.** If it isn't here, it isn't outstanding.
The other files in `docs/` are *reference* — record layouts, rules, dead ends already measured —
and you read them when a task sends you there.

When you finish something, **delete its entry**. Do not tick it off, and do not leave a
"CLOSED" note: what was learned goes into the reference doc the entry points at. Item numbers
are for conversation only and are renumbered freely; never cite one in code or a commit.

Last reviewed **2026-10-07**, after the data-layers refactor closed: extract dumps every table as stored, and the store models it raw → stg → int → `mart` (`dim_*`/`fact_*`) → `site` in dbt.

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

Every parser table is on the `core` framework ([`parser-architecture.md`](parser-architecture.md))
and the store is a dbt project ([`fmstats/CLAUDE.md`](../fmstats/CLAUDE.md)). The near-term work
is moving the scripts and skills onto the model (#19) and giving it real-data tests (#19a); the
long tail is the parser: new bytes (every byte of the save processed), then understanding the
bytes already read.

| | |
|---|---|
| career | **Boldklubben Frem** (Denmark, `--career frem`, managed tid 346, reserves 7296) |
| store | `fm-frem.duckdb`, latest snapshot **2028-05-09** (31 snapshots) (published copy on R2) |
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
  - squad status 65, read as "loaned out" (`tables/training.py`), mostly does not mark a loan:
    on the step-16 gate stores 67 of 1,475 status-65 snapshots are listed on loan by another
    club and 1,334 have no loan spell that season, while 9,292 listed loanees carry another
    status. Name the code before reading loans from it.
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
- **Which competition a fixture belongs to: finish the link.** A `fix_man` fixture names its
  stage (`stage_key`, the row number in `comp_man.dat`'s 78-byte stage grid) and its place in
  that stage (`stage_index` +76, `round_index` +77, which are the rules' `indx` and position in
  `rnds`). `comp_<uid>.dat` (`tables/comp_rules.py`) gives each competition's stages, and its
  file name is the competition's uid. The missing step is stage key → uid. Known so far:
  - A key belongs to one competition, and keeps it from season to season: over the 29
    published saves our matches label 28 keys in 9 competitions, none in two, and 7 keys carry
    the same competition across seasons (202 Friendlies, 337/350 Sydbank Pokalen).
  - A key is finer than a rules stage: one per knockout round (the Pokalen's stage 0 uses 8
    keys), one per group, one per leg of a two-legged round (EURO Cup 258/259).
  - Searched on 2023-06-29, 2027-06-29 and 2027-08-09, and the key → uid link is in none of:
    the fixture record; the `comp_man` stage row (every byte, u16 and u32 position; the
    Superliga's and 2. Division's rows are near byte-identical and hold neither uid nor cid);
    `comp_man`'s tail (a 5-year daily calendar of `(key, year)` items, then the roll of honour,
    which carries the cid but no keys); every tag of `comp_<uid>.dat`, read or unread, and the
    binary block after its trailer (some of a competition's keys never occur there, e.g. 45
    in `comp_6.dat`); the main save's competition record (whose 21-byte tail is three club
    uids and three years: holders and recent finishers, to verify against the roll of honour).
  - Not yet searched: `rgman.dat` / `rule_group.dat` (which hold uid and key near each other
    14 and 16 times) and the unmapped parts of the save ([`savefile-map.md`](savefile-map.md)).
  Until it is found, the store labels a stage from our own match in it or by the league rule
  (`dim_match.competition_source`); cups abroad stay unlabelled. Once found, `int_stage_competitions`
  becomes a join and the league rule goes.

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
Bytes the parser reads but cannot name yet. Fields that are named but not yet in the model are
#15.
- **Staff** `+34..+38`: five catalog indices. The six hidden staff attributes stay named by
  offset (fmm-editor has no `Staff.cs`); `hidden_s27` is the one to identify next — 85% of
  staff read 1–4, distinctive enough for a small ground-truth set.
- **Match event type `0x0e`**: 2 events, both reserve fixtures.
- **`att_avg` / `att_min` / `att_max`** in the club record: read correctly, but the names from
  fmm-editor fail every check (a 12,500 ceiling, multiples of 100, Barcelona's max below its
  avg). Not attendance — `mart.club_attendance` is. Carried in `raw.club_details` only.
- **Origin clubs**: 3,936 of 22,624 origin tids resolve to no club in `raw.clubs` —
  probably youth/academy or defunct clubs in another structure.
- **The match record** (`tables/matches.py`): the event's last 8 bytes (two u32, never a tid
  of the match), the player slot's 33 unnamed bytes (+54..61 two more u32; +2 equals the
  opponent's score on the goalkeeper's slot), the team head and tail (75 and 46 bytes), the
  body head's +19..51 and +67..77 (one u8 reads 90-96 on detailed matches: the final whistle's
  minute?), and our tactic in the tail: +0..32 small bitfields (team instructions?), eleven
  per-starter 8-byte rows at +1196 (bytes 0-1 are the role family, partly mapped; bytes 2-4
  vary per match, maybe a duty or role variant: see `agent-context/match-position-encoding.md`
  "Per-starter tactic rows"), a u16 coordinate grid at +220..1182 that changes with
  the back line, and team-looking u16 values after +1295. The positions at +102 are a second
  copy of +69, byte-identical on all 1,027 matches measured. A Formation-tab screenshot for one
  match would settle the per-starter rows.
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

### 12a. Raw mirrors the save, one table per table
Low priority. Raw is still not one table per save
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
`mart.standings` (and the old `mart.league_tables`) rebuild tables from the fixture list and
rank level points by goal difference, then goals scored. Against the game's own final
positions (`raw.club_league_history`; `fact_competition_outcome.final_position`), measured on
the step-14b gate stores: complete single-stage tables agree for England (21/21) and Germany
(9/9), Danish split leagues with points carried over 8/8. What is still wrong:
- **Spain ranks level points by head to head.** Its labels and totals are right; every
  disagreement is teams level on points, and head to head decides all 41 such pairs it
  separates. The tie-breakers are probably in the competition's rules member (`comp_<uid>.dat`,
  TODO #6); read them there rather than hard-coding a nation's rule.
- **Split leagues**: `standings` holds each stage's own matches. Whether points carry into the
  championship and relegation groups, and Belgium's (which disagree, 0/2), is also a rules
  question.
- **The World Cup groups are labelled as the Nations League** (2026, cid 47): national teams
  name that competition as their league, so the league rule takes a four-team World Cup group
  for one of its groups. The old view does the same.
- **Complete tables need complete fixtures**: a snapshot's fixture list holds only part of the
  season before (2023-07-02 has 2021/22 from January), so the table of a season no snapshot
  saw whole is partial. On the full career every season is seen whole.

### 14. Person identity across snapshots
- **A scrapbook entry's tid can name a newgen** once the player it was written for has
  retired (Lewandowski's 2024 World Best XI entry, tid now "Fabio Voeste" on 2027-08-09).
  `mart.fact_player_award` resolves an entry to its `person_id` (`<tid>-<dob>`): the person
  with that tid whose dob gives the entry's age on its date (or one less: the stored age lags a
  birthday by a day or two). Anything else reading old entries must do the same
  (`int.scrapbook_entries` is only our current squad, so safe).

### 15. Surface what the parser already reads
Named fields that stop short of the mart.
- **Player of the Match**: `raw.matches.player_of_match` is the game's own pick. It reaches
  `int.our_matches` and stops there; carry it onto `dim_match` (or `fact_team_match`) and then
  the site's match page.
- **Opposition positions**: the parser reads both sides' full-time positions (the team head's
  +30, `home_positions` / `away_positions` in `matches.json`), but `load_duckdb.py` fills
  `raw.match_player_stats.position` for our side only. Fill the opponent's too, so scouting and
  `rating_adj` can split the opposition by position, then rebuild (the role baselines move).
  Check the reserve fixtures first: AI-managed sides may carry a default shape.

### 16. Match facts
- **Goals exceed shots** on 260 of 11,161 player-match rows (`goals > shotA`). Probably
  penalties or deflections; until settled, no conversion rate from these columns.

### 16b. Career-history rating on youth-team lines
49 career-history lines across the Frem gate store's snapshots (45 once unioned), every one at an academy tid with 38-40 apps,
read a rating of 646.75-647.63 (u16 64675-64763). As a signed value that is -7.73 to -8.61,
an ordinary average negated, so a youth-team line may store its rating that way. Prove it
against a youth player's in-game history screen before reading these as ratings;
`stg_player_history_seasons` passes them through. (0xFFFF, the save's "none", reads NULL.)

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

### 19. Move the scripts and skills onto the model
#149, #154 and #155 retired the legacy `mart.*` views, the `raw.players` /
`raw.player_attributes_exact` compat views, `dashboard/db.py`, `fmq` and `fmstats/scout.py`.
These still use them, so each fails at import or at its first query:
- **The model fits** -- blocks #18. `scripts/fit_attribute_model.py`, `fit_value_model.py`
  and `holdout_score.py` read `raw.players` joined to `raw.player_attributes_exact`. Port them
  to `stg.persons` ⋈ `stg.player_attributes` (`sid`) for the record bytes, CA/PA and reputation,
  and `int.player_attributes_exact` for the labels (`tests/test_attribute_model.py` has the
  join). Gate: refit on the same rows and reproduce the stored `stg.attribute_model` and
  `stg.value_model` coefficients, and `holdout_score.py`'s published figures, before changing
  anything. `holdout_score.py` also fails at import (`HIDDEN_OFFSETS` undefined).
- **The weight-set scripts**: `scripts/derive_weight_set.py` and
  `attribute_stat_correlations.py` import `dashboard.db` and read `mart.match_player_facts`,
  `mart.managed_club`, `mart.position_roles` and `mart.role_weights`. Swap `db.q` for a
  read-only connection (`scripts/dbopen.py`) and the views for `fact_player_match`,
  `dim_team`, `stg.position_roles` and `stg.role_weights`. Gate: re-derive
  `frem_minmax_4231` and get a byte-identical `seeds/role_weights.csv`.
- **The skills**: query-fm-data, scout-opponent, fm-season-review, preseason-squad-review,
  season-outlook and where-are-they-now cite `fmq`, `fmstats.scout`, `squad_current`,
  `squad_on` or `effective_table`; attribute-profiles calls scripts deleted in #82/#73
  (`export_attribute_lab.py`, `check_rating_parity.py`, `import_weight_set.py`). Rewrite each
  as SQL recipes against `mart.dim_*`/`fact_*` and `site.*`, and test each by running it once
  on the published store. query-fm-data first: the others lean on its catalogue.
- **CLAUDE.md**: its house rules and "Common commands" cite the same names (with #22).

### 19a. Port `tests/validate_mart.py` to dbt tests
The script stops at its first query: it reads the legacy mart views #149 retired (50 names,
~200 references, e.g. `mart.our_clubs`, `managed_club`, `player_growth`, `squad_on`), and only
a handful have a same-named successor. The dbt suite does NOT make it redundant: its 478 nodes
are structural (`unique_combination`, `relationship_combination`, `rows_match_source`, a few
`not_null`/`in_range`/`accepted_values`) plus 33 unit tests on toy fixtures. Nothing in dbt
asserts a property of the real data. Scoped 2026-10-07 from the check labels, the script's
~90 checks split four ways:
- **Already covered, drop (~15):** the grain checks (`mart.<obj> is unique on ...`, "one row
  per player per snapshot/week"); `unique_combination` on the successor models covers them.
- **Generic data invariants, port as singular dbt tests (~30):** these hold for any career, so
  they belong in `fmstats/tests/`. Spells: no same-type overlap, no inverted range, latest
  snapshot a superset. Matches: both sides mirror, result/points agree with the score, no
  minutes after a red card, event side resolves, a two-legged tie has at most two legs,
  `player_seasons` reproduces the match facts. Tables: positions 1..n with no gaps, the
  save's own final positions reproduced. Head-to-head totals equal the matches they sum.
  Academies: u16 complement, no club/academy collision, 0xFFFF is not a club, eligibility
  never removed. Homegrown: months at most the window, club-trained implies
  association-trained, never NULL, B-list fixed-date. `rating_adj`: every position maps to a
  role, each role's baseline mean equals the pool mean, at least 30 starts per role, set
  exactly for positioned starts, raw average unchanged. `level_*` in [0,100]. No raw-ability
  column in `site` (`check_immersion()` guards the JSON, not the schema). Division resolved
  as-at. Transfers fee coverage. Every training focus named.
- **Frem known answers, port as tagged singular tests (~25):** the 14+ loan-ins incl. Oliver
  Jeppe, winter/summer windows, 2024 league goals 73 (70 + 3 OGs), golden boot Jakobsen 30,
  first team 39 / reserve 59 games, Garly and Møller-Jensen growth, youth tid 65189, tier-25
  rule set, fixture-stage labels, named transfer fees, training focus on 2027-06-15, named
  spells. Tag them `known_answers` and enable them only for `var('career') == 'frem'`. They
  assume a full rebuild.
- **Retired with their view, drop (~15):** growth/tenure/attribute-growth and the keeper-block
  total, `squad_on` vs roster, `at_club_spells` ghosts, `our_clubs`/`managed_club`
  (now `dim_team`), `player_position_fit` coverage, `player_role_seasons`, and the
  "CM − DM > 0.2" penalty, which is a finding, not an invariant. Before dropping, check
  whether `site.forecast`/`site.age_curve` and `site_players.development` should keep their
  monotone-forecast and four-band (an immersion guard) checks.

Then delete the script, and point the CLAUDE.md "after editing" command at `dbt test`.

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
- **Loader speed**: `orjson` for the JSON decode and flattened row construction in `load_core`
  measured ~2.9 s → ~1.6 s per snapshot.
