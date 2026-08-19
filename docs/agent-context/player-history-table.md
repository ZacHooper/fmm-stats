---
name: player-history-table
description: "Career-history table location/format in the save (for the Bilbao origin-club strategy) — spike-validated, not yet fully decoded"
metadata:
  node_type: memory
  type: reference
  originSessionId: e454ef70-998b-4f22-a5f3-5cc24a02618f
---

## 2026-08-19 (afternoon) — SOLVED END TO END: pointer chains + the `P-38` id link

The table is fully decoded and **reproduces all five in-game Player-History screenshots
exactly** — every season line and every career TOTAL (Dirksen, M. Andersson, M. Thrane, Fugl,
Erenbjerg; `denmark-24-start.fms`, in-game 30 Jun 2023).

**SHIPPED.** `fmparser/history.py` was rewritten on this model and is wired into `extract.py`
(`H.build(mm, info, attrs)` — it needs `attrs` now, for the `P-38` link). All 10 frem saves
parse and pass the forest check, 21.4k–23.6k players each; **8 of those 10 previously returned
zero rows**. `scripts/history_v2.py` is now a thin debugging CLI over the module.
`scripts/find_history_table.py` was deleted (superseded prototype).

The morning's section below is superseded where it conflicts; its diagnosis of *why* v1 broke
was right, its proposed record grammar was not.

### 1. `+4` IS A NEXT-ROW POINTER, NOT A COUNTER
This is the whole thing. Each row stores the **0-based index of the next row in that
player's chain**, or `0xFFFFFFFF` for end-of-chain. On a fresh save every record is
physically contiguous, so row `k` holds `k+1` — which is exactly why v1 read it as a
monotonic counter and why `FFFFFFFF` looked like a record trailer. Both readings happen to
work on `denmark-start` and on nothing else.

On a played-in save the seasons played DURING the career are appended into **recycled slots**
elsewhere in the slab and the chain jumps to them. So the `+1` sequence breaks *inside* a
record, and every rule built on "sequence break = new record" over-split. That is the entire
established-save bug.

**Record starts = rows with in-degree 0** — rows nothing points at. Exact, no heuristics.

### 2. THE SLAB IS FIXED-SIZE — 265,423 rows in EVERY frem save
World creation to 2023, unchanged; only the byte offset drifts. `u32 @ (start - 12)` is that
row count. The v1 locator was landing on a **false header**: a mid-table row whose `+4` field
happened to read as a plausible row count, giving a truncated 143,337-row window starting at
40,925,450 when the real table starts at **40,331,690**.

v2 locator signal: `next == k+1` for a supermajority of sampled rows (c0 is not read from row
0 — row 0 is often a recycled row), plus every non-FF pointer must be `< V`. **One surviving
candidate on all 10 frem saves**, and on each one the pointer graph audits clean:
`max in-degree == 1` and `#(in-degree-0 rows) == #(FFFFFFFF rows)` — a perfect forest.

| save | start | untouched rows | records |
|---|---|---|---|
| denmark-start | 39,561,805 | 80.9% | 50,776 |
| denmark-end-22 | 42,453,234 | 79.2% | 35,344 |
| denamrk-23-end | 43,389,246 | 71.9% | 26,428 |
| denmark-24-start | 40,331,690 | 67.2% | 34,565 |

### 3. THE READING RULE — the club column leads the stats by one row
Walking a chain gives rows `[h, r1, r2, …]`. For each row `k` after the head:
**season + stats come from row `k-1`; club + fee come from row `k`.** The head therefore
contributes no season, only the **youth/origin club**.

This one rule covers both the contiguous and the appended parts of a chain — an earlier
framing ("stats are staggered by one, but only in the appended region") was a mis-reading of
the same fact and is superseded.

Two independent confirmations, both exact:

**a) Every career TOTAL matches.** The in-game screen shows a TOTAL line; all five agree to the
appearance, and they only agree under this rule (reading stats off the same row double-counts
the debut row and overshoots):

