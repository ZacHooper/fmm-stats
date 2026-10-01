#!/usr/bin/env python3
"""
Row-for-row comparison of one table or view across two DuckDB stores.

The gate for every data-layers step (`docs/plans/2026-10-01-data-layers.md`): build a store
from `main`, build one from the branch, and compare the tables the change touches.

    uv run python scripts/audit/diff_stores.py OLD.duckdb NEW.duckdb \\
        --table mart.clubs --key season,phase,tid
    uv run python scripts/audit/diff_stores.py OLD.duckdb NEW.duckdb \\
        --table mart.clubs --key season,phase,tid --table mart.leagues --key season,phase,cid
    uv run python scripts/audit/diff_stores.py OLD.duckdb NEW.duckdb --table OLD_NAME=NEW_NAME ...

With `--key`, rows are matched on the key and the report gives the rows only in one store and,
for every common column, how many matched rows differ, with examples. Without a key the two
sides are compared as multisets (`EXCEPT ALL`), which says how many rows differ but not where.
A duplicated key is reported and counts as a difference: a key that is not a key cannot gate.

Each side is read in its OWN connection and copied to a temporary parquet file before
comparing. ATTACHing both stores in one connection would be simpler, but a view whose SQL
calls a macro (`phase_ord`, ...) resolves that macro against the connecting database, not
the attached one, so most mart views fail across an ATTACH.

Columns are compared with `IS DISTINCT FROM` (two NULLs agree). `--tol` lets floating-point
columns differ by up to that absolute amount. Columns present on one side only are listed,
not compared.

Exit codes: 0 every table identical, 1 a difference, 2 a table could not be read.
"""
import argparse
import os
import shutil
import sys
import tempfile

import duckdb


def _quote(name):
    return '"' + name.replace('"', '""') + '"'


def _snapshot(path, table, where, out):
    """Copy `table` from the store at `path` to the parquet file `out`; returns its columns
    as [(name, type)]."""
    con = duckdb.connect(path, read_only=True)
    con.execute("SET enable_progress_bar = false")
    try:
        sql = f"SELECT * FROM {table}" + (f" WHERE {where}" if where else "")
        con.execute(f"COPY ({sql}) TO '{out}' (FORMAT parquet)")
        return [(r[0], r[1]) for r in con.execute(f"DESCRIBE {sql}").fetchall()]
    finally:
        con.close()


def _is_float(t):
    return t.upper() in ("DOUBLE", "FLOAT", "REAL") or t.upper().startswith("DECIMAL")


