# fmm-stats — guide for agents

Reverse-engineering **Football Manager Mobile 2022** `.fms` save files into a queryable DuckDB
store and a static web app. Read-only: nothing is ever written back to a save. The
[README](README.md) is the human introduction; this file is the working guide.

**A new player with no `fmm.toml` yet:** follow
[`.claude/skills/get-started/SKILL.md`](.claude/skills/get-started/SKILL.md), whatever agent you
are. It takes them from a save file to their stats site, and they don't need to code.

**Before anything else, read the user's own files if they exist** (both are gitignored):
- **`fmm.toml`** — their careers (managed club tid, rollover day, rating method), storage, site
  URL and **play-style switches**. Template: [`fmm.example.toml`](fmm.example.toml). The
  switches change how you must answer — see [Play style](#play-style-set-in-fmmtoml).
- **`CAREER.md`** — their notes on the career they are playing: the club, the tactic, house
  rules, what has happened so far. Treat it as the user's standing instructions.

## The three parts

| part | code | job | guide |
|---|---|---|---|
| **Parser** (extract) | `fmparser/`, `extract.py` | save bytes → `output/<label>/*.json`, one file per table as stored | [`fmparser/AGENTS.md`](fmparser/AGENTS.md) |
| **Stats** (load + transform) | `load_duckdb.py`, `fmstats/` | JSON → `raw` tables → dbt: `stg` → `int` → `mart` (`dim_*`/`fact_*`) → `site` | [`fmstats/AGENTS.md`](fmstats/AGENTS.md) |
| **Site** | `site/`, `site-worker/`, `scripts/export_data.py` | a phone-friendly view of the `site` marts | [`site/AGENTS.md`](site/AGENTS.md) |

Read the part's guide before changing it. The boundaries are enforced by
`tests/test_boundary.py`:
- **The parser is career-agnostic.** `fmparser/` imports neither duckdb, `fmstats`, `careers.py`
  nor `fmconfig.py`: a save reads the same whoever owns it. `extract.py` is a flat list of steps
  (`steps()`), one per table, in the order the save stores them, with a cursor that refuses a
  table found before the end of the one before it (`--no-cursor` skips that check).
- **The loader is glue.** `load_duckdb.py` writes JSON into `raw` tables plus the reference
  seeds only the parser can supply, and owns the career (`--career`, `careers.py`): it places
  each snapshot in its campaign by the career's rollover day, and checks the match table against
  the world fixture list.
- **`fmstats/` is a dbt project** and the semantic model ([`docs/data-model/`](docs/data-model/README.md))
  is its blueprint. Consumers (`export_data.py`, scripts, agents) read `site.*` and `mart.*`.
  dbt project variables are asserted against `fmparser` directly.

## Resuming work
**[`docs/TODO.md`](docs/TODO.md)** is the one doc to read to resume: where the project is, and
every open item. If it isn't in TODO, it isn't open. When you finish something, DELETE its entry
rather than marking it done. Everything else in `docs/` is reference, read when a task sends you
there.

## Answering a football question
Use the **`query-fm-data`** skill (`.claude/skills/`): it has the mart catalogue, the `ATTACH`
recipe and a runner for multi-statement queries. Three rules that make a query WRONG, not
imprecise:
- **Never use a bare `club_tid = <our tid>` filter for "our squad".** A lapsed loan can leave a
  departed player's `club_tid` on our club indefinitely. Use `mart.squad_membership` (the
  squad arrays): `WHERE is_current AND is_managed_club` for today (`team_tid` splits first team
  from reserves), `snapshot_date = '<date>'` for another snapshot, `team_tid = <tid>` for any
  other club.
- **dbt bakes the store's file name into every view as its catalog.** Open `fm-<career>.duckdb`
  under that file name, or `ATTACH` a copy `AS "fm-<career>"` and `USE` it; under any other name
  every view fails with `Catalog "fm-<career>" does not exist`.
- **Aggregate `fact_player_match` BEFORE joining dimensions** (aggregate first, name second).

## Play style (set in `fmm.toml`)
Some rules are the player's taste, not the project's. They live in `fmm.toml`, and the defaults
are the strict ones.

