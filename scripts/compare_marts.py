#!/usr/bin/env python3
"""Compare each rebuilt consumer view (`site.<view>`) with the old one (`mart.<view>`) in one
store, row for row, and fail on any difference `transform/compare/expected.yml` does not
explain (data-layers step 17).

    uv run python scripts/compare_marts.py fm-frem.duckdb
    uv run python scripts/compare_marts.py fm-frem.duckdb --view transfers --samples 5
    uv run python scripts/compare_marts.py fm-frem.duckdb --exports OLD_DIR NEW_DIR

`--exports` also diffs two exports (`export_data.py` and `export_data.py --schema site`) file by
file: each JSON file equal, or which of its keys differ and, for a dict of players, which
players (generated_at and the file sizes in index.json always differ and are skipped). It
reports, and does not fail: an export difference follows from a view difference above.

For each view the yml names its key. Rows are matched on the key (NULLs match NULLs); then
  only_old   a key the old view has and the new one does not
  only_new   the reverse
  <column>   a matched row where the column differs (the new value cast to the old type)
are counted. A difference is explained by an entry of the view's `differences`, whose `when`
is a SQL condition over `o` (the old row) and `n` (the new row; only `o` for only_old, only
`n` for only_new) and defaults to true:

    transfers:
      key: [person_id, by_phase]
      differences:
        - rows: only_old
          when: "o.move_type in ('internal', 'released')"
          reason: a move within a club, or into free agency, is not a transfer
        - columns: [from_club_tid, from_club]
          reason: a net move A -> B -> C between two snapshots names B, the history's seller

Exit 0 when every difference is explained, 1 otherwise, 2 when a view cannot be read. A view in
`site` with no entry in the yml is compared on all its columns as a set (EXCEPT ALL both ways).
The store is opened read-only, as its own catalog, so the old views' macros resolve.
"""
import argparse
import os
import sys

import duckdb
import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPECTED = os.path.join(REPO, "transform", "compare", "expected.yml")


def q(name):
    return '"' + name.replace('"', '""') + '"'


def columns(con, schema, view):
    return con.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_catalog = current_database() AND table_schema = ? AND table_name = ? "
        "ORDER BY ordinal_position", [schema, view]).fetchall()


def compare(con, view, spec, samples):
    """Counts of each kind of difference for one view, explained and not."""
    old_cols = columns(con, "mart", view)
    new_cols = dict(columns(con, "site", view))
    if not old_cols:
        return {"error": "mart view missing"}
    missing = [c for c, _ in old_cols if c not in new_cols]
    if missing:
        return {"error": f"site view lacks columns {missing}"}
    key = spec.get("key")
    diffs = spec.get("differences", [])
    report = {"old_rows": con.execute(f"SELECT count(*) FROM mart.{q(view)}").fetchone()[0],
              "new_rows": con.execute(f"SELECT count(*) FROM site.{q(view)}").fetchone()[0],
              "kinds": {}}
    if not key:
        cols = ", ".join(q(c) for c, _ in old_cols)
        for kind, a, b in (("only_old", "mart", "site"), ("only_new", "site", "mart")):
            n = con.execute(f"SELECT count(*) FROM (SELECT {cols} FROM {a}.{q(view)} EXCEPT ALL "
                            f"SELECT {cols} FROM {b}.{q(view)})").fetchone()[0]
            report["kinds"][kind] = (n, 0)
        return report

    on = " AND ".join(f"o.{q(k)} IS NOT DISTINCT FROM n.{q(k)}" for k in key)
    con.execute("CREATE OR REPLACE TEMP TABLE _o AS SELECT * FROM mart." + q(view))
    con.execute("CREATE OR REPLACE TEMP TABLE _n AS SELECT * FROM site." + q(view))
    dup = {}
    for side in ("_o", "_n"):
        dup[side] = con.execute(
            f"SELECT count(*) FROM (SELECT {', '.join(q(k) for k in key)} FROM {side} "
            f"GROUP BY ALL HAVING count(*) > 1)").fetchone()[0]
    if dup["_o"] or dup["_n"]:
        report["key_not_unique"] = {"old": dup["_o"], "new": dup["_n"]}

    def explained(kind, cols_of_entry=None):
        conds = []
        for d in diffs:
            if kind in ("only_old", "only_new"):
                if d.get("rows") == kind:
                    conds.append(f"({d.get('when', 'true')})")
            elif kind in d.get("columns", []):
                conds.append(f"({d.get('when', 'true')})")
        return " OR ".join(conds) if conds else "false"

    for kind, sql in (
        ("only_old", f"SELECT o.* FROM _o o WHERE NOT EXISTS (SELECT 1 FROM _n n WHERE {on})"),
        ("only_new", f"SELECT n.* FROM _n n WHERE NOT EXISTS (SELECT 1 FROM _o o WHERE {on})"),
    ):
        alias = "o" if kind == "only_old" else "n"
        total = con.execute(f"SELECT count(*) FROM ({sql})").fetchone()[0]
        ok = con.execute(f"SELECT count(*) FROM ({sql}) {alias} WHERE {explained(kind)}"
                         ).fetchone()[0] if total else 0
        report["kinds"][kind] = (total, ok)
        if total - ok and samples:
            report.setdefault("samples", {})[kind] = con.execute(
                f"SELECT * FROM ({sql}) {alias} WHERE NOT ({explained(kind)}) LIMIT {samples}"
            ).df()

    for col, typ in old_cols:
        if col in key:
            continue
        differs = (f"o.{q(col)} IS DISTINCT FROM TRY_CAST(n.{q(col)} AS {typ})")
        base = f"FROM _o o JOIN _n n ON {on} WHERE {differs}"
        total = con.execute(f"SELECT count(*) {base}").fetchone()[0]
        if not total:
            continue
        ok = con.execute(f"SELECT count(*) {base} AND ({explained(col)})").fetchone()[0]
        report["kinds"][col] = (total, ok)
        if total - ok and samples:
            keys = ", ".join(f"o.{q(k)}" for k in key)
            report.setdefault("samples", {})[col] = con.execute(
                f"SELECT {keys}, o.{q(col)} AS old_value, n.{q(col)} AS new_value {base} "
                f"AND NOT ({explained(col)}) LIMIT {samples}").df()
    return report


