# Contributing

Thanks for looking. This is a fan project for **Football Manager Mobile 2022**; contributions
are welcome, especially decodes that work on careers other than the two it was built on.

## Ground rules
- **Never commit save data.** No `.fms` saves, DuckDB stores, `output/` extracts or exported
  site JSON — they are drawn from the game's database. `.gitignore` covers them; please don't
  force them in, and don't paste large extracts into issues either.
- **No game assets.** No logos, artwork or files from the game itself.
- Keep your own settings in `fmm.toml` and `CAREER.md` (both gitignored), not in code.

## Setup
```bash
uv sync
cp fmm.example.toml fmm.toml     # then add your career (scripts/discover_career.py)
```
[`README.md`](README.md) has the quickstart and [`AGENTS.md`](AGENTS.md) is the working guide
(it is written for coding agents, and reads fine for humans too). Read the guide for the part
you're changing first: [`fmparser/AGENTS.md`](fmparser/AGENTS.md),
[`fmstats/AGENTS.md`](fmstats/AGENTS.md) or [`site/AGENTS.md`](site/AGENTS.md).

## Tests
```bash
uv run python tests/run_tests.py       # unit tests run anywhere; parser tests need saves
uv run python tests/test_boundary.py   # the parser never imports the store, and so on
```
Most parser tests read real saves from `[storage] saves_dir` and skip without them. If your
change touches the parser, run them against your own saves and say which career and season
you tested on in the pull request. Loading a save runs the full dbt test suite.

## Decoding something new
Read [`fmparser/AGENTS.md`](fmparser/AGENTS.md) first. The short version: find the record's
extent before naming its fields, never validate a field by joining on it, and show the evidence
(a screenshot of the in-game value is the best ground truth there is). A finding that holds on
two careers is worth far more than one that holds on one.

## Pull requests
- One change per pull request, with what you tested it on.
- Comments describe the format as it is, not the history of how it was found.
- CI runs the unit tests and the boundary test.
