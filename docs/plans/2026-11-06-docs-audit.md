# Docs framework and clean-up

> **Status (2026-11-06): planned.** Do this before the fresh public repo is cut, so the public
> history starts with docs that describe the project as it is.

## Why
The docs grew with the project: 80 files, ~14,500 lines of current reference, finished plans,
vendored assistant memory and investigation logs. A scan on 2026-11-06 found ~95 references to
files that no longer exist, across 37 docs. A stale doc is worse than none: it reads as
authoritative. **Fewer docs is better**, as long as nothing true and hard-won is lost.

## Who reads them
1. **Now: developers** using this code to improve their own parsers and tools.
2. **Later: players who don't code.** Their agent clones the repo, they hand over a save from
   their phone, and they're done. Every part needs an agent-runnable path from save to answer.

So: **the README and each part's overview are written for humans. Everything else is written
for agents, and kept lean.** A dense doc wastes an agent's context as much as a human's
attention. Link to detail; don't inline it.

## What we document
**The present, not the past.** The parse is deterministic now, so the docs say how to read a
save as we know it today. How we got here stays in git history. The method that still applies
(how to decode a new table) is kept as current practice, not as a story.

For each part (parser, stats, site, skills), and nothing more:

| | answers | reader |
|---|---|---|
| **What it is** | what it does, inputs, outputs, how it's used | human |
| **How to develop it** | conventions, patterns, the feedback loop, tests | agent |
| **Reference** | the specification: tables, models, API shapes | agent |
| **Data quirks** | where the data misleads you, and what to do about it | agent |

**Decisions, dead ends and quirks are callouts, not docs.** They sit in the doc that describes
the thing they're about, never in a separate file and never as comment clutter in the code:

```markdown
> **Decision:** the data lives in R2, not git: it is drawn from the game's database and
> rewrites wholesale on every import.

> **Dead end:** possession is not stored. <What was searched, and how, in one line.>

> **Quirk:** a lapsed loan can leave `club_tid` on the old club. Use `mart.squad_membership`.
> Tested by `<test name>`.
```

**What to keep:** a nugget survives only if it is **still true** (checked against the code or
data) **and** either prevents a wrong answer or would take real effort to rediscover. Narration,
status updates, step logs and superseded hypotheses go; a disproved idea worth knowing survives
as a one-line Dead end callout.

## Where it lives: as close to the thing as possible

| part | what it is | develop | reference | quirks |
|---|---|---|---|---|
| **Parser** | `fmparser/README.md` | `fmparser/AGENTS.md` | **one doc per table**, `docs/parser/<table>.md`, plus the whole-file map | callouts in the table doc; a test where possible |
| **Stats** | `fmstats/README.md` | `fmstats/AGENTS.md` | **dbt yml descriptions** (models and columns), read with `dbt docs`; the data model overview | callouts in the yml description or overview; dbt tests |
| **Site** | `site/README.md` | `site/AGENTS.md` | `site/API.md` | callouts in `API.md` |
| **Skills** | a table in the README | each `SKILL.md` | — | in the skill |

Plus, at the top: `README.md` (human), `AGENTS.md` (agent, short), `CONTRIBUTING.md`,
`docs/TODO.md`, `docs/DEPLOY.md`. A short **modelling** note in `docs/stats/` covers the
analysis work (the attribute model, the CA weighting, how weight sets are derived) as
greenfield work in progress, without the Frem-specific conclusions.

The parser's table docs follow one template, so an agent can load exactly one:

```markdown
# <table>  (fmparser/tables/<table>.py)
What it is, in one line. Where it sits in the save, how it is framed.
## Layout          field | type | meaning | how we know (provenance)
## Provenance      the in-game screen each field was checked against, with an example
## Quirks          callouts
## Output          output/<label>/<table>.json, and the raw table it loads into
```

### Provenance
Mostly a parser concern, and the weakest part of the docs today. For each table, one
**ground-truth record**: an in-game screen, the value it shows, the raw bytes, and the parsed
value. It lives in the table doc's Provenance section, and where it can, as a test fixture
(`tests/fixtures/`) that asserts the parse. The record is written as text, the screen named and
the value transcribed. The screenshots themselves stay private: they are the game's UI.

## Phases
Each phase **harvests, writes, deletes** in one PR: pull the nuggets out of the docs it
retires, write them into their new home in the template, delete the old doc (git keeps it; the
PR links its last commit), and fix every link.

0. **Checker.** `scripts/check_docs.py`: every repo path a doc cites exists, and every relative
   link resolves. In CI. Its first run lists the work.
1. **Parser.** One doc per table (27), from the module docstrings, `savefile-map.md`,
   `table-framing.md`, `save-archive.md`, the record docs, `IDS.md`, `BUGS.md` and the parser
   notes in `agent-context/`. Then `fmparser/README.md` and a trimmed `fmparser/AGENTS.md`.
   Provenance records start here; the user supplies screenshots table by table.
2. **Stats.** Column descriptions in the dbt yml: model descriptions are complete (170 of
   173), and only 11 columns are documented. Then the data-model overview, `fmstats/README.md`,
   and the modelling note from `ca-weighting.md`, `attribute-model.md`, `ATTRIBUTE_DECODING.md`
   and the analysis notes.
3. **Site and skills.** `site/README.md`, a lean `site/API.md`, and the skills, together with
   the TODO entry "Finish making the project career-agnostic".
4. **Delete the rest** and review `CAREER.md`. `docs/agent-context/` and finished plans go.
   Replace every `TODO #N` citation with the entry's title: numbers get reused, and ~25 such
   citations already point at the wrong entry.

## Where today's docs go
Proposed; each is confirmed as it's harvested.

| today | goes to |
|---|---|
| `savefile-map.md`, `table-framing.md`, `save-archive.md`, `archive-coverage.md`, `IDS.md`, `light-results-record.md`, `standings-record.md`, `transfer-history-record.md`, `record-expansion.md`, `career-region-sizing.md`, `date-search.md`, `parser-architecture.md` | the per-table docs, the whole-file map, `fmparser/AGENTS.md` |
| `BUGS.md` | Dead end and Quirk callouts in the docs they belong to; open bugs to TODO |
| `ca-weighting.md`, `attribute-model.md`, `ATTRIBUTE_DECODING.md`, `role-ids.csv` | the modelling note and the dbt yml |
| `data-model/*` | kept as the stats overview; detail moves to the yml |
| `agent-context/` parser notes (history chains, names, matches, injuries, loans, anchors, boundaries, tid recycling) | parser table docs |
| `agent-context/` analysis notes (correlations, value estimation, role weights, shot quality, scouting reads, rating bias, Level vs Fit, footedness, trait lines, tactic options) | the modelling note, the skills, or `CAREER.md` |
| `agent-context/` storage notes (`multi-device-and-storage`, `remote-duckdb-access`) | `DEPLOY.md`; the author's specifics to `CAREER.md` |
| `danish-registration-rules.md`, `agent-context/homegrown-derivation.md` | `site/` (the house-rule example) or `CAREER.md` |
| `fmm-tactic-blueprints.md` | the skills or `CAREER.md` |
| `agent-context/MEMORY.md`, superseded notes, finished plans | deleted |

## Done when
- `scripts/check_docs.py` passes in CI.
- Every parser table has its doc, with at least one provenance record.
- Every `mart` and `site` column has a dbt description.
- `docs/agent-context/` is gone; `docs/plans/` holds only open plans.
- A newcomer gets from the README to the doc for any part in two clicks, and an agent can load
  one table's or one model's doc without pulling in the rest.
- The TODO entry "Audit and clean up the docs" is deleted.
