# fm-parser — project guide for agents

Reverse-engineering **Football Manager Mobile 2022** `.fms` save files into a queryable
DuckDB store + a Streamlit dashboard. **Career-aware:** the one genuinely career-specific
fact is the club you manage (its TID), which is how the parser finds your squad's exact
names+attributes. Careers are registered in **`fmparser/careers.py`** and each has its own
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

Extract with `--career <key>`. **Starting a new career:** run
`python3 scripts/discover_career.py <save.fms>` — it reads the "(Nickname)" the save header
opens with and ranks candidate clubs; add the winning first-team + reserve tids to
`careers.py`, then extract. All saves for a career must be that same career.

## Resuming work
**[`docs/HANDOFF.md`](docs/HANDOFF.md)** is the current-state handoff — what's done, what's next,
what's outstanding, and where the football analysis left off. Read it before starting anything.

## Answering a quick football question — don't default to a local rebuild
A question like "who was our top scorer last season" does NOT need
`scripts/rebuild.py` (~1 min/snapshot, dozens of minutes total) if a local `fm-<career>.duckdb`
isn't already sitting there. **`ATTACH` the already-published R2 copy directly instead** — same
data, ready in seconds, no local store needed at all:
```sql
INSTALL httpfs; LOAD httpfs;
CREATE SECRET r2 (TYPE s3, KEY_ID '<R2_ACCESS_KEY>', SECRET '<R2_SECRET_ACCESS_KEY>',
                   ENDPOINT '<R2_ACCOUNT_ID>.r2.cloudflarestorage.com',
                   URL_STYLE 'path', REGION 'auto');
ATTACH 's3://fmm-stats/site-data/fm-frem-mart.duckdb' AS m (READ_ONLY);

-- "who was our top scorer" — note the name JOIN: mart fact tables are keyed by
-- person_id (a tid is a recycled slot), and names live on the spell tables.
SELECT any_value(s.name) AS name, ps.goals, ps.apps, ps.avg_rating
FROM m.mart.player_seasons ps
JOIN m.mart.at_club_spells s USING (person_id)
WHERE ps.season = 2024 AND ps.team_tid IN (SELECT club_tid FROM m.mart.managed_club)
GROUP BY ps.person_id, ps.goals, ps.apps, ps.avg_rating
ORDER BY ps.goals DESC LIMIT 5;
```
**Attach the mart object (~11 MB), not the full store (~34 MB)** — it holds the `mart` schema
as real tables with the correctness rules already applied, so a top-scorer query is one
`SELECT` rather than a re-derivation of latest-phase/person_id/minutes logic. Use the full
`site-data/fm-frem.duckdb` only when you need raw `staging` (typically world-wide current
attributes for recruitment).
`.claude/hooks/session-start.sh` sets up everything this needs (`rclone`, the `r2:` remote, the
`httpfs` extension) automatically on a Claude Code web session — see
[`docs/agent-context/remote-duckdb-access.md`](docs/agent-context/remote-duckdb-access.md) for
the full story and [`site/AGENTS.md`](site/AGENTS.md)'s "Query cookbook" for the two dedup traps
in `match_player_stats`/`players` that make a naive query wrong, not just imprecise. The only
reasons to fall back to a real local rebuild: you need raw `ca`/`pa` (NULLed in the R2 copy by
design — see the immersion house rule below) or data more recent than the last
`publish_duckdb.py --upload` (re-run after every import — not automatic).

