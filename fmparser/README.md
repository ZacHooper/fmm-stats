# fmparser

Reads a **Football Manager Mobile 2022** save (`.fms`) and writes what it holds as JSON, one
file per table, as the save stores it. Read-only: nothing is ever written back to a save.

The format is undocumented. Everything here was worked out from the bytes and checked against
the game's own screens; each table's doc shows the screen, the bytes and the parsed value side
by side.

## Input and output

- **In:** one save, uncompressed (`<career>-<YYYY-MM-DD>.fms`). A save reads the same whoever
  owns it, so the parser takes no career and imports nothing from the stats side.
- **Out:** `output/<label>/`, one JSON file per table: people, attributes, staff, clubs,
  competitions, nations, stadiums, cities, contracts, career history, club records, player
  progress, training, our matches, the player lists, the world fixture list and each
  competition's stages and rounds, plus a `summary.json`. The full list is in `extract.py`'s
  docstring.

```bash
uv sync                                                   # once: Python 3.13+, zstandard
uv run python extract.py ~/fm-saves/<career>/<save>.fms   # -> output/<save name>/
```

`load_duckdb.py` then loads the bundle into the store (`fmstats/`); see the
[project README](../README.md) for the whole pipeline.

## How it is built

- `extract.py` is a flat list of steps, one per table, in the order the save stores them. A
  cursor checks that each table starts after the one before it ends, so a table found in the
  wrong place fails loudly.
- `fmparser/tables/` has one module per table: where the table is and its record layout,
  declared once (`core.Record`, `core.TableDef`) so the parser reads from the declaration and
  the audit scripts check against it.
- `fmparser/core/` is the engine: primitives, record and table declarations, the tagged-format
  reader, and the zstd archive reader for the save's tail.

## Where the docs are

| you want | read |
|---|---|
| one table: layout, in-game evidence, quirks, output | [`docs/parser/<table>.md`](../docs/parser/) |
| the whole file, start to end | [`docs/parser/savefile-map.md`](../docs/parser/savefile-map.md) |
| how tables are found and read, the method and the tests | [`AGENTS.md`](AGENTS.md) |
| what is still open | [`docs/TODO.md`](../docs/TODO.md) |
