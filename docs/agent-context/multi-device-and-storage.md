---
name: multi-device-and-storage
description: "Three storage tiers: git (code+seeds+manifest), R2 (saves+live state), local (derived store). The store is DISPOSABLE — rebuild, never sync or commit."
metadata:
  node_type: memory
  type: project
---

**Set up 2026-08-20** so the project can be worked from two laptops (work + personal) and read on
a phone. The organising idea: **the DuckDB store is a build output, not an artefact.** Saves +
code + seeds reproduce it exactly, so it is never committed, never synced, and never backed up.

## The three tiers

| Tier | Holds | Where |
|---|---|---|
| Code + build inputs | source, `seeds/` (role_weights, eligible_origin_clubs, config_bundle, **manifest**) | git (private GitHub) |
| Archive + live state | `.fms.gz` saves, shortlist, saved scouts | Cloudflare R2 (`r2:fmm-stats`) |
| Derived | `fm-*.duckdb`, `output/`, `site/` | local only |

Because each machine builds its own store, **there is no multi-writer problem** — which is the
real reason this shape was chosen, not just the file size.

## Why the store had to stop being committed

- It had grown to **96 MiB** (`fm-frem.duckdb`, 100,413,440 B) against GitHub's **100 MiB hard
  per-file limit** — about 4 MiB of headroom left. The docs still claimed ~26 MB.
- It rewrites **wholesale** on every import and gzips only to 44 MB, so each load added ~96 MB to
  history permanently. 19 committed copies had already taken `.git` to **257 MB**.
- History was stripped with `git filter-repo --path-glob '*.duckdb' --invert-paths` before the
  first push, while no remote existed and rewriting SHAs was still free.

## Rebuilding

```bash
uv run python scripts/rebuild.py --career frem        # ~12 min for 12 snapshots
```

Reads `seeds/manifest.csv` (`career,save_file,label,season,phase,active`), fetches each
`<save>.fms.gz` from R2, gunzips into `$FM_SAVES_DIR/<career>/`, then extracts and loads.

Two things that are easy to get wrong:
- **`staging.extracts.save_path` stores a BASENAME.** It used to store an absolute
  `/Users/<you>/Downloads/...` path, which silently made the rebuild recipe machine-specific — the
  manifest could not have rebuilt anything anywhere else. Fixed in `load_duckdb.py`.
- **Season and phase are passed explicitly** from the manifest, never re-derived. A save whose
  in-game date differs from its last match date otherwise lands on a *different* phase and adds a
  duplicate slice instead of replacing the intended one.

Regenerate the manifest after any import: `uv run python scripts/export_manifest.py`.

## Saves: compressed, and why that's safe

`scripts/archive_save.py` moves a save to `$FM_SAVES_DIR` (default `~/fm-saves/<career>/`), gzips
it, and **verifies the round-trip by hash**, refusing to keep a `.gz` that doesn't reproduce the
original. 23 saves: 1.2 GB → **271 MB** (5.1–6.5x, thanks to the `00`/`ff` filler).

Compression **cannot** move a byte offset: gzip is byte-exact, so `regions.py` windows, tid/uid
signature scans and the history slab's pointer chains all behave identically. That guarantee holds
**only because we decompress first** — mmap a `.gz` and every offset is garbage. Invariant:
`extract.py` never sees anything but raw bytes.

Verified independently with `cmp` against an untouched original, not just the script's own hash.

## Live state: one object per entry

`dashboard/state.py` mirrors `state/<kind>/<id>.json` to `r2:fmm-stats/state/<kind>/`. Kinds:
`shortlist`, `scouts`.

**One object per entry is load-bearing, not tidiness.** R2 has no append, so a shared JSONL means
read-modify-write, and two devices adding a player at the same moment silently lose one. Per-entry
objects make adds collision-free, a delete an object delete, and sync a plain union (`rclone copy`
both directions — never `sync`, which would delete). Only deletes need to be explicit remotely, or
the next pull resurrects them. It's also what lets a Cloudflare Pages Function accept a shortlist
add from the phone: it PUTs one object and is done.

- Shortlist ids are **microsecond timestamps**, not UUIDs, because `2_Squad_Tool.py` does
  `int(sl["id"])`.
- Scout keys are `<opponent_tid>-<snapshot_label>`, preserving the old JSONL de-duplication
  semantics (re-scouting the same opponent on the same data overwrites one object).
- Degrades to local-only with no rclone or no configured remote — an offline laptop shows the
  last-synced state rather than erroring. `FM_STATE_OFFLINE=1` forces that.

