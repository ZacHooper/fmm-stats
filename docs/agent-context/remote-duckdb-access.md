# Remote-agent SQL access to the DuckDB store

**Status (2026-08-24): pivoted from the Worker-forwarding design to a direct R2 `ATTACH`,
PR open, upload in progress.** PR: https://github.com/ZacHooper/fmm-stats/pull/1, branch
`claude/duckdb-r2-storage-d1rumw`.

## Why

The web app's JSON API (`site/api/*.json`, `/api/all`) only answers the fixed shapes
`export_data.py` chose to export. A remote agent session — no local store, no saves — that wants
an ad-hoc query has no way to do it. DuckDB can `ATTACH` a remote database file in **read-only**
mode via the `httpfs` extension, using range requests so it never downloads the whole file. That
gives a second, SQL-shaped access path alongside the JSON one, at the cost of one more R2 upload
step per import.

## Two ways to serve the file, and why the second one won

**v1 (original PR, now removed): a Worker route.** `worker/index.js` had a `/api/db?career=`
route forwarding `Range` headers to R2, so a caller would `ATTACH
'https://fmm-stats.zac-g-hooper.workers.dev/api/db?career=frem'`. This worked (verified via the
PR's Cloudflare branch preview) but turned out to be the wrong host for the actual target
audience: a Claude Code session running in a network-restricted sandbox — exactly the kind of
"remote agent with no local store" this feature is for — often has `*.workers.dev` blocked by
its environment's egress policy, with no way to fix that from inside the session.

**v2 (current): DuckDB `ATTACH`es the R2 object directly**, over DuckDB's native S3 protocol,
using the R2 credentials a Claude Code session in this project already carries as env vars
(`R2_ACCESS_KEY`/`R2_SECRET_ACCESS_KEY`/`R2_ACCOUNT_ID`):

```sql
INSTALL httpfs; LOAD httpfs;
CREATE SECRET r2 (TYPE r2, KEY_ID '<R2_ACCESS_KEY>', SECRET '<R2_SECRET_ACCESS_KEY>',
                   ACCOUNT_ID '<R2_ACCOUNT_ID>');
ATTACH 's3://fmm-stats/site-data/fm-frem.duckdb' AS fm (READ_ONLY);
SELECT * FROM fm.staging.players LIMIT 5;
```

This turned out to already work from a restricted sandbox: the account-scoped R2 endpoint
(`<account-id>.r2.cloudflarestorage.com`) was reachable in testing even though the bare
`r2.cloudflarestorage.com` and every `*.workers.dev` host were not — confirmed live (`rclone
lsd r2:fmm-stats` succeeded; `curl` to both blocked hosts got a proxy 403). The **one remaining
requirement** is that `extensions.duckdb.org` be reachable too, since `INSTALL httpfs` fetches
the extension binary from there on first use — that single host needs adding to a restricted
sandbox's network policy (an environment-level setting, not something fixable in-session; see
https://code.claude.com/docs/en/claude-code-on-the-web). `worker/index.js`'s `/api/db` route and
its `CAREER_RE` constant were removed since nothing serves this way anymore. `export_data.py`'s
`index.json["files"]["database"]` now points at the `s3://` key instead of the Worker URL.

**Data size was never the constraint** — the scrubbed store is ~90 MB, comfortably small for
almost any storage backend. A pivot to Postgres/Supabase was considered and rejected: it would
mean rewriting the loader, `dashboard/*.py`, and `fmq.py` (all speak DuckDB SQL directly today)
plus ongoing hosting, to fix what was actually just a two-domain gap in one sandbox's network
allowlist.

## What was built

- **`scripts/publish_duckdb.py`** — clones `fm-<career>.duckdb`, `UPDATE`s
  `staging.players SET ca = NULL, pa = NULL` in the clone (the only table/columns holding raw
  ability — see `load_duckdb.py`'s schema), `CHECKPOINT`s, and uploads the clone to R2 at
  `site-data/fm-<career>.duckdb` via `rclone copyto`. The live store is opened through
  `_dbopen.open_readonly` (same single-writer-safe fallback every other read-only tool uses) and
  is never itself touched.
- Docs updated for the `s3://` access path: `site/AGENTS.md` ("Prefer SQL?" section),
  `docs/DEPLOY.md` ("SQL access for a remote agent"), `CLAUDE.md` storage-tiers table,
  `export_data.py`'s `files.database` key.

## Why scrub instead of gate

The JSON export enforces "never surface raw CA/PA" per-field (`export_data.py`'s
`check_immersion`). Raw SQL access has no per-field filter to hide behind once it's shipped —
whoever holds the R2 credentials can `SELECT ca FROM staging.players` directly. So the rule is
enforced by scrubbing the *data* in the published copy instead of trying to gate the *query*.

## What's still open — for whoever picks this up next

1. **`rclone` + real R2 credentials are now confirmed working** in a Claude Code sandbox for
   this project (installed via `apt-get install rclone`; the account already carries
   `R2_ACCESS_KEY`/`R2_SECRET_ACCESS_KEY`/`R2_ACCOUNT_ID`/`R2_ENDPOINT` env vars). One
   installed-rclone quirk: the apt-packaged 1.60.1 throws `LoadCustomCABundleError` if
   `AWS_CA_BUNDLE` is set alongside this environment's proxy transport — worked around with a
   `/usr/local/bin/rclone` wrapper that drops that one env var before exec'ing the real binary
   (harmless outside this kind of proxied sandbox).
2. **`INSTALL httpfs` needs `extensions.duckdb.org` reachable.** Confirmed blocked in the
   sandbox that did this pivot (403 on CONNECT), same failure class as the `workers.dev` block
   this pivot was meant to avoid — but only one host to unblock instead of the whole Worker
   domain, and it's needed for `httpfs` regardless of which serving approach is used.
3. Once `extensions.duckdb.org` is reachable: run the `ATTACH` snippet above for real, confirm
   `ca`/`pa` come back `NULL`, and confirm a plain query (row counts, a known player) matches
   the live store.
4. Tick the checklist in the PR body once verified, and update this note.

See also: [Multi-device and storage](multi-device-and-storage.md) for the three-tier storage
model this extends, and `docs/DEPLOY.md` for the full deploy runbook.
