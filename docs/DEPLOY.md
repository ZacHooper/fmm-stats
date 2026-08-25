# Deploying the app

**Live at <https://fmm-stats.zac-g-hooper.workers.dev>.**

One app for phone and desktop. It's a **static single-page app** — no server, no build step, no
Node toolchain — that ships the data and computes on the client. It runs as a **Cloudflare Worker
with static assets**: files in `site/` are served directly, and `worker/index.js` handles the two
things files can't do.

> **Not Pages.** This started as a Pages project with a `functions/` directory; that directory is
> not read by the Workers runtime, so both endpoints 404'd with an empty body (the asset handler's
> 404, not ours). The logic now lives in `worker/index.js` and `functions/` is gone. If you ever
> move to a real Pages project, that's the thing to reinstate.

```
laptop:  import save  ->  export_data.py  ->  git commit + push   (small JSON, the app)
                                     \
                                      -> R2: site-data/all.json   (4 MB, never in git)
                                                        |
Cloudflare Workers Builds (GitHub) ---------------- deploys site/ + worker/ in seconds
```

**Routing.** Cloudflare serves a matching static asset *first* and only invokes the Worker when
nothing matches. So `api/index.json`, `api/core.json` and the rest come straight off disk, and
only `/api/all` and `/api/shortlist` — which have no file behind them — reach `worker/index.js`.
`not_found_handling` is `"none"` on purpose: the app is hash-routed (`#/squad`), so every real
path is a real file, and an SPA rewrite would return `index.html` for the API paths instead of
letting them through.

## Why it's built this way

**Ratings are computed in the browser.** A role rating is `SUM(attribute × weight)` and the whole
weight table is 5 KB, so the app ships attributes plus weights rather than precomputed ratings.
That's smaller than shipping ratings for seven tactics *and* strictly more capable: switching
tactic re-rates every player instantly, offline, with no rebuild. Verified against the database —
36,920 (player, tactic, role) combinations, zero difference.

**Ability percentiles are not computed in the browser.** They derive from the game's overall
ability number, and that number never leaves the machine that runs the export (house rule). So
`Level %ile` arrives precomputed and is the only ability that exists client-side. The exporter
parses every file it writes and fails the build on a raw-ability key at any depth.

**The exporter reads only the `mart` schema.** Since 2026-08-25 `export_data.py` touches no
`staging` table and no `main` view: the four snapshot-shape rules (latest-phase-per-season,
snapshot-scoped joins, `person_id` not `tid`, 255-sentinel minutes) live in `fmparser/mart.py`
and both the site and the Streamlit dashboard read them from there. Practical consequence: a
change to `mart.py` does not reach a store until something re-runs it, so
`uv run python load_duckdb.py --refresh-only --db fm-frem.duckdb` after editing it (an import
does this anyway).

`site/api/*.json` is git-tracked and the export is deterministic, which makes
`git diff site/api` the regression test for any change to the data path — a no-op export must
produce a no-op diff.

**The 4 MB every-player file is not in git.** It rewrites wholesale each import and minified JSON
deltas badly; committing it would repeat the mistake that took this repo's `.git` to 257 MB with
the DuckDB stores in it. It lives in R2 and is streamed by a Function, so only a global search
pays for it. Everything else is 125 KB gzipped and committed.

| File | Size (gzip) | Where | When it's fetched |
|---|---|---|---|
| `api/core.json` | 92 KB | git | on boot — our clubs + the whole division ladder |
| `api/clubs.json` | 66 KB | git | resolving a club name/tid outside the ladder |
| `api/matches.json` | 19 KB | git | Matches / History / any match column |
| `api/squad.json` | 8 KB | git | growth trajectories + career history |
| `api/positions.json` | 5 KB | git | the position review |
| `api/index.json` | 1 KB | git | manifest |
| `api/all.json` | 1.3 MB | **R2** | "load every player"; `?club=`/`?tid=` filters the same file server-side to a few KB |
| `fm-<career>.duckdb` (scrubbed) | ~34 MB | **R2** | `site-data/fm-<career>.duckdb` — a remote agent `ATTACH`es this over DuckDB's native S3 protocol (R2 creds) and runs arbitrary SQL instead of the fixed shapes above |
| `fm-<career>-mart.duckdb` | ~24 MB | **R2** | `site-data/fm-<career>-mart.duckdb` — the `mart` schema as real tables. Prefer this for analysis: it is what generates the files above, so anything the site shows is answerable from it |

