# fm-parser — project guide for agents

Reverse-engineering **Football Manager Mobile 2022** `.fms` save files into a queryable
DuckDB store + a Streamlit dashboard. **Career-aware:** the one genuinely career-specific
fact is the club you manage (its TID), which is how the store finds your squad's exact
names+attributes (each player in our squad arrays: the 7 plain attributes from his own record,
the rest from his latest scrapbook entry while it is at most a year old, `int.scrapbook_entries`). Careers are registered in **`careers.py`** and each has its own
DuckDB store (`fm-<key>.duckdb`):

| key | club | managed tid | reserve | store | state |
|---|---|---|---|---|---|
| `frem` | Boldklubben Frem (Denmark) | 346 | 7296 | `fm-frem.duckdb` | **active** |
| `bucaspor` | Bucaspor 1928 (Turkey) | 6567 | 11320 | `fm-buca.duckdb` | archived (`active=False`) |

**Only Frem is built.** Bucaspor's saves stay in the archive because they're the only
cross-career regression test the parser has — a decode that works on Denmark *and* Turkey is a
decode that generalises — but its store isn't rebuilt. `db.available_careers()` keys off whether
the store FILE exists, so not building one is all it takes to drop a career from the dashboard.
Rebuild it any time with `scripts/rebuild.py --career bucaspor --include-inactive`.

