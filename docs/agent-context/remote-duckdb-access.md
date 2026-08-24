# Remote-agent SQL access to the DuckDB store

**Status (2026-08-24): design verified end-to-end in a restricted sandbox, PR open, waiting on
the actual store upload.** PR: https://github.com/ZacHooper/fmm-stats/pull/1, branch
`claude/duckdb-r2-storage-d1rumw`.

## Why

The web app's JSON API (`site/api/*.json`, `/api/all`) only answers the fixed shapes
`export_data.py` chose to export. A remote agent session — no local store, no saves — that wants
an ad-hoc query has no way to do it. DuckDB can `ATTACH` a remote database file in **read-only**
mode via the `httpfs` extension, using range requests so it never downloads the whole file. That
gives a second, SQL-shaped access path alongside the JSON one, at the cost of one more R2 upload
step per import.

## Two ways to serve the file, and why the second one won

**v1 (original PR, removed): a Worker route.** `worker/index.js` had a `/api/db?career=` route
forwarding `Range` headers to R2, so a caller would `ATTACH
'https://fmm-stats.zac-g-hooper.workers.dev/api/db?career=frem'`. This worked (verified via the
PR's Cloudflare branch preview) but was the wrong host for the actual target audience: a Claude
Code session in a network-restricted sandbox — exactly "a remote agent with no local store" —
commonly has `*.workers.dev` blocked by its environment's egress policy.

**v2 (current): DuckDB `ATTACH`es the R2 object directly**, over DuckDB's native S3 protocol,
using the R2 credentials a Claude Code session in this project already carries as env vars
(`R2_ACCESS_KEY`/`R2_SECRET_ACCESS_KEY`/`R2_ACCOUNT_ID`). **Verified working, full round trip,
in a restricted sandbox** (uploaded a probe file with `rclone`, read it back with a real DuckDB
`ATTACH`/`read_text` over `s3://`):

```sql
INSTALL httpfs; LOAD httpfs;
CREATE SECRET r2 (TYPE s3, KEY_ID '<R2_ACCESS_KEY>', SECRET '<R2_SECRET_ACCESS_KEY>',
                   ENDPOINT '<R2_ACCOUNT_ID>.r2.cloudflarestorage.com',
                   URL_STYLE 'path', REGION 'auto');
ATTACH 's3://fmm-stats/site-data/fm-frem.duckdb' AS fm (READ_ONLY);
SELECT * FROM fm.staging.players LIMIT 5;
```

`worker/index.js`'s `/api/db` route and its `CAREER_RE` constant were removed since nothing
serves this way anymore. `export_data.py`'s `index.json["files"]["database"]` now points at the
`s3://` key instead of the Worker URL.

**Data size was never the constraint** — the scrubbed store is ~90 MB, comfortably small for
almost any storage backend. A pivot to Postgres/Supabase was considered and rejected: it would
mean rewriting the loader, `dashboard/*.py`, and `fmq.py` (all speak DuckDB SQL directly today)
plus ongoing hosting, to fix what was actually just a network-allowlist gap.

## Three things that tripped this up, in order, each with a fix now baked into the docs

1. **`TYPE r2` + `ACCOUNT_ID` silently mis-routes.** The documented DuckDB shorthand for R2
   (`CREATE SECRET (TYPE r2, ACCOUNT_ID '...')`, which is supposed to auto-construct the
   `<account-id>.r2.cloudflarestorage.com` endpoint) instead sent the request to public AWS S3
   (`*.s3.us-east-1.amazonaws.com`), which then failed auth ("Invalid Access Key:
   proxy-injected" — this sandbox's egress proxy intercepts unauthenticated-looking AWS-shaped
   requests and injects its own placeholder credentials, which is a red herring; the real
   problem is the request went to AWS instead of R2 at all). **Fix: use `TYPE s3` with an
   explicit `ENDPOINT`, `URL_STYLE 'path'`, `REGION 'auto'`** — confirmed working. Every doc now
   uses this form instead of the shorthand.
2. **`*.workers.dev` is commonly blocked** in a network-restricted agent sandbox — this is what
   drove the v1→v2 pivot above. The account-scoped R2 endpoint
   (`<account-id>.r2.cloudflarestorage.com`) is not the same host and is commonly allowed, since
   it's the same one `rclone`/`publish_duckdb.py` already upload through.
3. **`INSTALL httpfs` defaults to plain HTTP** (`http://extensions.duckdb.org/…`, not
   `https://`), which can still 403 even once the HTTPS host is allowlisted — a network policy
   commonly allows a host by scheme, and only the HTTPS variant tends to get added. Confirmed in
   testing: `curl https://extensions.duckdb.org/...httpfs.duckdb_extension.gz` → 200, but
   `INSTALL httpfs` (which requests the plain-HTTP URL) → 403. **Fix: skip `INSTALL` and fetch
   the extension over HTTPS directly**, then load it from the local cache:
   ```bash
   v=$(python3 -c "import duckdb; print(duckdb.__version__)")
   curl -o /tmp/httpfs.gz "https://extensions.duckdb.org/v$v/linux_amd64/httpfs.duckdb_extension.gz"
   mkdir -p ~/.duckdb/extensions/v$v/linux_amd64
   gunzip -c /tmp/httpfs.gz > ~/.duckdb/extensions/v$v/linux_amd64/httpfs.duckdb_extension
   ```
   then `LOAD httpfs;` (no `INSTALL`) picks it up with zero network calls. (Trying
   `SET custom_extension_repository = 'https://...'` first — the obvious fix — doesn't work: it
   changes the expected filename and 404s instead.)

## What was built

- **`scripts/publish_duckdb.py`** — clones `fm-<career>.duckdb`, `UPDATE`s
  `staging.players SET ca = NULL, pa = NULL` in the clone (the only table/columns holding raw
  ability — see `load_duckdb.py`'s schema), `CHECKPOINT`s, and uploads the clone to R2 at
  `site-data/fm-<career>.duckdb` via `rclone copyto`. The live store is opened through
  `_dbopen.open_readonly` (same single-writer-safe fallback every other read-only tool uses) and
  is never itself touched. Docstring carries the full verified `ATTACH` syntax plus the httpfs
  install-over-HTTP workaround.
- Docs updated for the `s3://` access path: `site/AGENTS.md` ("Prefer SQL?" section),
  `docs/DEPLOY.md` ("SQL access for a remote agent"), `CLAUDE.md` storage-tiers table.

## Why scrub instead of gate

The JSON export enforces "never surface raw CA/PA" per-field (`export_data.py`'s
`check_immersion`). Raw SQL access has no per-field filter to hide behind once it's shipped —
whoever holds the R2 credentials can `SELECT ca FROM staging.players` directly. So the rule is
enforced by scrubbing the *data* in the published copy instead of trying to gate the *query*.

## What's still open — for whoever picks this up next

1. **The actual store hasn't been re-uploaded with this session's fixes verified against it
   yet** — the probe-file round trip confirms the R2 credential path works, but the real
   `fm-frem.duckdb` upload (`uv run python scripts/publish_duckdb.py --career frem --upload`)
   and a query against it (confirming `ca`/`pa` come back `NULL` on real data) is the last step.
2. Tick the checklist in the PR body once that's done, and update this note.

See also: [Multi-device and storage](multi-device-and-storage.md) for the three-tier storage
model this extends, and `docs/DEPLOY.md` for the full deploy runbook.
