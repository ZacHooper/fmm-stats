# Deploying the static site

The site is **pre-rendered and committed**, so Cloudflare Pages has nothing to build — it just
serves `site/`. That's the whole reason for this design: no Node toolchain, no build step that
can break, no CI that needs access to the DuckDB store. The store never leaves the machine that
built the pages.

```
laptop:  import save  ->  scripts/build_site.py  ->  git commit + push
                                                        |
Cloudflare Pages (GitHub integration) --------------- deploys site/ in seconds
```

## One-time setup

### 1. Create the Pages project

Cloudflare dashboard → **Workers & Pages** → **Create** → **Pages** → **Connect to Git** →
pick `ZacHooper/fmm-stats`.

| Setting | Value | Why |
|---|---|---|
| Production branch | `main` | |
| Framework preset | **None** | |
| Build command | *(leave empty)* | the HTML is already in the repo |
| Build output directory | `site` | |

Give the project an **unguessable name** — it becomes `<name>.pages.dev`, and that URL is the
only thing standing between the site and the open internet. Nothing here is sensitive (it's a
football save, and the immersion rule keeps raw ability out of the JSON), but don't pick
`frem-stats` either.

`functions/` at the **repo root** is picked up automatically — it stays outside `site/` on
purpose, because `build_site.py --clean` wipes the output directory and would take the Function
with it.

### 2. Bind R2 so the shortlist can be written from the phone

Project → **Settings** → **Functions**:

- **R2 bucket bindings** — variable name `FM_STATE`, bucket `fmm-stats`. A native binding, so
  the Function needs no access key and there is no credential to leak or rotate.
- **Environment variables** → add a **secret** `FM_SHORTLIST_TOKEN`, e.g.
  `openssl rand -hex 24`. The Function refuses every request when it's unset — unconfigured
  fails closed rather than open.

Then open `/shortlist.html` on each device and paste the token once. It's kept in that
browser's localStorage, never in the page source: a committed secret is a published secret.

What the token buys, precisely: it stops someone who finds the URL from writing to the bucket.
It is **not** per-user auth, and it does reach the browser. Treat it as a write gate on a game
save.

### 3. Verify from the phone, on cellular

Turn wifi **off** first — that's the actual test. If it loads with both laptops shut, the
hosting problem is solved:

1. `https://<project>.pages.dev/` — the overview.
2. Scroll a depth chart sideways on **Positions**; the table should scroll inside its own box
   while the page itself doesn't move horizontally.
3. Add a player on **Shortlist**, then on a laptop `rclone copy r2:fmm-stats/state/shortlist
   state/shortlist` and confirm it appears in the Streamlit Squad Tool.

## Refreshing after an import

```bash
uv run python scripts/build_site.py          # newest snapshot of the default career
git add site && git commit -m "site: <snapshot>" && git push
```

Pages redeploys on push. `--season/--phase` pins an older snapshot, `--method` a different
weight-set, `--min-fam` the familiarity floor.

Preview locally before pushing:

```bash
uv run python -m http.server -d site 8000    # http://localhost:8000
```

The pages work fully; only `/api/shortlist` is missing, because that's a Pages Function and
there's no Function runtime in front of `http.server`.

## Giving Claude access

Point it at `https://<project>.pages.dev/api/index.json`. That file lists every other file, the
snapshot, the division ladder, and the caveats that matter for advice — including that
**opponent tactics and formation are not in the save**, so it has to ask you for the in-game
scout's read. From there `api/squad.json` and `api/club/<tid>.json` are enough for a scout
report or a transfer argument with both laptops off.

Scoped per club deliberately: the whole effective table is ~30k players and useless in a chat
context, while our squad plus one opponent is a couple of hundred KB.

## The cost to watch

Each build commits ~800 KB (620 KB of it the 36 club JSON files), and it changes wholesale
every snapshot because minified JSON deltas poorly. At roughly one import a week that's ~40 MB
of git a year — fine, but not free, and this repo has already been poisoned once by committing
derived binaries.

If it ever starts to bite, the escape hatch is to stop committing the output: add `site/` to
`.gitignore` and deploy by direct upload instead —

```bash
npx wrangler pages deploy site --project-name <name>
```

That trades the "no Node toolchain" property for a git history that stays small. Don't do both.
