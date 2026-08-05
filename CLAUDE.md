# fm-parser — project guide for agents

Reverse-engineering **Football Manager Mobile 2022** `.fms` save files into a queryable
DuckDB store + a Streamlit dashboard. **Career-aware:** the one genuinely career-specific
fact is the club you manage (its TID), which is how the parser finds your squad's exact
names+attributes. Careers are registered in **`fmparser/careers.py`** and each has its own
DuckDB store (`fm-<key>.duckdb`):

| key | club | managed tid | reserve | store |
|---|---|---|---|---|
| `bucaspor` | Bucaspor 1928 (Turkey) | 6567 | 11320 | `fm-buca.duckdb` |
| `frem` | Boldklubben Frem (Denmark) | 346 | 7296 | `fm-frem.duckdb` |

Extract with `--career <key>`. **Starting a new career:** run
`python3 scripts/discover_career.py <save.fms>` — it reads the "(Nickname)" the save header
opens with and ranks candidate clubs; add the winning first-team + reserve tids to
`careers.py`, then extract. All saves for a career must be that same career.

## Read this first — accumulated project knowledge
The durable context an agent needs lives in **[`docs/agent-context/`](docs/agent-context/)**
(vendored from the assistant's memory so it travels with the repo). Start with
[`docs/agent-context/MEMORY.md`](docs/agent-context/MEMORY.md) — it indexes the rest:
- **fm-parser-project** — the save-format reverse-engineering story + goals.
- **etl-duckdb-dashboard** — how the ETL + dashboard + `fmq.py` CLI + scouting tooling work. **The main reference.**
- **squad-comparison-bridge**, **seyhun-attr-investigation**, **loan-status-unreliable**, **fmm-tactic-options** — specific findings; read when relevant.

These are point-in-time notes — verify file/line claims against the current code before asserting them as fact.

## Skills (in `.claude/skills/`, auto-discovered)
- **import-fm-saves** — parse new `.fms` saves → load into the career's DuckDB store. Use when new saves appear.
- **scout-opponent** — technical-analyst opposition briefing (combines our data + the user's in-game scout report).
- **preseason-squad-review** — squad review at a season boundary.
- **developing-with-streamlit** — conventions for editing the dashboard.

## Toolchain
- **Extractors are pure-stdlib** — run with `python3 extract.py …` / `python3 dump_lightresults.py …` (NOT uv).
- **Everything else is uv** — `uv sync` to set up; loader is `uv run python load_duckdb.py …`; CLI is `uv run python fmq.py …`; dashboard is `uv run streamlit run dashboard/Home.py`.
- **DuckDB is single-writer**: a running Streamlit holds the lock. For read-only CLI work either `pkill -f streamlit` first, or set `FM_DUCKDB_READONLY=1`, or query a `cp` of the store. The `fmq scout` command auto-copies when the DB is locked.
- **Career selection**: the dashboard shows a sidebar **Career** selector (defaults to the newest store); it repoints the DB + "us" club. Override anywhere with env `FM_CAREER=<key>` (and `FM_DUCKDB=<path>` to force a specific store).
- Season = **end-year** of the campaign (22/23 → 2023, Aus-FY style); phase ∈ {start, mid, end}.

## Common commands
```bash
uv sync                                                   # one-time env setup
uv run streamlit run dashboard/Home.py                    # dashboard (sidebar Career selector)
python3 scripts/discover_career.py <save.fms>             # find a new career's club tids
python3 extract.py <save.fms> --career <key> --label <l>  # extract (pure-stdlib, NOT uv)
uv run python load_duckdb.py output/<label> --db fm-<key>.duckdb --season <YYYY> --phase <start|mid|end>
uv run python fmq.py scout <team>                          # opposition briefing (auto-saves)
```

## House rules
- **Immersion: NEVER surface the raw CA/PA number.** Reason with weighted role ratings, `pos_index`, percentiles, match stats, and attributes only. **Allowed exception:** the **Level %ile** (`level_*` in `effective_table`) is a tactic-agnostic quality *percentile* derived from CA — the raw ability is `EXCLUDE`-d from the query so only the percentile ever leaves. It sits next to the tactic **Fit %ile** (`pctile_*`). Keep raw `ca`/`pa` out of every surfaced frame; don't remove Level %ile thinking it breaks this rule.
- **Opponent tactics/formation are NOT in the save** — always ask the user for the in-game scout's formation + style. Opponent names aren't parsed (profile by position + percentile). Opponent attributes are model estimates (±1) except pace/physicals.
- Our tactic/method is **`buca_433`** (the dashboard default).

## Data setup on a fresh clone
`git clone` + `uv sync` gives you the code, skills, context, **and the committed per-career stores** (`fm-buca.duckdb`, `fm-frem.duckdb`, ~26MB each). What's NOT in git:
- **`.fms` save files** (personal, large) — transfer out-of-band (AirDrop / shared cloud folder) if you need to re-extract.
- **`output/`** (extract JSON, ~400MB) — regenerable via the `import-fm-saves` skill; never committed.

The committed stores are enough to run the dashboard, CLI, and all scouting/analysis immediately — you only need the saves to import *new* snapshots. Note: a **day-1 save** (0 matches) has no leagues/competitions/results yet, so the vs-league and scouting views stay empty until games are played; squad attributes/ratings work regardless.
