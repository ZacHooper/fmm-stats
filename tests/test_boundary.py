#!/usr/bin/env python3
"""The layer boundary: fmparser extracts, warehouse transforms, and neither imports the other's side.

  * nothing under fmparser/, nor extract.py, imports duckdb, fmstats or careers — the parser
    writes JSON, knows no store and no career: a save reads the same whatever career it is;
  * nothing under fmstats/ imports fmparser or extract — it reads the store the loader wrote,
    so it runs anywhere a .duckdb file exists;
  * every var the dbt project (transform/dbt_project.yml) generates its SQL from equals the
    authoritative fmparser constant it mirrors.

The loader (load_duckdb.py), scripts/ and tests/ are the glue and may import both.
Static: parses the source, needs no save and no store.
"""
import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.harness import FAIL, PASS, ROOT                                  # noqa: E402

RULES = {"fmparser": {"duckdb", "fmstats", "careers"},
         "extract.py": {"duckdb", "fmstats", "careers"},
         "fmstats": {"fmparser", "extract", "careers"}}


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
        root = os.path.join(ROOT, pkg)
        paths = ([root] if pkg.endswith(".py") else
                 [os.path.join(d, f) for d, _, files in os.walk(root)
                  for f in files if f.endswith(".py")])
        for p in paths:
            bad += [f"{os.path.relpath(p, ROOT)}:{ln} imports {mod}"
                    for ln, mod in imports(p) if mod in banned]
    for b in bad:
        print(f"  FAIL {b}")
    print(f"  {'FAIL' if bad else 'ok  '} import boundary: {len(bad)} violation(s)")

    from fmparser import model as M
    from fmparser.tables import player_attributes as PA
    from fmparser.tables.player_lists import CLUB_LISTS
    from fmparser.tables import training as TR
    from fmparser.core import primitives as PRIM
    from fmparser.tables import staff as ST

    parser_composites = {
        "Teamwork": (("unselfishness_src", "work_rate"), (0.50, 0.50, 0.0), False),
        "Aerial": (("heading_src", "jumping"), (0.24, 0.76, 0.8), True),
    }

    import yaml
    v = yaml.safe_load(open(os.path.join(ROOT, "fmstats", "dbt_project.yml")))["vars"]
    dbt = [
        ("attr_order", v["attr_order"], list(M.ATTR_ORDER)),
        ("exact_single", list(v["exact_single"]), list(M.EXACT_SINGLE)),
        ("attribute_columns", {int(k): c for k, c in v["attribute_columns"].items()},
         {**PA.SRC_OFFSETS, **PA.PLAIN_OFFSETS, **PA.HIDDEN_OFFSETS}),
        ("hidden_attributes", v["hidden_attributes"], list(PA.HIDDEN_OFFSETS.values())),
        ("composites", {a: (tuple(d["columns"]), tuple(d["w"]), d["estimate"])
                        for a, d in v["composites"].items()}, parser_composites),
        ("positions", list(v["positions"]), list(PA.POSITIONS)),
        ("club_lists", range(v["club_lists"][0], v["club_lists"][1] + 1), CLUB_LISTS),
        ("contracted", v["contracted"], TR.CONTRACTED),
        ("no_id16", v["no_id16"], PRIM.NO_ID16),
        ("no_id32", v["no_id32"], PRIM.NO_ID32),
        ("no_sid", v["no_sid"], PRIM.NO_ID32.to_bytes(4, "little").hex()),
        ("staff_style_bands", tuple(map(tuple, v["staff_style_bands"])), ST._STYLE_BANDS),
        ("staff_tier_bands", tuple(map(tuple, v["staff_tier_bands"])), ST._TIER_BANDS),
    ]
    dbt_differ = [name for name, declared, mirrored in dbt if declared != mirrored]
    for name, _, _ in dbt:
        print(f"  {'FAIL' if name in dbt_differ else 'ok  '} dbt var {name} matches fmparser")
    return FAIL if bad or dbt_differ else PASS


if __name__ == "__main__":
    sys.exit(main())
