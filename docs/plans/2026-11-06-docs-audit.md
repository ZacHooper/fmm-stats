# Docs audit and clean-up

> **Status (2026-11-06): planned.** Do this before the fresh public repo is cut, so the public
> history starts with docs that describe the project as it is.

## Why
The docs grew with the project: 80 files, ~14,500 lines. They are a mix of current reference,
finished plans, vendored assistant memory and investigation logs, and a lot of them describe
code that no longer exists. A scan on 2026-11-06 found **~95 references to files that are gone**
(the pre-`core` parser modules, the Streamlit `dashboard/`, `fmstats/mart.py`, deleted scripts)
across 37 docs, plus Streamlit/`fmq`/Pages wording in a dozen more. For a newcomer, or an agent,
a stale doc is worse than none: it reads as authoritative.

## What good looks like
- **Every doc has one reader and one job**, and says which in its first lines.
- **Reference docs describe the current state.** How it came to be belongs in git history.
  The same rule `AGENTS.md` sets for code comments.
- **Organised by the three parts** (parser, stats, site), with a `docs/README.md` index.
- **Nothing career-specific in the public docs.** Frem facts are worked examples at most; notes
  only true of one career go to the user's own notes (`CAREER.md`, or their private repo).
- **A checker keeps it that way**: dead file references and broken relative links fail CI.

### Target layout
```
README.md  AGENTS.md  CONTRIBUTING.md            entry points (done)
fmparser/AGENTS.md  fmstats/AGENTS.md  site/AGENTS.md  site/API.md   per-part guides (done)
docs/
  README.md          index: what each doc is for
  TODO.md            open work (exists)
  BUGS.md            known problems and dead ends (exists; prune)
  parser/            save format: savefile-map, table-framing, parser-architecture,
                     save-archive, the per-record docs, IDS, archive-coverage
  stats/             data-model/, attribute-model, ca-weighting, analysis methods
  site/              DEPLOY
  plans/             OPEN plans only
```
`docs/agent-context/` is dissolved: each note is folded into the reference doc it belongs to,
moved to the author's private notes, or deleted.

## Method
1. **Phase 0, the checker (half a day).** `scripts/check_docs.py`: every repo path a doc cites
   must exist, and every relative Markdown link must resolve. Run it in CI. Its first run is the
   work list for phase 2. (The scan behind this plan is the prototype: a regex over
   `(fmparser|scripts|tests|fmstats|site|dashboard)/...\.(py|sql|js|md)`, then `test -e`.)
2. **Phase 1, delete.** Finished plans, superseded notes, investigation logs whose conclusion is
   already in a reference doc. Git keeps all of it. Before deleting, grep for inbound links.
3. **Phase 2, fix what stays.** Work through the checker's list. For each doc: verify its claims
   against the code (point-in-time notes drift), remove history narration, fix or drop dead
   references. A doc that needs more than this is a candidate for merging.
   Replace every `TODO #N` citation with the entry's title or a link: TODO numbers are
   renumbered freely (its own rule), and ~25 citations in `data-model/`, `table-framing.md`,
   `savefile-map.md` and others already point at the wrong entry or a closed one.
4. **Phase 3, dissolve `agent-context/`.** One note at a time, by the triage table below.
5. **Phase 4, restructure.** Move into `docs/parser|stats|site/`, write `docs/README.md`, fix
   every link (the checker proves it). One mechanical commit, so review is easy.
6. **Phase 5, skills.** The same pass over `.claude/skills/`, together with the TODO entry "Finish making the project career-agnostic" (they
   hardcode Frem).

Each phase is its own PR. Phase 4 must not mix with content edits.

## Triage (proposed — confirm each before acting)
Dead = references to files that no longer exist, from the 2026-11-06 scan.

