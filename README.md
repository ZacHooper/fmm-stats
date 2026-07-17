# fm-parser

Read-only extraction of a **Football Manager Mobile 2022** save. Drop in a `.fms`
file and get the season's matches and the whole league's player attributes as JSON/CSV.
Nothing is written back to the save.

> Scoped to one career (Bucaspor). It's built to run on the *same* save pulled at
> different points in a season (start / mid / end). See [Portability](#portability).

## Usage

```bash
python3 extract.py path/to/save.fms
# or pin the label yourself:
python3 extract.py path/to/save.fms --label 2022-end
```

This writes `output/<label>/`:

| file | contents |
|------|----------|
| `players.json` / `players.csv` | **whole player DB** (~24k): 23 attributes (exact + estimated), CA/PA, positions, feet, reputation, club, DOB, nationality |
| `matches.json` | every match: per-player stats (23 fields), events, team stats, formation, man-of-the-match |
| `player_match_stats.csv` | flat one-row-per-(match, player), carrying the team actually played for |
| `transfers.json` | players whose current club differs from a team they played for this season |
| `staff.json` | ~7k non-players (managers/coaches/scouts): identity only |
| `clubs.json` | club TID → name |
| `summary.json` | counts, date range, competitions, how the label was derived |

The label defaults to `<season-end-year>-<period>`, read from the save's latest match
date (`Aug–Sep`→start, `Oct–Feb`→mid, `Mar–Jul`→end). Override with `--label`.
A zero-match save (fresh season) still produces the full player DB — the player list
comes from the info spine, not from matches — but can't auto-derive a year, so pass `--label`.

## What you get (and how much to trust it)

| grade | meaning |
|-------|---------|
| **Exact** | read directly, or a formula verified against ground truth |
| **±1** | regression estimate, ~93% within one point (held-out) |
| **Derived** | computed from stored parts (the game doesn't store it either) |

- **Matches** — player stats, events, score/date/attendance/competition, and formation are **exact**. Shots / shots-on-target / team rating and man-of-the-match are **derived** (the game recomputes them too).
- **Attributes** — 8 of 23 are **exact** (physical + Teamwork); the other 15 (technical + GK clusters) are **±1**. CA/PA, positions, feet, reputation are **exact**. Your own squad is fully **exact** (from the snapshot); everyone else uses the estimator.
- **Not recoverable** — possession, clear-cut chances, roles/duties (not in the save). Player names are decodable only for your own club (opponent name index uncracked, and deliberately left off). See [`docs/BUGS.md`](docs/BUGS.md).

## How it works (staging → join)

Each region of the save is scraped independently into a keyed table, then joined — the
player **info section is the identity spine** (~31k records: `TID`, `SID`, `club_tid`,
name IDs, DOB). Attributes join on `SID`, clubs on `club_tid`, names on `TID`. This
decouples *who exists* (info) from *what happened* (matches), so a fresh season with no
matches still yields the full DB. Non-players (staff) are split out by `SID == ffffffff`.
See [`fmparser/staging.py`](fmparser/staging.py).

## Layout

```
extract.py            entry point
fmparser/             the library
  save.py             mmap loader + search helpers
  regions.py          career config + region windows (the save-specific bits)
  staging.py          sweep each region into keyed tables (info spine, attributes)
  matches.py          per-match stats, events, team stats, formation
  attributes.py       own-squad (exact) + record locator + estimator
  model.py            frozen regression coefficients + predict()
  reference.py        club / competition names, player info field
data/                 ground truth, screenshots, rough-guide, breadcrumbs
docs/                 ATTRIBUTE_DECODING.md, BUGS.md
archive/              exploratory + model-derivation scripts (provenance)
tests/                ground-truth regression guard
output/               extractions (gitignored)
```

## Tests

```bash
python3 tests/test_ground_truth.py
```

Asserts the known-correct values still parse (the 3-3 match's team stats and formation,
two scouted opponents within ±1, CA/PA exact). This is the tripwire for a new save that
shifts offsets — if region-finding breaks, this fails loudly.

## Portability

Everything save-specific lives in `fmparser/regions.py`:

- **Career config** (managed club TID, competition IDs) — stable across the career.
- **Region windows** (byte ranges for matches / snapshot / global attributes) — these
  drift as the save grows over a season, so they're generous and every record is
  validated on read. If a future save moves data out of range, widen them there; the
  ground-truth test will flag it.

Running on a *different* career or a full-DB export would need the config generalised
(auto-detect the managed club and its competitions) — not done yet.

## How it was worked out

The reverse-engineering story — record layouts, the exact formulas, the attribute
regression, and everything that turned out **not** to be stored — is in
[`docs/ATTRIBUTE_DECODING.md`](docs/ATTRIBUTE_DECODING.md) and
[`docs/BUGS.md`](docs/BUGS.md).
