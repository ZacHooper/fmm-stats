#!/usr/bin/env python3
"""Bring a weight-set built in the Attribute Lab back into the repo.

The Lab runs in a browser, which has no R2 credentials and is blocked by the artifact CSP from
reaching the R2 endpoint, so a page cannot publish to R2 itself. Instead the page saves the
weight-set into its own artifact database (or hands you a JSON file), and this script puts it
where the rest of the project can see it:

    page -> artifact db -> (read_db, saved to a file) -> state/weights/<name>.json -> R2
                                                              |
                                                              +-> staging.role_weights (--promote)

`state/weights/` rides the sync `dashboard/state.py` already runs for the shortlist and saved
scouts: one object per entry, collision-free, union-merged across machines.

    uv run python scripts/import_weight_set.py frem_custom_20260912.json
    uv run python scripts/import_weight_set.py set.json --promote        # make it a real method
    uv run python scripts/import_weight_set.py --list                    # what's already stored

After `--promote`, the method exists in the store but the derived views do not know it yet:

    uv run python load_duckdb.py --refresh-only --db fm-frem.duckdb
    uv run python scripts/export_data.py --upload-all      # to reach the web app
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

KIND = "weights"
CAT = {4: "key", 3: "important", 2: "useful"}     # mirrors dashboard/pages/5_Tactics.py
NAME_OK = re.compile(r"^[a-z0-9_]{3,48}$")


def validate(doc):
    """Fail loudly rather than writing a weight-set that silently rates everyone the same."""
    problems = []
    name = doc.get("method", "")
    if not NAME_OK.match(name):
        problems.append(f"method name {name!r} must be 3-48 chars of [a-z0-9_]")
    weights = doc.get("weights")
    if not isinstance(weights, dict) or not weights:
        problems.append("no `weights` object")
        return problems, 0
    cells = 0
    for role, ws in weights.items():
        if not isinstance(ws, dict):
            problems.append(f"role {role!r} is not an object")
            continue
        for attr, w in ws.items():
            if attr != attr.lower():
                problems.append(f"{role}.{attr} must be lowercase")
            if not isinstance(w, int) or w not in (2, 3, 4):
                problems.append(f"{role}.{attr} weight {w!r} must be 2, 3 or 4 "
                                "(1 is the implicit default and is never stored)")
            cells += 1
    if cells == 0:
        problems.append("every weight is 1 — this rates every attribute equally")
    return problems, cells


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file", nargs="?", help="weight-set JSON from the Attribute Lab")
    p.add_argument("--list", action="store_true", help="list the weight-sets already stored")
    p.add_argument("--promote", action="store_true",
                   help="also write it into staging.role_weights as a usable method")
    p.add_argument("--career", default=os.environ.get("FM_CAREER", "frem"))
    p.add_argument("--db")
    a = p.parse_args()

    os.environ["FM_CAREER"] = a.career
    if a.db:
        os.environ["FM_DUCKDB"] = a.db

    from dashboard import state

    if a.list:
        rows = state.entries(KIND)
        if not rows:
            print(f"no weight-sets stored yet (state/{KIND}/)")
            return
        for key, payload in sorted(rows.items()) if isinstance(rows, dict) else rows:
            edited = payload.get("edited_roles") or []
            print(f"  {key:34s} base={payload.get('base_method','?'):22s} "
                  f"edited={','.join(edited) or '—'}  {payload.get('created','')[:10]}")
        return

    if not a.file:
        p.error("give a weight-set JSON file, or --list")

    doc = json.load(open(a.file))
    problems, cells = validate(doc)
    if problems:
        print("REFUSED — the weight-set is not well formed:")
        for x in problems[:12]:
            print("  -", x)
        sys.exit(1)

    name = doc["method"]
    state.put(KIND, name, doc)
    synced = "and pushed to R2" if state.remote_configured() else "(no R2 remote configured)"
    print(f"stored state/{KIND}/{name}.json {synced}")
    print(f"  {cells} weighted cells across {len(doc['weights'])} roles, "
          f"based on {doc.get('base_method','?')}")

    if not a.promote:
        print("\nnot promoted. Re-run with --promote to make it a selectable method.")
        return

    from dashboard import db
    rows = [(name, role, attr, CAT[w], w)
            for role, ws in doc["weights"].items() for attr, w in ws.items()]
    db.write("DELETE FROM staging.role_weights WHERE method=?", [name])
    db._conn().executemany("INSERT INTO staging.role_weights VALUES (?,?,?,?,?)", rows)
    print(f"\npromoted: {len(rows)} rows in staging.role_weights as method '{name}'")
    print("  refresh the derived views so ratings pick it up:")
    print("    uv run python load_duckdb.py --refresh-only")


if __name__ == "__main__":
    main()
