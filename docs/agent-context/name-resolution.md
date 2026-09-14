---
name: name-resolution
description: "SOLVED — resolve any player's name (incl. non-managed) from first_name_id/last_name_id via the browse table + id-index tables"
metadata:
  node_type: memory
  type: reference
  originSessionId: e454ef70-998b-4f22-a5f3-5cc24a02618f
---

**SOLVED 2026-08 (denmark-start.fms).** Every player's name — INCLUDING non-managed clubs — is
resolvable from the info field's name ids. Validated 10/10 managed squad + Diyar Ali (Dalum, tid
26862) + full Dalum/Herlev squads → clean Danish names. (Inline names @~58M are managed-club ONLY;
the id link avoids duplicating the name strings for everyone else — user's insight.)

**The resolution chain (three structures):**
1. **Browse table** (offset 299 .. ~515797, section 1): a flat `[len u32][utf-8]` list, ~45,942
   entries, nation-grouped (NOT id-order). Walk it once → `browse[ordinal] = string`.
2. **Two id-index tables** (in the big binary section ~37M), each **16 bytes/record**, **dense &
   sorted by id from 0**: record = `[browse_ordinal u32][id u32][~const u32][flags u32]` (id at +4
   self-verifies). `+0` is the ordinal into the browse table.
   - **Surname table** @ 37.109M (den) — 28,624 entries (id 0..28623). `last_name_id` indexes this.
   - **First-name table** @ 37.624M (den) — 15,366 entries (id 0..15365). `first_name_id` indexes this.
   - Layout: surname table first (lower offset, larger), then first-name table. Bases are per-save
     (offsets differ Frem vs Buca) and NOT 4-byte aligned to the file — discover, don't hardcode.
3. **Info field** (`reference.parse_info`): `first_name_id`=u32(+8), `last_name_id`=u32(+12).

**resolve(tid):** `first = browse[ id_first[first_name_id].ordinal ]`,
`last = browse[ id_sur[last_name_id].ordinal ]`, full name = `f"{first} {last}"`.
Anchors used this save: BASE_SUR = 37243546 − 8389*16 = 37109322; BASE_FIRST = 37698950 − 4703*16 =
37623702 (Grønne last_id 8389 → ord 21114; Rasmus first_id 4703 → ord 40712).

**Why it was hard / how the boundary map helped:** the id has NO positional relationship to the
browse table (adjacent entries Andersen id1450 / Sørensen id160), and there's no offset-index array —
so id→string needs these separate id-index tables, which sit mid-file inside the big binary section
(not adjacent to the names). Found via searching the whole file for the `[ordinal][id]` u32 pair.

**SHIPPED (2026-08).** `reference.build_name_resolver(mm, validate=…)` auto-discovers the browse table
(`_walk_browse`) + both id-index tables (`_discover_id_tables`, anchors on id=8192, walks the dense
run back to base). Orientation: larger table = surnames, then a self-check against the managed squad's
snapshot names flips it if needed (WATCH: swap only if the alternative scores *higher* — the naive
condition is inverted). `reference.resolve_name(mm, first_id, last_id)` → "First Last" (cached per
mmap). `extract.build_database` builds the resolver validated on `own_names`, then
`full_name(tid,p) = own_names.get(tid) or resolve_name(...)` for every player + staff row. **Result:
denmark-start → 24,315/24,315 named (100%); Frem squad 23→29 (reserves Wedege/Fugl/Balslev now appear
— that was the "mislabel"); Diyar Ali + all division opponents named; Bucaspor ground-truth still
passes.** Resolve from the SCRAPED per-record name ids (staging.scrape_players already reads
first/last_name_id), NOT `parse_info(tid)` — the by-tid search collides on low tids (returned wrong
players in a proto). Bonus not yet used: the inline snapshot record (@~58M, managed only) also carries
club + league as text. See [[savefile-boundary-map]], [[player-history-table]], [[etl-duckdb-dashboard]].

**CLUB names are a different path — `reference.resolve_club` — and it has two traps (2026-08-19).**
1. **A shape filter can eat REAL records.** `_valid_name` required >= 2 alphabetic characters, and
   a club record is only accepted if its SHORT name validates — so `"B.93"` (one letter) threw away
   the entire real club record for tid 334, leaving only an unrelated *award* record that happens to
   share the tid. B.93 rendered as "Player of the Month". Fixed: short names use `min_alpha=1`, long
   names keep the stricter guard. Exactly 5 of 4,836 clubs changed, all Danish/Faroese "B.xxxx"
   sides (331 B1908, 332 B1909, 333 B1913, 334 B.93, 586 B68).
2. **A tid can match more than one record, and first-match wins.** 346 matches BOTH Boldklubben Frem
   (@6.53M) and an award "Team of the Week" (@13.77M); Frem is correct only because its real record
   comes first in the file. Still latent. `club_record()` has the discriminator — **real clubs carry
   a league AND a country; award records carry neither.**

**So: never diagnose a bug from a resolved club NAME — check the tid.** Chasing "why is an award
showing as a player's club" as a career-history bug cost real time; the history parse was correct
and the name lookup was wrong.

## Club names: the uid gate dropped 327 real clubs (2026-09-12)

`reference.py`'s club branch accepted only `1 <= uid <= 400_000_000`. Every club whose uid sits
in the ~2-billion band was thrown away: **327 in a 2026 Frem save, 363 in a 2022 Bucaspor save**.
At the 2026-03-22 snapshot that left **293 players at 79 clubs** that could only render `#<tid>`.

Ground truth came off two in-game player profiles, not from the parse: Shawn Beeckaert plays for
tid 6863, which the game shows as **"EM United"** — Erpe-Mere United, uid 2,000,004,399, a
well-formed record at byte 10,104,532. We were keeping "Erpe-Mere United **Reserves**" (uid
200,010,882, under the ceiling) while dropping the first team. Jesús Bernal's tid 7153 is
"Paracuellos" = C.D. Paracuellos Antamira, uid 2,000,112,622.

**Third uid gate in this file to be wrong the same way** — `find_comp_record`'s old `uid >= 1000`
rule skipped every top division for the mirror-image reason. A uid is an identifier, not a range.

The ceiling was NOT simply raised. Widening it in place **corrupts real clubs**: person records
match the club shape (a first name followed by a surname) and win low tids on file order, renaming
C Cerro Porteño → 'Ultee', Club Sporting Cristal → 'Boujemaoui', Club Centro Deportivo Municipal →
'Leemans'. So the band is a second, strictly **gap-filling** tier — a tier-1 record can never
displace a tier-0 one — and it additionally requires the club **trailer marker** (`ff ff` at
p+160), which costs 9 of 336 fills and removes all 9 surnames. A wrong club name is worse than a
missing one.

Verified additive on both careers: **0 existing names changed, 0 lost**.
`tests/test_club_uid_gate.py` holds the screenshot ground truth plus the three displacement cases.

This is the same lesson as the award-record note above, from the other direction: the club index
is where club-name bugs live, and the discriminators that work are STRUCTURAL (trailer marker,
league, country) — never a guessed numeric range.

## A tid you CANNOT name is probably not a person (2026-09)

Reported as "some player names not coming through — I presume they have retired". They had not.
Every real player we ever fielded IS nameable, including retirees and departures, because he sat
in some snapshot's `players` table while he was around and `mart.player_snapshots` spans every
snapshot. So an unnameable tid means something else entirely.

On Frem's store all 49 of them came from one band (33007–33106) and all of them from **reserve**
fixtures. Three facts settle what they are:

* not one of them appears in **any** club's squad in **any** snapshot (the real reserve squad at
  tid 7296 is 35 players with tids 701–32160);