## One-time setup

### 1. Configuration is in the repo, not the dashboard

`wrangler.jsonc` declares everything except the secret: the Worker name, the entrypoint, the
assets directory, and the R2 binding. **With that file present it is the source of truth** — the
same fields become read-only in the dashboard, which is the point: the deploy config is versioned
with the code instead of living in a UI nobody can diff.

Validate a change without deploying:

```bash
npx wrangler deploy --dry-run          # checks config + bindings, bundles, uploads nothing
```

### 2. The one thing that must stay in the dashboard

**`FM_SHORTLIST_TOKEN`** — a secret, so it is deliberately *not* in `wrangler.jsonc`; a secret in
the repo is a published secret. Set it once:

```bash
npx wrangler secret put FM_SHORTLIST_TOKEN     # or Settings -> Variables and Secrets
openssl rand -hex 24                           # to generate one
```

The shortlist endpoint refuses every request while it's unset — unconfigured fails closed, never
open. The R2 binding (`FM_STATE` → `fmm-stats`) needs no credentials at all; that's the advantage
of a native binding over an access key.

Then open **Recruitment → Shortlist** on each device and paste the token once. It's kept in that
browser's localStorage, never in the page source. What it buys, precisely: it stops someone who
finds the URL from writing to your bucket. It is not per-user auth and it does reach the browser.
Reads of the player data are deliberately unauthenticated — gating them would mean shipping the
token to every visitor just to look.

Then open **Recruitment → Shortlist** on each device and paste the token once. It's kept in that
browser's localStorage, never in the page source. What it buys, precisely: it stops someone who
finds the URL from writing to your bucket. It is not per-user auth and it does reach the browser.
Reads of the player data are deliberately unauthenticated — requiring a token there would mean
shipping it to every visitor just to look.

### 3. Verify from the phone, on cellular

Turn wifi **off** — that's the actual test.

1. <https://fmm-stats.zac-g-hooper.workers.dev> loads with both laptops shut.
2. **Squad** → *Columns* → add `Pace` and `G/90`; sort by tapping a header. Wide tables scroll
   inside their own box while the page doesn't move sideways.
3. Change **tactic** in the header — every rating and Fit %ile changes, Level %ile doesn't.
4. **Recruitment → Search the save → Load every player** — proves the R2 Function works.
5. Add a shortlist entry, then on a laptop `rclone copy r2:fmm-stats/state/shortlist
   state/shortlist` and confirm it shows in the Streamlit Squad Tool.

## Refreshing after an import

```bash
uv run python scripts/export_data.py --upload-all
uv run python scripts/publish_duckdb.py --career frem --upload   # full copy, ~34 MB — see below
uv run python scripts/publish_mart.py   --career frem --upload   # analysis copy, ~24 MB
git add site docs && git commit -m "site: <snapshot>" && git push
```

**Neither R2 database is refreshed by an import.** `load_duckdb.py` writes the LOCAL store
only; the two `publish_*` scripts are separate objects in R2 and separate commands — running
one does not update the other. Skip them and a remote agent's `ATTACH` silently reads the
previous snapshot, which looks like a working query returning stale answers.

`--upload-all` pushes the every-player file to R2; drop it to skip (the app then falls back to
whatever is already in the bucket). `--skip-all` skips generating it entirely for fast iteration.
Other flags: `--season/--phase` to pin an older snapshot, `--method` for the default tactic,
`--min-fam` for the familiarity floor on the position review.

## SQL access for a remote agent

The JSON API only ever answers the fixed shapes `export_data.py` chose to export. A remote agent
session — no local store, no saves — that wants an arbitrary query instead can `ATTACH` the
actual database straight from R2, over DuckDB's native S3 protocol, using the same R2
credentials a Claude Code session in this project already carries as env vars:

