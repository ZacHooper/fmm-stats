---
name: seyhun-attr-investigation
description: FIXED (Option 1) — attr_record now returns freshest snapshot copy + extracts player value; re-imported. Option 3 (map C1-list) in docs/ATTRIBUTE_DECODING.md §7.
metadata: 
  node_type: memory
  type: project
  originSessionId: 681be847-7279-4c83-87e8-ccd414e19fd8
---

**STATUS 2026-07-27: Option 1 SHIPPED + re-imported.** `attr_record()` now returns the
LAST (freshest) match within `snapshot_bounds` (was: first = stale block A), and extracts
the **player transfer value** from `M+4` (u32; Sertgöz £2K, Seyhun £98K — confirmed). Wired
value through extract.py → players.json → `staging.players.player_value` (BIGINT, added via
`ALTER TABLE ADD COLUMN IF NOT EXISTS`, NOT --reset — that would wipe custom tactics
buca_433/personal + app_config). Re-extracted + re-loaded all 6 saves into fm.duckdb.
Verified: Seyhun 2023-mid/end + 2024-start now Shooting 16/Tackling 4/Decisions 6/Movement 7
(older reserves-era saves correctly show younger 12), 38/38 squad have values, custom
tactics/config preserved, all 3 dashboard pages render clean. Full byte-layout of the
snapshot region is now in **docs/ATTRIBUTE_DECODING.md §7** (Option 3 foundation).
PARKED 2026-07-27: hunted for personality/social-group/club-hierarchy/training bytes in
the snapshot record — NOT there (squad_status, known for all 39, isn't a clean function of
any byte in the window; personality lives in the global 5MB record §1; social/training are
separate structures). Confidently-known record fields: 23 attrs, 15 positions, TID,
transfer_value, feet, form/rating float, idx24≈condition(unconfirmed). Leftover post_+25..
bytes look like form/match counters. Would need bulk ground truth (~12-15 players' social
group + hierarchy) to pursue further.
KNOWN LIMITATION: ~3 players (Erdem/Duruk/Köseoğlu) whose live copy is in the C1 cluster
(~600 KB later, outside snapshot_bounds) still resolve to their in-bounds copy — needs a
per-record freshness signal / squad-list mapping (Option 3, §7.2). Trail below.


Updated 2026-07-27. **This is a real parser bug, not a stale-save problem.** (My first
pass wrongly concluded "Shooting is flat at 14, just need a newer save" — that was based
on only re-parsing the two post-jump Downloads files. Corrected below.)

**Symptom:** Dashboard shows Selahattin Seyhun (tid 22908, Bucaspor 6567, `loaned_out=True`
in every label) Shooting=14; the live in-game screen (20 Jun 2023) shows Shooting=16
(also Tackling 3→4, Decisions 5→6, Movement 6→7; all other attrs identical).

**Root cause (confirmed on two save files):** The squad-snapshot region contains **TWO
attribute records** for Seyhun. `fmparser/attributes.py::attr_record()` does
`mm.find(le, pos)` in a loop and returns the **first** match — which is a **stale copy**.
The **second** (higher-offset) record is the **live** set and matches the UI on *every*
attribute.

Evidence — `attr_record`-style scan within `snapshot_bounds`:
- `fm_save1-23-mid.fms`: rec1 @63555806 Shooting=14 (4 mismatches vs UI); rec2 @63575662
  Shooting=16 → **full match, 0 mismatches** vs the 20-Jun UI.
- `fm_save4-23-end.fms`: rec1 @64217169 Shooting=14 (same 4 mismatches); rec2 @64237015
  Shooting=16 → **full match**.
Reproduce: loop `mm.find(struct.pack('<I',22908))`, keep hits where
`mm[i+8:i+12]==CLUB_MARKER`, decode `mm[i+8-59 : i+8-23]` with `A.decode`.

**Actual attribute history (per DuckDB `v_player_attributes`, tid 22908):** NOT flat.
Shooting = 12 (2022 mid/end, 2023-start; club_tid 11320 Reserves) → 14 (2023 mid/end,
2024-start; club_tid 6567). So the 12→14 jump the user remembers IS captured; the
remaining gap is 14 (our stale pick) vs 16 (live). The "off by 2" is NOT a uniform
offset — it's reading a stale copy in which a handful of attrs differ.

**Squad-wide scan (fm_save1-24-start.fms, 2026-07-27):** NOT loan-specific — **33 of 39**
managed-squad players have ≥2 distinct snapshot records. Records fall in offset "blocks":
A (~61.11–61.13M), B (~61.137–61.148M), C (~61.76–61.82M). Combos: A-only 6, A+B 23,
A+C 6, A+B+C 3, B+C 1. For Seyhun the **later** block (B) is the UI-correct one; block A is
stale. Direction of the A→later diff VARIES (most players later-block is higher, e.g. many
+1 on Leadership/Stamina; but some — Murat Behram, Metin Yüksel — are lower), so the fix
can't be "take the max" — hypothesis is "**take the latest-offset record**" (Seyhun confirms;
needs user to verify a few more in-game). Full diff CSV was written to the session scratchpad
`dup_records_24start.csv` (player, tid, stat, A/B/C values). Verification worksheet handed to
the user: Berke Bıyık Leadership A7/B8, Murat Demir Stamina A7/B8, Yusuf Yıldırım Stamina
A11/B12, Ahmet Sun Leadership A9/B10, Turan Demirci Dribbling A10/C11 — question: does the
in-game value equal the LATER record in each case?

Repro for the scan: iterate every `CLUB_MARKER`, `tid=u32 at marker-8`, decode
`mm[marker-59:marker-23]`, keep tids in the managed squad with all confirmed attrs 1..20,
group by tid, diff distinct decodes.