| player | in-game TOTAL Pld/Gls/Ast | parsed |
|---|---|---|
| Dirksen | 198 / 10 / 0 | 198 / 10 / 0 |
| Andersson | 286 / 16 / 2 | 286 / 16 / 2 |
| Thrane | 195 / 26 / 4 | 195 / 26 / 4 |
| Fugl | 46 / 8 / 12 | 46 / 8 / 12 |
| Erenbjerg | 82 / 19 / 3 | 82 / 19 / 3 |

**b) The individual stat lines land on unique rows.** Searching all 265,423 rows for each
player's real in-game numbers puts them at exactly `chain row - 1`, every time; four of these
signatures are globally unique in the slab:

| player | season | in-game | chain row | stats found at |
|---|---|---|---|---|
| Fugl | 2021/22 | 29/5/9 @7.12 | 62,466 | **62,465** (1 match file-wide) |
| Fugl | 2022/23 | 17/3/3 @7.35 | 6,397 | **6,396** |
| Andersson | 2021/22 | 25/2/2 @6.87 | 12,125 | **12,124** (unique) |
| Andersson | 2022/23 | 15/3/0 @6.85 | 2,589 | **2,588** (unique) |
| Erenbjerg | 2022/23 | 17/3/3 @6.87 | 19,646 | **19,645** (unique) |
| Dirksen | 2021/22 | 3 @5.66 | 10,541 | **10,540** |

**It fixes transfer years, not just stats.** Reading the club off the same row put Dirksen at
Frem from 2018/19; the club column is what shows he actually signed for **2017/18** — which is
what the user read off the screenshot originally. A same-row reading also mislabels Thrane's
2020/21 (Nykøbing instead of Frem). Both are correct under this rule.

**The debut row falls out for free.** The last row of the contiguous run is a debut/summary row
(0 apps, `+8` = the debut season, usually the season the player turned 15/16). Under this rule
it is consumed as a *club* row and never emitted as a phantom season — which is precisely why
the totals come out exact.

### 4. LINKING IS SOLVED — `u32 @ P-38` in the ATTRIBUTE record
The history table has no player id (that part of the morning's finding stands). The pointer
runs the other way: the attribute record holds `[SID u32 @ P-42][history chain head u32 @
P-38]`. **25,627/25,627 in-range values are valid chain heads, all distinct.** Full write-up
in `docs/IDS.md` § PLAYER → CAREER HISTORY. The sid-ordering / banded-DP approach is obsolete.

### 5. SEASON BASE IS 1971 — settled by three independent anchors
`end_year = 1971 + code`. Erenbjerg's loans (Thisted **21/22** = code 51, Frem **22/23** =
code 52) pin it, and Dirksen's 2018/19 32ap-1gl / 2019/20 16ap-1gl / 2020/21 1ap and
Andersson's 22 / 19 / 16ap-1gl reproduce exactly. Codes stop at 52 in a 2023-07-01 save, as
they must. **The earlier "off by one, base is 1970" scare came from the user transcribing
Dirksen's screenshot a year early — the screenshot itself agrees with 1971.**

### 6. ROW LAYOUT (final)
```
+0  u16  club tid (0xffff = none)
+2  u16  fee: ffff stay / fffe LOAN / fffd ? / 0 free / else £000s
+4  u32  NEXT ROW POINTER (0-based) or FFFFFFFF = end of chain
+8  u8   season code, end_year = 1971 + code
+9  u8   apps          |
+10 u8   goals -- CONCEDED for goalkeepers (a 29-app "48 goals" row is a keeper)
+11 u8   assists       | -- these four are at row k-1 in the appended region
+14 u16  average rating x100 (in-career rows only; 0 for pre-career rows)
```
The last row of the contiguous run is a **debut/summary row**: 0 apps, `+8` = debut season
(Dirksen 38, Andersson 40, Fugl 47), often the season the player turned 15/16.

