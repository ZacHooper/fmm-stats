---
name: squad-comparison-bridge
description: How the fm-parser save extract feeds the fm-data-entry weighted player comparison
metadata: 
  node_type: memory
  type: project
  originSessionId: 88430ef4-cdf6-43ef-a7ad-c15a62632d3c
---

The sibling repo `fm-data-entry` (a marimo dashboard, not "fm-data-parser") holds the
player-comparison + weighted-scoring logic; `fm-parser` auto-extracts the attributes.
The two attribute schemas match exactly (23 stats — fm-parser capitalises them,
fm-data-entry uses lowercase `stat_names`).

Bridge built in fm-data-entry:
- `utils/save_import.py` — reads `../fm-parser/output/<label>/players.csv`, filters to our
  club, maps raw FM position codes → the app's coarse `positions`, returns app schema.
- `squad_comparison.py` — new marimo dashboard ranking the squad by the `black_hawk`
  weighting (reuses `utils/ratings.py`). Run: `uv run marimo run squad_comparison.py`.

Managed club = **Bucaspor 1928**, fm-parser `club_tid` 6567 (25 players); reserves =
**Bucaspor 1928 Reserves**, `club_tid` 11320 (11 players). Reserve player NAMES aren't
decoded in the extract (blank) — loader falls back to `#<tid>`. Related: [[fm-parser-project]].
