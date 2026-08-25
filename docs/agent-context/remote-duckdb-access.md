# Remote-agent SQL access to the DuckDB store

**Status (2026-08-24): DONE and verified end-to-end against the real store, PR open awaiting
merge.** PR: https://github.com/ZacHooper/fmm-stats/pull/1, branch
`claude/duckdb-r2-storage-d1rumw`. Ran the `ATTACH` snippet below against
`site-data/fm-frem.duckdb` for real: 484,746 player rows, 0 rows with non-NULL `ca`/`pa`
(386,038 scrubbed on publish), 32 tables visible.

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

### Which object to ATTACH (updated 2026-08-25)

Two are published, and for ANALYSIS you almost always want the smaller one:

| object | size | holds | use it when |
|---|---:|---|---|
| `site-data/fm-frem-mart.duckdb` | **~24 MB** | the `mart` schema only, as real tables | analysing the career — squads, growth, spells, match facts, clubs, leagues, current attributes |
| `site-data/fm-frem.duckdb` | **~34 MB** | full `staging` (+ `mart` views) | you need raw staging, or per-snapshot history for a player who was never ours |

`mart` bakes in the four correctness rules (latest-phase-per-season, snapshot-scoped joins,
`person_id`-not-`tid`, 255-sentinel minutes) that raw `staging` makes you re-derive — so the
slim object is both smaller AND harder to get wrong. Prefer it.

Since the 2026-08-25 site refactor the mart is also what generates the web app, so it covers
the dimensions too: `mart.clubs`, `mart.leagues` (with `skill_idx`, the division-strength
index), `mart.club_leagues` (club->league **as at** a snapshot), `mart.comparison_ladder`,
`mart.player_snapshots` (bio, contract and the 23 attributes wide), `mart.player_position_levels`
(the Level percentiles), `mart.player_career_seasons`, `mart.player_origin`, `mart.club_matches`
(every match already oriented per club: venue, opponent, gf/ga, result, pts, our_/opp_ stats),
and `mart.role_weights` / `mart.position_roles` / `mart.app_config` so a role rating is
computable from the artefact alone.

#### Scoping — what is and is not in the published copy

| family | scope | why |
|---|---|---|
| growth (`player_growth*`, `player_attribute_growth`) | our clubs only | unscoped, `player_attribute_growth` alone is 8.88M rows / 108 MB — bigger than the store |
| `player_snapshots`, `player_position_levels`, `player_origin`, `player_career_seasons` | **newest snapshot only** | world-wide dimensions; at every snapshot they were 17 MB of the artefact. Our players' history is the growth family; for anyone else the question is "how good is he now" |
| `match_player_facts`, `at_club_spells`, `player_spells`, `club_matches`, `matches` | **not scoped** | opposition analysis is a first-class use — all opponent appearances and all ~3,330 clubs are kept |
| `player_role_ratings`, `player_position_fit` | **absent** | 27M and 9.4M rows, the method-dependent rating layer. Views in the local store only; they need the ability number, which the published copy does not have |

`scripts/publish_mart.py` refuses to upload anything over 40 MB, so a new object that
materialises far bigger than expected fails loudly instead of quietly shipping.

#### The macro gotcha, and the view that avoids it

`mart.squad_on(d)` is a **parameterised table macro**, and a macro's body resolves unqualified
names against the CURRENT catalog. So over an `ATTACH` it fails:

```sql
SELECT * FROM m.mart.squad_on('2024-06-30');
-- Catalog Error: Table with name "mart.player_spells" does not exist
```

Two ways round it:

```sql
USE m;  SELECT * FROM mart.squad_on('2024-06-30');   -- any date
SELECT * FROM m.mart.squad_current;                   -- the newest snapshot, no USE needed
```

`mart.squad_current` is a plain view for exactly this reason, and it is **one row per person**
(`squad_on` returns one per spell, so a borrowed player appears twice — once `at_club`, once
`loan_in`). It carries `is_loan_in` and `is_reserve`.

#### Reading attribute growth

Filter `is_gk_attr` — attributes a player's role does not use only jitter, so a bare
`ORDER BY delta DESC` surfaces outfielders drifting on keeper attributes. Join
`mart.player_growth` for `is_gk` and drop `is_gk_attr AND NOT is_gk`:

```sql
SELECT g.name, g.attribute, g.delta
FROM m.mart.player_attribute_growth g
JOIN m.mart.player_growth pg USING (person_id, season, phase)
WHERE NOT (g.is_gk_attr AND NOT pg.is_gk) AND g.delta IS NOT NULL
ORDER BY g.delta DESC;
```

> **This filter did not work before 2026-08-25.** `is_gk_attr` was rendered from a constant
> holding all 23 attributes rather than the 5 keeper ones, so it was TRUE for every row and the
> filter above discarded every outfielder instead of the keeper-attribute noise. Against an
> older artefact, check with
> `SELECT COUNT(DISTINCT attribute) FROM mart.player_attribute_growth WHERE is_gk_attr` — it
> must be 5, not 23.

**Both objects are stale until explicitly republished.** `load_duckdb.py` writes the LOCAL
store only; `scripts/publish_duckdb.py --upload` and `scripts/publish_mart.py --upload` are
separate steps, and running one does not refresh the other. See the import skill's checklist.

`worker/index.js`'s `/api/db` route and its `CAREER_RE` constant were removed since nothing
serves this way anymore. `export_data.py`'s `index.json["files"]["database"]` now points at the
`s3://` key instead of the Worker URL.

**Data size was never the constraint** — the scrubbed store was ~90 MB then (~34 MB now that
`publish_duckdb.py` run-length-encodes it, ~11 MB for the mart-only object), comfortably small for
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
- Docs updated for the `s3://` access path: `site/AGENTS.md` ("Prefer SQL?" section + a new
  "Query cookbook" documenting two dedup traps in the raw schema), `docs/DEPLOY.md` ("SQL access
  for a remote agent"), `CLAUDE.md` (storage-tiers table + a new "Answering a quick football
  question" section steering a fresh agent at this path instead of a local rebuild).
- **`.claude/hooks/session-start.sh`** (registered in `.claude/settings.json`) — makes every
  piece of this setup automatic for a Claude Code web session: `uv sync`, `rclone` installed +
  configured against `r2:` (with the `AWS_CA_BUNDLE` wrapper below baked in), and the `httpfs`
  extension pre-placed from our own R2-vendored copy. Verified by wiping `rclone`, its config,
  and the DuckDB extension cache, re-running the hook, and confirming a full `ATTACH` + query
  against the real store works immediately afterward with zero manual steps.
- **`vendor/duckdb-extensions/v<duckdb-version>/linux_amd64/httpfs.duckdb_extension`** in R2 —
  our own copy of the `httpfs` extension binary, fetched once over HTTPS and re-hosted so no
  session ever needs to touch `extensions.duckdb.org` again (not even the HTTPS variant — this
  sidesteps gotcha #3 below structurally rather than requiring every session to route around it
  itself). Re-vendor only if the project's duckdb version bumps (see
  `scripts/publish_duckdb.py`'s docstring for the exact command).

## Why scrub instead of gate

The JSON export enforces "never surface raw CA/PA" per-field (`export_data.py`'s
`check_immersion`). Raw SQL access has no per-field filter to hide behind once it's shipped —
whoever holds the R2 credentials can `SELECT ca FROM staging.players` directly. So the rule is
enforced by scrubbing the *data* in the published copy instead of trying to gate the *query*.

## What's still open — for whoever picks this up next

1. **Merge the PR.** Everything is built, documented, and verified against the real published
   store — nothing left to fix.
2. **Re-run `scripts/publish_duckdb.py --career frem --upload` after every import** you want
   reflected remotely — it's not automatic. `docs/DEPLOY.md`'s "Refreshing after an import" and
   the `import-fm-saves` skill's step 7 both call it out now, so a normal import flow won't miss
   it, but a manual `load_duckdb.py` outside that skill still needs it run by hand.
3. If a *different* Claude Code sandbox hits either of the two gotchas above again despite this
   note documenting the fix, that's a sign DuckDB's own behaviour changed (a version bump) or
   the sandbox's network policy is stricter than this one was — re-verify rather than assume the
   old fix still applies.

See also: [Multi-device and storage](multi-device-and-storage.md) for the three-tier storage
model this extends, and `docs/DEPLOY.md` for the full deploy runbook.