### 7. FEE CODES, AND ONE COSMETIC GAP
`+2` on a club row is the fee for the move INTO that club: `ffff` = no fee recorded,
`fffe` = loan, `fffd` and `0` = free, else £000s. Display note: the game shows `ffff` as blank
when the club is unchanged but as **"Bos"** on a row where the player moved — one stored
value, two labels. `fffd` renders as "Free" (Thrane's 2021/22 Næstved move).

Remaining cosmetic gap: **blank youth seasons can be one row short.** The game renders a row
for the debut season itself; we start at the first stored row. Fugl shows three blank Næstved
seasons in game (2018/19–2020/21) and two from the table. Apps are 0 there, so totals and every
played season are unaffected.

**FIXED, and it was not a history bug: club naming.** Erenbjerg's club rendered as the award
"Player of the Month", and Thrane's 2021/22 club looked *missing*. Both were
`reference._valid_name` requiring >= 2 alphabetic characters — which rejects the short name
"B.93", so the whole real club record was discarded and only an unrelated award record sharing
the tid survived. Short names are abbreviations and are allowed one letter (`min_alpha=1` for
the short name only); long names keep the stricter guard. Exactly 5 of 4,836 clubs change, all
Danish/Faroese "B.xxxx" sides: 331 B1908, 332 B1909, 333 B1913, 334 B.93, 586 B68. Thrane's
2021/22 row was never missing — it is club 2604 = **B36**, which now names correctly and
matches his screenshot exactly. Note that a club can also have a *second* shape-matching record
(346 Frem has an award record "Team of the Week" at 13.77M); Frem resolves correctly only
because its real record comes first in the file, so first-match ordering is still a latent
hazard — `club_record()` has the discriminator (real clubs carry league + country).

### 8. REGRESSION ANCHORS (denmark-24-start.fms)
| player | tid | sid | chain head | check |
|---|---|---|---|---|
| Dirksen | 9328 | 5,779 | 66,162 | Holbæk ×8 → Frem 32/1, 16/1, 1; 21/22 = 3 @5.66; 22/23 blank |
| M. Andersson | 9400 | 5,833 | 66,926 | Frem every season; 21/22 = 25/2/2 @6.87; 22/23 = 15/3/0 @6.85 |
| M. Thrane | 9430 | 5,854 | 67,195 | Hellerup 10/11 4ap; 21/22 Næstved 14/3/1 @7.14; 22/23 Frem 29/5/3 @7.06 |
| Fugl | 10272 | 6,605 | 73,214 | Næstved ×3 blank; 21/22 Frem 29/5/9 @7.12; 22/23 17/3/3 @7.35 |
| Erenbjerg | 10224 | 6,561 | 73,022 | B.93; 21/22 Thisted LOAN 5 @6.60; 22/23 Frem LOAN 17/3/3 @6.87 |

Verify with `python3 scripts/history_v2.py <save> --player <tid>`; the CLI prints the TOTAL
line so it can be diffed straight against a screenshot. Note denmark-start now yields **21,428**
players (was 21,761 under the positional DP) — the drop is the old low-confidence tail, which
the docstring itself said not to trust. Every row we emit now comes from a stored pointer.

### 9. METHOD NOTES THAT PAID OFF
- **Dump every byte between two known anchors and read it.** The user's call. 765 rows of
  fully-decoded hex made the two interleaved counter series obvious in about a minute, after
  a session and a half of signature-hunting found nothing.
- **Search the whole slab for the ground-truth stat line, then look at where it landed
  relative to what you predicted.** The `-1` delta fell out instantly and unambiguously
  because several stat signatures are unique in 265k rows.
- **Read the screenshots directly** rather than working from a typed summary of them — the
  "base is 1970?" detour came entirely from one transcription slip.
- Club names from `staging.clubs` contain junk (tid 334 = B.93 renders as "Player of the
  Month"). Don't diagnose a parser bug from a club NAME; check the tid.

---

**ESTABLISHED-SAVE LOCATOR FAILS — DIAGNOSED, NOT FIXED (2026-08-17).** `player_history` parses only on
**full-DB saves** (denmark-start, demark-winter-transfer-22: ~19–21k rows, ~4,500 clubs); it returns **0
rows on every in-season/established save** (all four 2023 Frem snapshots; 103/104 on the two mid-2022
in-season saves, ~2,700 clubs). NOT a pipeline/config gap — `extract.py` runs history every time and
`load_duckdb` loads it; it's `history.find_table_start` raising, caught by the try/except at extract.py
~148 → silently 0. **Three compounding causes on established saves (verified vs
`~/Downloads/denmark-23-mid-start-of-winter.fms`):**
1. **Region drift** — the real table sits at **~44.59M** here (season_plausible 1.0, real club tids
   625/4874/2742/5771, ascending per-player seasons), not 39.56M.
2. **The `+4` counter no longer resets to 1** — it's cumulative, starting ~**131,957**. `find_table_start`
   gates on `mm.find(counter==1)` BEFORE the season-plausibility test, so it never even reaches a valid
   table. (Fresh saves reset to 1, which is why start/winter-transfer work.)
3. **The counter is also non-monotonic** (jumps 131,967→247,827 mid-table), so even after locating the
   region, `enumerate_records`' counter-based `end_gap=6` stops after 618 records. `end_gap=10**9` (rely
   on empty-run/zero-fill termination) → **20,356 records / 13,572 non-empty** over 44.59–46.51M ≈ right
   size.
**THE HARD WALL:** `align_anchored` needs the table's EXACT first row (records are sid-ordered from the
lowest-sid player). Season-plausibility ALONE cannot bound the table — the 20–55 season range hits ~14%
of random bytes, so ≥3 adjacent stride-16 look-alike tables merge under any gap-tolerant scan (a 32,970-row
"run" at 39.36M yields 17k aligned players but **0/8 correct origins**; feeding a hand-verified *mid-table*
offset also gives 0/8 because the whole sid↔record mapping shifts). Cracking established saves needs a NEW
structural anchor to replace the dead counter + a way to positively ID the true table among decoys —
**a dedicated deep-RE task, not a patch.** Per user (2026-08-17): treat as a **`map_regions`-style problem**
— there are multiple stride-16 season-plausible regions across the save; map them by filler/signature (see
[[savefile-boundary-map]]) to positively identify the history table rather than heuristic run-finding.
**PRACTICAL FIX (recommended, quick, not yet built):** origin club is career-CONSTANT → backfill
`origin_club_tid`/eligibility in the loader from the newest snapshot that DID parse (covers **90.8%** of
current players; the ~9% gap = regens/new arrivals). Ground-truth origins (from the 2022 full parse, for
regression): `{10526→337 Brøndby, 10404→2465 FCN, 10407→344 FCK, 26734→1125 (NOT capital), 9520→2398,
10225→356 Hillerød, 26726→5277, 9846→1164 Vejle}`. Also make the loader WARN on any 0-history snapshot so
it never passes silently. See [[denmark-region-drift]], [[phase-is-date]].

