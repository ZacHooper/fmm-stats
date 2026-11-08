#!/usr/bin/env python3
"""Check the dbt project's column definitions: one shared doc block per column concept.

    uv run python scripts/check_dbt_docs.py                # dbt parse, then check the yml
    uv run python scripts/check_dbt_docs.py --empty-store  # also check every built column (CI)
    uv run python scripts/check_dbt_docs.py --catalog      # the same, against target/catalog.json
    uv run python scripts/check_dbt_docs.py --renames      # print the rename list as Markdown
    uv run python scripts/check_dbt_docs.py --strict       # a listed synonym fails too

Every column concept is defined once, as a `{% docs <name> %}` block in `fmstats/models/_docs/`
(one file per family), named after the concept's canonical column name. A model's yml points
each column at its block: `description: '{{ doc("club_tid") }}'`, or, for a role on a shared
concept, one sentence and then the block (`'The club he left. {{ doc("club_tid") }}'`).
`dbt parse` records which blocks each column uses (`doc_blocks` in `target/manifest.json`), and
needs no store, so this runs in CI.

It FAILS when:
- a mart or site column has no doc block (with a catalog: also a built column the yml leaves out,
  or a yml column the model doesn't build);
- a doc() names a missing block (dbt parse fails first), or a block is used by no column;
- two columns of one name use different blocks (a listed synonym aside);
- a column's name is not its block's name, nor a role on it (`<role>_<block>`, or
  `<block>_<qualifier>`), nor a listed synonym of it;
- a name breaks the naming convention (docs/plans/2026-11-07-docs-overhaul.html#naming) and is
  not a listed synonym: an abbreviation (CONVENTION_ABBREVIATIONS), a `_a`/`_b` side, `_kind`
  for a category, money (a block in money.md) without `_gbp`; with a catalog, a BOOLEAN column
  not named `is_*`/`has_*` and a DATE column not named `*_date`. A block's own name must keep
  the convention: it is the canonical name.

A block lists the names that drift from it on a line of its own:

    Synonyms: `apps`, `n_games`, `fact_player_season.rating`, `opp_shots` → `opponent_shots`,
    `pos_*` → `familiarity_*`.

An entry is a column name, `model.column` for one model's column only, or a glob (`*`); the
rename target is the block's name unless `→` gives another. A column that uses a listed
synonym is reported as KNOWN, not a failure: the known list is the rename list. `--strict` makes
it a failure, for when the renames are done.

With `--empty-store` it builds an empty store with the whole schema (as scripts/lint_sql.py
does), runs the models into it and generates the catalog, so the built columns are checked
with no data. `--catalog` reads an existing target/catalog.json (`dbt docs generate`).
Exit 0 when nothing fails, 1 otherwise.
"""
import argparse
import fnmatch
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DBT_DIR = os.path.join(ROOT, "fmstats")
DOCS_DIR = os.path.join(DBT_DIR, "models", "_docs")
CHECKED_LAYERS = ("mart", "site")  # every column of these is documented

# Abbreviations the convention spells out ("whole words"); established ids (tid, cid, uid,
# ca, pa, u21) are not here. A token is one `_`-separated part of a name.
CONVENTION_ABBREVIATIONS = {
    "opp": "opponent", "avg": "average", "att": "attendance", "pts": "points",
    "gf": "goals_for", "ga": "goals_against", "est": "estimated", "lvl": "level",
    "pos": "position", "hg": "home_grown", "dob": "birth_date", "apps": "appearances",
}
SIDE_TOKENS = {"a", "b"}            # never _a / _b: home_/away_, or relative to the subject
MONEY_FILE = "money.md"             # a block in this file is money: its name ends _gbp
SYNONYM_LINE = re.compile(r"^\s*Synonyms?:(.*)$", re.M)
SYNONYM_ENTRY = re.compile(r"`([A-Za-z0-9_.*]+)`(?:\s*→\s*`([A-Za-z0-9_*]+)`)?")
DOC_BLOCK = re.compile(r"{%-?\s*docs\s+(\w+)\s*-?%}(.*?){%-?\s*enddocs\s*-?%}", re.S)


def run(cmd, env=None, cwd=DBT_DIR):
    res = subprocess.run(cmd, cwd=cwd, env={**os.environ, **(env or {})},
                         capture_output=True, text=True)
    if res.returncode:
        sys.stdout.write(res.stdout[-4000:] + res.stderr[-4000:])
        sys.exit(f"failed: {' '.join(cmd)}")
    return res


