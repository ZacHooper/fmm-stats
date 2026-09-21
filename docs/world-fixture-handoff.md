# Handoff — world fixtures: decode the competition, then model it

**Written 2026-09-21.** Self-contained: everything established during planning, every negative
result, and the ground truth. Read this plus `CLAUDE.md` and you have the full picture. The
in-game screenshots that anchor this work are **transcribed below** — you will not have the
images.

Branch: **`feat/world-fixture-competitions`** (off `main` @ `a2a845e`).

---

## 1. The task

`fix_man.dat`, inside the save's tail zstd archive, is the **world** fixture list: ~27,000
matches per snapshot over ~1,750 clubs, against the 275 our own match parser can see. It is
extracted (`fmparser/fixtures.py`) and emitted (`world_fixtures.json`) but **nothing loads it**,
and it ships 5 fields out of a 92-byte record — ~70 bytes are declared `PAD`.

Two things were believed to block modelling it: no competition field, and no scores. **Both
beliefs are wrong**, and the competition key was found during planning.

### Scope, decided with Zac

| | |
|---|---|
| Competition naming | **Go all-in.** This is the centre of the work. |
| Fixture bytes | **Dump all 92** first, so nothing is being skipped. |
| The archive | **Confirm every member** — the bridge is most likely in there. |
| Scores | **Decode them.** Without scores there are no tables, only fixtures. |
| Deliverable | **Data layer only.** No `site/`, no `export_data.py`, no `publish_mart.py`. |

---

## 2. THE HEADLINE — the competition key is at `+31`

Inside `Field(16, 25, UNKNOWN, PAD)` in `fmparser/fixtures.py:129`. A `u32` at `+31`
(effectively `u16@+31` plus a 2-bit `+32`; `+33`/`+34` are always 0) taking **409 distinct
values on `frem-2026-06-11`, partitioning all 26,954 fixtures with nothing left over**.

It is a **stage** key, not a competition id:

- A league season gets **one key for all its rounds** (Premier Division = 74, rounds 0–37).
- A knockout gets **one key per round** (FA Cup R3/R4/R5/QF/SF = 418/450/477/530/550).
- A two-legged tie gets **one key per leg** (Champions Cup KO = 430 first leg, 431 second).

Cross-save: 409 keys on `frem-2026-06-11`, 426 on `frem-2026-06-29`, 35 on the day-one
`frem-2021-07-01`, 373 on `bucaspor-2022-05-25`. Range 21..859. **Stability across saves is NOT
established — measure it before any cross-snapshot union.**

### So: "how do you know a fixture is FA Cup or EFL Cup?"

**The key already separates them, perfectly and per round.** What we cannot yet do is put the
string `"FA Cup Third Round"` on key 418.

---

## 3. GROUND TRUTH — transcribe-only, the images are not in the repo

### 3a. Liverpool, Club Fixtures, 2025/26 — from `frem-2026-06-11` (we HAVE this save)

This is the primary oracle. Screenshot columns: date, score, opponent, H/A/N, competition.
Verified line-by-line against `fix_man` during planning — **every row matched**.

| date | score | opponent | venue | competition (in-game) | `+31` | `round` |
|---|---|---|---|---|---|---|
| 26 Jun 25 | 1-0 | Higashiosaka Rosa (1326) | N | Club World Ch'ship Group D | 849 | 2 |
| 28 Jun 25 | 3-1 | Barcelona (1000) | N | Club World Ch'ship Quarter Final | 497 | 0 |
| 2 Aug 25 | 5-0 | A. Madrid (989) | H | **Friendly** | 202 | 255 |
| 9 Aug 25 | 2-1 | Chelsea (431) | N | **Community Shield** | 64 | 0 |
| 16 Aug 25 | 0-1 | Newcastle (481) | H | Premier Division | 74 | 0 |
| 23 Aug 25 | 0-2 | Sheff Utd (499) | A | Premier Division | 74 | 1 |
| 30 Aug 25 | 1-1 | Arsenal (406) | H | Premier Division | 74 | 2 |
| 13 Sep 25 | 3-1 | West Ham (524) | A | Premier Division | 74 | 3 |
| 16 Sep 25 | 0-2 | Milan (749) | H | **Champions Cup Group D** | 313 | 0 |
| 20 Sep 25 | 2-0 | West Brom (523) | H | Premier Division | 74 | 4 |
| 23 Sep 25 | **0-0 p** | Leicester (468) | A | **Carabao Cup Third Round** | 308 | 2 |
| 27 Sep 25 | — | Man UFC (474) | A | Premier Division | 74 | 5 |