**Mechanism (confirmed by age analysis 2026-07-27):** Block A is an EARLIER-in-time
snapshot; block B is CURRENT. Net change (B−A) tracks development: young players up
(19yo: +15/+16/+17), veterans down (Behram 34: −16, Yüksel 34: −14, Gölbaşı 33: −2).
Avg age developing 24.8 vs declining 28.6. So reading block A = showing stale/pre-
development attributes. **Block C (~61.77–61.82M) is UNRELIABLE** — for some players it's
normal (Turan Demirci C=A+1) but for others it's a placeholder full of 1s (Efe Doğan block-C:
Stamina 1, Strength 3, Passing/Tackling/Crossing 1 → false −38 net). So the fix is NOT
"take the last offset" (that would pick C's junk for Efe Doğan/Berkay Ertürk); it's
"**prefer the block-B current record; never let a block-C record win**". Still worth a
quick in-game spot-check that B (not A) is what the UI shows for a couple of the easy cases.

**User in-game ground truth (2026-07-27) + full mechanism:** The snapshot region holds
several HISTORICAL copies of each player; the record blocks are time-points, oldest→newest
roughly: A (~61.11–61.13M, oldest — what we wrongly read) → B (~61.137–61.148M) → C1
(~61.766–61.772M, often freshest) → C2 (~61.819–61.822M, junk/duplicate, e.g. Efe Doğan's
all-1s). Confirmed correct picks: Özcan Sertgöz=B, Yusuf Can Abay=B, Berke Bıyık=B, Ege
Okka=B, Efe Doğan=B (his only other copy C2 is junk), Emre Erdem=C1, Alper Duruk=C1, Gökhan
Köseoğlu=C1. So the correct value = **the freshest NON-junk copy = latest offset excluding
the trailing C2 cluster**. "Definitely not A."

**Limitation for mid-change players:** Ercan Şirin & Berkay Ertürk matched NO stored copy
exactly. Their in-game screens show ↑ arrows (Berkay Stamina→9 but every record has 8; Ercan
Passing/Decisions/Movement just ticked up) — the live value out-ran the newest snapshot, so
no full record equals the UI (off by ~1 on the just-changed attrs). This is inherent to
snapshot parsing, not fixable by a better record-pick. User's heuristic matches exactly:
"2 records → the later is current; 3+ → can be all over the shop" (the 3+/messy ones are the
actively-developing players whose live value outran the snapshots).

**FIX (agreed direction):** change `attr_record()` to return the freshest valid copy — latest
file offset, skipping junk/placeholder records (many 1s / implausibly low) and the trailing
duplicate cluster — instead of the first. Needs a structural (not hardcoded-offset) way to
identify "freshest" and "junk" since offsets drift across saves. Exact for the majority,
±1 on just-changed attrs for the rare mid-development case. Then re-import.

**Byte-level flag hunt (2026-07-27) — DEAD ENDS, don't re-run:** No per-record "use-me"
flag found. `CLUB_MARKER = <6567 LE> ffff` (`a7 19 ff ff`) — all copies are managed-club-
anchored (multiple internal lists, not per-club markers). Bytes `M-4..M-1` constant
(`ad 00 e4 00`). `M+4` is a varying u16 (value/rating-like; Okka & Berkay = 500 = their
£500 in-game value) but does NOT track stale-vs-correct (Sertgöz stale & correct both 2000).
Attr-array indices 26–34 (`FF FF FF FF FF 00…` in Seyhun's stale copy) are NOT a clean flag —
several correct records (Sertgöz, Erdem, Okka) also show `FF…/0` there. Float at attr idx
31–34 (~6–8, e.g. 0x40fc7ae1≈7.89) is not a freshness/timestamp (doesn't order copies).
Neither "latest offset" (fails Bıyık/Okka — later copies stale; Doğan — later is junk) nor
"fixed region B" (fails Erdem/Duruk/Köseoğlu — correct is the ~61.77M region) nor squad-list
membership (Duruk & Köseoğlu are first-team 6567 yet correct∈~61.77M like reserve Erdem)
universally picks the live copy. **Freshness is per-record, scattered across ≥2 internal
squad lists.** Only rock-solid rule: block A (earliest ~61.11–61.13M) is ALWAYS stale — and
that's exactly what `attr_record()` returns today (first match).

**Open questions for the fix:**
1. How to robustly choose the live record? In both samples the **later/second** offset is
   live, but "take the last" needs validating so it doesn't break single-record
   (non-loaned) players (there it's the only record → no change) and isn't just an artifact.
   The two records are ~20k bytes apart; no club id (6567/11320) sits within ±400 bytes of
   either, so proximity-to-club won't distinguish them — need another discriminator
   (maybe one record lives in the parent-club sub-cluster, the other in the loan/reserve
   sub-cluster of the snapshot). Likely correlates with the club_tid flip 11320↔6567.
2. Is the second copy always present, or only for loaned/dual-registered players? Scan the
   whole managed squad for tids with >1 CLUB_MARKER-anchored snapshot record.
3. Separate anomaly: `fm_save3-23-start.fms` returns **0** records inside
   `snapshot_bounds` (bounds detection landed wrong for that file), yet the DB has 2023-start
   values (Shooting 12) — so extract found them via a different path. `snapshot_bounds`
   robustness per-save is worth a look (see [[fm-parser-project]]).

**Fix + re-load:** change `attr_record` to select the live record, validate across the
whole squad against any UI screenshots, then re-run the import ([[etl-duckdb-dashboard]]
import-fm-saves) so the dashboard reflects corrected values.

Related: [[fm-parser-project]] [[etl-duckdb-dashboard]]
