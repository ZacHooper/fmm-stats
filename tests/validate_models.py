#!/usr/bin/env python3
"""Assert every declared model's own checks against a built store (fmstats/models/).

For each model: its grain is unique and never NULL, and each foreign key resolves. The checks
come from the declarations (`fmstats.models.checks`), so declaring a grain or a key is what
adds its test; there is no second list to keep in step.

    uv run python tests/validate_models.py --db fm-frem.duckdb

Exit codes: 0 every check passes, 1 a check fails, 2 the store has no built models.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import duckdb  # noqa: E402

from fmstats import models  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", required=True)
    a = ap.parse_args(argv)
    con = duckdb.connect(a.db, read_only=True)
    con.execute("SET enable_progress_bar = false")
    if not con.execute("SELECT 1 FROM information_schema.schemata "
                       "WHERE schema_name = 'int'").fetchone():
        print(f"{a.db} has no models; build them with "
              f"`uv run python load_duckdb.py --refresh-only --db {a.db}`")
        return 2
    failed = 0
    for m in models.order():
        for desc, sql in models.checks(m):
            n = con.execute(sql).fetchone()[0]
            failed += bool(n)
            print(f"  {'FAIL' if n else 'ok  '} {desc}" + (f" -- {n:,} rows" if n else ""))
    print("PASS" if not failed else f"{failed} check(s) FAILED")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
