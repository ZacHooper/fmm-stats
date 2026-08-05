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

**ROW/RECORD FORMAT — FULLY DECODED (2026-08).** A player's history = a variable-length run of 16-byte
rows, oldest→newest, DELIMITED by a row where **`+4 == 0xFFFFFFFF` AND `+8`(season)==40** (next real
record's first row has season 41). Data row = `[+0 club u16][+2 flag ffff/0000][+4 u32 global
counter][+8 season code][+9 appearances][+10 goals][+11..15 ~0]`. The `+8` season byte is an **ABSOLUTE year code, NOT a per-player reset**: **50 = current season
(2021/22)**, counting back (49=2020/21 … 40=2011/12 … 39=2010/11). Careers START at whatever year they
began — a one-club Frem veteran runs 40→50 (11 rows), a youngster runs 47→50 — and **almost every
active player's LAST row = season 50 (their current club)**. `+9/+10` are real per-season apps/goals
(verified career: Brøndby youth 0-app → Hvidovre 18/4,25/6 → Frem 27/5,12 → loan Skovshoved 4 → Frem).
The DELIMITER row (`+4==FFFFFFFF`) carries season 39 or 40 and a club in `+0` that's often the adjacent
player's origin/current club but not reliably — semantics unresolved, not needed. (Earlier note that
season "resets to 40" was WRONG — corrected here.) **Annotated dump: ~/Downloads/history_dump.txt.**

**Lead for the link:** since season-50 row = current club, a record's season-50 club should equal that
player's info `club_tid`. Matching records→players by (season-50 club + career shape) is the most
promising angle for the ordinal key next session (loans complicate: season-50 club may be a loan club).

**LINK MECHANISM CONFIRMED (2026-08, via user's in-game screenshots) — records are SID-ORDERED.**
Ground truth: **Mikkel Andersson** (tid 9400, sid 5833) record @40632797 — our apps sum=246, goals=11
EXACTLY match his screenshot TOTAL; **Pierre-Emile Højbjerg** (tid 9394, sid 5828) record @40631741
(København→Brøndby→Bayern→Augsburg/Schalke loans→Southampton→Tottenham). Key facts:
- **Delimiter row's `+0` = the player's CURRENT club** (Andersson→Frem 346, Højbjerg→Tottenham 518).
- **`+2` is the TRANSFER FEE, not a flag:** `0xffff`=stayed, `0xfeff`=loan, `0`=free, else £000s
  (`15000`=£15M Tottenham, `12256`=£12.25M Southampton) — user-decoded, verified.
- **`+8` season is ABSOLUTE: 50 = 2020/21** (last COMPLETED season; save date 4 Jul 2021 so 2021/22
  has 0 games), counting back. `+9`=apps, `+10`=goals, `+11..15`=assists/yellows/reds/avg-rating
  (trailing, per user). NOTE a ~1-row lag: the club/stat can be off-by-one vs the screenshot (e.g.
  Augsburg showed 23 not 16) — alignment of stat→season within a record needs a tweak.
- **Ordinal by SID:** the 6-player window sid 5828→5833 maps 1:1 IN ORDER to 6 consecutive records
  (current-club matched 4/6, the 2 misses being loans where info.club_tid=loan club ≠ history
  current). BOTH anchors gave the IDENTICAL local offset (record#↔sid-position), i.e. clean 1:1 by
  sid LOCALLY. There is NO 3-hop pointer (a record's +4 counter appears only in the table, not in the
  player's info/attr record). So the link = **sort players by sid; the Nth (that has history) = the
  Nth record**, current club = delimiter +0.

**REMAINING WALL = robust enumeration of the FRAGMENTED table.** Delimiter counts swing wildly by
filter (2.5k–50.8k) because the history records sit in clusters interspersed with FF-filler / other
data, so no single region-bound or season-filter cleanly isolates ALL records — hence global
sid-alignment fails (offset constant within a cluster, jumps between). NEXT SESSION: (1) isolate each
clean history CLUSTER precisely (contiguous run of valid [club][fee][counter][season] rows with the
+4 counter increasing by 1 between FFFFFFFF delimiters); (2) enumerate records per cluster; (3) align
each cluster to the sid-sorted player list using the constant local offset + current-club(delimiter+0)
as the anchor, handling loans (current club may be the loan club). Then per-player full history is
readable. Format is DONE; only the fragmented enumeration + per-cluster sid-anchoring remain.

**(old) TWO REMAINING WALLS (superseded by the SID finding above):**
1. **Table is FRAGMENTED.** The dense clean run around 40.630–40.634M is only ~16 records, then a big
   gap, then another cluster — the ~24k histories are scattered in many small clusters across ~39–45M
   (the boundary-map "fragmented 38–39M zone"). Enumerating ALL clusters cleanly is unsolved.
2. **Ordinal key unknown.** No tid/uid/sid in the record (confirmed — id searches inside a record are
   coincidental byte hits). Linking must be ordinal, but current-club alignment fails for
   uid/tid/sid/file-order (0/16 position-match on a clean 16-record cluster; faint 11/16 subsequence
   signal only). The order the game uses is still not identified.

Next session starts from HERE: format is known; (a) find/bound every history cluster, (b) find the
ordinal key (try: reputation, ca, dob, nationality-grouped, or the attribute-record physical order).

**TWO OPEN BLOCKERS (history is NOT yet cracked — deeper than names):**
1. **Segmentation is wrong/unclear.** The 0xFFFFFFFF-marker + s8-reset gives ~13–14 row blocks, but
   Wedege's validated rows (`[359,346,346,346]`, s8=45..48) sit in the MIDDLE of such a block, not at
   its start — so the markers are NOT per-player boundaries. Real per-player grouping + multiple-
   rows-per-season (s8 repeats, e.g. 48,48) still undecoded.
2. **No player→segment LINK found.** Checked and ruled out: tid/uid/sid do NOT appear in or near
   the history segment; no uid companion-index in the 38–49.5M region; the player's main record
   (@ uid, ~1.7M) has NO pointer into 40M and no segment-counter. So linking a history run to a tid
   is the fundamental unsolved problem. Remaining hypotheses: (a) ORDINAL ALIGNMENT — segments in the
   same order as some player enumeration (info/attr/uid order), align Nth↔Nth (untested); (b) a
   player→history index elsewhere (the 3-hop pattern, not yet found).

**ALIGNMENT TEST RAN — FAILED (2026-08).** Marker-delimited segments (+4==0xFFFFFFFF boundaries) in
the clean region 39.56–43.81M number **23,189 ≈ 24,315 players** (encouraging), median 7 clubs/seg.
BUT ordinal alignment does NOT hold: segment last-club vs uid-sorted and tid-sorted players'
current club = **0/2000** position matches. And segment "last clubs" are ~all unique whereas real
current-clubs repeat heavily (40 players at club 1201) — so either the segmentation captures
marker/summary rows or the marker≠player-boundary assumption is still wrong. Earlier "screenshot
matches" (Wedege [359,346,346,346]) were club-SEQUENCE pattern matches, NOT tid-confirmed — that
window sat mid-journeyman-segment, likely coincidental. Net: neither segmentation NOR linking is
actually solved; the club/season DATA is present but the record structure resists. Deprioritised —
needs a dedicated deep-RE session, not a quick win.

**ROOT CAUSE FOUND (2026-08): true bounds/delimiter still unknown.** The link is NOT embedded — a
known player's uid/tid/sid appears NOWHERE in 39–44M, and marker rows (`+4==0xFFFFFFFF`, e.g.
`6c01ffff ffffffff 2800...`: +0=a club, s8=0x28=40) carry no id — so linking MUST be ordinal (as the
user reasoned: parallel load-order arrays). BUT ordinal alignment can't be validated yet because the
segmentation is wrong: the `sane-+4` region bound (39.56–43.81M, 265k rows) is mostly NOT history —
filtering to real club rows (+0 in 250–8500, +12==0) inside it yields ~0, so most of that region is
other data, and the 23,189 "segments" were junk (hence all-unique last-clubs, 0/3000 alignment for
uid/tid/sid/info-order). NEXT SESSION must: (1) find the EXACT history-table extent (contiguous run
where every 16-byte row is club+season) — the clean rows are around 40.63M but the true start/end and
whether it's multi-segment are unknown; (2) find the real per-player delimiter within it; (3) THEN
re-test ordinal alignment against info/attr/sid load-order. This is a dedicated deep-RE task, not a
quick win — deprioritised in favour of shipping the scout tool on names+attributes (both done).

**User constraint (2026-08, important):** FM won't store history it doesn't surface (wasted space), so
each player's stored history == exactly the screenshot seasons — COMPACT. Wedege = ~4 rows
`[Hvidovre, Frem, Frem, Frem]`, NOT the 12-row Brøndby→…→Frem run I kept matching. That long run's
season byte increments UNBROKEN across 5 clubs, so it spans MULTIPLE players and the season byte is
NOT the per-player delimiter. Concrete next-session target: in the true (compact) history table,
Wedege appears as a ~4-row `{359,346}` run — find the delimiter that makes that run a clean unit
(candidates: the +2 flag ffff/0000, or a marker I haven't isolated), then each player is a short run
and ordinal alignment to load-order becomes testable.

**What IS present:** the history DATA is real and readable per-run (club sequences look like careers) —
screenshot; Dalum players resolve). It's the *systematic* segmentation + tid-linking that's hard.
Loans are a further wrinkle (Diyar Ali's B1913=tid 333 loan row didn't appear as expected). Pragmatic
call: the scouting tool can ship on names+attributes NOW (both done); history/eligibility is a
follow-on once the link is cracked. Origin-club/eligibility is analysis-side (a config list of
eligible club tids), NOT the parser's job. Then: pick row0 club → look up
in a curated Capital-Region eligible-club list. See [[fm-parser-project]] (tagged region ~13-20M was
the wrong place — history is this packed table at 40.6M, not the tagged section).
