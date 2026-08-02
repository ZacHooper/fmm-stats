# fm-parser — project guide for agents

Reverse-engineering **Football Manager Mobile 2022** `.fms` save files into a queryable
DuckDB store + a Streamlit dashboard, for a single managed career (**Bucaspor**: first team
`tid 6567`, reserves `tid 11320`). The parser is hardcoded to that career — every save must
be the same career or the extraction is garbage (verify `clubs.json` has `6567` and `11320`).

## Read this first — accumulated project knowledge
The durable context an agent needs lives in **[`docs/agent-context/`](docs/agent-context/)**
(vendored from the assistant's memory so it travels with the repo). Start with
[`docs/agent-context/MEMORY.md`](docs/agent-context/MEMORY.md) — it indexes the rest:
- **fm-parser-project** — the save-format reverse-engineering story + goals.
- **etl-duckdb-dashboard** — how the ETL + dashboard + `fmq.py` CLI + scouting tooling work. **The main reference.**
- **squad-comparison-bridge**, **seyhun-attr-investigation**, **loan-status-unreliable**, **fmm-tactic-options** — specific findings; read when relevant.

These are point-in-time notes — verify file/line claims against the current code before asserting them as fact.

## Skills (in `.claude/skills/`, auto-discovered)
- **import-fm-saves** — parse new `.fms` saves → load into `fm.duckdb`. Use when new saves appear.
- **scout-opponent** — technical-analyst opposition briefing (combines our data + the user's in-game scout report).
- **preseason-squad-review** — squad review at a season boundary.
- **developing-with-streamlit** — conventions for editing the dashboard.

## Toolchain
- **Extractors are pure-stdlib** — run with `python3 extract.py …` / `python3 dump_lightresults.py …` (NOT uv).
- **Everything else is uv** — `uv sync` to set up; loader is `uv run python load_duckdb.py …`; CLI is `uv run python fmq.py …`; dashboard is `uv run streamlit run dashboard/Home.py`.
- **DuckDB is single-writer**: a running Streamlit holds the lock. For read-only CLI work either `pkill -f streamlit` first, or set `FM_DUCKDB_READONLY=1`, or query a `cp` of `fm.duckdb`. The `fmq scout` command auto-copies when the DB is locked.
- Season = **end-year** of the campaign (22/23 → 2023, Aus-FY style); phase ∈ {start, mid, end}.

## Common commands
```bash
uv sync                                                   # one-time env setup
uv run streamlit run dashboard/Home.py                    # dashboard
uv run python fmq.py labels                                # what's loaded
uv run python fmq.py scout <team>                          # opposition briefing (auto-saves)
uv run python fmq.py scouts                                # saved scout log
uv run python load_duckdb.py output/<label> --season <YYYY> --phase <start|mid|end>
```

## House rules
- **Immersion: NEVER surface CA/PA.** Reason with weighted role ratings, `pos_index`, percentiles, match stats, and attributes only.
- **Opponent tactics/formation are NOT in the save** — always ask the user for the in-game scout's formation + style. Opponent names aren't parsed (profile by position + percentile). Opponent attributes are model estimates (±1) except pace/physicals.
- Our tactic/method is **`buca_433`** (the dashboard default).

## Data setup on a fresh clone
`git clone` + `uv sync` gives you the code, skills, context, **and a working `fm.duckdb`** (committed, ~26MB). What's NOT in git:
- **`.fms` save files** (personal, large) — transfer out-of-band (AirDrop / shared cloud folder) if you need to re-extract.
- **`output/`** (extract JSON, ~400MB) — regenerable via the `import-fm-saves` skill; never committed.

The committed `fm.duckdb` is enough to run the dashboard, CLI, and all scouting/analysis immediately — you only need the saves to import *new* snapshots.