**ORIGIN-BUG FIXED (2026-08-11).** Symptom: on the winter (mid-season) save, origins were wrong for
~all players (`confidence` 'low' for 21,208/21,227) — Danish players showed Belgian/German origins.
**Root cause in `history.align_anchored`:** it set `ceiling = max(0, NR-NP)` and used it BOTH as the
`align()` DP `max_staff` cap AND as the anchor-validity filter (`0 <= i-j <= ceiling`). When the
high-sid tail is newgens with no record, **NR < NP so ceiling collapses to 0**, forcing the whole map
to offset 0 — but the real record↔player offset is the count of interleaved staff records (here
**~1744→2420**, drifting), which has nothing to do with NR-NP. So `align()` (capped at 200) could
never reach the true offset → 7 anchors → all 'low'. (Worked on denmark-START only because there
NR>NP gave ceiling 1513 > its smaller 634-769 offset.) **Fix:** replace `ceiling` with a data-driven
`band = min(NR, max(4000, (NR-NP)+500))` for the DP width, anchor filter, and offset cap. Result:
winter **5,762 high / 13,201 medium / 342 low** (was 7/12/21208); start improved to 8,709/13,044/8.
Frem squad ground-truth: ~20/23 now correct Danish origins (Aslani→Brøndby, Haarbo→FCK loan-parent,
Randolf→Nordsjælland). A few transfer-heavy cases still wrong (Sundstrup→Rubin Kazan). Dashboard also
**suppresses 'low'** origins (`db.eligibility_frame` NULLs them). The stayer-match rate is genuinely
lower on mid-season saves (trailer=last-completed-season club ≠ current after summer+Jan windows), so
medium (fitted-offset) carries most players there — trust high, treat medium as ~right, hide low.
See [[phase-is-date]], [[denmark-division-tiers]].

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

