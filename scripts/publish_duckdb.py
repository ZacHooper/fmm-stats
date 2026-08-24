#!/usr/bin/env python3
"""Publish a queryable copy of the career's DuckDB store to R2 — for a remote agent session
with no local store and no saves, wanting arbitrary SQL instead of the fixed JSON shapes
`export_data.py` produces.

    uv run python scripts/publish_duckdb.py --career frem --upload

DuckDB can ATTACH a remote database over plain HTTP(S) in read-only mode via the httpfs
extension, using range requests so it never downloads the whole file:

    INSTALL httpfs; LOAD httpfs;
    ATTACH 'https://fmm-stats.zac-g-hooper.workers.dev/api/db?career=frem' AS fm (READ_ONLY);
    SELECT * FROM fm.staging.players LIMIT 5;

(`worker/index.js` serves that URL, forwarding Range requests straight to R2 — see its
`dbFile` handler.)

The published copy is a SCRUBBED CLONE, never the live store: staging.players.ca/.pa (raw
ability) are NULLed here before upload. That's the same immersion house rule export_data.py
enforces for the JSON API (see CLAUDE.md) — applied at the row level, because raw SQL access
has no per-field filter to hide behind once it's shipped. The live store is opened read-only
and is never itself touched.

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

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))

import _dbopen                                                          # noqa: E402

R2_REMOTE = os.environ.get("FM_R2_REMOTE", "r2:fmm-stats")
# Table, columns to NULL. Only staging.players carries raw ability — see CLAUDE.md's immersion
# house rule and load_duckdb.py's schema (ca/pa are not duplicated anywhere else).
SCRUB = [("staging.players", ["ca", "pa"])]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--career")
    ap.add_argument("--upload", action="store_true",
                    help="rclone the scrubbed copy to R2 (site-data/fm-<career>.duckdb)")
    ap.add_argument("--out", help="write the scrubbed copy here instead of a scratch temp "
                                  "file, and keep it afterwards (handy for inspecting it "
                                  "before trusting an upload)")
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
        for table, cols in SCRUB:
            sets = ", ".join(f"{c} = NULL" for c in cols)
            n = con.execute(f"SELECT COUNT(*) FROM {table} "
                            f"WHERE {' OR '.join(f'{c} IS NOT NULL' for c in cols)}").fetchone()[0]
            con.execute(f"UPDATE {table} SET {sets}")
            print(f"  scrubbed {', '.join(cols)} on {n} rows in {table}")
        con.execute("CHECKPOINT")
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
