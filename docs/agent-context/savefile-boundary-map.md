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

**Status:** not started; parked for a dedicated session. Deliverable: a `scripts/map_regions.py`
(or `fmparser/regions.discover()`) that prints/labels the segment map for any save.