* the **same** tid turns out for up to nine different reserve clubs in a single season
  (33052 played for 7296, 7284, 7297, 7277, 7309, 7318, 7320, 9805 and 7294) — no person does
  that;
* their stat blocks are otherwise well-formed: real ratings, real minutes, real positions.

So the save simulates the reserve league with **anonymous filler**, and the tid in those stat
blocks is a per-match roster slot, not a player id. There is no name to find; do not go looking
for one, and do not widen the name chain above to try.

They are also not harmless. `mart.our_clubs` includes the reserve club, so they rode into
`matches.json` and put "#33015" second in the site's all-time average-rating table, ahead of most
of the first team. `scripts/export_data.py` now drops match rows whose tid cannot be named, which
is exactly this set — a real player's reserve appearances are named and unaffected.

## Resolve a match row's name by person_id, never by tid alone (2026-09)

Found while verifying the export above. `matches.json`'s `player_names` was built with
`SELECT tid, ANY_VALUE(name) ... FROM mart.player_snapshots GROUP BY tid`. A tid is a recycled
slot ([[tid-recycling]]), so that group sweeps in the snapshots where the slot belonged to
somebody else entirely, and `ANY_VALUE` then picked between the two people by scan order.

**7 of our 74 named players came back under a stranger's name — and a different stranger on the
next export.** tid 4240 alternated between Johan Nordberg (ours) and Thomas De Clercq; 20597
between Jean Pierre Graabæk and Raúl Tirilonte. The History page was quietly attributing a Frem
career to a man who never played for us, and the value was not even stable run to run.

The match row already carries the answer: `mart.match_player_facts.person_id`. Key the name
lookup on that and the era ambiguity never arises. Two things make it safe:

* no tid serves two different people among our own appearances, so one name per tid is still
  well defined and the site's tid-keyed map does not need reshaping;
* `person_id` is a **string** `'<tid>-<dob>'`, not an integer — casting it with `int()` raises.

Pick the winner with an explicit `ROW_NUMBER() ... ORDER BY phase_date DESC, tid DESC, name`
rather than `ANY_VALUE`: one person_id does carry two spellings, and an unordered pick there is
the same non-determinism one level down.
