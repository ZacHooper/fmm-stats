#!/usr/bin/env python3
"""The layer boundary: fmparser extracts, fmstats transforms, and neither imports the other's side.

  * nothing under fmparser/ imports duckdb or fmstats — the parser writes JSON and knows no store;
  * nothing under fmstats/ imports fmparser or extract — it reads the store the loader wrote,
    so it runs anywhere a .duckdb file exists;
  * fmstats.contract.ATTR_ORDER, the attribute columns the mart's SQL is generated from, equals
    fmparser.model.ATTR_ORDER, the list the extract writes.

The loader (load_duckdb.py), scripts/ and tests/ are the glue and may import both.
Static: parses the source, needs no save and no store.
"""
import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.harness import FAIL, PASS, ROOT                                  # noqa: E402

RULES = {"fmparser": {"duckdb", "fmstats"}, "fmstats": {"fmparser", "extract"}}


def imports(path):
    tree = ast.parse(open(path, encoding="utf-8").read(), path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield node.lineno, a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.lineno, node.module.split(".")[0]


def main():
    bad = []
    for pkg, banned in RULES.items():
        for d, _, files in os.walk(os.path.join(ROOT, pkg)):
            for f in files:
                if f.endswith(".py"):
                    p = os.path.join(d, f)
                    bad += [f"{os.path.relpath(p, ROOT)}:{ln} imports {mod}"
                            for ln, mod in imports(p) if mod in banned]
    for b in bad:
        print(f"  FAIL {b}")
    print(f"  {'FAIL' if bad else 'ok  '} import boundary: {len(bad)} violation(s)")

    from fmparser.model import ATTR_ORDER as extracted
    from fmstats.contract import ATTR_ORDER as declared
    same = list(extracted) == list(declared)
    print(f"  {'ok  ' if same else 'FAIL'} fmstats.contract.ATTR_ORDER == fmparser.model.ATTR_ORDER")
    return FAIL if bad or not same else PASS


if __name__ == "__main__":
    sys.exit(main())
