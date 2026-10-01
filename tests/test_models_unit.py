#!/usr/bin/env python3
"""Synthetic unit tests for the models framework (fmstats/models/). No save needed.

  ORDER     the declared models build upstream first, every name once
  CHECKS    a duplicated grain, a NULL key and a dangling foreign key are each caught,
            and a clean model passes
  KIND      a view model replaces a table of its name and itself; a table, a view
  NAMES     int.person_names: the common name first, else first + last, NULL when either is
            missing; a store's stored name stands in for a snapshot with no ids
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

    names = duckdb.connect()
    names.execute("CREATE SCHEMA raw")
    names.execute("CREATE TABLE raw.players_raw (season INTEGER, phase VARCHAR, tid INTEGER, "
                  "first_name_id BIGINT, last_name_id BIGINT, common_name_id BIGINT)")
    names.execute("CREATE TABLE raw.name_strings (season INTEGER, phase VARCHAR, "
                  "ordinal INTEGER, name VARCHAR)")
    names.execute("CREATE TABLE raw.name_ids (season INTEGER, phase VARCHAR, "
                  "name_table VARCHAR, id BIGINT, ordinal BIGINT)")
    names.execute("INSERT INTO raw.name_strings VALUES (1, 'p', 0, 'Adenor'), (1, 'p', 1, 'Bachi'),"
                  " (1, 'p', 2, 'Tite'), (1, 'p', 3, 'Kim')")
    names.execute("INSERT INTO raw.name_ids VALUES (1, 'p', 'first_names', 5, 0),"
                  " (1, 'p', 'surnames', 7, 1), (1, 'p', 'nicknames', 0, 2),"
                  " (1, 'p', 'first_names', 6, 3)")
    names.execute("INSERT INTO raw.players_raw VALUES (1, 'p', 1, 5, 7, 0),"   # common name
                  " (1, 'p', 2, 5, 7, 4294967295),"                           # none: legal
                  " (1, 'p', 3, 6, 99, 4294967295)")                          # no surname
    M.build(names, ["int.person_names"], compat_views=False)
    got = dict(names.execute("SELECT tid, name FROM int.person_names").fetchall())
    check("NAMES: common name, else first + last, else NULL",
          got == {1: "Tite", 2: "Adenor Bachi", 3: None})
    names.execute("ALTER TABLE raw.players_raw ADD COLUMN name VARCHAR")
    names.execute("INSERT INTO raw.players_raw (season, phase, tid, name) "
                  "VALUES (1, 'p', 4, 'Stored Name')")
    M.build(names, ["int.person_names"], compat_views=False)
    got = dict(names.execute("SELECT tid, name FROM int.person_names").fetchall())
    check("NAMES: a stored name stands in where there are no ids",
          got[4] == "Stored Name" and got[1] == "Tite")

    print("OK" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
