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

**ROW FORMAT (clean region ~40.6M):** 16 bytes = `[club u16][flag u16(ffff/0000)][+4 u32 GLOBAL
counter][+8 s8 season-code][+9,+10 two stat bytes][+12 u32 ≈0]`. The `+4` counter is a global
sequential row index (continuous down the whole table); rows where `+4 == 0xFFFFFFFF` are marker rows,
and `s8` resets to 40 right after each marker then increments +1 per row.

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