Extract takes no career (a save's tables read the same whatever career it is); the loader
does: `load_duckdb.py --career <key>`, else the career the store already records.
**Starting a new career:** run
`python3 scripts/discover_career.py <save.fms>` — it reads the "(Nickname)" the save header
opens with and ranks candidate clubs; add the winning first-team + reserve tids to
`careers.py`, then extract and load. All saves for a career must be that same career.

## Resuming work
**[`docs/TODO.md`](docs/TODO.md)** is the ONE doc you read to resume — where the project is
now, plus every outstanding thing in a single register. If it isn't in TODO, it isn't open.
Everything else in `docs/` is reference you read when a task sends you there. When you finish
something, DELETE its TODO entry rather than marking it done — otherwise that file rots into
another changelog, which is what retiring the four `*_HANDOFF.md` docs was undoing.

## Answering a quick football question — use the `query-fm-data` skill, not a local rebuild
The store is read directly with DuckDB (e.g. `python3 -c "import duckdb..."` or SQL CLI). The `query-fm-data` skill has the mart view catalogue and the ATTACH recipe. Two rules that make a query WRONG, not imprecise:
- **Never use a bare `club_tid = <our tid>` filter for "our squad"** — a lapsed loan can leave a departed player's `club_tid` on our club indefinitely (real save data). Use `mart.mart_squad_membership WHERE is_current AND is_managed_club` (or `site.site_squad`), or `mart.mart_squad_membership WHERE is_current AND (team_tid = <opp_tid> OR club_tid = <opp_tid>)` for an opponent club.
- **Macros do not resolve across an `ATTACH`** — `USE m` first and qualify nothing. Aggregate stats on `person_id` BEFORE joining person info.

## Three layers: extract, load, transform
- **`fmparser/` is the E** — save bytes to `output/<label>/*.json`, one file per table as
  stored. It imports neither duckdb, fmstats nor `careers.py`: a save reads the same whatever
  career it belongs to. `extract.py` is a flat list of steps (`steps()`), one per table, in
  the order the save stores them, with a cursor that refuses a table found before the end
  of the one before it (`--no-cursor` skips that check).
- **`load_duckdb.py` is the L** — JSON into `raw` tables, plus the reference seeds only the
  parser can supply (`raw.event_types`, the career keys in `raw.app_config`). It is glue:
  it may import both sides. It owns the career (`careers.py`, `--career`): it places each
  snapshot in its campaign by the career's rollover, and checks the match table against the
  world fixture list for our two clubs.
- **`fmstats/` is the T, and the semantic model
  ([`docs/data-model/`](docs/data-model/README.md)) is its foundation.** `fmstats/` is a
  **dbt** project building raw → stg → int → the model's `dim_*`/`fact_*` tables in `mart`,
  and presentation marts in `site.*`. Consumers (`export_data.py`, scripts, and agents)
  read directly from `site.*` and `mart.*`. **Read [`fmstats/CLAUDE.md`](fmstats/CLAUDE.md) before changing it** — it
  explains the schemas and the rules.

`tests/test_boundary.py` enforces the boundary rules: fmparser never imports DuckDB,
and dbt project variables in `fmstats/dbt_project.yml` are asserted directly against fmparser.

## The parser — read [`fmparser/CLAUDE.md`](fmparser/CLAUDE.md) before any save-format work
It holds the parser architecture pointer, the feedback loop (`tests/run_tests.py`, the `tests/assert_identical.py` acceptance gate) and the region-first reverse-engineering method, including **never validate a field by joining on it** and **prove a record's extent, not just its fields**. It loads automatically under `fmparser/`; read it explicitly when the work starts in `scripts/audit/` or a raw save.

## Read this first — accumulated project knowledge
The durable context an agent needs lives in **[`docs/agent-context/`](docs/agent-context/)**
(vendored from the assistant's memory so it travels with the repo). Start with
[`docs/agent-context/MEMORY.md`](docs/agent-context/MEMORY.md) — it indexes the rest:
- **multi-device-and-storage** — git / R2 / local tiers; the store is DISPOSABLE (rebuild, never commit). **Read before touching data layout.**
- **fm-parser-project** — the save-format reverse-engineering story + goals.
- **etl-duckdb-dashboard** — how the ETL + dashboard + `fmq.py` CLI + scouting tooling work. **The main reference.**
- **history-chain-pointers** — the history pool is a forest of linked lists; how the `P-38` player link works (its "stats on the previous row" rule was a framing error — see [`docs/parser-architecture.md`](docs/parser-architecture.md) shape B).
- **fmm-editor-record-comparison** — field-by-field map of our parsers vs the FMM26 database layouts (`nyongrand/fmm-editor`). **Read before decoding any new field** — it names the record you're in.
- **[`docs/ca-weighting.md`](docs/ca-weighting.md)** — how the save hands us each of the 23 displayed attributes (direct byte / plain-byte composite / CA-modelled), **FM's per-position CA weight tables** recovered from 155k snapshots, and the **94.8% label ceiling** every attribute-accuracy figure is measured against. Read before quoting an accuracy number or reasoning about what the game rewards in a position.
- **[`docs/attribute-model.md`](docs/attribute-model.md)** — the entangled-attribute decoder: CA enters as ONE shared per-player shift, not per attribute. Read before touching `raw.attribute_model`.
- **[`docs/table-framing.md`](docs/table-framing.md)** — the save declares its own table sizes (`[8xFF][count][records]`); the declared-vs-read audit, the five defects it found, and the inventory of walkable tables still to be named. **Read before walking a new table.**
- **[`docs/record-expansion.md`](docs/record-expansion.md)** — the 2026-09-16 parser expansion: the staff record (manager formation triple + Style), the club/stadium/city/nation records, and the traps it hit.
- **[`docs/save-archive.md`](docs/save-archive.md)** — the save's last ~1.3 MB is a **zstd archive** (`sicomps`, 159 named members, 6.6 MB decompressed), read by `fmparser/core/archive.py`. Its `fix_man.dat` is the **world fixture list with scores** — 26,954 rows, verified 282/285 against our own matches in both careers. Read before touching fixtures/results, and note the rule that found it: **rank an unknown region by BLOCK ENTROPY, never by printable fraction** — compressed bytes are 37% printable by construction (`scripts/audit/entropy_profile.py`).
- **[`docs/savefile-map.md`](docs/savefile-map.md)** — the whole-file map, start to end, with what is known, what is a fixed pool, what is wiped each July, and the ranked list of what is still unidentified.
- **squad-comparison-bridge**, **seyhun-attr-investigation**, **loan-status-unreliable**, **fmm-tactic-options** — specific findings; read when relevant.
- **light-results-rolling-buffer**, **master-schedule-plan** — both **SUPERSEDED 2026-09-17**. The ~47 MB region is the per-club **Club History record tables** (`fmparser/tables/club_records.py`, verified against in-game screenshots), NOT a list of simulated results, and nothing is deleted by a ring buffer. 55–58 MB is our own matches, the count-framed `fmparser/tables/matches.py`. Read [`docs/light-results-record.md`](docs/light-results-record.md) before doing anything with either.

These are point-in-time notes — verify file/line claims against the current code before asserting them as fact.

## The web app
`site/` is the static web app (Cloudflare Pages), the primary UI; Streamlit stays for what writes to DuckDB. **Before touching `site/`, read [`site/CLAUDE.md`](site/CLAUDE.md)** (sections, loan outlook, the Danish registration HOUSE RULE) and [`docs/DEPLOY.md`](docs/DEPLOY.md).

**`scripts/export_data.py` reads only the `site` schema** (`site.*`, `fmstats/models/site/`) — no `raw` table, no `main` view.
Add a field to the site by adding it to the `site` dbt models first (see
[`docs/plans/2026-10-03-site-marts.md`](docs/plans/2026-10-03-site-marts.md)). And because `site/api/*.json` is git-tracked and the export is deterministic, `git diff site/api`
is the regression test: a no-op export must produce a no-op diff.

## Toolchain
- **Run everything under uv** — `uv run python extract.py …`, `uv run python load_duckdb.py …`; numpy (used by `fmparser/tables/history.py`) is in the uv env, so no system python is needed.
- **Everything else is uv** — `uv sync` to set up; loader is `uv run python load_duckdb.py …`. If zstandard (the save archive's codec) is somehow missing, extract stops with a message rather than write empty fixture files (`--no-archive` goes on without them).
- **DuckDB is single-writer**: a process writing the store holds the lock. `scripts/dbopen.py`'s `open_readonly` (used by the publish/export scripts) copies the store to a temp file when it is locked, and refuses when a `.wal` says a write is in flight.
- **Career selection**: the dashboard shows a sidebar **Career** selector (defaults to the newest store); it repoints the DB + "us" club. Override anywhere with env `FM_CAREER=<key>` (and `FM_DUCKDB=<path>` to force a specific store).
- Season = **end-year** of the campaign (22/23 → 2023, Aus-FY style); the game's new season
  starts on the career's rollover day (Frem **30 June**, Bucaspor 20 June). **`phase` = the save's in-game DATE** ('YYYY-MM-DD', from the save's
  header title), so multiple
  in-season snapshots coexist and sort chronologically. Legacy stores may still hold the old words
  `start/mid/end` — they keep working (ordering treats them as epoch, before any real date).

## Where things live (and what is disposable)
Three tiers. **Nothing binary is shared**, and because each machine builds its own store there is
no multi-writer problem to solve:

| Tier | Holds | Where | Notes |
|---|---|---|---|
| Code + build inputs | source, `seeds/`, `seeds/manifest.csv` | **git** | small, text, mergeable |
| Archive + live state | `.fms.gz` saves, shortlist, scouts | **Cloudflare R2** | 271 MB of a 10 GB free tier |
| Derived | `fm-*.duckdb`, `output/` | **local only** | rebuild, never sync |
| Published | `site/` (the web app + small JSON) | **git** -> Cloudflare Pages | regenerated by `export_data.py`; see [`docs/DEPLOY.md`](docs/DEPLOY.md) |
| Published (big) | `site-data/all.json` (every player, 4 MB) | **R2**, streamed by a Pages Function | NEVER git — rewrites wholesale per import |
| Published (SQL) | `site-data/fm-<career>.duckdb` (run-length compacted, carries `raw.*`, `mart.*`, and `site.*`) | **R2**, `ATTACH`ed directly | NEVER git — `scripts/publish_duckdb.py`, an explicit step after an import |
| Published (queryable) | `site-data/fm-<career>.duckdb` (raw `ca`/`pa` included, unscrubbed) | **R2** (`site-data/`), read via DuckDB's native S3 protocol | for a remote agent: `ATTACH 's3://fmm-stats/site-data/fm-<career>.duckdb' (READ_ONLY)` over httpfs with a `CREATE SECRET (TYPE s3, ENDPOINT '<account-id>.r2.cloudflarestorage.com', …)` (not the `TYPE r2`/`ACCOUNT_ID` shorthand — it mis-routed to AWS S3 in testing), using the R2 creds a Claude Code session here already carries — arbitrary SQL, not just the fixed JSON shapes. Not served through the Worker (`*.workers.dev` is often unreachable from a restricted sandbox; the R2 endpoint usually isn't). Published by `scripts/publish_duckdb.py --upload`; see its docstring for the exact `ATTACH` syntax and the httpfs-install-over-HTTP gotcha. NEVER git. |

- **The store is NOT committed and must not be.** It reached 96 MiB (within 4 MiB of GitHub's hard
  per-file limit), rewrites wholesale on every import, and only gzips to 44 MB — 19 committed
  copies had already taken `.git` to 257 MB. Rebuild it instead:
  `uv run python scripts/rebuild.py --career frem` (~12 min for 12 snapshots).
- **`seeds/manifest.csv` is the recipe** — which save produced which snapshot. Regenerate with
  `scripts/export_manifest.py` after an import. `raw.extracts.save_path` holds a **basename**;
  an absolute path there silently makes the recipe machine-specific.
- **Saves live in `$FM_SAVES_DIR`** (default `~/fm-saves/<career>/`), raw for parsing plus a
  verified `.gz` beside each. `scripts/archive_save.py` does the move, the gzip, and a hash
  round-trip check. They compress 5–6.5x (mostly `00`/`ff` filler).
  **gzip cannot affect parsing** — decompression is byte-exact, so every offset in `regions.py`
  still lands. That only holds because we decompress *first*: mmap a `.gz` and every offset is
  garbage, so `extract.py` must never see anything but raw bytes.
- **Live state is `state/<kind>/<id>.json`**, mirrored to R2 by `dashboard/state.py` — the
  shortlist and saved scouts. One object per entry, deliberately: R2 has no append, so a shared
  file would mean read-modify-write and two devices adding at once would silently lose one. Adds
  are collision-free, a delete is an object delete, sync is a plain union (`rclone copy` both
  ways). Degrades to local-only with no rclone or no remote configured.
- `FM_SAVES_DIR`, `FM_R2_REMOTE` (default `r2:fmm-stats`), `FM_STATE_OFFLINE=1` to skip all
  syncing, `FM_STATE_TTL` for the pull throttle.

## Save + label naming convention
**`<career>-<YYYY-MM-DD>[-<tag>].fms`** — e.g. `frem-2023-07-02.fms`. The date is the save's
**in-game date**, which is exactly `phase`, half the store's natural key `(season, phase)`. So the
name states identity rather than nicknaming it: unique by construction, chronologically sortable,
career-scoped. `season` is omitted because it's derivable (a phase in July or later belongs to the
next campaign).

**The label is the same string** — `extract.py` names `output/<label>/` after the save, and
`raw.extracts.label` uses it, so save file, extract dir and DB label are one vocabulary.
`scripts/rebuild.py` refuses a manifest row whose label is not its save's name, or whose
season/phase the save's header does not give.

An optional `-<tag>` may follow the date as a human note (`frem-2023-07-02-window-open.fms`).
Nothing parses it, so it can never break a rebuild — only `<career>-<date>` carries meaning.

New saves: `scripts/archive_save.py <file> --career frem --upload` names it canonically on the
way in, from the in-game date in the save's own header title (`9/8/27 - Mr Manager (Frem)`,
`fmparser/tables/save_header.py`) -- a 0-match save included. `--phase` overrides it.
`extract.py` writes the same header date into `summary.json`; the loader takes `phase` from
it and `season` from it with the career's rollover day (`Career.rollover`: Frem 30 June,
Bucaspor 20 June). `scripts/canonicalise_names.py` (deleted; restore from git if needed) retro-fitted the
convention across saves, `.gz`, R2 objects, `output/` dirs, both stores' `save_path` + `label`,
and saved-scout keys — all five, because the manifest is generated FROM the store, so renaming
files without updating `raw.extracts` silently reverts the manifest on the next export.