**ENUMERATION SOLVED (2026-08).** The table is ONE contiguous counter-run:
**start = offset 39,561,805 (where +4 counter resets to 1), end = 41,460,349; 118,659 rows,
11,238 records.** Walk 16-byte rows from the start; **a row is a record-END trailer iff `+4 ==
0xFFFFFFFF`** — the trailer consumes its own counter slot (counter stays perfectly sequential 1..118659,
breaks cleanly at the end). **ROOT-CAUSE BUG that broke every prior count:** the old delimiter filter
required `season(+8)==40`, but **the trailer's `+8` = the player's DEBUT season, NOT a constant** —
Højbjerg debuted s40 (hence 40), record-0's veteran debuted s22 (trailer +8=22). Dropping the season
constraint makes enumeration exact. **Trailer row = `[+0 current club][+2 ~0][+4 FFFFFFFF][+8 debut
season][+9,+10 ~0]`.** Record lengths: min 1, median 9, mean 10.6, max 39 rows. Just before the table
start (@~39.5617M) sits a small **increasing `[u16][u32]` array then a zero-gap** — a candidate
cluster/pointer index, unconfirmed. Big annotated start-dump: **~/Downloads/history_start_dump.txt**.

**FULL FEATURE BUILT on branch `player-history-parser` (4 commits, NOT merged to main, 2026-08):**
85cd5e1 parser (`fmparser/history.py` + extract.py→history.json), 6e2608f anchor-fit alignment +
confidence tiers, ee060f1 ETL (`staging.player_history` / `player_history_seasons` /
`eligible_origin_clubs`, seed `seeds/eligible_origin_clubs.csv` = Danish Capital Region), b38660f
dashboard (`db.eligibility_frame` + `dashboard/pages/9_Recruitment.py`). The Recruitment page is the
Athletic-Bilbao board: browse players whose ORIGIN club is on the eligible list, high/medium confidence
only, ranked by tactic-fit, immersion-safe (Fit %ile + Level %ile). VALIDATED via AppTest: 459 eligible,
top names are real Capital-origin Danes (Poulsen/Lyngby, Delaney & Højbjerg/FCK, Wass/Brøndby,
Damsgaard/Nordsjælland). **TO SEE IT LIVE:** the committed fm-frem.duckdb predates the parser — must
RE-IMPORT the frem save (extract→load_duckdb) to populate history. Branch not merged pending that +
final user sign-off. (Original 'do not ship until tail cracked' resolved: tail is honestly 'low',
excluded from the board; high+medium covers the Danish core.)