### Delete
| doc | why |
|---|---|
| `plans/2026-09-21-table-engine-migration.md` | done (every table is on `core`); 9 dead refs |
| `plans/2026-10-01-data-layers.md` | done (its own status line); 862 lines, 29 stale mentions |
| `plans/2026-10-03-site-marts.md` | done (the export reads only `site.*`) |
| `plans/2026-09-23-match-rating-normalisation.md` | built and published (its status line); fold any rule still live into `fmstats/AGENTS.md` |
| `plans/2026-09-22-parser-optimization-plan.md` | verify what landed; move anything open to TODO |
| `agent-context/light-results-rolling-buffer.md` | marked SUPERSEDED |
| `agent-context/master-schedule-plan.md` | marked SUPERSEDED |
| `agent-context/etl-duckdb-dashboard.md` | describes the Streamlit dashboard, `fmq` and `scout.py`, all gone |
| `agent-context/fm-parser-project.md` | the project story, now told by README + `parser-architecture.md`; stale SHAs |

### Fold into a reference doc, then delete
| doc | into |
|---|---|
| `ATTRIBUTE_DECODING.md` | `ca-weighting.md` / `attribute-model.md` (it predates both) |
| `agent-context/savefile-boundary-map.md` | `savefile-map.md` |
| `agent-context/parser-hardcoded-anchor-audit.md` | `table-framing.md` (what is still hardcoded) |
| `agent-context/history-chain-pointers.md`, `player-history-table.md` | a `parser/history.md` record doc |
| `agent-context/name-resolution.md`, `nickname-players-missing.md` | a names section in `parser-architecture.md` |
| `agent-context/match-position-encoding.md`, `ghost-match-anchors.md` | the matches record doc |
| `agent-context/injury-progress-decode.md`, `loan-value-marker.md`, `reserve-marker-stale-attrs.md`, `loan-status-unreliable.md` | the player-record section they describe |
| `agent-context/tid-recycling.md`, `user-supplied-save-date-wins.md`, `day1-league-membership.md`, `ground-truth-beats-my-parse.md` | `AGENTS.md` traps / `fmparser/AGENTS.md` method (a few lines each) |
| `agent-context/remote-duckdb-access.md`, `multi-device-and-storage.md` | `DEPLOY.md` (generic part); the author's R2 specifics to `CAREER.md` |
| `career-region-sizing.md`, `date-search.md` | `savefile-map.md`, if anything in them is still true |
| `agent-context/MEMORY.md` | replaced by `docs/README.md` |

### Keep, fix (verify claims, drop history, fix dead refs)
`savefile-map.md`, `table-framing.md` (1 dead), `parser-architecture.md` (2), `save-archive.md`
(3), `record-expansion.md` (4), `light-results-record.md` (2), `standings-record.md` (2),
`transfer-history-record.md`, `IDS.md` (1), `archive-coverage.md`, `ca-weighting.md`,
`attribute-model.md` (1), `data-model/*`, `DEPLOY.md`, `BUGS.md` (6; also prune items fixed
since), `TODO.md`, `fmparser/AGENTS.md` (1), `site/API.md` (1), `site/guides/*`
(`registration.md`: 1).

### Analysis methods: keep the general, move the Frem-specific
These are useful to any player, but most are written about Frem's squad. Keep the method and
measurements, make Frem a worked example, move squad-specific conclusions to private notes:
`agent-context/attribute-stat-correlations.md` (3 dead), `player-analysis-methods.md` (2),
`player-value-estimation.md`, `role-weight-methods.md`, `scoring-and-shot-quality.md`,
`scouting-attribute-reads.md`, `match-rating-position-bias.md`, `level-vs-fit-percentile.md`,
`wide-footedness.md`, `report-trait-lines.md`, `fmm-tactic-options.md`,
`fmm-tactic-blueprints.md` (1), `fmm-editor-record-comparison.md` (5; parser side).

### Move to the author's private notes
`danish-registration-rules.md` (unless the house-rule switch keeps the Danish rules as the
example), `agent-context/homegrown-derivation.md` (same), `agent-context/seyhun-attr-investigation.md`,
`agent-context/squad-comparison-bridge.md`.

## Done when
- `scripts/check_docs.py` passes in CI.
- `docs/agent-context/` is gone and `docs/plans/` holds only open plans.
- Every remaining doc names its reader and job in its first lines, and `docs/README.md` lists it.
- A newcomer can get from README to the doc for any part in two clicks.
- The TODO entry "Audit and clean up the docs" is deleted.
