# Deploying the app

One app for phone and desktop. It's a **static single-page app** — no server, no build step, no
Node toolchain — that ships the data and computes on the client. Cloudflare Pages serves the
files; two Pages Functions handle the two things files can't do.

```
laptop:  import save  ->  export_data.py  ->  git commit + push   (small JSON, the app)
                                     \
                                      -> R2: site-data/all.json   (4 MB, never in git)
                                                        |
Cloudflare Pages (GitHub integration) ------------- deploys site/ in seconds
```

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

**The 4 MB every-player file is not in git.** It rewrites wholesale each import and minified JSON
deltas badly; committing it would repeat the mistake that took this repo's `.git` to 257 MB with
the DuckDB stores in it. It lives in R2 and is streamed by a Function, so only a global search
pays for it. Everything else is 125 KB gzipped and committed.

| File | Size (gzip) | Where | When it's fetched |
|---|---|---|---|
| `api/core.json` | 92 KB | git | on boot — our clubs + the whole division ladder |
| `api/matches.json` | 19 KB | git | Matches / History / any match column |
| `api/squad.json` | 8 KB | git | growth trajectories + career history |
| `api/positions.json` | 5 KB | git | the position review |
| `api/index.json` | 1 KB | git | manifest |
| `api/all.json` | 1.3 MB | **R2** | only on "load every player" |

## One-time setup

### 1. Create the Pages project

Cloudflare dashboard → **Workers & Pages** → **Create** → **Pages** → **Connect to Git** →
`ZacHooper/fmm-stats`.

| Setting | Value |
|---|---|
| Production branch | `main` |
| Framework preset | **None** |
| Build command | *(leave empty)* — the app is already in the repo |
| Build output directory | `site` |

Pick an **unguessable project name**: it becomes `<name>.pages.dev` and that URL is the only
thing between the site and the open internet. Nothing here is sensitive, but don't pick
`frem-stats`.

`functions/` sits at the **repo root**, outside `site/`, and is picked up automatically.

### 2. Bind R2

Project → **Settings** → **Functions**:

- **R2 bucket binding** — variable `FM_STATE`, bucket `fmm-stats`. A native binding, so there is
  no access key to leak or rotate. Both Functions use it: `api/all` streams the player file,
  `api/shortlist` reads and writes shortlist entries.
- **Environment variable (secret)** — `FM_SHORTLIST_TOKEN`, e.g. `openssl rand -hex 24`. The
  shortlist Function refuses every request when it's unset: unconfigured fails closed.

Then open **Recruitment → Shortlist** on each device and paste the token once. It's kept in that
browser's localStorage, never in the page source. What it buys, precisely: it stops someone who
finds the URL from writing to your bucket. It is not per-user auth and it does reach the browser.
Reads of the player data are deliberately unauthenticated — requiring a token there would mean
shipping it to every visitor just to look.

### 3. Verify from the phone, on cellular

Turn wifi **off** — that's the actual test.

1. `https://<project>.pages.dev/` loads with both laptops shut.
2. **Squad** → *Columns* → add `Pace` and `G/90`; sort by tapping a header. Wide tables scroll
   inside their own box while the page doesn't move sideways.
3. Change **tactic** in the header — every rating and Fit %ile changes, Level %ile doesn't.
4. **Recruitment → Search the save → Load every player** — proves the R2 Function works.
5. Add a shortlist entry, then on a laptop `rclone copy r2:fmm-stats/state/shortlist
   state/shortlist` and confirm it shows in the Streamlit Squad Tool.

## Refreshing after an import

```bash
uv run python scripts/export_data.py --upload-all
git add site docs && git commit -m "site: <snapshot>" && git push
```

`--upload-all` pushes the every-player file to R2; drop it to skip (the app then falls back to
whatever is already in the bucket). `--skip-all` skips generating it entirely for fast iteration.
Other flags: `--season/--phase` to pin an older snapshot, `--method` for the default tactic,
`--min-fam` for the familiarity floor on the position review.

Preview locally before pushing:

```bash
uv run python -m http.server -d site 8000     # http://localhost:8000
```

Everything works except the two Functions, so the shortlist shows "offline" and global search
falls back to `site/api/all.json` on disk. That fallback is why the file is still written locally.

## What is still dashboard-only

Not a phone problem — these genuinely need the local DuckDB store, because they **write** to it:

- **Tactics** — editing a weight-set writes to `staging.role_weights`. Change it in the dashboard
  (or `seeds/role_weights.csv`) and re-export; the app reads all seven tactics but can't add one.
- **Config** — the familiarity curve and default tactic write to `staging.app_config`.

And one that could be ported but isn't yet:

- **Team Builder** — assembling an XI slot-by-slot with live weight tuning. Everything it needs is
  already client-side (attributes and weights are both loaded), so it's a view to write, not a
  data problem.