Saves with no manifest row have no date and so no canonical name; they live in
`<career>/unfiled/`.

## Common commands
```bash
uv run python extract.py ~/fm-saves/frem/<save>.fms                # -> output/<save name>
uv run python load_duckdb.py output/<save name>                    # -> fm-frem.duckdb (runs dbt)
uv run python scripts/publish_duckdb.py --career frem --upload     # compacts & uploads store to R2
uv run python scripts/publish_mart.py --career frem --upload       # builds & uploads standalone mart to R2

# importing a NEW save
uv run python scripts/archive_save.py ~/Downloads/<save>.fms --career frem --upload
uv run python extract.py ~/fm-saves/frem/<save>.fms                # -> output/<save name>
uv run python load_duckdb.py output/<l> --db fm-frem.duckdb   # season+phase from the header + the store's career
uv run python scripts/export_manifest.py                  # refresh the rebuild recipe, then commit

uv run python scripts/discover_career.py <save.fms>       # find a new career's club tids

# after editing fmstats/ models or load_duckdb.py's VIEWS
uv run python load_duckdb.py --refresh-only --db fm-frem.duckdb
uv run python tests/test_boundary.py

# refreshing the web app (after an import) — see docs/DEPLOY.md
uv run python scripts/export_data.py --upload-all         # -> site/api/*.json; fails on a CA leak
uv run python scripts/export_site.py --out /tmp/new       # delegates to export_data.py
uv run python scripts/publish_duckdb.py --career frem --upload  # -> R2, for remote-agent SQL
uv run python -m http.server -d site 8000                # preview before pushing
git add site && git commit -m "site: <snapshot>" && git push   # Pages deploys on push
```

