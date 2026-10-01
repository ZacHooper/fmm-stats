#!/usr/bin/env python3
"""The layer boundary: fmparser extracts, fmstats transforms, and neither imports the other's side.

  * nothing under fmparser/ imports duckdb or fmstats — the parser writes JSON and knows no store;
  * nothing under fmstats/ imports fmparser or extract — it reads the store the loader wrote,
    so it runs anywhere a .duckdb file exists;
  * every constant in fmstats.contract (the attribute columns, the record's byte names, the
    composite weights, the position order, the squad lists) equals the fmparser constant it
    mirrors;
  * every var the dbt project (transform/dbt_project.yml) generates its SQL from equals the
    fmstats.contract constant it mirrors.

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

    from fmparser import model as M
    from fmparser.tables import player_attributes as PA
    from fmparser.tables.player_lists import CLUB_LISTS
    from fmparser.tables import training as TR
    from fmstats import contract as C
    pairs = [
        ("ATTR_ORDER", list(C.ATTR_ORDER), list(M.ATTR_ORDER)),
        ("EXACT_SINGLE", set(C.EXACT_SINGLE), set(M.EXACT_SINGLE)),
        ("SRC_OFFSETS", C.SRC_OFFSETS, PA.SRC_OFFSETS),
        ("PLAIN_OFFSETS", C.PLAIN_OFFSETS, PA.PLAIN_OFFSETS),
        ("HIDDEN_OFFSETS", C.HIDDEN_OFFSETS, PA.HIDDEN_OFFSETS),
        ("COMPOSITES weights", {a: w for a, (_, w, _) in C.COMPOSITES.items()},
         {"Teamwork": M.TEAMWORK_W, "Aerial": M.AERIAL_W}),
        ("POSITIONS", list(C.POSITIONS), list(PA.POSITIONS)),
        ("CLUB_LISTS", C.CLUB_LISTS, CLUB_LISTS),
        ("CONTRACTED", C.CONTRACTED, TR.CONTRACTED),
    ]
    differ = [name for name, declared, extracted in pairs if declared != extracted]
    for name, _, _ in pairs:
        print(f"  {'FAIL' if name in differ else 'ok  '} fmstats.contract.{name} matches fmparser")

    import yaml
    v = yaml.safe_load(open(os.path.join(ROOT, "transform", "dbt_project.yml")))["vars"]
    dbt = [
        ("attr_order", v["attr_order"], list(C.ATTR_ORDER)),
        ("exact_single", list(v["exact_single"]), list(C.EXACT_SINGLE)),
        ("attribute_columns", {int(k): c for k, c in v["attribute_columns"].items()},
         {**C.SRC_OFFSETS, **C.PLAIN_OFFSETS, **C.HIDDEN_OFFSETS}),
        ("hidden_attributes", v["hidden_attributes"], list(C.HIDDEN_OFFSETS.values())),
        ("composites", {a: (tuple(d["bytes"]), tuple(d["w"]), d["estimate"])
                        for a, d in v["composites"].items()}, C.COMPOSITES),
        ("positions", list(v["positions"]), list(C.POSITIONS)),
        ("club_lists", range(v["club_lists"][0], v["club_lists"][1] + 1), C.CLUB_LISTS),
        ("contracted", v["contracted"], C.CONTRACTED),
        ("wage_gbp_per_unit", v["wage_gbp_per_unit"], C.WAGE_GBP_PER_UNIT),
    ]
    dbt_differ = [name for name, declared, mirrored in dbt if declared != mirrored]
    for name, _, _ in dbt:
        print(f"  {'FAIL' if name in dbt_differ else 'ok  '} dbt var {name} matches fmstats.contract")
    return FAIL if bad or differ or dbt_differ else PASS


if __name__ == "__main__":
    sys.exit(main())