def compare_exports(old_dir, new_dir, samples):
    """Print, per JSON file of two export directories, whether it is equal and, if not, which
    keys differ (and which entries of a dict-valued key)."""
    import json
    names = sorted(set(os.listdir(old_dir)) | set(os.listdir(new_dir)))
    for name in names:
        if not name.endswith(".json"):
            continue
        a_path, b_path = os.path.join(old_dir, name), os.path.join(new_dir, name)
        if not (os.path.exists(a_path) and os.path.exists(b_path)):
            print(f"  {name:20} only in {'old' if os.path.exists(a_path) else 'new'}")
            continue
        a, b = json.load(open(a_path)), json.load(open(b_path))
        if name == "index.json":
            for d in (a, b):
                d.pop("generated_at", None)
                d.pop("counts", None)
        if a == b:
            print(f"  {name:20} equal")
            continue
        keys = [k for k in (set(a) | set(b)) if a.get(k) != b.get(k)] if isinstance(a, dict) \
            else ["(top level)"]
        print(f"  {name:20} differs in {sorted(keys)}")
        for k in keys:
            va, vb = (a.get(k), b.get(k)) if isinstance(a, dict) else (a, b)
            if isinstance(va, dict) and isinstance(vb, dict):
                entries = sorted(e for e in set(va) | set(vb) if va.get(e) != vb.get(e))
                print(f"    {k}: {len(entries)} entries differ")
                for e in entries[:samples]:
                    print(f"      {e}: old {va.get(e)}")
                    print(f"      {' ' * len(str(e))}  new {vb.get(e)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("store")
    ap.add_argument("--view", action="append", help="compare only these views")
    ap.add_argument("--expected", default=EXPECTED)
    ap.add_argument("--exports", nargs=2, metavar=("OLD_DIR", "NEW_DIR"),
                    help="also diff two export directories, file by file")
    ap.add_argument("--samples", type=int, default=3,
                    help="unexplained rows to print per kind (0 for none)")
    a = ap.parse_args()

    spec = {}
    if os.path.exists(a.expected):
        with open(a.expected) as f:
            spec = yaml.safe_load(f) or {}
    con = duckdb.connect(a.store, read_only=True)
    site_views = [r[0] for r in con.execute(
        "SELECT view_name FROM duckdb_views() WHERE database_name = current_database() "
        "AND schema_name = 'site' AND NOT internal ORDER BY view_name").fetchall()]
    views = a.view or site_views
    worst = 0
    for view in views:
        rep = compare(con, view, spec.get(view) or {}, a.samples)
        if "error" in rep:
            print(f"{view:24} ERROR {rep['error']}")
            worst = 2
            continue
        unexplained = sum(t - ok for t, ok in rep["kinds"].values())
        status = "ok" if not unexplained and "key_not_unique" not in rep else "DIFF"
        print(f"{view:24} {status:4}  old {rep['old_rows']:>8,}  new {rep['new_rows']:>8,}")
        if "key_not_unique" in rep:
            print(f"    key not unique: {rep['key_not_unique']}")
        for kind, (total, ok) in rep["kinds"].items():
            if total:
                print(f"    {kind:22} {total:>8,} differ, {ok:>8,} explained")
        for kind, df in rep.get("samples", {}).items():
            print(f"    -- unexplained {kind}:")
            print("      " + df.to_string(max_cols=12, max_colwidth=24).replace("\n", "\n      "))
        if status != "ok":
            worst = max(worst, 1)
    if a.exports:
        print("exports:")
        compare_exports(*a.exports, a.samples)
    sys.exit(worst)


if __name__ == "__main__":
    main()