**Side effect worth knowing:** moving the shortlist out of `staging.shortlist` removed a
`CREATE TABLE IF NOT EXISTS` that ran on first read, which was why **Squad Tool and Team Builder
crashed against a read-only store**. All 14 pages now pass read-only — a prerequisite for any
hosted/read-only deployment.

## Careers

`Career.active` (in `fmparser/careers.py`) marks a career archived. **Only `frem` is built.**
Bucaspor's saves stay in R2 because they're the only cross-career regression test the parser has,
but its store isn't rebuilt — and since `db.available_careers()` keys off whether the store *file*
exists, not building one is all it takes to drop it from the dashboard. Rebuild with
`--career bucaspor --include-inactive`.

## The verification anchors (two of mine were wrong — use these)

Rebuilt a snapshot into a scratch store (`scripts/rebuild.py --db /tmp/verify.duckdb`) and diffed
it against the live one: **identical** — 23,800 players, 39 first-team + 7 reserve, same names. So
the recipe is faithful. But two anchors I'd written down were measuring the wrong thing:

- **Division sizes must be counted on `staging.league_members`, NOT `effective_table`.**
  `effective_table` only contains players with ratings, so a club with no rated players is
  invisible: the 3. Division shows **11**, not 12, because FC Sydvest has 0 players. That's
  exactly the trap `day1-league-membership.md` warns about — squad size is not a validity filter.
  The correct check:
  ```sql
  SELECT league_cid, COUNT(DISTINCT club_tid) FROM staging.league_members
  WHERE source='club_league' AND phase='<p>' AND league_cid IN (2,3,4,1147) GROUP BY 1
  ```
  → 12/12/12/12. Passes on both live and rebuilt.
- **Our squad at 2023-07-02 is 46 players (39 + 7 reserves), not 54.** The 54 figure — and the
  "30,337 players" one — came from a query missing `AND NOT is_staff`. 23,800 players + 6,537
  staff = 30,337; 46 + 8 staff = 54.

Anchors that hold as written: Frem's league = 3 (NordicBet Liga); Jakobsen **11/70** at ST in that
division at familiarity ≥15; Pingel **9/9** at DMC in Brabrand's squad with no familiarity floor.

One benign difference between a full store and a single-snapshot one: `effective_table`'s `lgn`
CTE resolves league→nation from `staging.leagues` across **all** phases with no phase filter, so a
store holding fewer snapshots knows fewer leagues' nations (17,090 vs 16,566 nation-null rows).
Harmless, but don't mistake it for a decode regression.

## Gotchas found doing this

- **Two Bucaspor saves lived in the repo root**, which is gitignored (`*.fms`) — they'd have been
  lost on any fresh clone. Both are archived now. Don't assume `~/Downloads` is the only place.
- **The shortlist had diverged.** A 2026-08-19 copy of the store held 17 entries the live store
  lacked, and the live store held 3 that copy lacked — two lineages, not a prune, presumably from
  a reload that wiped `staging.shortlist`. The live 7 were migrated; the 17 were preserved to
  `~/fm-saves/_recovered/` rather than merged blind. Exactly the failure mode the R2 move prevents.
- **`seeds/config_bundle.json` never existed** even though `load_duckdb.seed_config_bundle()` had
  always read it, so a rebuilt store came up unconfigured. It now carries the 3 app settings
  (`frem_attacking_ss`, `linear_floor`, floor `0.5`). Tactics stay in `role_weights.csv` — one
  source of truth per thing.
- **numpy is in the uv env**, so the old "extractors must run under bare `python3`" rule is
  obsolete and was a portability trap (it made a second machine depend on numpy outside uv).

## Deferred: the store is ~70% redundant rows

`player_history_seasons` is **14% unique** and `player_positions` **9% unique** — both are
re-stored in full for all 12 snapshots, so a career history that barely changes between two saves
a day apart has its 210k rows rewritten anyway. Deduping would take the store 96 MiB → ~30 MiB.
Deliberately not done: nothing syncs the store now, so its size costs only local disk and rebuild
minutes. It touches the loader's schema and needs all snapshots reloaded and re-verified.

## Still to build (Phase 2)

Static site on Cloudflare Pages — `scripts/build_site.py` renders HTML for reading on a phone
**and** `site/api/club/<tid>.json` per club so Claude can fetch the data and produce a scout
report with both laptops off. Committed `site/`, Pages deploys on push. Plus a Pages Function with
an R2 binding for shortlist adds from the phone. The immersion rule needs active guarding in the
exporter: published JSON must carry `level_*` percentiles and ability *ranks* only, never raw
`ca`/`pa` — reusing `effective_table` (which `EXCLUDE`s `ca`) and the rank helpers preserves that
by construction.
