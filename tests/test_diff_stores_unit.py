#!/usr/bin/env python3
"""Synthetic unit tests for scripts/audit/diff_stores.py. No save needed.

  SAME      identical tables compare clean, keyed and as multisets
  VALUE     a changed value is found, in the right column, on a matched key
  ROWS      a row present on one side only is reported, and fails the comparison
  DUP       a duplicated key fails the comparison
  COLUMNS   a column on one side only fails the comparison
  TOL       --tol lets a float column drift, and nothing else
  MACRO     a view calling a macro of its own store compares (no ATTACH)
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "audit"))

import duckdb  # noqa: E402

import diff_stores as D  # noqa: E402


def store(path, rows, extra_col=False):
    con = duckdb.connect(path)
    con.execute("CREATE SCHEMA mart")
    con.execute("CREATE TABLE mart.t (k INT, s VARCHAR, x DOUBLE"
                + (", extra INT" if extra_col else "") + ")")
    for r in rows:
        con.execute("INSERT INTO mart.t VALUES (" + ", ".join("?" * len(r)) + ")", list(r))
    con.execute("CREATE MACRO twice(v) AS v * 2")
    con.execute("CREATE VIEW mart.v AS SELECT k, twice(x) AS x2 FROM mart.t")
    con.close()


def run(old, new, key, table="mart.t", tol=0.0):
    lines = []
    ok = D.compare(old, new, table, table, key, tol=tol, out=lines.append)
    return ok, "\n".join(lines)


def main():
    base = [(1, "a", 1.0), (2, "b", 2.0), (3, None, 3.0)]
    fails = 0

    def check(name, cond, detail=""):
        nonlocal fails
        print(f"  {'PASS' if cond else 'FAIL'}  {name}")
        if not cond:
            fails += 1
            print(detail)

    with tempfile.TemporaryDirectory() as d:
        def mk(name, rows, **kw):
            p = os.path.join(d, name + ".duckdb")
            store(p, rows, **kw)
            return p

        a = mk("a", base)
        ok, txt = run(a, mk("same", base), ["k"])
        check("SAME keyed", ok, txt)
        ok, txt = run(a, os.path.join(d, "same.duckdb"), [])
        check("SAME multiset", ok, txt)

        ok, txt = run(a, mk("value", [(1, "a", 1.0), (2, "B", 2.0), (3, None, 3.0)]), ["k"])
        check("VALUE found in column s", not ok and "s: 1 rows" in txt and "'b' -> 'B'" in txt, txt)

        ok, txt = run(a, mk("rows", base[:2]), ["k"])
        check("ROWS only in old", not ok and "rows only in old: 1" in txt, txt)
        ok, txt = run(a, os.path.join(d, "rows.duckdb"), [])
        check("ROWS multiset", not ok and "rows only in old: 1" in txt, txt)

        ok, txt = run(a, mk("dup", base + [(1, "a", 1.0)]), ["k"])
        check("DUP key fails", not ok and "DUPLICATE KEYS in new" in txt, txt)

        ok, txt = run(a, mk("cols", [r + (0,) for r in base], extra_col=True), ["k"])
        check("COLUMNS only in new", not ok and "columns only in new: extra" in txt, txt)

        drift = mk("drift", [(1, "a", 1.0000001), (2, "b", 2.0), (3, None, 3.0)])
        ok, _ = run(a, drift, ["k"])
        check("TOL exact by default", not ok)
        ok, txt = run(a, drift, ["k"], tol=1e-6)
        check("TOL tolerates float drift", ok, txt)

        ok, txt = run(a, os.path.join(d, "value.duckdb"), ["k"], table="mart.v")
        check("MACRO view compares", ok, txt)

        rc = D.main([a, os.path.join(d, "value.duckdb"), "--table", "mart.t", "--key", "k"])
        check("exit code 1 on a difference", rc == 1)
        rc = D.main([a, a, "--table", "mart.nope"])
        check("exit code 2 on an unreadable table", rc == 2)

    print("OK" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
