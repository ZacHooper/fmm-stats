#!/usr/bin/env python3
"""Synthetic unit tests for the models framework (fmstats/models/). No save needed.

  ORDER     the declared models build upstream first, every name once
  CHECKS    a duplicated grain, a NULL key and a dangling foreign key are each caught,
            and a clean model passes
  KIND      a view model replaces a table of its name and itself; a table, a view
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import duckdb  # noqa: E402

from fmstats import models as M  # noqa: E402


def main():
    fails = 0

    def check(name, cond):
        nonlocal fails
        print(f"  {'PASS' if cond else 'FAIL'}  {name}")
        fails += not cond

    built = [m.name for m in M.order()]
    seen = set()
    upstream_first = True
    for m in M.order():
        upstream_first &= all(u in seen for u in m.upstream if u in M.models())
        seen.add(m.name)
    check("ORDER: every model once", len(built) == len(set(built)) == len(M.models()))
    check("ORDER: upstream first", upstream_first)

    con = duckdb.connect()
    con.execute("CREATE SCHEMA int")
    con.execute("CREATE TABLE int.parent AS SELECT * FROM (VALUES (1), (2)) t(id)")
    con.execute("CREATE TABLE int.child AS SELECT * FROM "
                "(VALUES (1, 1), (2, 2), (2, 9), (NULL, 1)) t(k, parent_id)")
    child = M.Model("int.child", "", grain=("k",), fks={"parent_id": "int.parent(id)"})
    got = {desc: con.execute(sql).fetchone()[0] for desc, sql in M.checks(child)}
    check("CHECKS: duplicated grain caught", got["int.child: grain (k) is unique"] == 1)
    check("CHECKS: NULL grain caught", got["int.child: grain (k) is never NULL"] == 1)
    check("CHECKS: dangling key caught", got["int.child(parent_id) -> int.parent(id) resolves"] == 1)
    parent = M.Model("int.parent", "", grain=("id",))
    check("CHECKS: clean model passes",
          all(con.execute(sql).fetchone()[0] == 0 for _, sql in M.checks(parent)))

    con.execute("CREATE TABLE int.thing AS SELECT 1 AS a")
    thing = M.Model("int.thing", "SELECT 2 AS a")
    for _ in range(2):
        M._create(con, thing)
    check("KIND: view replaces a table and itself",
          M._kind(con, "int.thing") == "VIEW"
          and con.execute("SELECT a FROM int.thing").fetchone()[0] == 2)
    M._create(con, M.Model("int.thing", "SELECT 3 AS a", materialised="test"))
    check("KIND: table replaces a view",
          M._kind(con, "int.thing") == "BASE TABLE"
          and con.execute("SELECT a FROM int.thing").fetchone()[0] == 3)

    print("OK" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
