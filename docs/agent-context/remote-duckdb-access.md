# Remote-agent SQL access to the DuckDB store

**Status (2026-08-24): implemented and pushed, PR open, NOT merged, NOT verified against real
R2.** PR: https://github.com/ZacHooper/fmm-stats/pull/1, branch `claude/duckdb-r2-storage-d1rumw`.

## Why

The web app's JSON API (`site/api/*.json`, `/api/all`) only answers the fixed shapes
`export_data.py` chose to export. A remote agent session — no local store, no saves, nothing
but a URL — that wants an ad-hoc query has no way to do it. DuckDB can `ATTACH` a remote
database file over plain HTTP(S) in **read-only** mode via the `httpfs` extension, using range
requests so it never downloads the whole file. That gives a second, SQL-shaped access path
alongside the JSON one, at the cost of one more R2 upload step per import.

## What was built

- **`scripts/publish_duckdb.py`** — clones `fm-<career>.duckdb`, `UPDATE`s
  `staging.players SET ca = NULL, pa = NULL` in the clone (the only table/columns holding raw
  ability — see `load_duckdb.py`'s schema), `CHECKPOINT`s, and uploads the clone to R2 at
  `site-data/fm-<career>.duckdb` via `rclone copyto`. The live store is opened through
  `_dbopen.open_readonly` (same single-writer-safe fallback every other read-only tool uses) and
  is never itself touched. Verified locally against a synthetic store: `ca`/`pa` come back
  `NULL` in the copy, source store untouched.
- **`worker/index.js`** — new `/api/db?career=<key>` route. Forwards the incoming `Range`
  header straight to R2 via `env.FM_STATE.get(key, { range: request.headers })` (R2 parses the
  header itself), answers `HEAD` (httpfs uses that first to learn the file size), returns 206
  with `Content-Range` for a ranged request. Validated with `npx wrangler deploy --dry-run` only
  — bundles clean, binding present — **never exercised against a live object**, since no object
  has been uploaded yet.
- Docs updated: `site/AGENTS.md` ("Prefer SQL?" section), `docs/DEPLOY.md` ("SQL access for a
  remote agent"), `CLAUDE.md` storage-tiers table, `index.json`'s `files.database` key.

## Why scrub instead of gate

The JSON export enforces "never surface raw CA/PA" per-field (`export_data.py`'s
`check_immersion`). Raw SQL access has no per-field filter to hide behind once it's shipped —
whoever holds the URL can `SELECT ca FROM staging.players` directly. So the rule is enforced by
scrubbing the *data* in the published copy instead of trying to gate the *query*.

## Usage (once published)

```sql
INSTALL httpfs; LOAD httpfs;
ATTACH 'https://fmm-stats.zac-g-hooper.workers.dev/api/db?career=frem' AS fm (READ_ONLY);
SELECT * FROM fm.staging.players LIMIT 5;
```

## What's still open — for whoever picks this up next

1. **Nothing has actually been uploaded to R2 yet.** `/api/db` will 404 until
   `scripts/publish_duckdb.py --career frem --upload` runs successfully once.
2. **This session's sandbox did not have working R2 credentials.** `rclone` was not on PATH (an
   unrelated `/opt/rclone/rclone-filestore` binary exists but isn't the CLI the scripts shell
   out to). `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` were present but only **14 characters
   each** — real R2 S3-compatible keys are 32-char hex, so these read as placeholders, not
   genuine credentials — and no R2 endpoint (`AWS_ENDPOINT_URL` or similar) was set, so even
   valid-looking keys would have nowhere to point (R2 needs
   `https://<account-id>.r2.cloudflarestorage.com`, never guess the account id). The user said
   to reset the environment rather than chase this further in-session.
3. **Before trusting new creds in a future session**, sanity-check them the same way: key
   length, an actual endpoint var or rclone remote config (`rclone config show` — do not print
   secret values, only structure/lengths), and a cheap connectivity probe (e.g.
   `rclone lsd r2:fmm-stats` or `rclone about r2:`) before running the real upload.
4. Once upload works: confirm `/api/db` end to end — `curl -I .../api/db?career=frem` for
   `200`/`accept-ranges: bytes`, then a real `duckdb` client running the `ATTACH` snippet above,
   checking `ca`/`pa` really do come back `NULL`. The Worker route only ships live once PR #1 is
   merged and deployed (Cloudflare Workers Builds deploys on push to the repo's default branch —
   see `docs/DEPLOY.md`); testing the route pre-merge needs a manual `wrangler deploy` from a
   branch checkout, or waiting for merge.
5. Tick the checklist in the PR body once verified, and update this note.

See also: [Multi-device and storage](multi-device-and-storage.md) for the three-tier storage
model this extends, and `docs/DEPLOY.md` for the full deploy runbook.
