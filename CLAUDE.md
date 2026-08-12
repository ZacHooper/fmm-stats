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
- **squad-comparison-bridge**, **seyhun-attr-investigation**, **loan-status-unreliable**, **fmm-tactic-options**, **light-results-rolling-buffer**, **master-schedule-plan** — specific findings; read when relevant.

These are point-in-time notes — verify file/line claims against the current code before asserting them as fact.

## Reverse-engineering method: ALWAYS region-first, then structural
When locating a **new field** in the save, do NOT start by guessing byte offsets. Follow this order —
it has repeatedly turned multi-hour hunts into quick finds:

1. **Map the file into filler-delimited sections first** — `python3 scripts/map_regions.py <save.fms>`.
   The save is cleanly split by long runs of `00`/`ff` filler; each section holds one kind of data. This
   shows you *where* to look and exposes regions we haven't mapped. Cross-check against `fmparser/regions.py`
   (whose windows are Bucaspor-tuned and often wrong for other careers).
2. **Find records structurally, never by absolute offset** — every window in `regions.py` **drifts** per
   save and per career (e.g. Frem's contract-expiry records sit at ~29–31M, nowhere near the Bucaspor
   `CONTRACT_LO=54M`). Locate a record by an embedded key (tid / uid / sid) plus a validating signature
   (a marker byte, a plausible year, an in-range value) and **validate every hit against the info spine**,
   exactly like the scrapers in `fmparser/staging.py`.
3. **Identify an unknown field with ground truth + contrast** — read the real values off an in-game
   screenshot for several players, then either (a) find the offset whose per-player value matches, or
   (b) find the offset that is *constant within a group and differs between groups* (how contract expiry
   was cracked: 6/2022 players vs 6/2023 players). **Money and dates are DISPLAYED ROUNDED** (value `1923`
   shows as "£2K"), so search a ±few-% band, not the exact number.
4. **When value-matching fails everywhere, DIFF TWO SAVES** — the definitive tool. Take two snapshots
   where the value changed for some players and find the field that changed iff the value did. Fields not
   stored adjacent to a player id (wages appear to live in a positional finance table) only fall to this.
5. **Encodings cheat-sheet:** money = raw currency (`2000` = £2K) but shown rounded; dates =
   `[day-of-year u16][year u16]` (see DOB in `staging.scrape_players`); seasons coded `1971 + n`.
   **Contract-detail record** (`staging.scrape_contracts`, section ~16–40M, `[tid u32][0x01][wage
   u16][6×00][expiry day-of-year u16][expiry year u16]`): **wage £/yr = `u16@+5` × ~520** (validated
   £15.5K–£17.75M, ±2%; the `0x01`-marked record is separate from the `0x87` status record), and
   **expiry = full date @+13** (some Danish deals expire 31 Dec, not 30 Jun — keep the day, not just
   the year).

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
- Season = **end-year** of the campaign (22/23 → 2023, Aus-FY style). **`phase` = the save's
  in-game DATE** ('YYYY-MM-DD'; match-less start saves → synthetic `YYYY-07-01`), so multiple
  in-season snapshots coexist and sort chronologically. Legacy stores may still hold the old words
  `start/mid/end` — they keep working (ordering treats them as epoch, before any real date).

## Common commands
```bash
uv sync                                                   # one-time env setup
uv run streamlit run dashboard/Home.py                    # dashboard (sidebar Career selector)
python3 scripts/discover_career.py <save.fms>             # find a new career's club tids
python3 extract.py <save.fms> --career <key> --label <l>  # extract (pure-stdlib, NOT uv)
uv run python load_duckdb.py output/<label> --db fm-<key>.duckdb   # season+phase(=in-game date) auto-derived
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