**WITHIN-RECORD FORMAT FULLY DECODED & SCREENSHOT-VALIDATED (2026-08, Højbjerg + Spinazzola +
Biraghi in-game History screens).** THE KEY: **the club column LEADS the stats by exactly one row.**
The apps/goals on byte-row k were PLAYED at the club on row k+1 (the last data row's stats → the
TRAILER's club). So a season = (season/apps/goals from row k) + (club from row k+1). Row 0's club =
the youth/ORIGIN club (never has stats of its own). Trailer (+4==FFFFFFFF) = current club + debut
season (+8). Other confirmed facts:
- **Fee (`+2`)**: `ff ff`=0xffff=stay, **`fe ff`=0xFFFE=LOAN** (earlier note said 0xfeff — WRONG,
  it's 0xfffe), `0`=free, else £000s (15000=£15M). The fee lives on the SELLING club's row; FMM
  DISPLAYS it on the BUYING club's arrival season (skipping loan seasons in between — e.g. Højbjerg's
  £12.26M sits on the Bayern row but shows on Southampton's arrival). So byte-fee-row ≠ in-game
  display row for loan-then-sale cases.
- **Assists / yellows / reds / avg-rating are NOT stored** — `+11..15` are ~zero; the in-game History
  screen shows Ast/Yel/Red/AvR as "-" for historical seasons (TOTAL row = 0/0/0). Only club/season/
  apps/goals/fee exist. (Do NOT try to decode assists from +11..15 — they're genuinely absent.)
- **club tid 65535 = "unknown" club** (in-game shows "unknown", often an unknown loan). Don't render
  it as "free".
Origin (row-0 club) and current (trailer club) were always correct; the fix was the middle seasons'
club↔stat offset + the loan sentinel. `history.py` now applies the +1 club shift and 0xfffe loan
decode. Remaining format polish (optional): move the fee to the in-game arrival season; relabel 65535. `find_table_start` (counter resets to
1, season-plausibility validated so it rejects the season-0 look-alike counter table at ~40.06M in
Buca), `enumerate_records` (records split on **FFFFFFFF trailer OR season-drop** — the +4 counter is
a row-index used only to BOUND the table with resync tolerance + a zero-region safety break, NOT to
split, because established saves like Buca have isolated +4 holes ~271k where players were added
mid-career), `align` (the banded staff-interleave DP), `build(mm, info)` -> {tid: {origin_club_tid,
last_season_club_tid, confidence, seasons:[{season,end_year,club_tid,fee,apps,goals}]}}. Wired into
`extract.py build_database` (attaches origin_club_tid/origin_club/history_confidence to each player
row + emits `history.json`; history clubs folded into club-name resolution). Never fatal (try/except
-> skip). **The 209194-at-41.46M "table end" from the earlier single-segment analysis was a SINGLE
+4 anomaly, not the end** — the real denmark table runs 39.56M→~43.8M and covers ALL players (the
"newgens" like Rwango/Basarte are real players w/ real foreign careers, not empty). Validated: full
Frem squad + 4/4 in-game (Bramsborg/Herslov/Grønne/Aslani all confirmed vs the game's History screen).
Buca self-locates at 42.53M. **HONEST CAVEAT — the high-sid TAIL is less reliable:** enumerate yields
more records (~50.8k denmark) than known entities (~30k info+staff), so the DP over-gaps in the tail
and some **"medium"**-confidence mappings are visibly wrong (a Danish youth -> Chelsea). The
**"high" confidence** rows (stayer: trailer club == player's current club — ~5.3k denmark) are the
trustworthy subset and cover the Danish senior core (the eligibility-relevant population). Frontend
should prefer high-confidence (or Danish-league) origins. Remaining polish: understand the
records>entities gap (foreign players absent from info scrape? duplicate copies past 43.8M?) to tidy
the tail; the origin-strategy core is done.

**RECORDS-VS-ENTITIES GAP SOLVED = PADDING + STAFF (2026-08).** Raw enumeration gave ~50.8k records
vs ~30k entities. Cause: (1) a **contiguous PADDING TAIL of ~25,002 EMPTY records** (data-less FF
trailers, club 65535) starting ~43.4M — reserved slots for future newgens (user predicted this).
`enumerate_records` now stops after `empty_run_limit` (64) consecutive empty records and drops the
run → table ends ~43.4M, **25,828 records**. (2) After padding removed: **23,509 real records ≈ 24,315
sid-players** (≈1 record-slot per player, empty if no career yet) **+ a ~1,500 surplus = staff/
ex-players with careers interleaved by SID** (staff sid==ffffffff, not in the player list → they are
the alignment "gaps"). Short empty runs (≤~30) are KEPT — genuine no-history players interleaved by
sid.

**ANCHOR-FIT ALIGNMENT SHIPPED (branch `player-history-parser`, commits 85cd5e1 + 6e2608f — NOT on
main / NOT merged).** `align_anchored()` replaces trusting the raw DP everywhere: take only
ceiling-valid stayer anchors (offset i−j ≤ len(recs)−len(players) ≈ 1513), isotonic-regress (PAVA,
`_pava`) the monotonic offset curve, assign every player from the fit. Anchors are DENSE for sid-rank
< ~13,000 (offset a smooth 513→809) and COLLAPSE after (high-sid tail is transfer/youth-heavy so
trailer==current-club almost never holds; its "anchors" are coincidences that blow past the ceiling).
Confidence tiers: **high** (5,570, stayer-validated, solid) / **medium** (7,563, anchor-supported sid
range, mapped by the fitted offset) / **low** (9,345, beyond the last reliable anchor — DO NOT trust;
Sindahl etc. now honestly 'low' not fake-confident Chelsea). Validated: Frem core + Højbjerg/
Spinazzola/Biraghi all high & correct. **high+medium (~13.1k) covers the whole Danish core = the
eligibility-relevant population.** Frontend eligibility should filter to high (or high+medium). Still
NOT merged pending user sign-off.

**FIRST DIVERGENCE = HARD BREAK at sid-rank ~13,496 (2026-08).** Not drift, not padding: the
SID-ORDERING simply STOPS there. Up to ~13,496 records are sid-ordered and align (offset smoothly
513→809→…→1513=ceiling). At the break the offset hits the ceiling; beyond it the tail records STILL
EXIST as real careers but belong to OTHER players — constant-offset stayer-match in the tail is ~0% at
EVERY offset tried (1400–1600), i.e. a PERMUTATION not a shift. The boundary block is Spanish B-team/
lower-league players (Villarreal B, Coruña B, Bilbao B) → the tail is likely ordered by a DIFFERENT key
(nation/division-grouped?), a separate un-cracked ordering. So high+medium (~13.1k, rank<13496) = the
reliable sid-ordered region (incl. the whole Danish senior core); the ~10.8k tail is correctly 'low'.
Cracking the tail's ordering key = a distinct future task, NOT eligibility-critical. NOTE some Frem
YOUTH (Sindahl etc.) have high sids and land in the low tail — youth with little history anyway.

**LINK ESSENTIALLY SOLVED — records are SID-ORDERED with a smoothly-drifting offset (2026-08).**
The record↔player map is `record_index = f(sid_rank)` where `f` is **monotonic, drifting +710
smoothly** across the range (windowed best-offset: rank 0→28, 1k→594, 4k→592, 6k(Frem)→730,
8k→734, 10k→738), then **records RUN OUT** — sid-rank ≳10,500 has NO record (offset collapses to 0
matches). Meaning: **records exist only for the ~10,500 LOWEST-sid players = the ones that existed at
world-creation (real careers); everything above is newgen/youth-intake with no senior history** (so
11,238 records ≠ 24,315 sid-players — the rest are kids). The smooth drift = the **5,827 sid-less
seed/legend/STAFF entities (sid==0xFFFFFFFF, tids 101+) interleaved by sid**, each nudging the offset
+1. VALIDATION (decisive): mapping our whole squad via the LOCAL offset **+721** (Danish senior block,
constant across sid 5308–6820) gives **coherent real careers for all 18 senior + 5 reserve Frem
players** (Andersson = Frem lifer 10/11→20/21; Youssef = FC Nordsjælland academy; Grønne = AB→Nykøbing;
etc.). The only "misses" are (a) **summer-2021 transfers** — trailer `+0` = last-COMPLETED-season club
(2020/21), which correctly differs from info `club_tid` (current, post-window), so a current-club
equality test is FLOORED and UNDERSTATES accuracy badly; (b) newgens mapping past the record end.
**So current-club match ≈13% is a measurement artifact, NOT the real accuracy** (the order is ~perfect
locally). NOT nation-grouped (0.5%), NOT uid/tid/file-order (all desync at record 4). Origin club =
first data row = READABLE now for our squad + the Danish block (Grønne origin Ballerup-Skovlunde, etc.)
— the Bilbao/eligibility signal is in hand. **REMAINING = one clean build:** a global **monotonic
sequence-alignment** (Needleman–Wunsch/anchored) of sid-sorted players → records, using trailer-club
as the match signal but ALLOWING transfer-mismatches (don't reset on a miss — that's why naive greedy
desynced), skipping the interleaved staff records. Anchor on "stayers" (unique trailer-club==current)
and interpolate offset between anchors (offset is piecewise-constant, +1 per staff record between
anchors) for EXACT per-player assignment. Then origin club + full history per player is done. Dumps:
~/Downloads/history_start_dump.txt (table start, record 0), ~/Downloads/frem_careers.txt (squad).

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