## Read this first — accumulated project knowledge
The durable context an agent needs lives in **[`docs/agent-context/`](docs/agent-context/)**
(vendored from the assistant's memory so it travels with the repo). Start with
[`docs/agent-context/MEMORY.md`](docs/agent-context/MEMORY.md) — it indexes the rest:
- **multi-device-and-storage** — git / R2 / local tiers; the store is DISPOSABLE (rebuild, never commit). **Read before touching data layout.**
- **fm-parser-project** — the save-format reverse-engineering story + goals.
- **etl-duckdb-dashboard** — how the ETL + dashboard + `fmq.py` CLI + scouting tooling work. **The main reference.**
- **history-chain-pointers** — the history slab is a forest of linked lists; how the `P-38` player link works.
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
5. **A monotonic-looking `u32` column may be a POINTER, not a counter.** Big tables here are
   **linked lists**, not arrays: the field holds the *next row's index*, with `FFFFFFFF` = end of
   chain. On a fresh save the rows are contiguous so row `k` holds `k+1` and the field is
   indistinguishable from a counter — the two readings only diverge once the game starts appending
   into recycled slots. Tell them apart with the **in-degree test**: build the pointer graph and
   check `max in-degree == 1` and `#(in-degree-0 rows) == #(FFFFFFFF rows)`. If that holds it is a
   forest of chains, record starts are the in-degree-0 rows, and you need no delimiter heuristics
   at all. Beware the **column offset**: in career history a row's stats belong to the season on the
   PREVIOUS row (club+fee from row `k`, season+stats from row `k-1`). Always confirm a whole record
   against ground truth — an in-game TOTAL line is the cheapest check, since an off-by-one either
   double-counts a row or drops one.
6. **If a table has no id in it, look for the pointer running the OTHER way.** Career history holds
   no tid/sid/uid anywhere; the *attribute* record points at it (`u32 @ P-38`). Before concluding a
   join is unsolvable, search the file for the target's row index / offset as a u32 — one hit outside
   the table is the link. See `docs/IDS.md`.
7. **Encodings cheat-sheet:** money = raw currency (`2000` = £2K) but shown rounded; dates =
   `[day-of-year u16][year u16]` (see DOB in `staging.scrape_players`); seasons coded `1971 + n`.
   **Contract-detail record** (`staging.scrape_contracts`, section ~16–40M, `[tid u32][0x01][wage
   u16][6×00][expiry day-of-year u16][expiry year u16]`): **wage £/yr = `u16@+5` × ~520** (validated
   £15.5K–£17.75M, ±2%; the `0x01`-marked record is separate from the `0x87` status record), and
   **expiry = full date @+13** (some Danish deals expire 31 Dec, not 30 Jun — keep the day, not just
   the year).

## The web app (one UI for phone and desktop)
`site/` is a static single-page app on Cloudflare Pages — the primary UI, since Streamlit can't be
hosted without a server. Six sections collate the 13 dashboard pages: **Squad** (one configurable
table merging the squad list, Development and Player Stats), **Positions**, **Recruitment**
(search + shortlist + the capital rule), **Opposition**, **Matches**, **History**. It ships DATA
and computes on the client, so switching tactic re-rates every player with no rebuild.
**Streamlit stays** for what writes to DuckDB (Tactics, Config) and for Team Builder.
Read [`docs/DEPLOY.md`](docs/DEPLOY.md) before touching it.

## Skills (in `.claude/skills/`, auto-discovered)
- **import-fm-saves** — parse new `.fms` saves → load into the career's DuckDB store. Use when new saves appear.
- **scout-opponent** — technical-analyst opposition briefing (combines our data + the user's in-game scout report).
- **preseason-squad-review** — squad review at a season boundary.
- **developing-with-streamlit** — conventions for editing the dashboard.

## Toolchain
- **Run everything under uv** — `uv run python extract.py …`, `uv run python load_duckdb.py …`.
  The extractors are stdlib-only **except numpy** (`fmparser/history.py` scans the 265k-row history
  slab column-wise), and numpy is in the uv env, so there's nothing left that needs a system
  python. The old "extractors need bare `python3`" rule was a portability trap: it made a second
  machine depend on numpy being installed outside uv. Bare `python3` still works here if the system
  interpreter happens to have numpy.
- **Everything else is uv** — `uv sync` to set up; loader is `uv run python load_duckdb.py …`; CLI is `uv run python fmq.py …`; dashboard is `uv run streamlit run dashboard/Home.py`.
- **DuckDB is single-writer**: a running Streamlit holds the lock. For read-only CLI work either `pkill -f streamlit` first, or set `FM_DUCKDB_READONLY=1`, or query a `cp` of the store. The `fmq scout` command auto-copies when the DB is locked.
- **Career selection**: the dashboard shows a sidebar **Career** selector (defaults to the newest store); it repoints the DB + "us" club. Override anywhere with env `FM_CAREER=<key>` (and `FM_DUCKDB=<path>` to force a specific store).
- Season = **end-year** of the campaign (22/23 → 2023, Aus-FY style). **`phase` = the save's
  in-game DATE** ('YYYY-MM-DD'; match-less start saves → synthetic `YYYY-07-01`), so multiple
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
| Published (SQL) | `site-data/fm-<career>.duckdb` (~34 MB, run-length compacted) + `site-data/fm-<career>-mart.duckdb` (~11 MB, mart only) | **R2**, `ATTACH`ed directly | NEVER git — `scripts/publish_duckdb.py` / `publish_mart.py`, each an explicit step after an import |
| Published (queryable) | `site-data/fm-<career>.duckdb`, ca/pa NULLed | **R2** (`site-data/`), read via DuckDB's native S3 protocol | for a remote agent: `ATTACH 's3://fmm-stats/site-data/fm-<career>.duckdb' (READ_ONLY)` over httpfs with a `CREATE SECRET (TYPE s3, ENDPOINT '<account-id>.r2.cloudflarestorage.com', …)` (not the `TYPE r2`/`ACCOUNT_ID` shorthand — it mis-routed to AWS S3 in testing), using the R2 creds a Claude Code session here already carries — arbitrary SQL, not just the fixed JSON shapes. Not served through the Worker (`*.workers.dev` is often unreachable from a restricted sandbox; the R2 endpoint usually isn't). Published by `scripts/publish_duckdb.py --upload`; see its docstring for the exact `ATTACH` syntax and the httpfs-install-over-HTTP gotcha. NEVER git. |

- **The store is NOT committed and must not be.** It reached 96 MiB (within 4 MiB of GitHub's hard
  per-file limit), rewrites wholesale on every import, and only gzips to 44 MB — 19 committed
  copies had already taken `.git` to 257 MB. Rebuild it instead:
  `uv run python scripts/rebuild.py --career frem` (~12 min for 12 snapshots).
- **`seeds/manifest.csv` is the recipe** — which save produced which snapshot. Regenerate with
  `scripts/export_manifest.py` after an import. `staging.extracts.save_path` holds a **basename**;
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

**The label is the same string** — `output/<label>/` and `staging.extracts.label` both use it, so
save file, extract dir and DB label are one vocabulary instead of three.

An optional `-<tag>` may follow the date as a human note (`frem-2023-07-02-window-open.fms`).
Nothing parses it, so it can never break a rebuild — only `<career>-<date>` carries meaning.

New saves: `scripts/archive_save.py <file> --career frem --phase <YYYY-MM-DD> --upload` names it
canonically on the way in. The date **cannot** be derived for a 0-match save (no matches to date
it from), hence an argument rather than a probe. `scripts/canonicalise_names.py` retro-fits the
convention across saves, `.gz`, R2 objects, `output/` dirs, both stores' `save_path` + `label`,
and saved-scout keys — all five, because the manifest is generated FROM the store, so renaming
files without updating `staging.extracts` silently reverts the manifest on the next export.

Saves with no manifest row have no date and so no canonical name; they live in
`<career>/unfiled/`.

## Common commands
```bash
uv sync                                                   # one-time env setup
uv run streamlit run dashboard/Home.py                    # dashboard (sidebar Career selector)
uv run python scripts/rebuild.py --career frem            # rebuild the store from saves + manifest
uv run python fmq.py scout <team>                         # opposition briefing (auto-saves)

# importing a NEW save
uv run python scripts/archive_save.py ~/Downloads/<save>.fms --career frem --upload
uv run python extract.py ~/fm-saves/frem/<save>.fms --career frem --label <l>
uv run python load_duckdb.py output/<l> --db fm-frem.duckdb   # season+phase auto-derived
uv run python scripts/export_manifest.py                  # refresh the rebuild recipe, then commit

uv run python scripts/discover_career.py <save.fms>       # find a new career's club tids

# refreshing the web app (after an import) — see docs/DEPLOY.md
uv run python scripts/export_data.py --upload-all         # -> site/api/*.json; fails on a CA leak
uv run python scripts/publish_duckdb.py --career frem --upload  # -> R2, for remote-agent SQL
uv run python -m http.server -d site 8000                # preview before pushing
git add site && git commit -m "site: <snapshot>" && git push   # Pages deploys on push
```

## House rules
- **Immersion: NEVER surface the raw CA/PA number.** Reason with weighted role ratings, `pos_index`, percentiles, match stats, and attributes only. **Allowed exception:** the **Level %ile** (`level_*` in `effective_table`) is a tactic-agnostic quality *percentile* derived from CA — the raw ability is `EXCLUDE`-d from the query so only the percentile ever leaves. It sits next to the tactic **Fit %ile** (`pctile_*`). Keep raw `ca`/`pa` out of every surfaced frame; don't remove Level %ile thinking it breaks this
  rule. **`scripts/build_site.py` enforces this for published JSON** — it parses every emitted
  file and fails the build on a raw-ability key at any depth, so anything new you add to the
  export is checked automatically.
- **Depth-chart logic lives in `dashboard/positions.py`**, shared by the Streamlit page and the
  exporter. Change it there, not in either consumer, or the app and the dashboard start giving
  different verdicts.
- **The web app computes ratings itself** (`site/js/data.js`) from attributes × role weights, so a
  change to the rating formula must land in BOTH the SQL (`v_player_ratings`) and the JS. They are
  verified equal to the last decimal over 36,920 combinations — keep it that way.
- **Opponent tactics/formation are NOT in the save** — always ask the user for the in-game scout's formation + style. Opponent **player names ARE resolved now** (the ETL id-resolver names every club — use real names alongside position + percentile). Opponent attributes are model estimates (±1) except pace/physicals.
- Our tactic/method is **`frem_attacking_ss`** — the strikerless SS setup, and the dashboard default (`seeds/config_bundle.json`). `buca_433` belongs to the archived Turkish career. Other Frem weight-sets: `frem_counter`, `frem_gegenpress`, `frem_lowblock_overload`, `frem_game_state`.

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
