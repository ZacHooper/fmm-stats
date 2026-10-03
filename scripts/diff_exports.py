#!/usr/bin/env python3
"""Diff two site exports file by file: `export_data.py` (the old marts) against
`export_site.py` (the site marts, data-layers step 17).

    uv run python scripts/diff_exports.py OLD_DIR NEW_DIR
    uv run python scripts/diff_exports.py OLD_DIR NEW_DIR --file core.json --samples 10

Each JSON file is equal, or the report names the keys that differ and, under each, what
differs: a dict's entries, a list's rows (matched on their first slot where the rows are
arrays, so a player row is matched on its tid), or the value. `generated_at` and the byte
counts in index.json always differ and are skipped.

Every difference is a regression or an intended change; `docs/plans/2026-10-03-site-marts.md`
lists the intended ones. Exit 0 when the two are equal, 1 otherwise.
"""
import argparse
import json
import os
import sys

SKIP = {"index.json": ("generated_at", "counts")}


def short(v, n=160):
    s = json.dumps(v, ensure_ascii=False, default=str)
    return s if len(s) <= n else s[:n] + "…"


def keyed(rows):
    """A list of array rows keyed on its first slot, where that is unique."""
    if not rows or not all(isinstance(r, list) and r for r in rows):
        return None
    keys = [json.dumps(r[0]) for r in rows]
    return dict(zip(keys, rows)) if len(set(keys)) == len(keys) else None


def diff_value(path, a, b, out, samples):
    """Append (path, old, new) for each difference below `path`, at most `samples` per
    list or dict, with a count line for the rest."""
    if a == b:
        return 0
    if isinstance(a, dict) and isinstance(b, dict):
        keys = sorted(set(a) | set(b), key=str)
        diffs = [k for k in keys if a.get(k) != b.get(k)]
        if len(diffs) > samples and all(not isinstance(a.get(k), (dict, list)) or
                                        not isinstance(b.get(k), (dict, list))
                                        for k in diffs):
            for k in diffs[:samples]:
                out.append((f"{path}.{k}", a.get(k, "<absent>"), b.get(k, "<absent>")))
            out.append((path, f"{len(diffs)} entries differ", None))
            return len(diffs)
        n = 0
        for i, k in enumerate(diffs):
            if i >= samples and len(diffs) > samples:
                out.append((path, f"{len(diffs)} entries differ", None))
                break
            n += diff_value(f"{path}.{k}", a.get(k, "<absent>"), b.get(k, "<absent>"),
                            out, samples)
        return max(n, len(diffs))
    if isinstance(a, list) and isinstance(b, list):
        ka, kb = keyed(a), keyed(b)
        if ka is not None and kb is not None:
            only_a = [k for k in ka if k not in kb]
            only_b = [k for k in kb if k not in ka]
            changed = [k for k in ka if k in kb and ka[k] != kb[k]]
            if only_a:
                out.append((path, f"{len(only_a)} rows only in old, e.g.",
                            [ka[k] for k in only_a[:samples]]))
            if only_b:
                out.append((path, f"{len(only_b)} rows only in new, e.g.",
                            [kb[k] for k in only_b[:samples]]))
            for k in changed[:samples]:
                ra, rb = ka[k], kb[k]
                slots = [i for i in range(max(len(ra), len(rb)))
                         if (ra[i] if i < len(ra) else None) != (rb[i] if i < len(rb) else None)]
                out.append((f"{path}[{k}] slots {slots}", ra, rb))
            if len(changed) > samples:
                out.append((path, f"{len(changed)} rows differ", None))
            return len(only_a) + len(only_b) + len(changed)
        if len(a) == len(b):
            diffs = [i for i in range(len(a)) if a[i] != b[i]]
            for i in diffs[:samples]:
                out.append((f"{path}[{i}]", a[i], b[i]))
            if len(diffs) > samples:
                out.append((path, f"{len(diffs)} items differ", None))
            return len(diffs)
        out.append((path, f"old {len(a)} items, new {len(b)} items", None))
        return 1
    out.append((path, a, b))
    return 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--file", action="append", help="compare only these files")
    ap.add_argument("--samples", type=int, default=3)
    a = ap.parse_args()

    names = a.file or sorted(n for n in set(os.listdir(a.old)) | set(os.listdir(a.new))
                             if n.endswith(".json"))
    worst = 0
    for name in names:
        pa, pb = os.path.join(a.old, name), os.path.join(a.new, name)
        if not (os.path.exists(pa) and os.path.exists(pb)):
            print(f"{name:20} only in {'old' if os.path.exists(pa) else 'new'}")
            worst = 1
            continue
        da, db = json.load(open(pa, encoding="utf-8")), json.load(open(pb, encoding="utf-8"))
        for k in SKIP.get(name, ()):
            da.pop(k, None)
            db.pop(k, None)
        if da == db:
            print(f"{name:20} equal")
            continue
        worst = 1
        out = []
        keys = sorted(set(da) | set(db)) if isinstance(da, dict) else [None]
        print(f"{name:20} differs")
        for k in keys:
            va, vb = (da.get(k, "<absent>"), db.get(k, "<absent>")) if k else (da, db)
            if va == vb:
                continue
            out.clear()
            n = diff_value(k or "", va, vb, out, a.samples)
            print(f"  {k}: {n} differences")
            for path, old, new in out:
                if new is None:
                    print(f"    {path}: {short(old)}")
                else:
                    print(f"    {path}")
                    print(f"      old {short(old)}")
                    print(f"      new {short(new)}")
    sys.exit(worst)


if __name__ == "__main__":
    main()
