---
name: savefile-boundary-map
description: "TODO — map the whole .fms into labelled regions with real reference points, so region bounds are never guessed wrong"
metadata: 
  node_type: memory
  type: project
  originSessionId: e454ef70-998b-4f22-a5f3-5cc24a02618f
---

**Idea (user, 2026-08).** Scan the ENTIRE save file and identify the clear boundaries between
structures — usually marked by long runs of `00` bytes or filler — then label each region and, where
possible, anchor it to a real reference point (a marker/signature at the start/end) rather than a
hard-coded offset. Goal: make "wrong region bounds" bugs go away, because bounds are derived, not
guessed.

**Why this matters (concrete pain).** Every hard-coded window in `fmparser/regions.py`
(SNAPSHOT_LO/HI, ATTR_LO/HI, MATCH_LO, LIGHT_LO/HI, CONTRACT_LO/HI, TAGGED_LO/HI) is tuned to the
Bucaspor saves and "drifts as the save grows". Concrete failure: the day-1 league-membership work
([[day1-league-membership]]) missed 3 of 12 clubs because the **club-record DB is split across
several segments (~6M/7M/9M/13M)** and I scanned only one window. A derived boundary map would have
caught all segments automatically.

**Approach sketch.** Walk the file, detect segment boundaries via long zero/filler runs and known
record signatures (e.g. `ff ff ff 00 00 00` registry records, club-record `[TID][UID][len][name]`
shape, tagged-region 4-char reversed tags, the `e4 07/e5 07` year markers). Emit a region table
{start, end, kind, anchor-signature}. Cross-check against the existing `regions.py` windows.
Ideally replace the static constants with a per-save discovered map (like `attributes.snapshot_bounds`
already does adaptively for the snapshot). This also complements the career-discovery work
(`scripts/discover_career.py`) — a fully self-locating parser.

**Status:** STARTED 2026-08 (denmark-start.fms, 59MB). The file IS cleanly delimited by **zero-runs**:
sections are separated by long `00` gaps (major ones 15KB–758KB; the 758KB gap before ~50M is the
biggest). Derived MAJOR-section skeleton (split on zero-gaps ≥8KB):

| span | size | content |
|---|---|---|
| 0.000–0.516M | 0.5M | **NAME TABLE** — 45,942 `[len u32][utf-8]` entries, flat (no internal breaks), nation-grouped browse order. Preceded by save-title header @0 + 49-byte header @250; followed by a 56KB zero gap. |
| 0.572–16.620M | 16M | FF-heavy **record section** (players/clubs/attributes; records delimited/padded by `ff ff ff ff` runs). Bucaspor "ATTR 3.8-6.6M" + "tagged 13-20M" are sub-regions of this. |
| 16.636–38.092M | 21M | biggest binary section (matches + more) |
| 38.1–39.27M | ~1M | heavily **fragmented** zone — many small sparse records with 8KB–115KB gaps between (entities/relationships?) |
| 39.274–49.458M | 10M | binary; contains the **player-history table @40.6M** ([[player-history-table]]). Then the **758KB** gap. |
| 50.216–59.176M | 9M | final section; **inline full names @57.99M & 58.64M** (snapshot copies), squad/snapshot data |

**Key structural facts:** (1) **zero-runs = section delimiters** (big) ; (2) within record sections,
**`ff ff ff ff` runs delimit/pad records** ("pages") — and deeper regions have fixed-stride records
(e.g. ~600-byte FF-heavy records around 39.5M); (3) the NAME section is unusual — pure flat text, no
FF/zero pages inside. **Offsets are per-save** (this 59MB Denmark save ≠ Bucaspor's regions.py
constants) — which is the whole point: derive bounds from the zero-gap skeleton, don't hardcode.

**TOOL SHIPPED (v1, 2026-08):** `fmparser/mapregions.py` (+ CLI `python3 scripts/map_regions.py
<save.fms>`) derives this map from any save — pure-stdlib. `sections(mm, min_gap)` splits on
zero-gaps; pluggable **detectors** label each section (add more as regions get decoded), else a
generic `characterize()` (text / ff-records / `pages~NB` fixed-stride / binary). Working detectors:
`name_table` (flat [len][utf8], ≥1000 names), `history_table` (16-byte rows, +4 counter increments,
+12==0), `inline_names` (`First Last` + `[len]First[len]Last` echo). Verified save-agnostic on
denmark-start.fms (Frem, 59MB) AND fm_save1.fms (Bucaspor, 64MB): both → name_table@0.0-0.5M
(45.9k / 45.8k names), ff-records@~0.57M, `pages~49B` mid-section, history_table (~42.5M Frem),
inline_names (Frem@57.99M 'Matthias Andersen', Buca@61.78M 'Jonny Evans'). Next iterations: locate
sub-regions inside the big sections (attr grid, club DB, match region, comp/tagged) as their
signatures get pinned; then have regions.py DERIVE its windows from discover() instead of hardcoding.

**Names blocker tie-in:** the name-id→string index is NOT adjacent to the name table (56KB zero gap,
then a record section). So name resolution likely uses a pointer inside the record section / name-table
header (@250 has candidate count fields like `60ea0000`=59968), not a standalone index array — a
hypothesis to test when [[task resumes]]. Deliverable still TODO: `scripts/map_regions.py` /
`regions.discover()` that emits this table for any save + labels each section by probing content.