```sql
INSTALL httpfs; LOAD httpfs;
CREATE SECRET r2 (TYPE s3, KEY_ID '<R2_ACCESS_KEY>', SECRET '<R2_SECRET_ACCESS_KEY>',
                   ENDPOINT '<R2_ACCOUNT_ID>.r2.cloudflarestorage.com',
                   URL_STYLE 'path', REGION 'auto');
ATTACH 's3://fmm-stats/site-data/fm-frem.duckdb' AS fm (READ_ONLY);
SELECT * FROM fm.staging.players LIMIT 5;
```

Use `TYPE s3` with an explicit `ENDPOINT`, not the `TYPE r2`/`ACCOUNT_ID` shorthand — in
testing from a network-proxied sandbox, the shorthand silently fell through to public AWS S3
(`*.s3.us-east-1.amazonaws.com`, then failed auth there) instead of routing to R2.

DuckDB's httpfs extension does this with range requests, so it never pulls the whole ~90 MB file.
**Deliberately not served through the Worker** (an earlier version of this had a `/api/db` route
forwarding `Range` headers to R2): a network-restricted agent sandbox often can't reach
`*.workers.dev`, but the account-scoped R2 endpoint above
(`<account-id>.r2.cloudflarestorage.com`) usually *is* reachable, since it's the same host
`rclone` and `publish_duckdb.py` already upload through.

`extensions.duckdb.org` must be reachable too, to install `httpfs` itself — add it to the
sandbox's network policy if `INSTALL httpfs` fails outright. One further wrinkle seen in
testing: DuckDB's installer defaults to a **plain HTTP** URL (`http://extensions.duckdb.org/…`),
which can still 403 even once the HTTPS host is allowed, since a network policy commonly
allowlists by host *and scheme*. If so, skip `INSTALL` and fetch the extension over HTTPS
yourself — see `scripts/publish_duckdb.py`'s docstring for the exact `curl`/`gunzip` commands
that drop it straight into DuckDB's extension cache, after which `LOAD httpfs` alone works.

**What's published is a scrubbed copy, not the live store.** `scripts/publish_duckdb.py` clones
`fm-<career>.duckdb`, NULLs `staging.players.ca`/`.pa` (raw ability) in the clone, then uploads
that to `site-data/fm-<career>.duckdb`. The JSON export enforces the same immersion house rule
per-field (see CLAUDE.md); raw SQL access has no per-field filter to hide behind, so this is
enforced by scrubbing the data itself instead. The live store is opened read-only and is never
touched — same single-writer-safe fallback `export_data.py` uses, so this is safe to run with a
dashboard open.

Needs `rclone` configured against the `r2:` remote to actually upload (see the main README /
CLAUDE.md for setup); without it, `--upload` fails with a clear message and `--out <path>` still
lets you produce and inspect the scrubbed copy locally.

Preview locally before pushing:

```bash
uv run python -m http.server -d site 8000     # http://localhost:8000
```

Everything works except the two Worker endpoints, so the shortlist shows "offline" and global
search falls back to `site/api/all.json` on disk. That fallback is why the file is still written
locally even though it's gitignored.

One wrinkle if you ever run `npx wrangler deploy` from the laptop rather than letting Cloudflare
build from git: it reads `site/` off disk, so it would upload that 4 MB `all.json` as a static
asset. Harmless — nothing requests it by that path — but wasteful. `.assetsignore` does *not*
exclude it (tested: the file is uploaded and the exclusion ignored), so just prefer the git build.

## What is still dashboard-only

Not a phone problem — these genuinely need the local DuckDB store, because they **write** to it:

- **Tactics** — editing a weight-set writes to `staging.role_weights`. Change it in the dashboard
  (or `seeds/role_weights.csv`) and re-export; the app reads all seven tactics but can't add one.
- **Config** — the familiarity curve and default tactic write to `staging.app_config`.

And one that could be ported but isn't yet:

- **Team Builder** — assembling an XI slot-by-slot with live weight tuning. Everything it needs is
  already client-side (attributes and weights are both loaded), so it's a view to write, not a
  data problem.
