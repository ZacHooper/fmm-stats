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

Two of our `ATTR_OFFSETS` entries disagree with the FMM26 names and need a ground-truth check
before either is trusted: we call `P-29` **Aerial** where this order says **Heading**, and we
derive Teamwork from `P-25`+`P-9` where the order says those are **Unselfishness** and
**Positioning**. Neither is necessarily wrong (FMM22's UI labels differ from the DB's internal
names, and a displayed value can be derived) — but they are the two to verify first.

## People / info record — FIXED 2026-09-16, see BUGS #14 Round 4

Was truncated at +64; the record is variable-length and ends with counted **language** and
**relationship** lists. Now fully accounted for. `PlayerId` (−1 for staff) is our SID staff rule.

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

## Competition record — we parse about half

We read cid, uid, long/short/code, type, nation_id, reputation. `Competition.cs` also has:
**`Level` (division tier!)**, **`ParentCompetitionId`**, `ContinentId`, foreground/background
`Color`, a `Qualifiers` table (n × 8 bytes), `Rank1..3` + `Year1..3` (a 3-season history), and
`IsWomen`. **`Level` is the one to grab** — we currently hardcode the Danish pyramid
(Superliga=2, 1.Div=3, 2.Div=4, 3.Div=1147) in [[denmark-division-tiers]]; `Level` would derive
it for any nation instead. Not yet located in the FMM22 record.

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
