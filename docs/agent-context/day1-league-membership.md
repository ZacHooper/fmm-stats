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
merges club-record leagues into club→league and writes `club_league.json`; `load_duckdb.py` loads it
(source='club_league'); the dashboard resolves on it. Verified: Frem day-1 → full 12-club 3. Division
pool + vs-league percentiles. See [[etl-duckdb-dashboard]].
