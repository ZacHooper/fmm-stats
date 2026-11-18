#!/usr/bin/env python3
"""Fetch a career's store from R2 instead of rebuilding it from every save.

    uv run python scripts/pull_store.py --career truro

`publish_duckdb.py --upload` leaves a full copy of the store at
`<r2_remote>/site-data/fm-<career>.duckdb`, `raw` included. That copy is compacted: each
snapshot-scoped raw table is a run-length-encoded `raw._rle_<table>` behind a VIEW of the
original name, which the loader cannot DELETE from or INSERT into. This script downloads it and
writes `fm-<career>.duckdb` with the loader's own DDL (`load_duckdb.create_schema`), then copies
every raw table and view into it by column name, so the result is the store the publish was
made from, in the shape the loader writes. Row counts are checked table by table.

Only `raw` is copied. `stg`/`int`/`mart`/`site` are dbt's, rebuilt by the next load or by
`load_duckdb.py --refresh-only`, so the store is current with this checkout's models.

The copy is only as new as the last `publish_duckdb.py --upload`: compare its
`raw.extracts` with `seeds/manifest.csv`, and load any snapshot it lacks. `scripts/rebuild.py`
remains the path with no published copy, or after a parser change.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

import duckdb

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import fmconfig  # noqa: E402


def restore(published, store):
    """Write `store` from the compacted `published` copy: loader DDL, then raw by name."""
    import load_duckdb
    con = duckdb.connect(store)
    load_duckdb.create_schema(con)
    con.execute(f"ATTACH '{published}' AS pub (READ_ONLY)")
    names = [n for (n,) in con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_catalog = 'pub' AND table_schema = 'raw' "
        "AND NOT starts_with(table_name, '_') ORDER BY table_name").fetchall()]
    for t in names:
        exists = con.execute(
            "SELECT count(*) FROM duckdb_tables() WHERE database_name = current_database() "
            f"AND schema_name = 'raw' AND table_name = '{t}'").fetchone()[0]
        if exists:
            con.execute(f'DELETE FROM raw."{t}"')   # create_schema seeds a few
            con.execute(f'INSERT INTO raw."{t}" BY NAME SELECT * FROM pub.raw."{t}"')
        else:
            con.execute(f'CREATE TABLE raw."{t}" AS SELECT * FROM pub.raw."{t}"')
        want = con.execute(f'SELECT count(*) FROM pub.raw."{t}"').fetchone()[0]
        got = con.execute(f'SELECT count(*) FROM raw."{t}"').fetchone()[0]
        if want != got:
            raise SystemExit(f"raw.{t}: {got:,} rows restored, the published copy has {want:,}")
    snaps = con.execute("SELECT label FROM raw.extracts ORDER BY season, phase").fetchall()
    con.execute("DETACH pub")
    con.execute("CHECKPOINT")
    con.close()
    return len(names), [s for (s,) in snaps]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--career")
    ap.add_argument("--force", action="store_true",
                    help="replace an existing local store")
    a = ap.parse_args()
    if a.career:
        os.environ["FM_CAREER"] = a.career
    import careers as C
    car = C.resolve_career(a.career or C.DEFAULT_CAREER)
    store = os.environ.get("FM_DUCKDB") or os.path.join(REPO, car.db)
    if os.path.exists(store) and not a.force:
        raise SystemExit(f"{store} exists; pass --force to replace it")
    if shutil.which("rclone") is None:
        raise SystemExit("rclone not installed")
    remote = f"{fmconfig.require_r2_remote()}/site-data/fm-{car.key}.duckdb"

    with tempfile.TemporaryDirectory() as tmp:
        published = os.path.join(tmp, f"fm-{car.key}-published.duckdb")
        print(f"fetching {remote}", flush=True)
        r = subprocess.run(["rclone", "copyto", remote, published])
        if r.returncode != 0 or not os.path.exists(published):
            raise SystemExit(f"no published store at {remote}: build it with "
                             f"scripts/rebuild.py --career {car.key}")
        partial = store + ".pulling"
        for p in (partial, partial + ".wal"):
            if os.path.exists(p):
                os.remove(p)
        n, snaps = restore(published, partial)
        if os.path.exists(store + ".wal"):
            os.remove(store + ".wal")
        os.replace(partial, store)
    print(f"wrote {store}: {n} raw tables, {len(snaps)} snapshots")
    for s in snaps:
        print(f"  {s}")
    print("models are not built: the next load_duckdb.py builds them "
          f"(or: load_duckdb.py --refresh-only --career {car.key})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
