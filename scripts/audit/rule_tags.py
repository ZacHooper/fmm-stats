#!/usr/bin/env python3
"""Flatten every competition rule file into one row per tagged field, for decoding tags.

Each rule file (the data dictionary's 667, `fmparser/tables/rule_files.py`) and each
configured archive member (`comp_<uid>.dat`, `fmparser/tables/comp_rules.py`) is a tagged
tree. This walks every tree and writes one row per field:

    source   'dict' | 'archive'
    file     the rule file's `file` name (`eng_national`)
    uid      the competition uid: the file's top-level `comp` (dictionary) or the member's
             name (archive); NULL for a file with neither
    copy     0, 1, ... for a file name the dictionary holds more than once
    path     the field's place in the tree, list elements indexed: `stgs[0].prmr.nrpl`
    parent   the path of the containing field (`stgs[0].prmr`)
    tag      the field's own tag; NULL for a tagless list element
    type     the type code (`core/types.py`)
    value    the scalar value as text; NULL for a container or list
    n_kids   the child count of a container or list
    fourcc   a u32 value read as a four-character code where all four bytes are printable
             (`id = 1886547314` is 'prmr'), else NULL

Usage:
    uv run python scripts/audit/rule_tags.py <save.fms> --out rule_tags.parquet
    uv run python scripts/audit/rule_tags.py <save.fms> --out rule_tags.duckdb

Query the result with DuckDB; the file is a decoding aid, not a store input.
"""
import argparse
import mmap
import sys
from pathlib import Path
from typing import Any, Iterator, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fmparser.core import archive as A                     # noqa: E402
from fmparser.core.types import TYPE_CONTAINER, TYPE_LIST  # noqa: E402
from fmparser.tables import comp_rules as CR               # noqa: E402
from fmparser.tables import rule_files as RF               # noqa: E402

COLUMNS = ("source", "file", "uid", "copy", "path", "parent", "tag", "type", "value",
           "n_kids", "fourcc")


def fourcc(v: Any) -> Optional[str]:
    """A u32 as its four-character code (stored reversed, so big-endian reads it)."""
    if not isinstance(v, int) or not 0x20202020 <= v <= 0x7e7e7e7e:
        return None
    b = v.to_bytes(4, "big")
    return b.decode("latin-1") if all(0x20 <= x < 0x7f for x in b) else None


def walk(fields: List[Tuple], parent: str = "") -> Iterator[Tuple]:
    """(path, parent, tag, type, value, n_kids, fourcc) for every field, depth first."""
    for i, (tag, typ, val) in enumerate(fields):
        if tag is None:
            path = f"{parent}[{i}]"
        else:
            path = f"{parent}.{tag}" if parent else tag
        if typ in (TYPE_CONTAINER, TYPE_LIST):
            yield path, parent, tag, typ, None, len(val), None
            yield from walk(val, path)
        else:
            if isinstance(val, str):        # control bytes escaped: '\\x00\\x00\\x02\\x00'
                text = val.encode("unicode_escape").decode("ascii")
            else:
                text = repr(val) if isinstance(val, tuple) else str(val)
            yield path, parent, tag, typ, text, None, fourcc(val)


def top(fields: List[Tuple], tag: str) -> Any:
    return next((v for t, _, v in fields if t == tag), None)


def rows(mm: Any) -> Iterator[Tuple]:
    seen: dict = {}
    for b in RF.all_blocks(mm):
        if not RF.is_rule_file(b):
            continue
        name = b.get("file")
        copy = seen.get(name, 0)
        seen[name] = copy + 1
        uid = top(b.fields, "comp")
        for r in walk(b.fields):
            yield ("dict", name, uid if isinstance(uid, int) else None, copy) + r
    for e in A.directory(mm)[1]:
        member = e.name if e.name.endswith(".dat") else f"{e.name}.dat"
        m = CR.MEMBER_PATTERN.match(member)
        if not m:
            continue
        fields = CR.scrape(A.extract(mm, member))
        if not fields:
            continue
        name = top(fields, "file")
        for r in walk(fields):
            yield ("archive", name, int(m.group(1)), 0) + r


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("save")
    ap.add_argument("--out", required=True, help="a .parquet or .duckdb path")
    args = ap.parse_args()
    import csv
    import tempfile
    import duckdb
    with open(args.save, "rb") as f, tempfile.NamedTemporaryFile(
            "w", suffix=".csv", newline="", encoding="utf-8", delete=False) as tmp:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        w = csv.writer(tmp)
        w.writerow(COLUMNS)
        for r in rows(mm):
            w.writerow(["" if x is None else x for x in r])
    con = duckdb.connect(args.out if args.out.endswith(".duckdb") else ":memory:")
    con.execute(f"""CREATE OR REPLACE TABLE rule_tags AS SELECT * FROM read_csv('{tmp.name}',
        header=true, delim=',', quote='"', escape='"', nullstr='', strict_mode=false, columns={{
        'source':'VARCHAR','file':'VARCHAR','uid':'BIGINT','copy':'INTEGER','path':'VARCHAR',
        'parent':'VARCHAR','tag':'VARCHAR','type':'INTEGER','value':'VARCHAR',
        'n_kids':'INTEGER','fourcc':'VARCHAR'}})""")
    Path(tmp.name).unlink()
    if args.out.endswith(".parquet"):
        con.execute(f"COPY rule_tags TO '{args.out}' (FORMAT parquet)")
    n = con.execute("SELECT count(*), count(DISTINCT source || file || copy) FROM rule_tags").fetchone()
    print(f"{n[0]:,} fields from {n[1]} files -> {args.out}")


if __name__ == "__main__":
    main()