## House rules
- **Immersion: NEVER surface the raw CA/PA number.** Reason with weighted role ratings, `pos_index`, percentiles, match stats, and attributes only. **Allowed exception:** the **Level %ile** (`level_*` in `effective_table`) is a tactic-agnostic quality *percentile* derived from CA — the raw ability is `EXCLUDE`-d from presentation views so only the percentile ever leaves. The underlying warehouse facts (`mart.fact_player_snapshot`) retain CA/PA so percentiles can be derived, but presentation layers (`site.*`, `scripts/export_data.py`, `fmq` output) strictly exclude raw ability. **`scripts/export_data.py`'s `check_immersion()` enforces this for published JSON** — it
  parses every emitted file and fails the build on a raw-ability key at any depth, so anything new you add to the
  export is checked automatically.
- **The loan outlook is computed in the exporter** (`scripts/_export_db.py` `build_loans`),
  because it orders players by ability; the browser only draws it. Ranking counts a club's
  natural players only (familiarity 15+): a club with none for a slot is an open door, not a
  guess at who the AI would play out of position.
- **The web app computes ratings itself** (`site/js/data.js`) from attributes × role weights, so a
  change to the rating formula must land in BOTH the SQL (`v_player_ratings`) and the JS. They are
  verified equal to the last decimal over 36,920 combinations — keep it that way.
