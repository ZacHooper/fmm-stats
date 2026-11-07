# fmm-stats

**Turn your Football Manager Mobile 2022 save into a database you can query and a stats app for
your phone.**

FMM22 shows you a lot, but it doesn't let you ask questions of it: who has actually hurt us in
the last five meetings, which youngster is growing fastest, which club's starter line would my
loanee walk into. This project reads a `.fms` save file and gives you all of it: every player in
the world with attributes, every match you've played with per-player stats, the whole world's
fixtures and results, transfers, contracts, club histories, and how your squad changes across
saves.

It is **read-only**. Nothing is ever written back to a save, and the game is never modified.

> **Unofficial.** This is a fan project. It is not affiliated with, endorsed by or connected to
> Sports Interactive or SEGA. *Football Manager* is a trademark of Sports Interactive Limited
> and SEGA. No game data is included in this repository: you bring your own save, and what you
> do with the data drawn from it is up to you. See [Disclaimer](#disclaimer).

## Fastest start

You need a Mac, your iPhone with FMM22 on it, and an AI coding agent (such as
[Claude Code](https://claude.com/claude-code)). No coding.

**1. Copy a save off your iPhone.** Plug the iPhone into the Mac, open **Finder**, click the
iPhone in the sidebar, open the **Files** tab and expand **FMM22**. Drag a save file (`.fms`)
into your Downloads folder.

**2. Give your agent this:**

> Clone https://github.com/ZacHooper/fmm-stats and set it up for me with its `get-started`
> skill. My save is in my Downloads folder.

It installs what's needed, finds your club in the save, builds your stats and opens the site.
Then ask it things: *scout my next opponent*, *who should start*, *review my season*.

## What's in it

```
your save (.fms)
   │
   ▼  Parser — fmparser/, extract.py
output/<save>/*.json        one file per table, exactly as the save stores it
   │
   ▼  Stats — load_duckdb.py, fmstats/ (dbt)
fm-<career>.duckdb          raw → stg → int → mart (dim_* / fact_*) → site
   │
   ├──▶ SQL: query it yourself, or ask an agent (skills in .claude/skills/)
   │
   ▼  Site — scripts/export_data.py, site/, site-worker/
a phone-friendly web app    squad, ratings, matches, history, world, recruitment
```

| part | what it does | start here |
|---|---|---|
| **Parser** | Decodes the binary save, table by table, into JSON. Knows nothing about your career. | [`fmparser/AGENTS.md`](fmparser/AGENTS.md), [`docs/parser/savefile-map.md`](docs/parser/savefile-map.md) |
| **Stats** | Loads each save as a dated snapshot into DuckDB, then a dbt project models it: players, clubs, matches, competitions, contracts, across every snapshot. | [`fmstats/AGENTS.md`](fmstats/AGENTS.md), [`docs/data-model/`](docs/data-model/README.md) |
| **Site** | A static web app (no build step) that rates players in your tactic's roles in the browser. Optional: deploys as a Cloudflare Worker. | [`site/AGENTS.md`](site/AGENTS.md), [`docs/DEPLOY.md`](docs/DEPLOY.md) |
| **Skills** | Recipes an AI agent follows: scout an opponent, season review, pre-season squad review, and more. | [`.claude/skills/`](.claude/skills/) |

## Quickstart for developers

You need **[uv](https://docs.astral.sh/uv/)** (it fetches Python 3.13) and an **FMM22 save
file** (`.fms`).

```bash
git clone https://github.com/ZacHooper/fmm-stats && cd fmm-stats
uv sync

# 1. Find your club in the save and write it into fmm.toml (prints the career <key>)
uv run python scripts/discover_career.py path/to/your-save.fms --write

# 2. Move the save into ~/fm-saves/<key>/, named by its in-game date, then parse it
uv run python scripts/archive_save.py path/to/your-save.fms --career <key>
uv run python extract.py ~/fm-saves/<key>/<key>-<date>.fms

# 3. Load it (builds fm-<key>.duckdb and runs every dbt model and test)
uv run python load_duckdb.py output/<key>-<date>

# 4. Look at it
uv run python scripts/export_data.py
uv run python -m http.server -d site 8000                      # http://localhost:8000
```

Add more saves from the same career over time: each becomes a snapshot, so growth, form and
history build up. Query the store directly with DuckDB:

```bash
uv run python -c "import duckdb; con = duckdb.connect('fm-<key>.duckdb', read_only=True); \
  print(con.sql('select * from mart.squad_membership where is_current and is_managed_club'))"
```

## Make it yours: `fmm.toml`

Everything personal lives in `fmm.toml` (gitignored; the template is
[`fmm.example.toml`](fmm.example.toml)): your careers, where saves live, an optional object
store (Cloudflare R2 or any rclone remote) for backing up saves and publishing the app, your
site's URL, and **how you like to play**.

The first play-style switch is **immersion**. With `hide_ability = true` (the default) the raw
current/potential ability number never leaves the database: the app and the agents talk in
percentiles, role fit and attributes, the way the game's own screens do, and the export refuses
to publish a raw-ability field. Set it to `false` if you'd rather see the number.

## Using it with an AI agent

The repo is built to be worked on, and asked questions, by coding agents.

- **[`AGENTS.md`](AGENTS.md)** is the agent's guide: the three parts and their boundaries, the
  rules that make a query wrong rather than imprecise, and where the reference knowledge lives.
  Each part has its own `AGENTS.md`. Claude Code reads them through one-line `CLAUDE.md` files.
- **Skills** in [`.claude/skills/`](.claude/skills/) are step-by-step recipes for common asks:
  `get-started` to set everything up from a save, `query-fm-data` for any quick question,
  `scout-opponent`, `season-outlook`, `preseason-squad-review`, `fm-season-review`,
  `where-are-they-now`, `attribute-profiles`, `import-fm-saves`. They were written around the author's own career, so they work best as
  templates; the data model they query is general.
- **`CAREER.md`** (optional, gitignored): write your own notes about the career you're playing
  (your tactic, house rules, what's happened so far). `AGENTS.md` tells agents to read it.
- **[`site/API.md`](site/API.md)** is published with the web app, for agents that read your
  deployed site's JSON rather than the database.

## What you can trust

| | grade |
|---|---|
| Your own squad's attributes | **exact**, from the club's own records (scrapbook entries up to a year old) |
| Other players: physical attributes, positions, feet, age, contracts | **exact** |
| Other players: technical, mental and goalkeeping attributes | **model estimates**, mostly within ±1 ([`docs/ca-weighting.md`](docs/ca-weighting.md)) |
| Your matches: scores, events, per-player stats, formations | **exact** |
| World fixtures and results | **exact** ([`docs/parser/fixtures.md`](docs/parser/fixtures.md)) |
| Shots, team rating, man of the match | **derived** from stored parts, as the game does |
| Possession, roles and duties, the exact XI on a given day | **not in the save** |

Open work, known problems included, is in [`docs/TODO.md`](docs/TODO.md); dead ends are
callouts in the doc about the table they concern ([`docs/parser/`](docs/parser/)).

## Tests

```bash
uv run python tests/run_tests.py       # parser and unit tests
uv run python tests/test_boundary.py   # the layer boundaries
```

Most parser tests need real saves and **skip** without them (the runner says so plainly; it
never reports a skip as a pass). The unit tests run anywhere. Loading a save runs the whole dbt
test suite against your data.

## How it was worked out

The save format is undocumented. The method (map the regions first, prove a record's extent,
never validate a field by joining on it) and the findings are in
[`fmparser/AGENTS.md`](fmparser/AGENTS.md), [`docs/parser/savefile-map.md`](docs/parser/savefile-map.md),
[`docs/table-framing.md`](docs/table-framing.md), the table docs in
[`docs/parser/`](docs/parser/) and
[`docs/agent-context/`](docs/agent-context/MEMORY.md).

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Disclaimer

This project reads save files that you create by playing a game you own, so that you can get
more out of that game. It does not modify the game or its saves, bypass any protection, or
include any of the game's code or database. Player, club and competition data appears only in
the output you generate from your own save, on your own machine. Please don't redistribute that
output in bulk.

*Football Manager*, *Football Manager Mobile* and related names are trademarks of Sports
Interactive Limited and SEGA, used here only to describe what the software is compatible with.

## Licence

[MIT](LICENSE) © Zac Hooper. The licence covers this project's code and documentation, not the
game or any data drawn from it.
