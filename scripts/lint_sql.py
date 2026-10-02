#!/usr/bin/env python3
"""Lint (or fix) the dbt project's SQL with sqlfluff (transform/.sqlfluff).

    uv run python scripts/lint_sql.py          # lint models/ and tests/
    uv run python scripts/lint_sql.py --fix    # apply the fixes sqlfluff can make

sqlfluff renders each model with the dbt templater, and rendering runs the queries
some models make of the store (a table's columns, the attribute coefficients). So it
lints against a store built here, empty but with the whole schema, and needs no data.
Exit code: sqlfluff's (0 clean, 1 violations).
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main(argv):
    with tempfile.TemporaryDirectory(prefix="lint_sql_") as tmp:
        store = os.path.join(tmp, "schema.duckdb")
        # in a child process: dbt keeps the store open until its process exits
        subprocess.run([sys.executable, "-c",
                        "import duckdb, load_duckdb as L; "
                        f"L.create_schema(duckdb.connect({store!r}))"],
                       cwd=ROOT, check=True, capture_output=True)
        cmd = ["sqlfluff", "fix" if "--fix" in argv else "lint", "models", "tests"]
        env = {**os.environ, "FM_DUCKDB": store}
        return subprocess.run(cmd, cwd=os.path.join(ROOT, "transform"), env=env).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