- **The exact XI on the day is NOT in the save — but the MANAGER's own preferences now are, and that's the baseline.** `mart.club_managers` names the opposition manager and carries his **preferred / attacking / defensive formation** and a derived **Style** (Attacking / Normal / Defensive, banded from a hidden attribute — see [`docs/record-expansion.md`](docs/record-expansion.md) §F), wired into `fmstats/scout.py`'s `opponent_manager()`/`scout_report()['manager']`. Use it as the default formation/style for a scout report **without asking the user first** — the Style bands are confirmed 7/7 in-game. Asking for the in-game scout's read is now an optional refinement (this week's actual team news — injuries, suspensions — which the manager record can't give you), not a prerequisite. Opponent **player names ARE resolved now** (the ETL id-resolver names every club — use real names alongside position + percentile). Opponent attributes are model estimates (±1) except pace/physicals.
- **Rating an opponent: Level %ile, not Fit %ile.** `pos_index`/`pctile_*` (`effective_table`) are OUR tactic's role-weighted Fit — how well an attribute set suits `frem_attacking_ss`, which is only a fair question for OUR OWN squad (we actually run it). `level_*` (Level %ile) is CA-derived and tactic-agnostic — the number to reach for when sizing up a stranger. `fmstats.scout.scout_report()`'s `key_players` and its `matchups` table (see next bullet) use `level_*`; only use `pos_index` for an opponent when the question really is "how would they fit our system" (e.g. a signing target).
- **A back line doesn't play a back line.** `scout_report()`'s `strength` table pairs each unit with itself (Defense-us vs Defense-them) — useful for "how strong is each line in isolation", but the contest that actually happens on the pitch is our attack vs their defense, their attack vs our defense, and midfield vs midfield. Use `matchups` (`matchup_table()`) for that reading, not `strength`.
- **Quality is not output.** `scout_report()['h2h_players']` is each opponent player's production in matches against us, with `still_there` for whether he is at the club now. Read it next to `key_players`: against OB the two men who hurt us most (5 goals; 11 key passes) sat at 53 and 23 on Level %ile, below six team-mates the ranking put first.
- We play a **4-2-3-1**, rated with **`frem_minmax_4231`** — the career's `rating_method` in `careers.py`, which the loader records in the store
(`raw.app_config.career_rating_method`) and `fmq scout` uses by default. **`frem_attacking_ss`** (the strikerless SS setup) is still `app_config.default_method`, the web app's display default (`seeds/config_bundle.json`), but not what we play. `buca_433` belongs to the archived Turkish career. **These two are the only weight-sets the store ships** (`seeds/role_weights.csv`): every player is rated in every role of every set, and the others were unused, so they are retired (`load_duckdb.RETIRED_METHODS` deletes them from an existing store too).
  **`frem_minmax_4231` is different in kind** — not hand-built from a tactic
  author's stated player traits but DERIVED from the match data by `scripts/derive_weight_set.py`,
  role by role, with every block that failed to beat a flat weighting left flat on purpose, and
  **every individual weight that failed to clear the evidence floor dropped or downgraded by
  `audit_block()`** — a block that beats flat does not license every line inside it. Two weights are
  held against the measurement on purpose and both are named in `HELD`. Read the script's docstring
  before editing it; hand-editing a derived set throws the audit trail away, and a
  judgement call belongs in `HELD` with its argument, not in the CSV.
