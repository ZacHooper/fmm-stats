---
name: player-history-table
description: "Career-history table location/format in the save (for the Bilbao origin-club strategy) — spike-validated, not yet fully decoded"
metadata:
  node_type: memory
  type: reference
  originSessionId: e454ef70-998b-4f22-a5f3-5cc24a02618f
---

**Career (season-by-season) player history lives in a stride-16 table at ~40.6–40.7M** in
denmark-start.fms (may be multi-segment like the club DB — only ~40.6M confirmed so far). Each
row = one player-season, **16 bytes**, players concatenated, rows **oldest-season-first**:
- `+0` u16 = **club TID** (a REAL club tid — 359 Hvidovre, 370 Næstved, 346 Frem, etc. — NOT the
  disjoint datadict id-space; so club→region eligibility mapping via tid will work).
- `+2` u16 = flag, `ff ff` or `00 00` (fee/loan/"current"? unconfirmed).
- `+4` u32 = a counter that increments +1 per row but **segments every ~11 rows** (NOT a global id,
  NOT the player key).
- `+8` u32 = season/apps/goals-ish (`[byte][byte][byte][0]`; not cleanly decoded — didn't match
  screenshot Pld).
- `+12` u32 = zeros.

**Spike validation (2026-08):** Rasmus Wedege @40.632M = `[359 Hvidovre, 346 Frem, 346, 346]` —
exactly his in-game history (Hvidovre 2018/19 → Frem ×3). **Origin club = first row's tid.** So the
linchpin of the Athletic-Bilbao "sign only Copenhagen-Capital-Region origin" strategy is READABLE.

**Ground-truth players (denmark-start.fms) for further decode:** Wedege origin Hvidovre(359, Capital ✓),
Balslev origin Frem(346, ✓), Fugl origin Næstved(370, ✗ Zealand), Diyar Ali[Dalum player] origin
Dalum(339, ✗ Odense). Fugl visible near 40.692M as `[370,370,370,…]`. Club tids: **B1913 =
Boldklubben 1913 = tid 333** (reserves 7283); it's an Odense club (✗ not Capital).

**Match-stats columns (Pld/Gls/Ast/Yel/Red) are NOT in these 16-byte club rows.** Calibrated vs
Wedege's known 7 apps (2019/20): the post-season bytes at +9/+10 read 27/5 (and a "–"/0 season reads
25/6) — so they're not apps. This table = the club-per-season list only (top of the History screen);
the stat columns live in a SEPARATE structure, still unlocated. Parsing career games/goals is a
distinct future decode (find the parallel stats table + calibrate + handle loans — Diyar Ali's B1913
loan season doesn't even appear as club 333 next to his Dalum rows, so loans are recorded
differently). NOT needed for the Bilbao origin strategy. We already parse per-MATCH stats for the
current DB's matches ([[etl-duckdb-dashboard]]); history stats would only add past seasons of other
clubs.

**Non-managed players ARE in this table** (confirmed 2026-08): 18+ Dalum (non-managed) players'
histories read cleanly in region 40.4–40.8M, every club resolving to a real named club (Brøndby 337,
OB 371, FC Midtjylland 360, FC Nordsjælland 2465, Silkeborg 374, Vejle 1164, HB Køge 5277, Hillerød
356, Kolding, Sønderborg…). So scouting other clubs' origins works. `65535`/`0xffff` = null club row.

**SEGMENTATION KEY (likely solved):** the `+8` low byte is a **season code that increments within a
player and DROPS at each new-player boundary** (e.g. `…0x31,0x32 | 0x24,0x25…`). So split the table
into players wherever the season byte decreases; within a player, **origin = the row with the lowest
season byte** (earliest season). Validated: Wedege origin Hvidovre, and all Dalum players' earliest
row = their origin. Still to firm up on the full build: exact season-code→year mapping, how loans are
recorded (a player's mid-career loan season didn't always show the loan club cleanly — e.g. couldn't
pin Diyar Ali's B1913 loan row; B1913 may be stored as OB/371 or handled as a loan variant), and
whether the table is multi-segment beyond ~40.6–40.7M. Then: pick row0 club → look up
in a curated Capital-Region eligible-club list. See [[fm-parser-project]] (tagged region ~13-20M was
the wrong place — history is this packed table at 40.6M, not the tagged section).
