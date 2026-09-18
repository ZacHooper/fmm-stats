---
name: fmm-editor-record-comparison
description: "Our save-file parsers vs nyongrand/fmm-editor's FMM26 database parsers, record by record — what we parse fully, what we truncate, and what we never touch"
metadata:
  node_type: memory
  type: reference
---

**`github.com/nyongrand/fmm-editor` (C#, `FMMLibrary/`) is a field-by-field reader for the
FMM26 pre-game database, and its record layouts map onto our FMM22 SAVE almost one-for-one.**
Comparing the two on 2026-09-16 showed we were truncating several records. This file is the
per-type comparison. Verified against `frem-2024-11-10.fms` unless marked otherwise.

`.dat` vs `.fms` is **not** an Android/iOS split — `.dat` is the shipped pre-game database a new
career is generated from, `.fms` is a save game. Both platforms have both; Android just exposes
the database folder where iOS seals it in the app sandbox. What matters here is that **the save
embeds the same record layouts as the database**, so fmm-editor's field names transfer.
Expect FMM22↔FMM26 drift at the margins; every divergence found is flagged below.

## Player / attribute record — WE TRUNCATE IT (13 bytes short)

fmm-editor `Player.cs` gives the whole record. Aligned to our `P` (positions-block start), the
FMM22 record is **`P-42 … P+35`, exactly the 78-byte grid `fmparser/attributes.py` already
walks**:

| offset | field | us |
|---|---|---|
| `P-42` | **Id** (this is what we call `sid`) | ✅ |
| `P-38` | **Uid** | ✅ (the `P-38` player link of [[history-chain-pointers]]) |
| `P-34 … P-8` | 27 outfield attributes | partial |
| `P-7 … P-1` | 7 GK attributes | partial |
| `P … P+14` | 15 position ratings | ✅ |
| `P+15/16` | left / right foot | ✅ |
| `P+17` / `P+19` | CA / PA | ✅ |
| `P+21` | **Home**Reputation (we call it just `reputation`) | ✅ |
| `P+23` | **CurrentReputation** | ❌ |
| `P+25` | **WorldReputation** | ❌ |
| `P+27` | **InternationalRetirement** (bool) | ❌ |
| `P+28` | Unknown1 — **FMM26 says "always 0x0000"; in FMM22 it is NOT zero** | ❌ |
| `P+30` | **SquadNumber** | ❌ |
| `P+31` | **PreferredSquadNumber** | ❌ |
| `P+32` | **Height (cm)** | ❌ |
| `P+34` | **Weight (kg)** | ❌ |

**Height/Weight are CONFIRMED, not inferred.** Over 26,518 records: height min 153, median 182;
weight min 55, median 73. And the decisive internal check — **goalkeepers average 188.2 cm /
78.2 kg against 180.4 / 71.8 for outfielders** (n=2,860 vs 19,628). `InternationalRetirement` is
0 for 26,492 of 26,518. Reputation ordering is sane (FCK > FCM > OB > Silkeborg > AaB).

**Divergence to chase:** `P+28..29` is a real non-zero u16 in FMM22 that FMM26 zeroed or
repurposed. Highly repetitive (one value on 4,437 records), high byte clusters in
{0x98,0x88,0xA8,0x89} — looks like a flags/enum field. Unidentified.

**The 34 attribute slots are now NAMED.** fmm-editor's order is, from `P-34`: Crossing,
Dribbling, Tackling, Finishing, LongShot, Heading, Jumping, Passing, Decision, Unselfishness,
**Pace, Strength, Stamina, Technique**, Consistency, **Aggression**, BigMatch, InjuryProne,
**Leadership**, Versatility, SetPieces, Penalty, Creativity, Movement, Positioning, WorkRate,
Flair, then Handling, Kicking, **Agility**, Aerial, Reflexes, Communication, Throwing.
**All seven offsets we had confirmed independently land exactly where this order predicts** —
Pace `P-24`, Strength `P-23`, Stamina `P-22`, Technique `P-21`, Aggression `P-19`, Leadership
`P-16`, Agility `P-5`. That is strong mutual validation of both decodes.

**FMM22 fills only 18 of the 34 slots** — and which 18 is the finding. The other 16 hold 0-255
data with ~150 distinct values; there is no overlap, so the two classes are separable by shape
alone. The live 18 are Heading, Jumping, Unselfishness, Pace, Strength, Stamina, Technique,
Consistency, Aggression, BigMatch, InjuryProne, Leadership, Versatility, SetPieces, Penalty,
WorkRate, Flair, Agility. The dead 16 are Crossing, Dribbling, Tackling, Finishing, LongShot,
Passing, Decision, Creativity, Movement, Positioning, Handling, Kicking, Aerial, Reflexes,
Communication, Throwing.

That is a semantic line, not a random one: FMM22 stores the ability-independent attributes
plain and the technical/goalkeeping ones in a wrapped 0-255 encoding. An 18/16 partition falling
that cleanly is independent confirmation of the order, on top of the seven anchors. On that
basis the nine unnamed attribute bytes were **named** on 2026-09-16: `jumping`, `consistency`,
`big_match`, `injury_prone`, `versatility`, `set_pieces`, `penalty`, `work_rate`, `flair`.

**The 0-255 slots are NOT computed at display time — they hold the attribute, entangled.**
`fmparser/model.py` has been predicting from those exact bytes all along, and a positional test
settles what they carry. At MATCHED ability (CA 95-105, n=3,596), each source byte ranks
positions exactly as its fmm-editor name says:

| byte | name | top | bottom |
|---|---|---|---|
| `P-34` | Crossing | AMR 263, MR 262, AML 260 | DC 219, GK 173 |
| `P-32` | Tackling | DC 272, DMC 268 | ST 211, GK 175 |
| `P-31` | Finishing | **ST 282**, AMC 251 | DC 213, GK 173 |
| `P-27` | Passing | MC 272, DMC 268 | ST 244, GK 241 |
| `P-11` | Movement | ST 270, AML 268 | DC 226, GK 181 |
| `P-10` | Positioning | DC 275, DMC 265 | ST 223 |
| `P-7…P-1` | the 5 GK attributes | **GK 244-279** | every outfield position flat at ~170-174 |

The goalkeeping five are decisive: GK ~80 points clear with all ten outfield positions
indistinguishable. `corr(byte, CA)` is only 0.02-0.25, and within a 10-point CA band the bytes
still have sd 20-35 — this is per-player information, not a re-encoding of ability.

So the ordering is confirmed **slot by slot**, not just at the seven anchors, and two
long-standing claims are retired: `fm-parser-project.md`'s "FMM stores a REDUCED set and
computes the full 23-attr screen on demand", and this PR's own earlier wording that FMM22
"computes those from CA at display time". Both wrong. **Follow-up worth having:** the frozen
model is ~63% exact / ~93% within 1, fitted on 28 players; bytes with signal this clean should
support a far better decode.



Two of our `ATTR_OFFSETS` entries disagree with the FMM26 names, and both are KEPT on purpose:
we call `P-29` **Aerial** where this order says **Heading** (the FMM22 UI says Aerial), and we
derive Teamwork from `P-25`+`P-9` where the order says those are **Unselfishness** and
**WorkRate**. FMM22's UI labels differ from the DB's internal names and a displayed value can be
derived, so neither is a conflict. (An earlier revision of this file said `P-9` was Positioning;
that was a slip — Positioning is `P-10`, and it is one of the dead 16.)

## People / info record — FIXED 2026-09-16, see BUGS #14 Round 4

Was truncated at +64; the record is variable-length and ends with counted **language** and
**relationship** lists. Now fully accounted for. `PlayerId` (−1 for staff) is our SID staff rule.

`People.cs` also settles where the **personality block** lives — the 8 bytes Adaptability,
Ambition, Controversy, Loyality, Pressure, Professionalism, Sportmanship, Temperament are
declared here, on the INFO record, which is where BUGS #14 verified them byte-exact against 7
managers' screenshots. `docs/ATTRIBUTE_DECODING.md`'s old `P-50 … P-43` row was wrong and is
corrected. **One discrepancy to keep in mind:** slot 3 is **Controversy** in FMM26 and reads
**Determination** on the FMM22 screens we checked. Ours is the ground-truth reading for our game.

## Staff / coach attributes — fmm-editor DOES NOT DECODE THIS RECORD

Worth stating plainly, because it is easy to assume otherwise: **there is no `Staff.cs`.** The
repo's model files are Player, People, Club, Competition, Nation, City, Stadium, Language,
Currency, Name, Region, Affiliate, Kit, NationalTeam, Relationship, PositionRating — and nothing
for coaching ability or the manager formation triple. `People.cs` reads the info record and
stops at `Unknown6b`, a u32 it never follows; that u32 is our `id2`, and it is the link to the
staff attribute record (`fmparser/staff.py`). Everything in that 39-byte record — the coaching
values, the formation triple, `attacking_intent` — is ours, verified against screenshots.

The practical consequence: the six unnamed staff bytes (`hidden_s18 … hidden_s28`) have **no
upstream order to borrow**. They stay named by offset until we have ground truth of our own.

## Club record — WE PARSE THE NAMES AND ALMOST NOTHING ELSE

`reference._build_refdata_index` reads tid, uid and the 3 name strings, and `club_league` picks
a league code off an empirical `+158`. fmm-editor's `Club.cs` decodes the entire trailer, and it
parses FMM22 cleanly. **FMM22 has 3 name strings (long/short/code); FMM26 added a 4th
(SixLetterName + ThreeLetterName) — our 3-string read is correct for our game.**

After the names (terminator byte follows strings 1 and 2):
`BasedId u16`, `NationId u16` (138 = Denmark, both read 138 for all Danish clubs tested — which
of the two is really BasedId is unverified), **6 × Color**, **6 × Kit** (`[2 flag bytes][10 ×
Color]`), `Status`, `Academy`, `Facilities`, `AttAvg`, `AttMin`, `AttMax`, `Reserves`,
**`LeagueId u16`**, `OtherDivision`, `OtherLastPosition`, `Stadium u16`, `LastLeague u16`,
length-prefixed `Unknown5`, `LeaguePos`, **`Reputation u16`**, 20 bytes, `Affiliates`
(**21 bytes each**: Unknown1, Club1Id, Club2Id, start day/year, end day/year, Unknown2),
`Players[]`, `Unknown7[11]`, `MainClub`, `Type`.

**A Color is a u16 in RGB555** (`r=(c>>10)&0x1f` etc., each <<3). This corrects BUGS #15, which
read the trailer's flood of `0x7FFF` as sentinels and guessed "stadium capacity / finance".
**`0x7FFF` is white** — that region is club colours and kits. Verified: AaB decodes to white +
red, FCK blue + white, FCM red + dark, OB white + blue.

Confirmed-plausible values on the 5 Superliga clubs tested:
- **`LeagueId` = 2 for all five**, and we independently know Superliga is cid 2. This is a
  direct, structural club→league link — better than the empirical `+158` offset.
- `AttAvg/Min/Max` rank FCK 3300/1000/5000 > OB 1100 > AaB 1300 > FCM 800 > Silkeborg 500 —
  real relative club size.
- `Reputation` FCK 6882 > FCM 6092 > OB 5524 > Silkeborg 5460 > AaB 5096 — plausible.
- `LastLeague` = 2 for everyone except AaB = 3, and AaB came up from the 1st Division.
- `Academy`/`Facilities` land in 13–18.

**`Players[]` is a real squad array and is the headline opportunity.** All five clubs yield
**exactly 40** entries, of which ~24–25 have an info-spine `club_tid` pointing back at that club.
The uniform 40 suggests FMM22 uses a **fixed 40-slot array** rather than FMM26's count-prefixed
list — *probable, not confirmed*. If it holds it is a direct answer to the
`club_tid`-is-not-safe problem in CLAUDE.md: a club's actual registered squad, straight from the
save, instead of inferring membership from loan spells. **`MainClub`** would likewise replace the
hardcoded reserve tids in `careers.py` — but it currently decodes to a negative sentinel, so the
tail alignment drifts somewhere after `Players[]`. Both need pinning down before use.

## Competition record — the whole record is now located (2026-09-18)

Superseded: this section used to read "we parse about half", with `Level`,
`ParentCompetitionId`, `ContinentId`, the colours and the `Rank1..3`/`Year1..3` history all
listed as "not yet located in the FMM22 record". They are all located now, and so is the
record's END — `reference._walk_comp_table` reads every slot the table declares by arithmetic
(1372 on Frem, 1371 on Bucaspor, `cid == slot index` throughout), which it could not do without
knowing the exact extent. `scripts/audit_records.py --map` prints the per-byte schema; that is
the documentation, generated rather than retyped, so prefer it over anything restated here.

The layout, after `[cid u16][uid u32]` and the three length-prefixed names (exactly one
terminator byte after the long and short names, none after the code):

| piece | width | holds |
|---|---|---|
| `comp_trailer` | 14 | `type`, `continent` (u16, FIFA confederation 0-5, `0xFFFF` = global), `nation` (u16, `0xFFFF` = none), `fg_colour`, `bg_colour`, `reputation`, **`level`**, **`parent_cid`** |
| `comp_history_count` | 4 | `n_entries` |
| `comp_history_entry` | 8 × n | UNNAMED — see below |
| `comp_history_tail` | 21 | 3 × u32 (unnamed) + `season_0..2` + u16 + u8 — fmm-editor's `Rank1..3`/`Year1..3` shape |

**`Level` is read** (`level`, trailer +11) — 0 = a nation's top flight, 1/2/3 below it — so the
hardcoded Danish pyramid in [[denmark-division-tiers]] can be derived for any nation instead.
Confederation-style records carry junk there (100/112), so filter on `type_id` before using it.

Two things deliberately NOT named, both because a plausible read is not a decode:
- the **8-byte history entry**. `[u32 value][u16 season][u16]` fits 21,440 of 25,758 entries
  and fails for 4,318 (Major League Soccer's read season 0 after the first).
- the **tail's three u32s**. They pair with the three seasons as parallel arrays, but 3F
  Superliga's read 505/526/507, which resolve as English clubs, so they are not club tids.

The entries sit BETWEEN the count and the tail, which was established by content and not by
arithmetic: all the candidate orderings give the same record length, and 1,348 of 1,372 records
have `n_entries == 0`, where they coincide. On the 914 records that do carry entries the season
triple reads as a plausible year at `record_end − 9` on 686 and at `count + 16` on zero.

`IsWomen` is a later-game-version field (per Zac); FMM22 saves do not carry it, so it is not
part of this record's unresolved extent. The `Qualifiers` table is the most likely identity of
the 8-byte entries, still unconfirmed.

## Record types we did not parse — now done (2026-09-16)

All five landed in `fmparser/places.py` (stadiums, cities) and `fmparser/lookups.py`
(languages, currencies, nations). Every table is located STRUCTURALLY — by chaining, by a
fixed stride, or by a signature — never by a constant offset, because regions.py windows
drift per save and per career.

| table | rows | keyed by | verified against |
|---|---|---|---|
| `staging.stadiums` | 15,987 | club record's `stadium_id` | Parken 38,065 and Aalborg Portland Park 13,800 — the real capacities, exactly |
| `staging.cities` | 10,928 | stadium's `city_id` | Copenhagen 55.6761/12.5683, Aalborg 57.0488/9.9217 |
| `staging.languages` | 77 | the language ids on every person record | 7=English, 10=German, 31=Danish — the ids inferred from the managers' lists |
| `staging.currencies` | 94 | — | Danish Krone 8.699, Czech Koruna 29.81 per GBP |
| `staging.nations` | 227 | `nationality_id` on every person | Denmark→Copenhagen→Parken, England→London→Wembley, Norway→Oslo→Ullevaal, Sweden→Stockholm→Friends Arena |
| `staging.nation_ranking_history` | 5,040 | nation | ranked nations only; the count GROWS with career length (10 in 2022, 24 by 2026) |
| `staging.nation_coefficients` | 1,441 | nation | UEFA-only (131 of 227): Germany 20.0, England 19.86, Italy 19.29 |

`mart.club_places` joins club → stadium → city, so every club has a ground, a capacity and
real coordinates. `mart.languages` / `mart.currencies` / `mart.nations` expose the lookups;
`mart.nations` supersedes the static `NATIONS` dict in `reference.py`.

**Three traps worth remembering**, all of which produced confidently wrong output first:
- **Club records have the same shape as nation records** (long name, short name, 3-letter
  code). A club called "Ghali Club de Mascara" claimed Belgium's id 131 on a first-wins scan.
- **Competition records do too**, and are packed just as densely, so "densest cluster" alone
  picks the competition table. Nations need a continent-id ceiling AND a position filter;
  neither works on its own.
- **A loose plausibility test is not a locator.** Finding the city table by "lots of valid
  lat/lon in one region" selected noise; the real signature is a long run of records spaced
  exactly one record apart.

**The nation record's national-team block is decoded too** — world ranking, ranking points,
rival nation, a growing ranking history and the UEFA country coefficients (`mart.nations`,
`mart.nation_ranking_history`, `mart.nation_coefficients`). The coefficients are what seed a
European campaign, so they matter once a club reaches continental football.

Three checks establish it without any external table:
- the ranking is very nearly a **permutation** — 186 distinct values over 1..210 across 209
  ranked nations, which a mis-read field cannot produce;
- every `rival_nation_id` resolves to a genuine rivalry: Belgium↔Holland, Brazil↔Argentina,
  England↔Scotland, Denmark↔Sweden, Portugal↔Spain, Croatia↔Serbia, Pakistan↔India;
- coefficients are **UEFA-only** — Brazil, Mexico, Peru and Argentina come back empty.
Russia is rank 0 while keeping 1,463 points (suspended), and non-FIFA territories (Bonaire,
Crimea, Réunion, Mayotte, Wallis & Futuna) are 0/0. The final coefficient is always 0.0: the
season in progress, which is why `mart.nations.current_coefficient` skips it.

Still unparsed: **Region** (name, nation, weather) and the nation record's counted language
list.

## How to use this

fmm-editor is a **layout oracle, not a drop-in**. It reads standalone `.dat` files with a
sequential `BinaryReader`; our records are embedded in a 63 MB save and must still be located
structurally (see CLAUDE.md's region-first method). The win is that once a record is located,
its field order is no longer guesswork. Clone it fresh when needed —
`git clone --depth 1 https://github.com/nyongrand/fmm-editor`.

**`jal-co/FMMLoader-26` is unrelated** — a mod installer for Football Manager 2026 *desktop*,
no binary parsing at all. Checked and discarded.
