# FMM Save Parser — reverse-engineering Football Manager Mobile saves

Reverse-engineering the binary save file `fm_save1.fms` (Football Manager Mobile
**2022**) to extract data — primarily **per-match player statistics**, which are
not documented anywhere online and were worked out from scratch here.

> **Goal:** read data *out* (players, and especially per-match player stats). This
> is a read/analysis project, **not** a save editor. We do not write back to the file.

---

## Status at a glance

| Area | Status |
| --- | --- |
| Per-match player stat blocks (all fields) | ✅ **solved & validated 100%** |
| Both teams' XIs per match | ✅ solved |
| Match header (teams, date, attendance) | ✅ solved |
| Match event stream (goals/cards/injuries + minute) | ✅ solved & confirmed in-game |
| Yellow cards (per player) · stoppage-time minutes (`90+3`) | ✅ solved (`yellow` @ block byte 53; `min_display`) |
| Star player per team (`star_home`/`star_away`) | ✅ derived from rating (not stored — see BUGS #3) |
| Whole-season enumeration + JSON export | ✅ solved (`season_extract.py dump` → `season_data.json`) |
| Score reconstruction (incl. own goals) | ✅ solved |
| Play-off labelling + First/Second Leg | ✅ solved (comp 227 → "… Play-Off", leg by date) |
| **Club TID → name** | ✅ solved (`clubs.py`, `clubs.json`) — 42/42 |
| **Competition / match type** | ✅ solved (`comps.py`) — league/cup/friendly/playoff/reserve |
| **Own-squad player TID → name** | ✅ solved (`squad.py`, `bucaspor_players.json`) — 28 players |
| **Own-squad player attributes** | ✅ solved (`attrs.py`) — all 23 visible attrs + idx9 hidden |
| **Preferred foot (left/right, 0–20)** | ✅ solved (`attrs.py`) — bytes M+33/M+34, 10/10 verified |
| **CA / PA** | 🟡 strong lead (bytes M+35/M+37, CA≤PA holds 28/28) — see BUGS #7 |
| **Player info field (Step 2)** | ✅ solved (`info.py`) — TID/UID/name-IDs/DOB/nationality/club/SID (`flag28` = TBD) |
| **Unified player profiles** | ✅ solved (`profiles.py`, `player_profiles.json`) — all structures joined |
| **League-wide player data** (positions, feet, CA/PA, reputation, 9 attrs) | ✅ solved (`league_attrs.py`) — 466/487 via SID; opponents included |
| Opponent full attribute set (technical/GK visibles) | ⛔ not stored raw in the global record — see [League-wide section](#solved-mostly--league-wide-player-data-opponents-included) |
| **Hidden attributes** | ⛔ low priority (per user; immersion) — idx9 + tail leads only |
| **Opponent player TID → name** | ⛔ open (needs global name index) — see [Open step 1](#open-step-1--tid--player-name-resolution) |

---

## The save file

- Path: `fm_save1.fms`, **64,423,598 bytes** (~61 MiB).
- **Uncompressed** — readable ASCII strings, large `00`/`ff` padded regions. Raw
  byte parsing works directly (no inflate/decrypt needed).
- Header (offset 0): `26/5/22 - Herr Manager (Bucaspor 1928)` — the save is
  FMM22, managing **Bucaspor 1928** (a Turkish 2. League club).

### Encoding conventions

- **Integers are little-endian.** (Online hex guides quote big-endian — reverse
  the byte pairs. `UID 37045583` → `0x0235454F` → bytes `4F 45 35 02`.)
- **Strings are length-prefixed**: a 4-byte little-endian length, then the bytes
  (UTF-8; Turkish letters appear as multi-byte sequences, e.g. `ş` = `C5 9F`).
- **IDs** (from the community hex guide, `rough-guide.md`):
  - **TID** (True/Team ID) — 4 bytes `XX XX 00 00`; the working identifier for an
    entity. Immediately precedes the UID in a record.
  - **UID** — the sortitoutsi-style unique ID.
  - **SID** (Stats ID) — links a player to their attribute/hidden-attribute record.
  - Bucaspor's club TID = `a7 19` (`0x19A7` = 6567); club UID = `0x042D4EE1`.

---

## Repository files

| File | What it is |
| --- | --- |
| `fm_save1.fms` | The save being parsed (FMM22). |
| `fmtool.py` | Exploration toolkit: mmap search, hex dump, UID→LE, **breadcrumb trail**. |
| `parse_match.py` | The validated 54-byte match-stat-block decoder. |
| `season_extract.py` | Whole-season extractor: headers, events, both XIs, scores. |
| `season_data.json` | Exported season (74 matches, ~1,960 player-match stat lines). |
| `clubs.py` | Club TID → name resolver. |
| `clubs.json` | Resolved club map (TID → long/short name). |
| `comps.py` | Competition ID → name resolver (match type). |
| `squad.py` | Own-club player TID → full name (from squad snapshots). |
| `bucaspor_players.json` | Resolved own-squad names (28 players). |
| `attrs.py` | Own-squad player attributes + positions + preferred foot. |
| `attrs_raw.json` | Per-player positions + decoded attributes + raw bytes. |
| `info.py` | Player info field (Step 2): DOB, nationality, club, SID. |
| `player_info.json` | Parsed info records for the squad. |
| `profiles.py` | Unified player profiles (name+info+attrs+season stats). |
| `player_profiles.json` | The joined profiles. |
| `BUGS.md` | Known bugs / follow-ups. |
| `ground_truth_match1.json` | Screenshot-derived truth for one match (validation set). |
| `breadcrumbs.json` | Durable trail of known offsets (see below). |
| `rough-guide.md` | Community FMM hex-editing guide (attribute maps etc.). |
| `README.md` | This file. |

### Toolkit quick reference (`fmtool.py`)

```bash
python3 fmtool.py find   <hex>        # find raw bytes, e.g. 6c560000
python3 fmtool.py finds  <ascii>      # find a string, e.g. Menize
python3 fmtool.py uid    <decimal>    # decimal UID -> little-endian bytes -> locate
python3 fmtool.py dump   <off> [n]    # annotated hex+ascii dump
python3 fmtool.py mark   <off> <note> # drop a breadcrumb
python3 fmtool.py trail               # replay all breadcrumbs
```

`Save` (in `fmtool.py`) mmaps the file: `from fmtool import Save; s = Save()`,
then `s.mm` (bytes), `s.find_all(needle)`, `s.dump(off, n)`, `s.mark(off, note)`.

### Reproduce the results

```bash
python3 parse_match.py 56549031        # decode Bucaspor's XI in the Karacabey match
python3 season_extract.py              # season summary table (75 anchors)
python3 season_extract.py 56546292     # full per-player detail for one match
python3 season_extract.py dump         # (re)write season_data.json (star/yellow/leg/min_display)
python3 squad.py && python3 info.py && python3 attrs.py && python3 profiles.py  # rebuild player data
```

---

## File map (major regions, by offset)

| Offset (approx) | Region |
| --- | --- |
| `0` | Save header / name. |
| `~2.75–2.9 MB` | **Global player info-fields** (TID, UID, name IDs, DOB). |
| `~315 K–406 K` | Surname string table (UTF-8, length-prefixed; not flat-indexed). |
| `~10 MB` | Club records (name, TID, UID, 3–4 letter code). |
| `~21.3 MB` | Tactics/formation records (`4-2 Diamond`…) — uses the match delimiter but has **no** stats. |
| `~56.2–56.6 MB` | **Match-stats region** — 75 matches (header + home XI + away XI). |
| `~62.4–63.1 MB` | Bucaspor squad snapshots: inline names + **attributes** + positions + TID + marker, then **feet + CA/PA** after the marker. |

---

## SOLVED — per-match player stat block

Located in the match-stats region. Each player is a **54-byte block**; blocks are
separated by an **8-byte `0xFF` delimiter** → **stride 62**. A team's XI is stored
contiguously in lineup order (`posOrder` byte). Home XI, then away XI; `posOrder`
resets to 1 for the away team.

**Block-start invariant** (robust; do *not* rely on byte 0, which is `assists`):
`condition[3]` in 1..100, bytes `[17]==[18]==[20]==0xFF`, `posOrder[41]` in 1..30,
and a nonzero player `TID[42:46]`.

### Field map (offsets within the 54-byte block) — all validated vs screenshots

| Off | Field | Off | Field | Off | Field |
| --- | --- | --- | --- | --- | --- |
| 0 | assists | 16 | interceptions | 32 | rating (whole number) |
| 3 | condition (%) | 19 | subOn minute (255 = n/a) | 35 | shots attempted |
| 4 | crosses attempted | 21 | subOff minute (255 = n/a) | 36 | shots on target |
| 5 | crosses completed | 22 | mistakes | 41 | posOrder (lineup slot) |
| 8 | dribbles | 23 | mistakes leading to goal | 42:46 | player **TID** (u32 LE) |
| 10 | goals | 25 | passes attempted | 28:30 | **SID** (u16) |
| 11 | headers attempted | 26 | passes completed | 48 | tackles attempted |
| 12 | headers won | 27 | key passes | 49 | tackles won |
| 16 | interceptions | 32 | rating | 53 | **yellow card** (1 = booked) |

Validation: all 11 starters × 17 comparable fields matched the in-game screenshots
exactly (`ground_truth_match1.json`, Karacabey Bld 3-3 Bucaspor, 30 Apr 2022). Yellow
card (byte 53) confirmed too (Karacabey pos2/pos3, Bucaspor pos6 Yüksel).
Still-unmapped bytes: `[1] [2] [6:8](u16?) [24] [30:32] [33:35] [37:41] [46:48] [50:53]`.

---

## SOLVED — match header

Each match begins with a **delimiter cluster**: the unit `?2 22 55 15 0a 00 00 00`
repeated ~10× (the same pattern used in the earlier mojo attempt), ending in a run
of `0x12` bytes. This is the reliable per-match anchor.

The header then contains tactics + team stats + an event list, and this signature:

```
[home TID:u16][away TID:u16][day:u16][year:u16 == 0x07xx][attendance:u16]
```

- **Date** = 1 Jan of `year` + `day` days. (`day 119 / 2022` → 2022-04-30.)
- `parse_header()` locates it by scanning for a plausible year word (2018–2030)
  with a valid day before it and sane TIDs/attendance around it.
- ~half the 75 records involve club TID `11320` with attendance `0` — these are
  other league fixtures the engine stored full stats for (not Bucaspor games).

---

## SOLVED — match event stream (goals, cards, injuries)

Sits just before the header signature. Each event is a fixed unit:

```
[b0][b1 = TYPE][minute:u16][b4][player TID:u32][ff ff ...]
```

- `b1` is the **event type**; `b0` is a modifier (for goals it varies — likely
  how-scored/assist). `minute` is a `u16`: **low byte = base minute** (0-based, +1),
  **high byte = added (stoppage) minutes** → `min_display` like `"90+3"`.
- **Parse events by validating the TID against the match's 40 players** — not by a
  numeric range (an earlier range filter silently dropped a goal by a low-TID player).

**Confirmed event types (`b1`)** — all verified against the game:

| `b1` | Meaning | | `b1` | Meaning |
| --- | --- | --- | --- | --- |
| `01` | goal | | `05` | red card |
| `02` | own goal | | `06` | injury |
| `03` | penalty (scored) | | `29` | disallowed goal (offside) |
| `04` | missed penalty | | | |

Plain **yellow cards are not logged** in this stream — only major events.

### Score reconstruction

Own goals are **not** credited to any player's `goals` field, so:

```
home_score = Σ(home players' goals) + (own goals scored by away players)
away_score = Σ(away players' goals) + (own goals scored by home players)
```

Own goals are identified from events (`b1 == 0x02`) and credited to the opposing team.

---

## SOLVED — season enumeration & output schema

`season_extract.py`:
1. Finds all 75 delimiter clusters in the match-stats region (match anchors).
2. For each: `parse_header` → `find_xi` (home) → `find_xi` (away) → `parse_events`.
3. `find_xis` returns stride-62 runs of blocks in file order (home XI, then away
   XI), splitting teams when `posOrder` resets. **A run must be ≥7 blocks** — this
   skips a per-match *team-totals record* that sits before the XIs and otherwise
   passes the block check (it caused a junk "home" block with bogus goals; verified
   fixed, 0 home/away order mismatches and 0 missing XIs across all 74 matches).

Every stat block passed a validation sweep: for all Bucaspor matches the home XI
matches `home_tid` (correct home/away orientation), and known-result matches
(Karacabey 3-3, Pendikspor 3-3, the Uşak playoff legs 2-1 / 1-0) all reconcile.

`season_data.json` is a list of matches:

```jsonc
{
  "anchor": 56546300,
  "date": "2022-04-30",
  "home_tid": 6353, "away_tid": 6567,
  "attendance": 975,
  "score": { "home": 3, "away": 3 },
  "events": [ { "min": 12, "tid": 21263, "type_byte": 1, "type": "goal", "b0": 8 }, ... ],
  "home_xi": [ { "posOrder": 1, "tid_int": 30973, "rating": 6, "goals": 0, ... }, ... ],
  "away_xi": [ ... ]
}
```

Every player line carries the full stat set from the field map above, plus `sid`.

---

## SOLVED — club TID → name

Club records are standalone, FF-padded, in the ~7–13 MB region:

```
[TID:u32][UID:u32][len:u32][long name][pad][len:u32][short name][pad][len:u32][code]...
```

- Read a name by: find the TID bytes, then `[+4]`=UID, `[+8]`=len, `[+12]`=name.
- **The discriminator that makes it reliable is the *club shape*:** a real club is a
  long name immediately followed by a valid length-prefixed **short name**. Regions
  (e.g. "Schleswig-Holstein"), stadiums (`uid=5000`, e.g. "MOSiR"), and first-name
  table collisions have the right TID bytes but *fail* this shape check.
- Do **not** filter on UID magnitude — real Turkish clubs range from `uid≈1863`
  (Altay) to `≈2e8` (reserve sides); an early UID floor wrongly hid the famous old
  clubs.

`clubs.py` resolves **42/42** club TIDs in the season (long + short names). Reserve
sides are separate records ("… Reserves"). `clubs.json` caches the map. Verified:
`6353` = Karacabey Bld., `6567` = Bucaspor 1928, `11320` = Bucaspor 1928 Reserves.

## SOLVED — competition / match type

Each match header stores a **competition ID** as a `u16` at **`date_off - 3`**
(immediately before the `[home][away][day][year][att]` core). Competition records
live in the ~13 MB region with the same shape as clubs:
`[compID:u16][UID:u32][len][long name][len][short name][len][code]`. `comps.py`
resolves the id → name (short names/codes can start with a digit, e.g. "2L").

Season distribution (confirmed against the game — the Uşak May two-leg tie is the
play-off, its other two meetings are league):

| comp_id | competition | matches |
| --- | --- | --- |
| 228 | Turkish 2. League White Group (regular season) | 34 |
| 1370 | Turkish Reserves Group 4 (reserve league) | 32 |
| 65 | Friendly | 4 |
| 117 | Turkish Cup | 2 |
| 227 | Turkish 2. League — promotion **play-off** phase | 2 |

Bucaspor's first team = 34 league + 4 friendly + 2 cup + 2 play-off = **42** (the
reserve fixtures use TID 11320 under comp 1370). `competition` + `comp_id` are now
in every `season_data.json` record.

## Breadcrumb trail

`breadcrumbs.json` (via `python3 fmtool.py trail`) records every confirmed offset
with a note, so we can re-find our place in the bytes. Key entries include the save
header, Bucaspor club record, the player info-field region, the surname table, the
match-stats region start, the event-unit format, and the Karacabey match anchor.

---

## Open step 1 — opponent player TID → name resolution

**Problem:** matches/events reference *players* by **TID**. Clubs are named, and our
**own squad is fully named** via `squad.py` (the club's snapshot records carry inline
full names — 27 players, `bucaspor_players.json`). What remains is **opponent**
players, who have no snapshot in our save and so need the global name index.

**What we know:**
- Every player has an **info-field** in the global DB (~2.75–2.9 MB). Layout:
  ```
  [TID:u32][UID:u32][firstNameID:u32][lastNameID:u32][FFFFFFFF][DOB day:u16, year:u16]...
  ```
  Find it by searching the TID bytes and checking `mm[hit+16:hit+20] == FF FF FF FF`
  (the empty-nickname marker). This yields `firstNameID` and `lastNameID` for any TID.
  (Verified: Menize TID 22124 → first 7657, last 16552.)
- Name strings live in a **surname string table** (~315 K–406 K), UTF-8,
  length-prefixed. Clubs are named in the ~10 MB club records (already readable).

**The blocker:** the name IDs are **not** flat indices into the surname table. We
pulled 11 known players' (TID → lastNameID) and found the implied table base is
inconsistent (949, 15470, 14650, …), so the strings are stored via an **indexed /
paged** structure, not by position. There is almost certainly an ID→offset index
(or per-page ID ranges) we have not located.

**What to try next:**
1. Find the name index: search near the surname table for a parallel array of
   `u16`/`u32` IDs or offsets. Look for a header/count before the string blocks and
   for per-block ID ranges (the table parses in chunks that stop at boundaries).
2. Separate the **first-name** table from the **surname** table (their ID ranges
   overlap; they may be distinct tables or share one index).
3. Calibrate with the 11 known (nameID → string) pairs already in hand:
   - firstIDs: Demir 437, Duruk 696, Balıkuv 676, Özcan 787, Köseoğlu 724,
     Yüksel 355, Menize 7657, Fındıkçı 7586, Sun 684, Bıyık 3085, Behram 437.
   - lastIDs: Demir 885, Duruk 16375, Balıkuv 16095, Özcan 4556, Köseoğlu 1165,
     Yüksel 15652, Menize 16552, Fındıkçı 16431, Sun 16444, Bıyık 16159, Behram 15717.
   Any candidate index must map these IDs to the correct strings.
4. Cross-check: the Bucaspor **squad-snapshot** region (~62 MB) has inline
   full names next to player TIDs (e.g. `6c 56 00 00` right before reputations in
   Menize's record) — usable to name our own squad without solving the global index.

**Ground-truth source:** sortitoutsi-style lookups, or in-game screens — the user
can supply exact name spellings for any TID we surface.

---

## SOLVED — own-squad player attributes, positions & feet

`attrs.py` reads each squad player's record from the snapshot region, anchored on the
club marker `a7 19 ff ff` at offset **M**. Layout:

```
M-59 … M-36  24 attribute bytes (idx 0–23; idx9 = one hidden attribute)
M-35 … M-24  12-byte tail (reputation / hidden traits — still unlabelled)
M-23 … M-9   15 position ratings (GK,SW,DL,DC,DR,DMC,ML,MC,MR,AML,AMC,AMR,ST,DML,DMR; 20 = natural)
M-8  … M-5   player TID (u32 LE)
M    … M+3   club marker  a7 19 ff ff   ← the per-player delimiter
M+33 / M+34  LEFT / RIGHT foot (0–20)
M+35 / M+37  CA / PA (u16 each; strong lead — CA≤PA holds for all 28)
M+39 … M+42  constant ref-UID   ·   M+43 ff ff
```

**Attribute byte → label** (all 23 visible attributes confirmed vs screenshots;
Demir/Ataş/Efe/Şener GKs + Behram/Bıyık/Duruk/… outfielders):

| idx | attr | idx | attr | idx | attr |
| --- | --- | --- | --- | --- | --- |
| 0 | Aerial | 8 | Dribbling | 17 | Leadership |
| 1 | Agility (GK) | 9 | *hidden* | 18 | Movement |
| 2 | Communication (GK) | 10 | Passing | 19 | Positioning |
| 3 | Handling (GK) | 11 | Shooting | 20 | Teamwork |
| 4 | Kicking (GK) | 12 | Tackling | 21 | Pace |
| 5 | Throwing (GK) | 13 | Technique | 22 | Stamina |
| 6 | Reflexes (GK) | 14 | Aggression | 23 | Strength |
| 7 | Crossing | 15 | Creativity | | |
| | | 16 | Decisions | | |

Notes: **Communication** display = raw + leadership boost (captain Demir raw 10 →
shown 13); a captain's **Leadership** shows boosted too (raw 9 → 12). Leadership &
Strength are raw 1:1. ±1 age-drift between save and later screenshots is normal.
Handling/Reflexes (idx 3/6) order per the rough guide.

**Preferred foot** — `preferred_foot((left,right))` maps the two 0–20 bytes to an
FM-style label. Verified against 10 players (incl. outfield left-footer Alıç and
two-footer Sun): left corr 0.92, right corr 0.97. All 10 labels exact.

### Remaining here (low priority)

1. **idx9** — one hidden attribute in the visible block, still unidentified.
2. **CA / PA** — bytes M+35/M+37 are a strong lead (CA≤PA holds 28/28); confirm vs a
   known CA/PA value if one can be sourced.
3. **Tail M-35…M-26** and **post-marker M+4…M+12 / M+25…M+29** — unlabelled bytes that
   *vary* across players (reputation, squad number, hidden traits?). The byte-map
   artifact lays these out per player with distinct-value counts to triangulate.
4. **Hidden attributes** — LOW PRIORITY (per user; immersion). Leads in `BUGS.md` #5.
5. **Opponent attributes** — needs attribute records outside our squad snapshots
   (same blocker as opponent names — the global index).

---

## Open step 3 — team-level match stats

The match summary screen also shows **possession, shots, shots on target, clear-cut
chances, corners, team rating**. These live in a per-match **team-totals record**
that sits just before the two XIs (breadcrumb at `56582523`): a ~54-byte block that
references **both team TIDs** (e.g. home `a7 19`, away `19 46`) and passes the
stat-block shape check (which is why it had to be excluded from XI detection).
Decoding it would add team-level stats to every match. Ground truth already exists
in `ground_truth_match1.json` (`team_stats`: possession 48/52, shots 11/8, SoT 5/4,
clear-cut 3/1, rating 6.6/6.7) to calibrate against.

---

## Ground truth still useful

- **A known CA/PA value** (or a large-CA/PA-gap wonderkid) to confirm bytes M+35/M+37.
- **Squad numbers / reputation** for a few players — to label the varying unknown
  bytes (tail M-35…M-26, post-marker M+4…M+29) surfaced in the byte-map artifact.
- **Opponent name spellings** for surfaced TIDs, if/when the global name index is
  cracked (Open step 1).
