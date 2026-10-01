#!/usr/bin/env python3
"""Synthetic unit tests for int.person_names (transform/models/int/). No save needed.

  NAMES     the common name first, else first + last, NULL when either is missing
  LEGACY    a store loaded before the name ids were handed over keeps the resolved name in
            raw.players_raw.name, and it stands in for a person with no ids
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import duckdb  # noqa: E402

import load_duckdb as L  # noqa: E402

NO_ID = 0xFFFFFFFF


def main():
    fails = 0

    def check(name, cond):
        nonlocal fails
        print(f"  {'PASS' if cond else 'FAIL'}  {name}")
        fails += not cond

    con = duckdb.connect(os.path.join(tempfile.mkdtemp(prefix="person_names_"), "t.duckdb"))
    L.create_schema(con)
    con.executemany("INSERT INTO raw.name_strings VALUES (1, 'p', ?, ?)",
                    [(0, "Adenor"), (1, "Bachi"), (2, "Tite"), (3, "Kim")])
    con.executemany("INSERT INTO raw.name_ids VALUES (1, 'p', ?, ?, ?)",
                    [("first_names", 5, 0), ("surnames", 7, 1), ("nicknames", 0, 2),
                     ("first_names", 6, 3)])
    ins = ("INSERT INTO raw.players_raw (season, phase, tid, first_name_id, last_name_id, "
           "common_name_id) VALUES (1, 'p', ?, ?, ?, ?)")
    con.executemany(ins, [(1, 5, 7, 0),         # a common name
                          (2, 5, 7, NO_ID),     # none: the legal name
                          (3, 6, 99, NO_ID)])   # no surname
    got = dict(con.execute("SELECT tid, name FROM int.person_names").fetchall())
    check("NAMES: common name, else first + last, else NULL",
          got == {1: "Tite", 2: "Adenor Bachi", 3: None})

    con.execute("ALTER TABLE raw.players_raw ADD COLUMN name VARCHAR")
    con.execute("INSERT INTO raw.players_raw (season, phase, tid, name) "
                "VALUES (1, 'p', 4, 'Stored Name')")
    L.build_models(con, "int_person_names")
    got = dict(con.execute("SELECT tid, name FROM int.person_names").fetchall())
    check("LEGACY: a stored name stands in where there are no ids",
          got[4] == "Stored Name" and got[1] == "Tite")

    print("OK" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