- **Code comments describe current reality, not past parser history.** Comments must document the actual binary layout, field semantics, and game engine mechanics factually. Avoid narrative archaeology ("we didn't used to parse this", "until now this was broken", "for the life of this parser"). State what the data is so future readers have an authoritative, noise-free specification.

## Data setup on a fresh clone
`git clone` + `uv sync` gives you the code, skills, context, seeds and the rebuild manifest — but
**no data**. One command gets you the rest:

```bash
uv run python scripts/rebuild.py --career frem      # fetches saves from R2, extracts, loads
```

That needs `rclone` with a remote named per `FM_R2_REMOTE` (default `r2:fmm-stats`); without it,
drop the `.fms` files into `~/fm-saves/frem/` by hand and the same command works offline. Budget
~1 min per snapshot (~12 min for Frem's 12).

What's deliberately absent from git:
- **`.fms` saves** — in R2 (`saves/<career>/<name>.fms.gz`, 271 MB for 23 saves).
- **`fm-*.duckdb`** — derived; rebuild as above.
- **`output/`** (extract JSON, ~67 MB per snapshot) — regenerable; never committed.
- **`state/`** — the shortlist and saved scouts, mirrored from R2. Appears on first sync or first
  write.

Note: a **day-1 save** (0 matches) has no leagues/competitions/results yet, so the vs-league and
scouting views stay empty until games are played; squad attributes/ratings work regardless.