def dbt(*args, target_path, store=None):
    env = {"FM_DUCKDB": store} if store else {}
    return run(["dbt", *args, "--profiles-dir", ".", "--target-path", target_path], env=env)


def build_empty_catalog(target_path):
    """An empty store with the whole schema, the models run into it, and its catalog."""
    tmp = tempfile.mkdtemp(prefix="check_dbt_docs_")
    store = os.path.join(tmp, "schema.duckdb")
    # in a child process: dbt keeps the store open until its process exits
    # the schema and the reference seeds the loader writes before any save (no career: the
    # models that read it build empty)
    run([sys.executable, "-c", "import duckdb, load_duckdb as L; "
         f"con = duckdb.connect({store!r}); L.create_schema(con); "
         "[f(con) for f in (L.seed_role_weights, L.seed_eligible_origin_clubs, "
         "L.seed_reference, L.seed_config_bundle, L.seed_event_types, L.seed_codes)]"],
        cwd=ROOT)
    dbt("run", "--select", "+path:models/mart", "+path:models/site",
        target_path=target_path, store=store)
    dbt("docs", "generate", "--no-compile", target_path=target_path, store=store)
    shutil.rmtree(tmp, ignore_errors=True)


def read_blocks():
    """{block: (file, text, [(pattern, target)])} from fmstats/models/_docs/*.md."""
    blocks = {}
    for path in sorted(glob.glob(os.path.join(DOCS_DIR, "*.md"))):
        text = open(path, encoding="utf-8").read()
        for name, body in DOC_BLOCK.findall(text):
            synonyms = []
            for line in SYNONYM_LINE.findall(body):
                for pattern, target in SYNONYM_ENTRY.findall(line):
                    synonyms.append((pattern, target or name))
            blocks[name] = (os.path.basename(path), body.strip(), synonyms)
    return blocks


def layer_of(node):
    return node["original_file_path"].split("/")[1] if node["original_file_path"].startswith(
        "models/") else None


def tokens(name):
    return name.lower().split("_")


def convention_breaks(name, kind=None, is_money=False):
    """Why a name breaks the convention, [] when it keeps it."""
    why = []
    toks = tokens(name)
    for tok in toks:
        if tok in CONVENTION_ABBREVIATIONS:
            why.append(f"abbreviation '{tok}' ({CONVENTION_ABBREVIATIONS[tok]})")
    if len(toks) > 1 and toks[-1] in SIDE_TOKENS:
        why.append("a side as _a/_b")
    if toks[-1] == "kind":
        why.append("a category is *_type")
    if is_money and toks[-1] != "gbp":
        why.append("money is *_gbp")
    if name == "n":
        why.append("a row count is n_<noun>")
    if kind == "BOOLEAN" and toks[0] not in ("is", "has"):
        why.append("a flag is is_*/has_*")
    if kind == "DATE" and toks[-1] != "date":
        why.append("a date is *_date")
    return why


def synonym_target(blocks, model, column, block_names):
    """The rename target when this column is a listed synonym of one of its blocks."""
    for block in block_names:
        for pattern, target in blocks.get(block, (None, None, []))[2]:
            subject = f"{model}.{column}" if "." in pattern else column
            if fnmatch.fnmatchcase(subject.lower(), pattern.lower()):
                if "*" in pattern and "*" in target:
                    stem = pattern.split(".")[-1]
                    pre, post = stem.split("*", 1)
                    middle = column[len(pre):len(column) - len(post) if post else None]
                    return target.replace("*", middle)
                return target
    return None