- **`[immersion] hide_ability`** (default `true`): never surface the raw current/potential
  ability (CA/PA) number. Reason with role ratings (Fit), percentiles, match stats and
  attributes. The **Level %ile** (`level_league`/`level_global` in
  `mart.fact_player_snapshot.positions`) is allowed: a tactic-agnostic percentile derived from
  CA. `mart.fact_player_snapshot` keeps CA/PA so percentiles can be derived, but presentation
  (`site.*`, the export, skill output) never carries it, and `export_data.py`'s
  `check_immersion()` fails the export on a raw-ability key at any depth. When `false`, the
  user is happy to see the number: you may quote it, and the export's guard is lifted.
- **Hidden/personality attributes:** say what the in-game report would say ("enigmatic",
  "inconsistent", "thrives in big matches"), not the number. Mapping and evidence:
  [`docs/agent-context/report-trait-lines.md`](docs/agent-context/report-trait-lines.md). Quote
  a hidden number only when asked.
- **House rules** (self-imposed constraints the game doesn't model, like the Danish squad
  registration rules in the web app) are described in `CAREER.md` when the user plays with them.

## Analysis rules
- **The exact XI on the day is not in the save, but each manager's preferences are.**
  `mart.fact_staff_snapshot` (via `mart.fact_staff_spell`, `role = 'manager' AND is_current`)
  carries each manager's preferred / attacking / defensive formation and a derived **Style**
  (Attacking / Normal / Defensive; [`docs/parser/staff.md`](docs/parser/staff.md)).
  Use it as the default for a scout report without asking first; the in-game scout's read (this
  week's injuries, suspensions) is an optional refinement.
- **Opponent names are resolved** (`mart.dim_person` names every club's players). Opponent
  attributes are model estimates (±1) except pace and physicals.
- **Rate an opponent with Level %ile, not Fit %ile.** Fit (`int.player_ratings` × familiarity)
  is the user's tactic's role-weighted rating, only a fair question for their own squad or a
  signing target. Level is tactic-agnostic.
- **A back line doesn't play a back line.** Compare our attack with their defence, their attack
  with our defence, midfield with midfield — not each unit with itself.
- **Quality is not output.** Read who has actually hurt us (`mart.fact_player_match` against
  us) next to the quality ranking; they often disagree.
- **Ratings are computed in two places that must agree to the last decimal:** the SQL
  (`int.player_ratings`, `fmstats/models/int/int_player_ratings.sql`) and the browser
  (`site/js/data.js`). A formula change lands in both.
- **The loan outlook is computed in the store** (`site.loan_outlook`) because it orders players
  by ability; the export ships only percentiles and ranks.
- **Weight sets** (`seeds/role_weights.csv`) rate every player in every role. A career's set is
  its `rating_method` in `fmm.toml`. `frem_minmax_4231` is DERIVED from match data by
  `scripts/derive_weight_set.py` (read its docstring before editing; a judgement call belongs in
  its `HELD` list with an argument, never as a hand edit to the CSV). `frem_attacking_ss` and
  `buca_433` are hand-built.

## Reference knowledge
[`docs/agent-context/`](docs/agent-context/MEMORY.md) holds findings accumulated while building
this — start at its `MEMORY.md` index. They are point-in-time notes: verify file/line claims
against the code. The ones to read before particular work:
- **save-format work:** [`fmparser/AGENTS.md`](fmparser/AGENTS.md) (method, feedback loop,
  *never validate a field by joining on it*), [`docs/table-framing.md`](docs/table-framing.md)
  (the save declares its own table sizes), [`docs/parser/savefile-map.md`](docs/parser/savefile-map.md) (the
  whole file, start to end, and the zstd archive at its tail), the table docs in
  [`docs/parser/`](docs/parser/) (each says where FMM22 departs from the FMM26 database
  layouts in `nyongrand/fmm-editor`; [`docs/parser-architecture.md`](docs/parser-architecture.md)
  Part 4 says how to use them).
- **attributes:** [`docs/ca-weighting.md`](docs/ca-weighting.md) (how each displayed attribute
  is recovered, the per-position CA weights, the 94.8% label ceiling) and
  [`docs/attribute-model.md`](docs/attribute-model.md) (the entangled-attribute decoder).
- **storage and devices:** [`multi-device-and-storage`](docs/agent-context/multi-device-and-storage.md).

## Toolchain
- **Everything runs under uv**: `uv sync` to set up, then `uv run python …`. Python 3.13+.
- **DuckDB is single-writer.** `scripts/dbopen.py`'s `open_readonly` (used by the export and
  publish scripts) copies a locked store to a temp file, and refuses when a `.wal` says a write
  is in flight.
