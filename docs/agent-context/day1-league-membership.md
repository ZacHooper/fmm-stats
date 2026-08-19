---
name: day1-league-membership
description: "SOLVED — how to read club→league membership (and thus the division's clubs) on any save, incl. day-1"
metadata: 
  node_type: memory
  type: reference
  originSessionId: e454ef70-998b-4f22-a5f3-5cc24a02618f
---

**SOLVED 2026-08 (Frem/Danish 3. Division).** club→league membership is stored **inside each
club's record** and is readable on day-1 (no matches needed). Cracked via the fmmvibe "How to make
a Super League" tutorial (club.dat editing) — the same structure is in the .fms save.

**The structure.** A club record = `[TID u32][UID u32]` then 3 length-prefixed name strings
(long / short / code; tolerate a 1-byte pad before each length, like reference.resolve_club). Let
`p` = offset just past the 3 name strings. Then:
- `p+0`: `[country u16][country u16]` = (competes-in, located-in) country. **Denmark = 138 (0x8a),
  England = 139 (0x8b)**. (Tutorial: Man City = `8b 00 8b 00`.)
- **`p+158`: `[league_code u16][ff ff]`** = the club's league. Verified: **English Premier = 5**
  (`05 00 ff ff`, matches tutorial), **Danish Superliga = 2**, **Danish 3. Division = 1147**
  (`7b 04 ff ff`). A club with no league / removed = `ff ff` there.

**To get a league's member clubs:** read the managed club's code at `p+158`, then scan EVERY club
record for that same code. Frem's 1147 → exactly **12 clubs**, matching the in-game 3. Division table
(Dalum, FC Roskilde, Frem, Herlev, Karlslunde, Lyseng, Næsby, Roskilde KFUM, Slagelse, Vanløse,
Young Boys FD, Vejlby Skovbakken). This is club→league for the WHOLE database — solves day-1
vs-league percentiles + scouting for any career, no results required.

**CRITICAL GOTCHA (cost us hours):** club records are **NOT in one contiguous region** — the club
DB is split across multiple segments (~6M / 7M / 9M / 13M in denmark-start.fms), separated by
filler. You MUST search the whole file, not a bounded window. A club can also appear in multiple
copies; the canonical one has the `[code][ff ff]` league field (secondary copies at ~13M read 0 /
`ff ff`). See the related TODO: [[savefile-boundary-map]].

**Why the other approaches failed (don't retrace):** the light-region 14-byte standings record and
the tagged datadict are both dead ends here — standings need a completed season; the tagged region's
ids are disjoint from club tids. The ~29.9M "fixture cluster" is a **global team registry** (all
~195 clubs, sequential entry-ids), not a division. The registry record's `+13..+14` field is a
club stature/reputation magnitude (Liverpool ~19000, Frem 30, Herlev 4) — useful as a strength
proxy but not a division label.

**SHIPPED (commit d0f60af):** `reference.club_record()` reads name + league code (+158) + country;
`reference.league_name()` resolves the code→name (relaxed UID cap + digit-initial names). `extract.py`
writes `club_league.json`; `load_duckdb.py` loads it (source='club_league'); the dashboard resolves on
it. Verified: Frem day-1 → full 12-club 3. Division pool + vs-league percentiles.
See [[etl-duckdb-dashboard]].

**THE CLUB RECORD IS THE ONLY SOURCE — never "merge" it with anything (fixed 2026-08-19).** The
original wording above said extract.py *merges* club-record leagues into club→league. It did, and the
merge ran the wrong way: `build_leagues()` seeded the map from the LIGHT RESULTS and the club records
only `setdefault`-ed into it, so light results won every conflict. Light results assign a club to the
competition its **already-played games** are tagged with, so on a season-boundary save they report
LAST season's division for every club that was promoted or relegated. On Frem's 2023-07-02 save that
put Aalborg in the Superliga (record: NordicBet Liga), Jammerbugt in the 1. Division (record: 2.
Division), Hellerup in the 3. Division (record: 2. Division), Middelfart in the 2. Division (record:
3. Division), and four relegated clubs in the 3. Division (records: Denmark's Series 476/477) — **50
clubs wrong, and every Danish division the wrong size (13/12/11/16 instead of 12/12/12/12)**. The
user's in-game ground truth caught it; see [[ground-truth-beats-my-parse]].

`extract.py` now builds club→league from the club records ALONE and explicitly discards
`build_leagues()`'s map (that call is retained only for the leagues *reference* — names, nation,
reputation). Cost of dropping light results entirely: 4 foreign clubs lose an assignment (2 with no
club record at all, 2 Belgian sides the light results mislabelled anyway). Zero Danish impact.

**Corollary — the extract emits a SNAPSHOT; derivation belongs in the ETL.** `club_league.json` is
"which competition is each club in on the save date", nothing more. The raw fixture list is loaded
separately (`staging.results`, every row carrying its cid), so any historical view can be derived in
SQL without contaminating the snapshot. Related: `dashboard/db.effective_table` used to resolve
club→league by taking the newest mapping **store-wide with no season filter**, which leaked a later
season's promotions back into historical slices; it now resolves as-at the requested (season, phase)
and only falls back to earlier snapshots.

**Sanity check to run after any change here:** every division in the managed nation must come out the
right size. `SELECT league_cid, COUNT(DISTINCT club_tid) FROM staging.league_members WHERE
source='club_league' AND phase=<p> GROUP BY 1` → Denmark should be 12/12/12/12 for cids 2/3/4/1147.
A club with 0–3 players can legitimately sit in a division (Brønshøj had 3, FC Sydvest 0), so squad
size is NOT a validity filter — don't "fix" the count by dropping those.
