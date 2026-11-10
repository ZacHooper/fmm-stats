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

Every parser table is on the `core` framework ([`fmparser/AGENTS.md`](../fmparser/AGENTS.md))
and the store is a dbt project ([`fmstats/AGENTS.md`](../fmstats/AGENTS.md)) whose build tests
the real data as well as its structure (`fmstats/tests/`). The near-term work is the weight-set
method (#18) and the docs (#22); the long tail is the parser: new bytes (every byte of the save
processed), then understanding the bytes already read.

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
- **`mart.club_attendance` is our-matches-only** — read `n_games` before trusting `average_attendance`.
- **A tid is a slot, not a person** — check `DISTINCT dob` per tid before telling a story
  about one ([`parser/person_info.md`](parser/person_info.md)).

### Where to look

| you want | read / run |
|---|---|
| how the parser is organised, and how to hook up a table | [`fmparser/AGENTS.md`](../fmparser/AGENTS.md) |
| where every byte of the file lives | [`parser/savefile-map.md`](parser/savefile-map.md) |
| which bytes no parser reads | `uv run python scripts/audit/audit_coverage.py` |
| the per-byte schema of every declared record | `uv run python scripts/audit/audit_records.py --map` |
| whether a region is text, records or compressed | `uv run python scripts/audit/entropy_profile.py <save.fms>` |
| the compressed archive and the fixture list in it | [`parser/savefile-map.md`](parser/savefile-map.md#the-archive), [`parser/fixtures.md`](parser/fixtures.md) |
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
- **The transfer band: read the rest of the row** (35.4–38.4 M,
  [savefile map](parser/savefile-map.md#the-transfer-band)). Count-framed and decoded on paper:
  every bid of the season, the accepted one with its fee and contract terms. Open: the kind
  codes `01`, `05`, `06`, `09`, `0b`; what +87 holds on a loan (1,508,051 … not money) and on
  a graduation (65,519); the club at +4; the 2 bytes after the count; the `0d` rows the
  Transfers screen doesn't list (Chukwuani, Behrndtz, Gernsøe on `frem-2026-06-11`); the 30
  rows near the end of `bucaspor-2022-06-19` whose index reads 0. Capture the Transfers screen
  into `docs/parser/img/` as the evidence record. Then a parser table, an extract step and a
  raw table ("Raw mirrors the save, one table per table").
- **13.96–16.68 M** — 85% filler. It opens with a u32 equal to the person count (32,966 /
  34,312) and 14-byte units: walk it as a per-person table and see where it ends.
- A **league-titles table** at ~56.3 M behind a 550-byte `0xFF` run, 0.13 MB after our
  matches ([savefile map](parser/savefile-map.md)): `[u8][cid u16][tid u16][year u16]` per
  65-byte entry, one per league title Frem has won, the first byte the entry count. Name it:
  the club's titles or the manager's, cups or not, and why `frem-2030-06-22` lacks its 2029
  title.

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
  - attribute-focus codes 0, 2, 10, 15.
  - intensity 0 and 1: only 3 (High) and 2 (Normal) are read off the screen.
  - **Squad status is not located.** Training `+39` (now `unknown_39`) is not it: ten players
    whose Transfer Status screen says First Team, Rotation, Backup or Youngster all read 171
    on `frem-2030-06-22` ([`docs/parser/training.md`](parser/training.md)). Find the real
    one: diff a save before and after changing one player's status in game.
  - the Progress bar: a green fill, or a full yellow bar when the player is unlikely to improve
    further. Not the stored `pa - ca` (0 on yellow and near-empty bars alike); the green-fill
    rows are the ones with `+17` and `+41` non-zero. Diff two saves a few weeks apart.
  - `+8` u8, `+9`/`+13` u32 (money-like; `+9` round), `+31..36`, `+38`, `+40..48` and the
    three dates at `+49/+53/+57`. The row also carries the contract flag (`+37`) and the
    unnamed `+39`, so it is a per-person status row as much as a training one.
  - `unknown_39` 65, read as "loaned out" (`tables/training.py` `LOAN_STATUS`), mostly does
    not mark a loan: on the step-16 gate stores 67 of 1,475 status-65 snapshots are listed on loan by another
    club and 1,334 have no loan spell that season, while 9,292 listed loanees carry another
    status. Name the code before reading loans from it.
  - surfacing it: each squad player's training focus on the site's Squad page.
- **Competition teams of the year are not snapshots**: the game shows only the current
  season's, and a player opens his live profile, so there is nothing stored per year to find.
- **Surface the World Best XI pools**: every season's pool is in `raw.player_scrapbook`
  (lists 0-30, 62/64); nothing reads it yet.

### 4a. Player progress: what is still unread
`tables/player_progress.py` hands every used row to `raw.player_progress` (the six lines
and the raw status included); the mart draws injury and loan spells from the bits
([`docs/parser/player_progress.md`](parser/player_progress.md)). All six lines are named. Open:
what the graph's markers mean (status bits 3, 4, 6 and 7 each draw one: tap one in game, or
match the dates against events), bit 2, the `fffa`/`fffc` fee codes in the history pool, and
the 23 u16 at +24 (17 filled for an outfield player, 6 for a goalkeeper --
the week's attribute values?). Named, the table could give every squad player's weekly
development, not just injuries and loans.

### 5. Reference-half tables not yet read
- The unnamed count-framed tables ([savefile map](parser/savefile-map.md)): the three 7-byte
  index tables after the staff table, the 807 awards (club-shaped records with a longer
  trailer) and the 888-row 7-byte list between currencies and languages.
- **`audit_table_headers.py --confirm` fails the nickname id-table on every save**: its check
  reads the last declared slot as in use, and that slot is an empty `ffffffff`. A tooling
  bug, not the data's: check the last *used* slot.
- The **Region** table, the unnamed bytes of the nation record (`NATION_TEAM`, `NATION_END`),
  and the ~7-entry
  **continent** table right after the nations (`[uid u32][Name][01][CodeName][Demonym][01]`,
  Africa..South America at ids 0–5, `World` at 6).
- The club record's unnamed stretches (`tables/clubs.py`): 20 bytes in `CLUB_STANDING`, 74 at
  the end of `CLUB_STAFF`, the `[u32 8][8 B]` block at +167, and the 9-byte tail items.
- The person record's unnamed bytes (`PERSON_MID`, three of each relationship's eight), and
  what its language `level` of 255 means.

### 6. Archive members and framing not yet read
[`parser/savefile-map.md`](parser/savefile-map.md#the-archive) is the reference.
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
  - That `stage_key` is a row number in `comp_man.dat`'s 78-byte grid is itself unproven: at
    row `stage_key` the round or stage name the rules give the fixture appears at +70 on 0 of
    42 keys, and at no offset or nearby row on more than a third
    ([comp_stages](parser/comp_stages.md)).
  - Not yet searched: `rgman.dat` / `rule_group.dat` (which hold uid and key near each other
    14 and 16 times) and the unmapped parts of the save ([`parser/savefile-map.md`](parser/savefile-map.md)).
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
member names its dictionary file (`file`), and its stage list equals that file's (73 of 73),
so the two join. Leads from the rules screens ([comp_rules](parser/comp_rules.md)): a round's
`date` is a rule, not a date (the Pokalen final's `{spld 'ascension'}` is 30 May 2030), `dat2`
is the second leg's, `drdt` the draw (`{time 1230, dyow 2, dyom 24, mont 7}` on a Monday 22
July draw), and `wnpz` / `lspz` / `apmn` carry prize money (`cash`, `curr`). The disciplinary
rules on the same screens (bans after 2 or 3 yellow cards, the Superliga's points system)
are not located. Decoded from screens but not read yet: `nrds` (rounds), `sort` (tie-breakers,
codes in the doc), `qurl` (which places go where), `relr` and `prmr` (who goes down or up, and where). The deleted
data-dictionary doc (last at commit 7cc46b6) holds guesses at many tag meanings — hypotheses
to test, not facts.

### 10. Unnamed fields in records we already read
Bytes the parser reads but cannot name yet.
- **Frame the roll of honour by its count, and name the competition holders**
  ([comp_honours](parser/comp_honours.md), [competitions](parser/competitions.md)). The roll
  of honour is `[count u32][count × 55 B]` ending on `comp_man.dat`'s last byte (7 of 7
  saves); `locate_comp_honours` starts 39 bytes into record 0, so it drops that record and
  hands every row the previous record's `start_year`/`end_year`. The competition record's
  21-byte tail is the last finished season's top three (club uids) and that season; 25 of 26
  leagues and four Past Winners screens agree. Name both in the module (`COMP_HISTORY_TAIL`),
  and consider extracting the holders and the roll of honour together: the in-game Past
  Winners list is exactly the two. Nothing reads either today, so `competitions.json` and
  the rest of the extract do not change.
- **Staff** `+34..+38`: five catalog indices. The six hidden staff attributes stay named by
  offset (fmm-editor has no `Staff.cs`); `hidden_s27` is the one to identify next — 96% of
  staff read 1–4, distinctive enough for a small ground-truth set.
- **Match event type `0x0e`**: 2 events, both reserve fixtures.
- **The world fixture's tie aggregate** ([fixtures](parser/fixtures.md)): read +9 / +14 as
  the tie's aggregate (second legs; `ff` otherwise) into `world_fixtures.json` and the store.
  An output change: re-record `tests/assert_identical.py`.
- **Staff `+17` above 20** (`tables/staff.py`): 43 records on `frem-2030-06-22`, retired
  goalkeepers, read 51–99 where `goalkeeping_coaching` is 1–20 for everyone else. They are
  carried as stored ([`docs/parser/staff.md`](parser/staff.md)); name what the byte holds for them.
- **Club `main_club_tid` drops tid 0** (`tables/clubs.py` `_club`): the `0 < tid` filter
  loses the one parent that is tid 0, so Algeria U21 (11103) has no parent while the other 227
  U21 sides resolve ([`docs/parser/clubs.md`](parser/clubs.md)). An output change: re-record
  `tests/assert_identical.py`.
- **`att_avg` / `att_min` / `att_max`** in the club record: read correctly, but the names from
  fmm-editor fail every check (a 12,500 ceiling, multiples of 100, Barcelona's max below its
  avg). Not attendance — `mart.club_attendance` is. Carried in `raw.club_details` only.
- **Origin clubs**: 3,936 of 22,624 origin tids resolve to no club in `raw.clubs` —
  probably youth/academy or defunct clubs in another structure.
- **The match record** (`tables/matches.py`): the event's last 8 bytes (two u32, never a tid
  of the match), the player slot's 32 unnamed bytes (+54..61 two more u32; +2 equals the
  opponent's score on the goalkeeper's slot), the team head and tail (50 and 46 unnamed bytes), the
  body head's +19..51 and +67..77 (one u8 reads 90-96 on detailed matches: the final whistle's
  minute?), and our tactic in the tail: +0..32 small bitfields (team instructions?), eleven
  per-starter 8-byte rows at +1196 (bytes 0-1 are the role family, partly mapped; bytes 2-4
  vary per match, maybe a duty or role variant: see [matches](parser/matches.md)), and
  team-looking u16 values after +1295 (+220..1182 is the formation's catalog template). A
  Formation-tab screenshot for one match would settle the per-starter rows.
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

### 11. Read the season rollover from the game, not from config
A save's campaign depends on the day its career's new season starts: Denmark 30 June, Turkey
20 June, measured from the managed club's record and set per career as `Career.rollover`. A
new career needs it measured again. The game holds it -- most likely each nation's calendar in
the data dictionary's rule files (#7, #8) -- so decode it there. The fixture list does not
change at the rollover, and no fixed-offset season field exists in the first 14 MB.
**Drift mechanism confirmed:** the game's internal season loop ticks a strict 365 days rather than
aligning with leap years. Every leap year (2024, 2028), the calendar rollover shifts backwards by
one day (Denmark: 30 June in 2021-2023 -> 29 June in 2024-2027 -> 28/29 June in 2028). Recorded via
`rollovers` in `fmm.toml` until dynamically read.


### 11a. Attribute decoder (low priority: exploring the game)
- **Attribute decoder** ([`attribute-model.md`](attribute-model.md) — read its "ruled out"
  section first): the misses are bias, not noise (`|mean signed error|` vs exact rate −0.91),
  and good players are under-predicted (83.6% exact at true 4–6, 22.4% at 16–20). Re-test two
  near-misses on the larger store: feet for Dribbling, height/weight for Shooting.
- **Retrain on time-aligned rows.** Our squad's "exact" attributes are scrapbook entries
  (`tables/player_lists.py`), dated by `scrapbook_date`, and a player who has not played this
  season carries one up to two years old. The fit pairs an entry with the CURRENT save's
  record bytes and CA (`scripts/_attribute_rows.py` joins `stg.player_attributes` to
  `int.player_attributes_exact` on the snapshot), so some rows ask a 2024 entry to predict a
  2026 player -- and the same stale entry is repeated in every store snapshot until he plays
  again. Pair each distinct entry with the snapshot nearest its date, once per entry, as
  `int.player_value_labels` does for values; the World Best XI entries would add elite
  players to the labels the same way. Re-score on the held-out players
  (`scripts/holdout_score.py`) before and after; expect a small change, but it is a flaw in the
  labels, and the 94.8% label ceiling (`docs/ca-weighting.md`) was measured on the same rows.
- **Goalkeepers** (7 at Frem) stay on frozen coefficients; they need more careers, not more
  snapshots.

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
- **Parsed but never extracted.** `officials` (match officials: with
  `int.world_matches.referee_tid` it gives `dim_referee` its link), `comp_honours` (roll of
  honour) and `comp_stages` (stages calendar) from `comp_man.dat`, and `match_slots`. Each needs
  an extract step, a raw table and a stg model.
- **Not parsed.** The transfer band's 143-byte rows are decoded on paper
  ([savefile map](parser/savefile-map.md#the-transfer-band)) but have no parser module, and
  the save wipes them each July ("The transfer band: read the rest of the row").

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
  separates. The tie-breakers are in the competition's rules member: the stage's `sort` list
  ([comp_rules](parser/comp_rules.md)), `[3, 0, 1]` for Spain (head to head, goal difference,
  goals scored), `[0, 1, 3]` for England. Read `sort` into `competition_rounds` and rank by it
  rather than hard-coding a nation's rule; code 6 is not yet seen on a screen (Belgium's
  Championship Group), and 14 is only probably the Bundesliga's play-off-on-equal-record line.
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
- **That rule can resolve one entry to two people**: Luka Vodišek (tid 13443) has two
  `person_id`s on the full Frem store, dob 1998-11-29 and 1998-06-08, both inside the
  one-year age tolerance, so his 2028 World Best XI entry is two rows. The
  `fact_player_award` key on `player_tid` warns on it; pick one person per entry (the
  nearer age, then the later snapshot) and make that test an error again.

### 16. Match facts
- **Goals exceed shots** on 260 of 11,161 player-match rows (`goals > shotA`). Probably
  penalties or deflections; until settled, no conversion rate from these columns.

### 16b. Career-history rating on youth-team lines
49 career-history lines across the Frem gate store's snapshots (45 once unioned), every one at an academy tid with 38-40 apps,
read a rating of 646.75-647.63 (u16 64675-64763). As a signed value that is -7.73 to -8.61,
an ordinary average negated, so a youth-team line may store its rating that way. Prove it
against a youth player's in-game history screen before reading these as ratings;
`stg_player_history_seasons` passes them through. (0xFFFF, the save's "none", reads NULL.)

### 18. Rebuild the weight-set method on team results
([`agent-context/role-weight-methods.md`](agent-context/role-weight-methods.md), "What the match
data says"). `scripts/derive_weight_set.py` fits blocks from per-90 output on 12-26 players a
role, which the data cannot support: its blocks flip between runs (re-derived on the current
store, DM and AMC go flat and ST gains Tackling 3 / Leadership 2; the shipped set does not
reproduce, and the input difference behind it was not isolated). Change it to: score a block
against team results per match (points, goal difference, goals against; within season, venue and
opponent controlled) beside rating and per-90; resample by player and check leave-one-player-out;
start from a base block (`frem_attacking_ss`, or a role's in-game key attributes) and let the
data veto. Then ship: CB, CM, AMC, AML/AMR as now (confirmed against results); ST on the
target-man brief (aerial, shooting, strength key; movement, pace, aggression, dribbling
secondary) as a `HELD` judgement; LB/RB and DM marked not measurable. Group players by the
position they started in: `attribute_stat_correlations.build(positions="played")` does it, but
the derivation still passes `positions="familiar"` so it does not move before this rework.

---

## Site

### 23. Our full-time formation per match
The Matches page's formation is the kick-off shape (the match tail's formation string,
`fmparser/tables/matches.py`). The full-time shape is in the save too: the team head's
`positions`, 11 starters in posOrder order ([matches](parser/matches.md)).
Collapse those bands into a formation string in the dbt site models (not the browser), ship
it in `site.matches`, then give the Splits tab's Formation split a kick-off / full time /
changed-in-game choice and the Results tab an "Ended in" column beside "Started in".

### 24. Show hidden attributes as report trait lines
The profile sheet's "+ personality & hidden" toggle (`site/js/profile.js`, `extraAttrColumns`)
shows raw hidden values. The manager prefers the in-game report's words. Derive the trait line in
the `site` dbt models from
[`agent-context/report-trait-lines.md`](agent-context/report-trait-lines.md) (one line, highest
priority wins), ship it with the profile, and show it in place of the numbers, keeping the numbers
behind an explicit opt-in. Finish the doc's pending checks first, so the thresholds are pinned
before they're coded.

---

## Docs

### 22. Audit and clean up the docs
Many docs describe code that no longer exists (~95 dead file references across 37 docs on
2026-11-06). The plan, with a brief per phase and a destination for every doc, is
[`plans/2026-11-07-docs-overhaul.html`](plans/2026-11-07-docs-overhaul.html) (open it in a browser; each phase is a brief an agent can pick up). Do it before the fresh
public repo is cut.

### 25. Finish making the project career-agnostic for other players
The README, `AGENTS.md`, `fmm.toml` and the R2-served site data are done. Still personal:
- **Skills** (`.claude/skills/`) hardcode Frem (tid 346, `fm-frem`, the Superliga) and assume the
  author's R2 store. Read the career from `fmm.toml` / `site.config`, or label them examples.
- **Generic dbt tests that fail on a short history**: on a store holding only the latest Frem
  save, `tables_reproduce_save_positions`, `ratings_adj_baseline`, `ratings_adj_coverage` and
  `unique_combination_fact_player_award_award_id__person_id__entry_date` (44 rows) fail on
  `main` too. A new user's first load is exactly that store, so each should hold on one
  snapshot or say why it can't; the award uniqueness one looks like a real duplicate.
- **`seeds/manifest.csv`** is the author's rebuild recipe (save names and dates). Move it next to
  the saves (R2) or make `rebuild.py` read a per-user path.
- **`seeds/config_bundle.json`** makes `frem_attacking_ss` the app's display default; it should
  default to the career's `rating_method`.
- **House-rule switch**: the Danish registration rules are always on in the web app
  (`site/js/registration.js`). Add `[careers.<key>] house_rules` to `fmm.toml` and hide the
  registration column and card when it's off.
- **`docs/agent-context/`** is mostly the author's career; split the general findings from the
  Frem-specific ones and move the latter to the author's own notes.
- **`scripts/lint_sql.py` fails on `main`** (14 layout violations, plus models that need a
  store to compile). Fix, then add it to CI.
- **Public history**: `site/api/*.json` (game data) is in the history of every commit before it
  was untracked. Rewrite history or start the public repo from a fresh commit before making it
  public.

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
- **`reserve_tid` is configured by hand (fmm.toml)** — the club record's `main_club_tid` could derive it.
- **Loader speed**: `orjson` for the JSON decode and flattened row construction in `load_core`
  measured ~2.9 s → ~1.6 s per snapshot.