def compare(old_path, new_path, old_table, new_table, key, where=None, tol=0.0, examples=5,
            out=print):
    """Compare one table; returns True when identical. Raises duckdb.Error when a side
    cannot be read."""
    tmp = tempfile.mkdtemp(prefix="diff_stores_")
    try:
        po, pn = os.path.join(tmp, "old.parquet"), os.path.join(tmp, "new.parquet")
        cols_o = _snapshot(old_path, old_table, where, po)
        cols_n = _snapshot(new_path, new_table, where, pn)
        con = duckdb.connect()
        con.execute("SET enable_progress_bar = false")
        con.execute(f"CREATE VIEW o AS SELECT * FROM '{po}'")
        con.execute(f"CREATE VIEW n AS SELECT * FROM '{pn}'")
        n_o = con.execute("SELECT count(*) FROM o").fetchone()[0]
        n_n = con.execute("SELECT count(*) FROM n").fetchone()[0]
        title = old_table if old_table == new_table else f"{old_table} -> {new_table}"
        out(f"== {title}: {n_o:,} rows old, {n_n:,} rows new")

        names_o, names_n = [c for c, _ in cols_o], [c for c, _ in cols_n]
        types = dict(cols_o)
        only_o = [c for c in names_o if c not in names_n]
        only_n = [c for c in names_n if c not in names_o]
        common = [c for c in names_o if c in names_n]
        same = not only_o and not only_n
        if only_o:
            out(f"  columns only in old: {', '.join(only_o)}")
        if only_n:
            out(f"  columns only in new: {', '.join(only_n)}")

        if not key:
            sel = ", ".join(_quote(c) for c in common)
            gone = con.execute(f"SELECT count(*) FROM (SELECT {sel} FROM o EXCEPT ALL "
                               f"SELECT {sel} FROM n)").fetchone()[0]
            added = con.execute(f"SELECT count(*) FROM (SELECT {sel} FROM n EXCEPT ALL "
                                f"SELECT {sel} FROM o)").fetchone()[0]
            if gone or added:
                out(f"  rows only in old: {gone:,}   rows only in new: {added:,}")
            else:
                out("  identical rows")
            return same and not gone and not added

        missing = [k for k in key if k not in common]
        if missing:
            raise duckdb.BinderException(f"key column(s) not on both sides: {', '.join(missing)}")
        kcols = ", ".join(_quote(k) for k in key)

        def match(a, b):
            return " AND ".join(f"{a}.{_quote(k)} IS NOT DISTINCT FROM {b}.{_quote(k)}"
                                for k in key)
        on = match("o", "n")
        okey = ", ".join(f"o.{_quote(k)}" for k in key)

        clean = same
        for side in ("o", "n"):
            dup = con.execute(f"SELECT count(*) FROM (SELECT {kcols} FROM {side} "
                              f"GROUP BY ALL HAVING count(*) > 1)").fetchone()[0]
            if dup:
                clean = False
                name = "old" if side == "o" else "new"
                out(f"  DUPLICATE KEYS in {name}: {dup:,} key values occur more than once")
                for r in con.execute(f"SELECT {kcols}, count(*) AS n FROM {side} GROUP BY ALL "
                                     f"HAVING count(*) > 1 ORDER BY ALL LIMIT {examples}").fetchall():
                    out(f"      {r}")

        for a, b, label in (("o", "n", "old"), ("n", "o", "new")):
            anti = f"FROM {a} ANTI JOIN {b} ON {match(a, b)}"
            cnt = con.execute(f"SELECT count(*) {anti}").fetchone()[0]
            if cnt:
                clean = False
                out(f"  rows only in {label}: {cnt:,}")
                sel = ", ".join(f"{a}.{_quote(k)}" for k in key)
                for r in con.execute(f"SELECT {sel} {anti} ORDER BY ALL LIMIT {examples}").fetchall():
                    out(f"      {r}")

        diffs = []
        for c in common:
            if c in key:
                continue
            qc = _quote(c)
            if tol and _is_float(types[c]):
                cond = (f"(o.{qc} IS NULL) <> (n.{qc} IS NULL) "
                        f"OR abs(o.{qc} - n.{qc}) > {tol}")
            else:
                cond = f"o.{qc} IS DISTINCT FROM n.{qc}"
            cnt = con.execute(f"SELECT count(*) FROM o JOIN n ON {on} WHERE {cond}").fetchone()[0]
            if cnt:
                diffs.append((c, cnt, cond))
        matched = con.execute(f"SELECT count(*) FROM o JOIN n ON {on}").fetchone()[0]
        if diffs:
            clean = False
            out(f"  {matched:,} rows matched on ({', '.join(key)}); columns that differ:")
            for c, cnt, cond in diffs:
                out(f"    {c}: {cnt:,} rows")
                qc = _quote(c)
                for r in con.execute(f"SELECT {okey}, o.{qc}, n.{qc} FROM o JOIN n ON {on} "
                                     f"WHERE {cond} ORDER BY {okey} LIMIT {examples}").fetchall():
                    k, vo, vn = r[:len(key)], r[len(key)], r[len(key) + 1]
                    out(f"      {k}: {vo!r} -> {vn!r}")
        elif clean:
            out(f"  identical ({matched:,} rows matched on {', '.join(key)})")
        else:
            out(f"  {matched:,} rows matched on ({', '.join(key)}); every common column agrees")
        return clean
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("old", help="the store built from main")
    ap.add_argument("new", help="the store built from the branch")
    ap.add_argument("--table", action="append", required=True,
                    help="schema.table to compare; OLD=NEW when it was renamed (repeatable)")
    ap.add_argument("--key", action="append", default=[],
                    help="comma-separated key columns, one per --table in the same order; "
                         "'-' or omitted for a multiset comparison")
    ap.add_argument("--where", help="a filter applied to both sides, e.g. \"season = 2026\"")
    ap.add_argument("--tol", type=float, default=0.0,
                    help="absolute tolerance for floating-point columns (default exact)")
    ap.add_argument("--examples", type=int, default=5, help="example rows per difference")
    args = ap.parse_args(argv)

    if len(args.key) > len(args.table):
        ap.error("more --key than --table")
    keys = args.key + ["-"] * (len(args.table) - len(args.key))
    status = 0
    for t, k in zip(args.table, keys):
        old_t, _, new_t = t.partition("=")
        key = [] if k in ("-", "") else [c.strip() for c in k.split(",")]
        try:
            ok = compare(args.old, args.new, old_t, new_t or old_t, key, where=args.where,
                         tol=args.tol, examples=args.examples)
        except duckdb.Error as e:
            print(f"== {t}: CANNOT COMPARE: {e}")
            return 2
        if not ok:
            status = 1
    print("IDENTICAL" if status == 0 else "DIFFERENT")
    return status


if __name__ == "__main__":
    sys.exit(main())