- **Career selection:** `--career <key>`, else `FM_CAREER`, else `[careers] default` in
  `fmm.toml`. `FM_DUCKDB=<path>` points dbt at a specific store.
- **Season = end-year** of the campaign (22/23 → 2023). The new season starts on the career's
  rollover day. **`phase` = the save's in-game date** (`YYYY-MM-DD`, from the save header,
  never the last match's date), so several snapshots per season coexist and sort
  chronologically.

## Where things live
Nothing derived is in git, and nothing drawn from the game's database is either.

| tier | holds | where |
|---|---|---|
| code + build inputs | source, `seeds/`, docs, skills | git |
| saves + live state | `.fms.gz` saves, shortlist, saved scouts | object store (`[storage] r2_remote`, any rclone remote) or local |
| derived | `fm-<career>.duckdb`, `output/`, `site/api/` | local only — rebuild, never commit |
| published | the site's data, a compacted store copy | object store (`site-data/`), served by the Worker or `ATTACH`ed |

- **The store is disposable.** Rebuild it: `uv run python scripts/rebuild.py --career <key>`
  (~1 min per snapshot). `seeds/manifest.csv` is the recipe (which save produced which
  snapshot); regenerate it with `scripts/export_manifest.py` after an import.
  `raw.extracts.save_path` holds a basename — an absolute path silently makes the recipe
  machine-specific.
- **Saves live in `<saves_dir>/<career>/`** (`[storage] saves_dir`, default `~/fm-saves`), raw
  for parsing plus a verified `.gz` beside each (`scripts/archive_save.py`). Decompress first:
  `extract.py` must only ever see raw bytes.
- **Live state is one object per entry** (`state/<kind>/<id>.json`), because object stores have
  no append: adds are collision-free and sync is a plain union.

## Save and label naming
**`<career>-<YYYY-MM-DD>[-<tag>].fms`**, the date being the save's in-game date (= `phase`).
`extract.py` names `output/<label>/` after the save and `raw.extracts.label` uses the same
string. `scripts/archive_save.py <file> --career <key>` names a new save canonically from its
header. The optional `-<tag>` is a human note that nothing parses.

## Common commands
```bash
uv run python scripts/discover_career.py <save.fms> --write   # a new career -> fmm.toml
uv run python scripts/archive_save.py <save.fms> --career <key> [--upload]
uv run python extract.py <saves_dir>/<key>/<save>.fms     # -> output/<save name>
uv run python load_duckdb.py output/<save name>           # -> fm-<key>.duckdb (runs dbt)
uv run python scripts/export_manifest.py                  # refresh the rebuild recipe

# after editing fmstats/ models or the loader: rebuild models and run every dbt test
uv run python load_duckdb.py --refresh-only
cd fmstats && FM_DUCKDB=../fm-<key>.duckdb uv run dbt test --profiles-dir .

uv run python tests/run_tests.py                          # parser/unit tests (most need saves)
uv run python tests/test_boundary.py

uv run python scripts/export_data.py [--upload]           # -> site/api/*.json [-> R2]
uv run python -m http.server -d site 8000                 # preview
uv run python scripts/publish_duckdb.py --upload          # compacted store -> R2, for remote SQL
```
See [`docs/DEPLOY.md`](docs/DEPLOY.md) for the web app.

## House rules for code
- **Comments describe current reality**, not history: the binary layout, field semantics and
  engine behaviour as they are. No "we used to", "until now this was broken".
- **A no-op change to the data path must be a no-op export** — compare exports with
  `scripts/diff_exports.py`.
- **Never commit** saves, stores, extracts or exported data.

## A day-1 save
A save with no matches played has no leagues/competitions/results yet, so the vs-league and
scouting views stay empty until games are played; squad attributes and ratings work regardless.