Also visible in the screenshot's earlier scroll (not in the table above): `2025-06-19 A
Al-Ahly Sporting Club, key 849, round 0` — another Club World Championship group game.

**The `0 - 0 p` on 23 Sep is load-bearing for Phase 4** — it names what the non-plain goals
shape carries (a penalty shoot-out).

**Score display is HOME-FIRST**, confirmed by the win/loss colouring: 16 Aug `0-1` at Home is
red (Liverpool lost), 23 Aug `0-2` Away is green (Liverpool won 2-0). Same orientation as
`fix_man`.

### 3b. Liverpool's full 2025/26 as read from `fix_man` (the rest of the season)

Continues past the screenshot. Useful because it shows the whole stage-key structure:

```
2025-10-01 A AS PAOK Salonika      key=313 rnd=1    Champions Cup group MD2
2025-10-04 H Leeds United          key= 74 rnd=6
2025-10-19 A Brighton              key= 74 rnd=7
2025-10-22 A Villarreal            key=313 rnd=2    group MD3
2025-10-25 H Chelsea               key= 74 rnd=8
2025-10-28 H Millwall              key=352 rnd=3    Carabao R4
2025-10-31 A Brentford             key= 74 rnd=9
2025-11-04 H Villarreal            key=313 rnd=3    group MD4
2025-11-08 H Aston Villa           key= 74 rnd=10
2025-11-22 A Watford               key= 74 rnd=11
2025-11-26 H AS PAOK Salonika      key=313 rnd=4    group MD5
2025-11-29 H Leicester City        key= 74 rnd=12
2025-12-03 A Derby County          key= 74 rnd=13
2025-12-06 A Southampton           key= 74 rnd=14
2025-12-09 A AC Milan              key=313 rnd=5    group MD6
2025-12-13 H Manchester City       key= 74 rnd=15
2025-12-17 H Aston Villa           key=383 rnd=4    Carabao QF
2025-12-20 H Tottenham             key= 74 rnd=17
2025-12-26 A Everton               key= 74 rnd=18
2026-01-01 H Brighton              key= 74 rnd=19
2026-01-04 H Fulham                key=418 rnd=4    FA Cup R3
2026-01-07 A AFC Bournemouth       key= 74 rnd=16   (note: rnd 16 played after rnd 19)
2026-01-10 A Leeds United          key= 74 rnd=20
2026-01-18 H Brentford             key= 74 rnd=21
2026-01-24 H Ipswich Town          key=450 rnd=5    FA Cup R4
2026-01-31 A Chelsea               key= 74 rnd=22
2026-02-09 H Everton               key= 74 rnd=23
2026-02-14 H Sheffield United      key= 74 rnd=24
2026-02-18 H FC Bayern München     key=430 rnd=0    Champions Cup KO 1st leg
2026-02-21 A Newcastle United      key= 74 rnd=25
2026-02-28 A Tottenham             key= 74 rnd=26
2026-03-04 H Fleetwood Town        key=477 rnd=6    FA Cup R5
2026-03-07 H AFC Bournemouth       key= 74 rnd=27
2026-03-10 A FC Bayern München     key=431 rnd=0    Champions Cup KO 2nd leg
2026-03-14 A Manchester City       key= 74 rnd=28
2026-03-22 A Middlesbrough         key=530 rnd=7    FA Cup QF
2026-04-01 H Southampton           key= 74 rnd=29
2026-04-04 A Leicester City        key= 74 rnd=30
2026-04-08 A Aston Villa           key= 74 rnd=32
2026-04-11 H Derby County          key= 74 rnd=31
2026-04-19 A Chelsea               key=550 rnd=8    FA Cup SF
2026-04-24 H Watford               key= 74 rnd=33
2026-05-02 H West Ham United       key= 74 rnd=34
2026-05-09 A Arsenal               key= 74 rnd=35
2026-05-16 H Manchester UFC        key= 74 rnd=36
2026-05-24 A West Bromwich Albion  key= 74 rnd=37
```

Note `round` is the SCHEDULED matchday, not date order — rnd 16 was played 7 Jan after rnd 19
on 1 Jan (a postponement). Do not assume round order == date order.

### 3c. Manchester City, 2026/27 — from a **25 Feb 2027** save we DO NOT HAVE

Latest snapshot on disk is `frem-2026-07-02`. **Ask Zac to export the 2027-02-25 save** — it is
a second-season oracle naming FA Cup R3, Carabao QF and both Carabao SF legs.

| date | score | opponent | venue | competition |
|---|---|---|---|---|
| 8 Dec 26 | 3-3 | FC København | A | Champions Cup Group B |
| 13 Dec 26 | 2-0 | Brighton | H | Premier Division |
| 15 Dec 26 | 2-0 | Tottenham | H | Carabao Cup Quarter Final |
| 19 Dec 26 | 2-0 | Wolves | H | Premier Division |
| 23 Dec 26 | 2-0 | Leeds | H | Premier Division |
| 26 Dec 26 | 2-2 | Leicester | A | Premier Division |
| 28 Dec 26 | 3-2 | Man UFC | H | Premier Division |
| 2 Jan 27 | 1-2 | Birmingham | A | **FA Cup Third Round** |
| 5 Jan 27 | 3-4 | Aston Villa | A | **Carabao Cup Semi Final First Leg** |
| 9 Jan 27 | 0-2 | Watford | A | Premier Division |
| 12 Jan 27 | 5-1 | Aston Villa | H | **Carabao Cup Semi Final Second Leg** |

### 3d. Club tids (stable across all 25 snapshots)

```
Liverpool 471   Man City 473   Newcastle 481   Sheffield United 499   Arsenal 406
West Ham 524    West Brom 523  Leicester 468   Chelsea 431   Man UFC 474
Tottenham 518   Aston Villa 407   Birmingham 412   Leeds 466   Brighton 421
AC Milan 749    Barcelona 1000    A. Madrid 989    Higashiosaka Rosa 1326
```

Decoys to avoid: Sheffield Wednesday 500, "Sheffield" 3162, AFC Liverpool 5365, City of
Liverpool 6459, A. Madrid B 978, Barcelona B 980, Inter Milan 769, reserve sides 7341/7405/
7407/7415/7433/7457.

All the English clubs above sit in `league_cid = 5` (English Premier Division, 20 clubs).
**Higashiosaka Rosa has `league_id = 65535`** — the no-league sentinel; its nation (61, Japan)
has no loaded pyramid. ~925 of 4,553 clubs are in this state, so **~20% of clubs in the fixture
file have no league to match on.**

---

## 4. NEGATIVE RESULTS — do not re-run these

Each cost real time during planning.

1. **There is no cid in the fixture record.** Every offset 0..90 tested as `u16` and `u32`
   against 56 fixtures joined to our own matches with a known `comp_id` (2 = Superliga,
   65 = Friendly, 263 = Pokalen, 1342 = Danish Reserves Group 1): **zero offsets match.**
2. **The stage key is not in the `comp_<id>.dat` rule files.** Searched all 147 members for
   each of 19 known keys as a `u32`. Hits are small-int noise (`530` appears in 21 files) and
   **3 of 19 keys appear in no file at all** (352, 383, 450). Kills the "each comp file lists
   its stages" hypothesis.
3. **`comp_man.dat` is NOT a stride-78 grid.** Payload 232,440 = 78 × 2,980 divides exactly and
   that is a **coincidence**: record 133 at that stride lands mid-way through reversed tagged
   tags (`mmus`/`solc` = `summ`/`clos`). A prior investigation reported "stride 78, exact
   tiling, 980 anchors all at residue 42 mod 78" — the anchors are real, the grid is not. Its
   true framing is unknown and it is variable-length.
4. **The keys are not the `comp_<id>.dat` id space.** 0 of 409 match; those ids run
   1…2000099928.
5. **`reference.comp_refs` is not a route.** It returns `[{ref, season, ordinal}]` — an
   entrant list, not a fixture map — populated for only 24 of 1,272 competitions, and **empty
   for the European Champions Cup**, the case we most want.

---

## 5. THE FULL BYTE PROFILE (measured: 26,954 records, 409 stage groups, `frem-2026-06-11`)

Columns: offset, distinct u8 values, top values, how many of the 409 stage groups the byte is
constant within.

**Stage attributes** — constant in ALL 409 groups, so they describe the competition, not the
match. **This is the bridge material.**

| offset | distinct | note |
|---|---|---|
| `+31`/`+32` | 231 / 4 | **the stage key** (`+33`,`+34` always 0) |
| `+76` | 7 | 0 dominant (23,444), 255 on 1,770 |
| `+77` | 13 | 255 dominant (23,889) |
| `+80` | 4 | 0:22,449, 2:4,464, 64:38 |
| `+81` | 2 | 0:26,598, 4:356 |
| `+83` | 17 | Superliga 56, reserves 1, Pokalen 0, Friendly 18, an English league 0 — **reused across unrelated competitions, so a class not an id** |
| `+82` | 9 | constant in 408/409 |

**Per-fixture columns we currently discard:**

| bytes | measurement | reading |
|---|---|---|
| `+35`/`+36` | 256 / 58 distinct, const in only 53 / 82 of 409 | a per-fixture sequence id — the "no id column but the order implies it" shape |
| `+57..+60` | `+59`/`+60` = u16 year (2025/2026/108+7); `+57` 185 distinct, `+58` 7 | a **second date**, same shape as `+53`/`+55` |
| `+66`/`+67` | `0x07e8`/`0x07e9` = 2024/2025; 0 on 1,770 rows | a **third year**, plausibly the season |
| `+45`/`+46`, `+51`/`+52` | 255 on 26,566; sit immediately after each tid | likely a **second club pair** (aggregate/penalty winner?) |
| `+72..+75` | `+72` 206 distinct, `+74`/`+75` are 255-or-0 in lockstep with it | a `u32` present on 42% of rows |
| `+24`/`+25` | 8 / 7 distinct, const in only 53 / 54 groups | unclassified |
| `+39`, `+40` | 13 / 4 distinct | unclassified |
| `+84`..`+88` | 5 / 17 / 256 / 12 / 9 | unclassified; `+86` 256 distinct suggests a u16 |
| `day_raw >> 9` | `+54` has 5 distinct values | **we mask the day to 9 bits and throw away the top 7** |

**Genuinely constant (real padding):** `+0..+5`, `+16..+23`, `+26..+30`, `+43`/`+44`,
`+49`/`+50`, `+56`, `+61..+64`, `+68..+71`, `+89..+91`.

**The goals block `+2..+15`:** `+6` (10 distinct) and `+11` (7) are the goals; `+7`/`+8`/`+9`
and `+12`/`+13`/`+14` are 255 on ~99% of rows and carry small values on the rest. That is **six
goal-ish columns, not two** — 90/120 minutes, extra time, penalties.

### Why COVERAGE never caught this

`world_fixture` **is already registered** in `scripts/audit_records.py`'s `LAYOUTS` (line 144),
and it passes. COVERAGE asks "is every byte named or declared `UNKNOWN`?" — all 92 were.
**A declared-`PAD` span is a promise to come back, and nothing measured whether we had.** That
is the gap `scripts/profile_fixture_bytes.py` fills: it profiles the DATA and flags any
declared-PAD byte that varies, splitting per-fixture columns from stage attributes by testing
constancy under a grouping column.

---

## 6. THE ARCHIVE (`sicomps`, 159 members on Frem, 161 on Bucaspor)

`fmparser/archive.py`: `locate`, `directory`, `members(mm) -> {filename: Entry}`,
`read_member`, `extract(mm, "comp_man.dat") -> bytes` (payload starts at `blob[6:]`),
`summary`. Needs `zstandard`, **already installed** (0.25.0) — no `uv sync --extra archive`
needed, and note that command *replaces* the env, so pair it with `--extra dashboard`.
`_zstd()` raises `ArchiveError`, **not** `ImportError` — `fixtures.fixtures()`'s docstring says
`ImportError` and is wrong; fix it.

| member | unpacked (2026 save) | what is established |
|---|---|---|
| `fix_man.dat` | 2.52 MB | the 92-byte fixture grid |
| `comp_man.dat` | 232 KB | **best bridge candidate.** Variable-length, tagged fragments. 980 openers `01 ff ff 00 00 00` all at residue 42 mod 78. Semantics unknown |
| `stadium.dat` | 133 KB | `[u16 3][u32 15984]` then 8-byte pairs; 15,984 is one short of the reference stadium table's 15,987 |
| `rule_group.dat` | 67 KB | the only plain-text strings — engine log lines (`15/6/2025: Promoted seeding for Denmark (13th) - id=0 EURO Cup old_seed=2 new_seed=1`) |
| `comp_hosts.dat` | 31 KB | variable-length, one block per competition; 4-year host cycles (`0x07d2, 0x07d6, 0x07da, 0x07de`) |
| `rgman.dat` | 21 KB | clean 20-byte grid `[u32 index][u32 value][16 × 0xFF]` |
| `friend_man.dat` | 17 KB | index ramp then 14-byte records |
| `reserves.dat` | 1,500 B | constant within a career |
| `national_teams.dat` | 371 B | 9-byte `[u32 nation][u16 tid][u16 year][u8]`, 39 records |
| `discipline.dat` | 254 B | **byte-identical on every save of both careers** — a static enum |
| `fifa_rankings.dat` | 14 B | a date and one u16; no ranking table |
| `squad_man.dat` | 17 B | a stub by 2026 |
| `comp_<id>.dat` × 147 | 3.56 MB | see below |

### `comp_<id>.dat` — THE NAMES ARE ALREADY THERE

Each non-stub file is in the save's own **tagged** format (`fmparser/tagged.py`,
`walk_fields(blob, 6, len(blob))` parses it unchanged) and carries a `file=` string naming its
rules file, plus `SubF=` for the folder. **~90 of 147 are named this way:**

```
comp_6       dan_prem_3_6_euro_teams (3F Superliga)    comp_1301406  dan_cup (Sydbank Pokalen)
comp_7       dan_first          comp_8   dan_second    comp_2000016262 dan_third
comp_11      eng_prem           comp_12  eng_champ     comp_13  eng_league_one
comp_14      eng_league_two     comp_109201 eng_national
comp_1301426 eng_fa_cup_fmm     comp_1301427 eng_league_cup (Carabao)
comp_1301428 eng_charity (Community Shield)            comp_1301429 eng_efl_trophy_fmt
comp_109202  eng_fa_trophy
comp_1301394 eur_champions_cup_2021    comp_1301396 eur_uefa_cup_2021
comp_31051584 eur_conference_cup       comp_1301397 eur_super_cup
comp_1301385 wc_world_cup_2026         comp_100101..100105 wc_<confederation>_2026
comp_208999  wc_playoffs_2026          comp_90  inter_uefa_nations_league
comp_1301388 inter_euro_champ
```
Spanish / German / Belgian sets follow the same convention. Other tagged fields present:
`comp` (the file's own id, confirmed), `ftye`, `vers`, `type`, `levl`, `year`, `ygap`, `bsyr`,
`dtrn`, `stmn`/`styo`/`enmn`/`enyo`, `dcin`, **`fxri`**, **`stgs`**, **`indx`**, `ntms`,
`rvtm`, **`rnds`**, `mnts`, `tmmn`, `drdt`. The bolded ones are stage/round/index-shaped and
are the first things to read.

Stubs with no strings (276–348 B): `26, 27, 146957, 158186, 217951, 217952, 1702406, 5103714,
5103716, 18097860..18097867, 27001459, 27001479, 27001496, 27065986, 35010927, 91107110,
91107111, 94048275, 94048276, 2000099910..2000099928`. The 29-file block
`200001339..200001372` is 6–15 KB each with no strings — loaded competitions with no rules
file.

Each non-stub file is `[tagged rules block][large binary tail][tagged epilogue]`. On
`comp_100104.dat` the tagged block runs to 3,826 and the tail 3,826..46,951. The tail of
`comp_6.dat` is a **per-team grid carrying Danish club tids** (346, 344, 328, 337, 360) plus
~16 small values each. Stride not established.

**Zac's framing, and it is the right one: the name table is free. The only missing link is
`stage_key → comp id`.**

---

## 7. WHAT EXISTS IN THE STORE (`fm-frem.duckdb`, 25 snapshots, latest season 2027 / `2026-07-02`)

- **`staging.competitions`** — only 64 rows, ONLY comps *we* played in, and **empty for the
  latest snapshot**. Six distinct: cid 2 Superliga, 3 NordicBet, 4 2.Division, 65 Friendly,
  263 Sydbank Pokalen, 1147 3.Division, 1342 Danish Reserves Group 1.
- **`staging.leagues`** — 298 rows on the latest snapshot. **Leagues only, zero cups, by
  design**: `lightresults._is_league` filters `type_id in (0, 1)`. English: cid 5 Premier
  Division, 6 Championship, 7 League One, 8 League Two, 70 National League, 303/304 N/S,
  1347–1360 reserves.
- **`staging.league_members`** (`source='club_league'`) — the exact club→league map from each
  club's own record. 3,628 clubs / 296 leagues on the latest snapshot (79.7% of named clubs).
  `mart.club_leagues` wraps it.
- **`staging.results`** (14,396 rows, 7 OLD snapshots only) — has a real `cid` and resolved
  name, and it is the only place a foreign cup is named: **275 = English FA Cup**, 262 Belgian
  Cup, 266 DFB-Pokal, 273 Spanish Cup. **No date column** (`home_tid, away_tid, cid, seq, home,
  away, scoreH, scoreA, competition, copies`).
- **`staging.club_records`** — 246,864 rows, **123,432 carrying `(club_tid, opponent_tid,
  comp_cid, record_season, day)` across 46 comps**. Independently corroborates cid 275.
- **`staging.matches`** — 722 rows, **and they carry a REAL `comp_id`**: `reference.comp_id_at`
  reads a `u16` three bytes before the date field in the match header
  (`fmparser/matches.py:396`). This is a genuine labelled set but Danish-only — zero English,
  zero continental.
- **`mart.clubs.last_league_pos`** / `last_league_cid` — each club's **exact finishing position
  in its last completed league**, from the club record. A free oracle in every nation. Updates
  at the **July rollover** and describes the season that just ENDED. No points/W-D-L.
- **The save's own competition table** — `reference.find_comp_record` indexes **1,372 slots /
  1,272 named competitions**, a FIXED POOL identical across both careers. ~300 are non-league
  (i.e. the cups). `R.comp_detail(mm, cid) for cid in range(1372)` gives the complete
  cid→name→type table **including every cup**. Nobody has dumped it. Do this early — it is
  cheap and useful whichever bridge wins.
- **No cup structure anywhere**: a search of `information_schema.columns` across all schemas
  for `round|leg|group|seed|stage|cup|tie` returns **zero columns**.

---

## 8. PHASES

### Phase 1 — profile and declare every fixture byte *(IN PROGRESS)*

- **`scripts/profile_fixture_bytes.py` is WRITTEN but NOT YET RUN.** It reports per-offset
  distinct counts, top values, and **constancy within a grouping column** (default `+31`),
  flagging declared-PAD bytes that vary. Run it on the gate's four saves; verify the numbers in
  §5 reproduce, then check they hold on Bucaspor.
- Name in `fixtures.py` what the profile proves: `stage_key`, the stage attributes, the second
  date, the third year, the `+35` sequence id, the discarded day high bits. **Anything
  unproven stays `UNKNOWN`** — guessing a name is how `-140` became a Style candidate.
- Fix the `ImportError`/`ArchiveError` docstring error in `fixtures.fixtures()`.

### Phase 2 — confirm every archive member

- **`scripts/dump_archive_member.py <save> <member> [--hex|--tagged|--stride]`** — nothing in
  `scripts/` dumps a member today, and that gap is why `fix_man` sat unopened through four
  hunts. Reuse `archive.extract` + `tagged.walk_fields`; no new parsing machinery.
- Run over all 159 members on two saves per career; replace every "unexamined" in
  `docs/save-archive.md` with a structure or a measured negative.
- **`comp_man.dat` gets the most attention.**

### Phase 3 — find the bridge `stage_key → comp id`

Four routes. Stop at the first that validates against §3a's 8 named competitions plus our own 7
`comp_id`s.

1. **`comp_man` as the stage table.** If its records are stages, one carries a comp id and the
   key is its ordinal — the implicit-id pattern the codebase already relies on. Needs Phase 2's
   framing. **Most likely winner.**
2. **The tagged data dictionary 3-hop** (Zac's suggestion). `docs/save-archive.md` records that
   its `DBID` values overlap 54 of the 147 archive comp ids and its `comp` values 92. If a
   tagged record also carries a stage/fixture-group field the chain is
   `stage_key → tagged record → comp → file= name`.
3. **The `club_records` bridge.** 123,432 rows with `(club, opponent, comp_cid, season, day)`.
   Rebuild the date, join to a fixture on (club pair, date), read `stage_key → comp_cid` off.
   The only route landing in **our existing cid space**, where names already exist. Lower
   ceiling (club records are extremes, not fixtures) but mechanical and un-foolable.
4. **Dump all 1,372 competitions** via `reference.comp_detail` — the name table, worth having
   regardless of which bridge wins.

**Structural fallback, which ships either way.** Classify per STAGE, not per fixture — one
stage is one competition, so one verdict covers all 38 Premier Division rounds:
- `round = 255` → friendly.
- All clubs in the stage share one `league_cid` AND each round is a **perfect matching** over
  that league → that league, named exactly.
- Else: several divisions of one nation → that nation's domestic cup; across nations →
  continental.
Distinct stages stay distinct even when unnamed, so FA Cup and Carabao Cup are never conflated.

### Phase 4 — decode the goals block

Six goal-ish columns, not two (§5). Ground truth: the `0 - 0 p` Carabao tie (§3a), our 722
labelled matches, and the known counter-example:

```
plain (works):    01 14 ff ff ff ff  02 ff ff ff ff  01 ff ff ff ff   -> 2-1
frem 2023-02-22:  01 14 ff ff ff ff  00 00 ff 00 ff  00 01 ff 01 ff   -> reads 0-0, store says 0-1
```
Ship scores **only** under a per-row shape check, never the ~98% aggregate. Unexplained shapes
emit `NULL` and are **counted** — a known-unknown, not a silent wrong number.

### Phase 5 — load into staging and the mart

- **`staging.world_fixtures`**, raw per-snapshot. Measured: **444,526 rows across 25 snapshots,
  deduping to 73,392** distinct `(home, away, date)` — 6× overlap, **0 duplicates within a
  snapshot**. ~1.8× `staging.club_records`; not a scale problem.
- **Add `CREATE TABLE IF NOT EXISTS` to BOTH `DDL` and `_MIGRATIONS`.** `--refresh-only` runs
  `_migrate` + `create_views` + `create_mart` and **never calls `create_schema`**, so `DDL`
  alone will not create the table on an existing store and a mart view over it will fail with a
  Binder Error.
- **Add a `"world"` load group** alongside `core`/`light`/`standings` (`GROUPS`, `_GROUP_FN`,
  `_detect_groups`, `_clear_group`). A new table missing from `_clear_group` **doubles on
  re-load**. Guard the read with `os.path.exists` like `club_records` — `world_fixtures.json` is
  legitimately absent without the archive extra.
- Load pattern: build row tuples, call `_insert(con, table, cols, rows)` — a registered
  DataFrame + `INSERT ... SELECT`, **never `executemany`** (measured 300× slower). `dtype=object`
  is mandatory.
- **Mart is 58 views, 0 tables** — definitions cost nothing. Add to `ORDER` (topological, uses
  `.format()` so literal `%` must be `%%`). `MACROS` gives you `season_of(d)`.
  New views: `mart.world_fixtures` (career dedupe via `arg_max` over `mart.snapshots`),
  `mart.fixture_stages` (one row per stage), `mart.world_club_fixtures` (per-club, modelled on
  `mart.club_matches:771`, resolving opponent names **in the same snapshot**), and
  `mart.world_league_tables` if Phase 4 lands.
- **Deterministic `ORDER BY` everywhere** — PR #65 was exactly this bug.

### Phase 6 — validate across every league

- Per-stage perfect-matching coverage over all ~296 leagues, **reported as a table**. Baseline:
  on the 413 Premier-Division-club fixtures, 29 of 38 rounds are already a clean matching and
  the 9 failures are precisely where FA Cup (rounds 4–9) and Carabao (2–8) collide — which the
  stage key resolves outright.
- Cross-check `mart.clubs.last_league_pos` (needs Phase 4 scores to be meaningful).
- `validate_mart.py` invariants: **all 722 of our matches appear in `staging.world_fixtures`**
  (this check would have caught the day-late date bug on the spot); stage keys partition with
  no orphans; stage-attribute bytes really constant; grain uniqueness for the new views.
- **Measure cross-save stage-key stability before any cross-snapshot union.**

### Phase 7 — rebuild, gate, document

`docs/save-archive.md`, `docs/TODO.md` §4. Delete finished TODO entries rather than ticking
them.

---

## 9. OPERATIONAL FACTS

**A full re-extract is unavoidable.** All 25 `output/frem-*/world_fixtures.json` were written
before the `DAY_BASE` fix and the `round` decode: **every date is one day late and `round` is
absent in all of them** (verified: `wf.date == staging.matches.date + 1` for 722/722).
`--skip-existing` will **NOT** save you — its staleness marker keys on `players.json`, so those
dirs pass the check while carrying wrong fixture data. The four `output/oracle-*` dirs DO have
`round`.

Measured timings from `staging.extracts.loaded_at`: **full rebuild of 25 snapshots = 10 min
19 s** (~26 s each: ~21 s extract, ~5 s load). CLAUDE.md's "~12 min for 12 snapshots" is stale.

```bash
uv run python scripts/run_tests.py             # exit 2 means NOTHING ran
uv run python scripts/assert_identical.py      # THE GATE: 4 saves x 22 files, SHA-256, ~35s
uv run python scripts/assert_identical.py --record --note '<why>'   # when output SHOULD change
uv run python scripts/audit_records.py --map   # generated per-byte schema
uv run python scripts/audit_archive.py <save>  # CHAIN / COUNT / TILING / UNPACKED
uv run python scripts/rebuild.py --career frem # ~10.5 min
uv run python scripts/validate_mart.py --db fm-frem.duckdb
```

`extract.py` dumps with **no `sort_keys`**, so **JSON key order is part of the gate** — a reader
returning right values in the wrong order fails, correctly, because `load_duckdb.py` reads some
files positionally. `records.py` has `read_into`/`read_fields`/`read_group` specifically to
preserve order.

Saves are in `~/fm-saves/frem/` (27 of them, `frem-2021-07-01` … `frem-2026-07-02`) and
`~/fm-saves/bucaspor/`. DuckDB is single-writer — use `FM_DUCKDB_READONLY=1` or `read_only=True`.

**Git:** pushing needs `gh auth switch --user ZacHooper` (the default `zachooper-vinomofo`
account is read-only on the repo); switch back afterwards.

---

## 10. STATE AT HANDOFF

- Branch `feat/world-fixture-competitions`, **nothing committed yet**.
- `scripts/profile_fixture_bytes.py` — **written, not yet run or tested.**
- `docs/save-archive.md` line ~166 was corrected on a separate branch
  `docs/round-counter-in-archive-doc` (commit `d03a9f1`, unpushed) — it still said the round
  counter was "u32, not verified". Fold that in or cherry-pick it.
- Tasks #9–#15 in the task list mirror Phases 1–7.
- **Open ask for Zac:** export the **2027-02-25** save (the Man City fixture screenshot in §3c
  is from it, and it is a second-season naming oracle).
