#!/usr/bin/env python3
"""Publish a queryable copy of the career's DuckDB store to R2 — for a remote agent session
with no local store and no saves, wanting arbitrary SQL instead of the fixed JSON shapes
`export_data.py` produces.

    uv run python scripts/publish_duckdb.py --career frem --upload

DuckDB can ATTACH straight to the R2 object over its native S3 protocol (httpfs extension,
range requests, so it never downloads the whole file) using the same R2 credentials a Claude
Code session in this project already carries. Use `TYPE s3` with an explicit endpoint, not the
`TYPE r2` / `ACCOUNT_ID` shorthand — in testing the shorthand silently fell through to public
AWS S3 (`*.s3.us-east-1.amazonaws.com`) instead of R2 in a network-proxied sandbox:

    INSTALL httpfs; LOAD httpfs;
    CREATE SECRET r2 (TYPE s3, KEY_ID '<R2_ACCESS_KEY>', SECRET '<R2_SECRET_ACCESS_KEY>',
                       ENDPOINT '<R2_ACCOUNT_ID>.r2.cloudflarestorage.com',
                       URL_STYLE 'path', REGION 'auto');
    ATTACH 's3://fmm-stats/site-data/fm-frem.duckdb' AS fm (READ_ONLY);
    SELECT * FROM fm.staging.players LIMIT 5;

Deliberately NOT served through the Worker (`worker/index.js`): that would mean going out to
`*.workers.dev`, which a network-restricted agent sandbox may not be able to reach, whereas the
account-scoped R2 endpoint (`<account-id>.r2.cloudflarestorage.com`) commonly is allowed since
it's the same host `rclone`/this script already upload through.

`extensions.duckdb.org` must be reachable too, to install `httpfs` itself — add it to the
sandbox's network policy if `INSTALL httpfs` fails outright. One further wrinkle seen in
testing: DuckDB's installer defaults to a PLAIN HTTP url
(`http://extensions.duckdb.org/...`), which can still 403 even once the HTTPS host is
allowed, since a network policy commonly allowlists by host *and scheme*.

A Claude Code session in this repo never needs to work around either of those:
`.claude/hooks/session-start.sh` pre-places `httpfs` from our own R2-vendored copy
(`vendor/duckdb-extensions/v<duckdb-version>/linux_amd64/httpfs.duckdb_extension`) on startup,
so `LOAD httpfs;` alone (no `INSTALL`) just works — no network call to
`extensions.duckdb.org` at all. Elsewhere, fetch the `.gz` over HTTPS yourself and drop it in
DuckDB's extension cache instead of using `INSTALL`:

    v=$(python3 -c "import duckdb; print(duckdb.__version__)")
    curl -o /tmp/httpfs.gz "https://extensions.duckdb.org/v$v/linux_amd64/httpfs.duckdb_extension.gz"
    mkdir -p ~/.duckdb/extensions/v$v/linux_amd64
    gunzip -c /tmp/httpfs.gz > ~/.duckdb/extensions/v$v/linux_amd64/httpfs.duckdb_extension

then just `LOAD httpfs;` (no `INSTALL`) picks it up from the local cache. Re-vendor the R2 copy
(only needed if the project's duckdb version bumps) with:

    rclone copyto ~/.duckdb/extensions/v$v/linux_amd64/httpfs.duckdb_extension \
        r2:fmm-stats/vendor/duckdb-extensions/v$v/linux_amd64/httpfs.duckdb_extension

The published copy carries staging.players.ca/.pa (raw ability) UNCHANGED — it is not scrubbed.
The immersion house rule (CLAUDE.md: never SURFACE the raw ability number) is enforced at the
presentation layer — the dashboard, the skills, and export_data.py's JSON API (checked at build
time by scripts/build_site.py) — not by hiding the column from SQL. A query against this store
can compute Level %ile / Fit ratings same as a local rebuild; it just shouldn't print the raw
`ca`/`pa` value in a report, same rule that already applies everywhere else. (Before
2026-09-01 this script also NULLed ca/pa here, which meant mart.player_position_fit and
mart.player_position_levels — both of which require ca — came back EMPTY against this copy:
a remote scout report always read "0 rated players" regardless of the opponent. That's why the
scrub was dropped, not a change to what gets surfaced.) The live store is opened read-only and
is never itself touched.

Like all.json, this is a derived, R2-only artefact — NOT git (see the storage-tiers table in
CLAUDE.md). Re-run after every import that you want reflected remotely.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time

import duckdb

# ---------------------------------------------------------------------------------------
# Compaction (--compact, on by default)
#
# The live store is ~107 MB, of which ~45 MB is pure cross-snapshot duplication: staging
# mirrors the parser, one FULL row set per (season, phase), so an immutable fact is restored
# verbatim in every later snapshot. player_history_seasons is the extreme case — 3,383,704
# rows collapse to 470,092 distinct ones (7.2x), because a player's 2019 season row cannot
# change but is re-stored 16 times.
#
# So each snapshot-scoped table is RUN-LENGTH ENCODED: group by every column except
# season/phase, and record the contiguous run of snapshot indices the row was present for.
# Interval-per-group would be LOSSY — 59 groups in this career appear, vanish and reappear —
# so runs are found with gaps-and-islands, not min/max, which is exact.
#
# The published copy then exposes staging.<table> as a VIEW that expands the runs back, so
# every query already documented against the full store (docs/agent-context/
# remote-duckdb-access.md, site/AGENTS.md) keeps working against the identical schema. The
# RLE tables sit behind it as staging._rle_<table>. Verified row-for-row with a symmetric
# EXCEPT ALL against the source before upload — this refuses to publish otherwise.
#
# player_history measured 1.0x (no duplication at all — every row is snapshot-unique), where
# the two extra run columns cost more than dedupe saves, so it is left as a plain table.
SKIP_RLE = {"player_history"}


def compact(con):
    """RLE every snapshot-scoped staging table in `con`, exposing expansion views under the
    original names. Returns (tables_compacted, source_rows, encoded_rows)."""
    con.execute("""CREATE OR REPLACE TABLE staging._snapshots AS
        SELECT row_number() OVER (ORDER BY season, phase) AS snap_ix, season, phase
        FROM (SELECT DISTINCT season, phase FROM staging.extracts)""")

    tabs = [t for (t,) in con.execute(
        "SELECT table_name FROM duckdb_tables() WHERE schema_name = 'staging' "
        "AND NOT starts_with(table_name, '_') ORDER BY table_name").fetchall()]

    done, n_src, n_rle = 0, 0, 0
    for t in tabs:
        cols = [c for (c,) in con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = 'staging' "
            f"AND table_name = '{t}' ORDER BY ordinal_position").fetchall()]
        body = [c for c in cols if c not in ("season", "phase")]
        if t in SKIP_RLE or not body or not {"season", "phase"} <= set(cols):
            continue
        kl = ", ".join(f'"{c}"' for c in body)

        con.execute(f"""CREATE TABLE staging."_rle_{t}" AS
            WITH ph AS (
              SELECT p.*, n.snap_ix FROM staging."{t}" p
              JOIN staging._snapshots n USING (season, phase)),
            marked AS (
              SELECT {kl}, snap_ix,
                     snap_ix - row_number() OVER (PARTITION BY {kl} ORDER BY snap_ix) AS grp
              FROM ph)
            SELECT {kl}, min(snap_ix) AS snap_lo, max(snap_ix) AS snap_hi
            FROM marked GROUP BY {kl}, grp""")

        sel = "season, phase, " + kl
        expand = (f'SELECT n.season, n.phase, {kl} FROM staging."_rle_{t}" r '
                  f"JOIN staging._snapshots n ON n.snap_ix BETWEEN r.snap_lo AND r.snap_hi")
        miss = con.execute(f'SELECT count(*) FROM ((SELECT {sel} FROM staging."{t}") '
                           f"EXCEPT ALL ({expand}))").fetchone()[0]
        extra = con.execute(f"SELECT count(*) FROM (({expand}) EXCEPT ALL "
                            f'(SELECT {sel} FROM staging."{t}"))').fetchone()[0]
        if miss or extra:
            raise SystemExit(f"compaction of staging.{t} is LOSSY "
                             f"(missing={miss}, extra={extra}) — refusing to publish")

        n_src += con.execute(f'SELECT count(*) FROM staging."{t}"').fetchone()[0]
        n_rle += con.execute(f'SELECT count(*) FROM staging."_rle_{t}"').fetchone()[0]
        con.execute(f'DROP TABLE staging."{t}"')
        con.execute(f'CREATE VIEW staging."{t}" AS {expand}')
        done += 1

    con.execute("CHECKPOINT")
    return done, n_src, n_rle

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))

import _dbopen                                                          # noqa: E402

R2_REMOTE = os.environ.get("FM_R2_REMOTE", "r2:fmm-stats")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--career")
    ap.add_argument("--upload", action="store_true",
                    help="rclone the scrubbed copy to R2 (site-data/fm-<career>.duckdb)")
    ap.add_argument("--out", help="write the scrubbed copy here instead of a scratch temp "
                                  "file, and keep it afterwards (handy for inspecting it "
                                  "before trusting an upload)")
    ap.add_argument("--no-compact", action="store_true",
                    help="skip run-length compaction (publishes the full ~107 MB copy with "
                         "plain tables instead of expansion views); see compact() above")
    a = ap.parse_args()

    if a.career:
        os.environ["FM_CAREER"] = a.career
    from fmparser import careers as C
    car = C.resolve_career(a.career or C.DEFAULT_CAREER)
    store = os.environ.get("FM_DUCKDB") or os.path.join(REPO, car.db)
    if not os.path.exists(store):
        raise SystemExit(f"no store at {store} — build it with scripts/rebuild.py")

    # Reuse the existing single-writer-safe fallback: refuses a byte copy of a store that's
    # mid-write (a .wal beside it, or written in the last 90s), copies to a temp path if a live
    # dashboard holds the write lock, otherwise just confirms the original is safe to copy.
    con, used = _dbopen.open_readonly(store, tag="publish")
    con.close()

    keep = bool(a.out)
    dest = a.out or os.path.join(tempfile.gettempdir(), f"fm-{car.key}-publish.duckdb")
    try:
        if os.path.exists(dest):
            os.remove(dest)
        shutil.copy2(used, dest)

        con = duckdb.connect(dest)
        if not a.no_compact:
            before = os.path.getsize(dest)
            done, n_src, n_rle = compact(con)
            con.close()
            # a rewrite into a fresh file is what actually reclaims the freed blocks: DuckDB
            # reuses them in place but never shrinks the file, so an in-place CHECKPOINT alone
            # leaves the old size on disk.
            tmp2 = dest + ".packed"
            if os.path.exists(tmp2):
                os.remove(tmp2)
            c2 = duckdb.connect()          # in-memory driver; both stores are ATTACHed
            c2.execute(f"ATTACH '{dest}' AS old (READ_ONLY)")
            c2.execute(f"ATTACH '{tmp2}' AS packed")
            c2.execute("COPY FROM DATABASE old TO packed")   # carries tables AND views
            c2.execute("CHECKPOINT packed")
            c2.close()
            os.replace(tmp2, dest)
            print(f"  compacted {done} tables: {n_src:,} rows -> {n_rle:,} "
                  f"({n_src / max(n_rle, 1):.1f}x), verified exact; "
                  f"{before / 1024 / 1024:.1f} -> {os.path.getsize(dest) / 1024 / 1024:.1f} MB")
        else:
            con.close()

        size = os.path.getsize(dest)
        print(f"published copy: {dest} ({size / 1024 / 1024:.1f} MB)")

        if not a.upload:
            print("(not uploaded — pass --upload once rclone + the R2 remote are configured)")
            return 0

        if shutil.which("rclone") is None:
            raise SystemExit(f"rclone not installed — can't upload. Install rclone and "
                             f"configure the '{R2_REMOTE}' remote, or drop --upload and push "
                             f"{os.path.basename(dest)} to R2 yourself.")
        remote = f"{R2_REMOTE}/site-data/fm-{car.key}.duckdb"
        print(f"uploading to {remote} ...")
        t0 = time.time()
        r = subprocess.run(["rclone", "copyto", dest, remote], capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"upload failed: {(r.stderr or '').strip()[:300]}")
        print(f"uploaded in {time.time() - t0:.0f}s")
        return 0
    finally:
        if not keep and os.path.exists(dest):
            os.remove(dest)


if __name__ == "__main__":
    sys.exit(main())