def is_role(column, block):
    """`<role>_<block>` or `<block>_<qualifier>`: a role on (or a part of) the block's concept."""
    c, b = column.lower(), block.lower()
    return c == b or c.endswith("_" + b) or c.startswith(b + "_")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--empty-store", action="store_true",
                    help="build an empty store and check every built column")
    ap.add_argument("--catalog", action="store_true",
                    help="check every built column against target/catalog.json")
    ap.add_argument("--strict", action="store_true",
                    help="a column that uses a listed synonym fails")
    ap.add_argument("--renames", action="store_true",
                    help="print the rename list (the known synonyms) as Markdown")
    args = ap.parse_args(argv)

    target = os.path.join(DBT_DIR, "target")
    if args.empty_store:
        target = tempfile.mkdtemp(prefix="check_dbt_docs_target_")
        build_empty_catalog(target)
    else:
        dbt("parse", target_path=target)
    manifest = json.load(open(os.path.join(target, "manifest.json")))
    catalog = None
    if args.empty_store or args.catalog:
        catalog = json.load(open(os.path.join(target, "catalog.json")))

    blocks = read_blocks()
    failures, known = [], defaultdict(set)   # known: (column, target) -> {model}
    used = set()
    by_name = defaultdict(lambda: defaultdict(set))  # column -> blocks -> {model}

    models = {n["name"]: n for n in manifest["nodes"].values() if n["resource_type"] == "model"}
    for model, node in sorted(models.items()):
        layer = layer_of(node)
        checked = layer in CHECKED_LAYERS
        built = {}
        if catalog is not None and checked:
            entry = catalog["nodes"].get(node["unique_id"])
            if entry is None:
                failures.append(f"{model}: not in the catalog (not built?)")
            else:
                built = {c.lower(): (c, col["type"]) for c, col in entry["columns"].items()}
                declared = {c.lower() for c in node["columns"]}
                for c in sorted(set(built) - declared):
                    failures.append(f"{model}.{built[c][0]}: no doc block (not in the yml)")
                for c in sorted(declared - set(built)):
                    failures.append(f"{model}.{c}: in the yml, but the model doesn't build it")
        for column, col in node["columns"].items():
            names = [b.split(".")[-1] for b in col.get("doc_blocks", [])]
            used.update(names)
            if not names:
                if checked:
                    failures.append(f"{model}.{column}: no doc block")
                continue
            for name in names:
                if name not in blocks:
                    failures.append(f"{model}.{column}: doc('{name}') names no block")
            kind = built.get(column.lower(), (None, None))[1]
            if kind:
                kind = kind.upper().split("(")[0]
            renamed = synonym_target(blocks, model, column, names)
            if renamed:
                if checked:
                    known[(column, renamed)].add(model)
                continue
            by_name[column.lower()][tuple(sorted(names))].add(model)
            if not any(is_role(column, n) for n in names):
                failures.append(f"{model}.{column}: named neither as its block ({', '.join(names)})"
                                " nor a role on it, and not a listed synonym")
            money = any(blocks.get(n, ("",))[0] == MONEY_FILE for n in names)
            why = convention_breaks(column, kind, money)
            if why:
                failures.append(f"{model}.{column}: breaks the convention ({'; '.join(why)})"
                                " and is not a listed synonym")

    for column, uses in sorted(by_name.items()):
        if len(uses) > 1:
            detail = "; ".join(f"{'+'.join(b)} in {', '.join(sorted(m))}" for b, m in uses.items())
            failures.append(f"column '{column}' uses different blocks: {detail}")
    for name, (path, _, _) in sorted(blocks.items()):
        if name not in used:
            failures.append(f"_docs/{path}: block '{name}' is used by no column")
        why = convention_breaks(name, is_money=(path == MONEY_FILE))
        if why:
            failures.append(f"_docs/{path}: block '{name}' breaks the convention ({'; '.join(why)})")

    if args.renames:
        print("| column | rename to | models |\n|---|---|---|")
        for (column, renamed), ms in sorted(known.items(), key=lambda kv: (kv[0][1], kv[0][0])):
            print(f"| `{column}` | `{renamed}` | {', '.join(f'`{m}`' for m in sorted(ms))} |")
        return 0

    documented = sum(len(n["columns"]) for n in models.values() if layer_of(n) in CHECKED_LAYERS)
    print(f"{len(blocks)} doc blocks; {documented} mart/site columns documented"
          f"{' (checked against the catalog)' if catalog else ''}")
    if known:
        n = sum(len(ms) for ms in known.values())
        print(f"KNOWN: {n} column(s) use a listed synonym ({len(known)} renames; --renames lists them)")
        for (column, renamed), ms in sorted(known.items(), key=lambda kv: (kv[0][1], kv[0][0])):
            print(f"  {column} -> {renamed}: {', '.join(sorted(ms))}")
    if args.strict:
        failures += [f"{m}.{column}: a listed synonym (rename to {renamed})"
                     for (column, renamed), ms in sorted(known.items()) for m in sorted(ms)]
    for f in failures:
        print(f"FAIL {f}")
    print(f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
