#!/usr/bin/env python3
"""The refactor's acceptance gate: prove an extract still produces the SAME BYTES.

The parser refactor moves record decoding onto declared layouts read by a shared reader.
Every one of those commits is supposed to change how a value is read and not what it is, and
the only check that actually establishes that is a byte comparison of the extract's output
against a baseline taken before the change.

Why bytes and not values. `extract.py`'s `dump()` calls `json.dump` with NO `sort_keys`, so
**key order is part of the output**. A generic reader that emits the same fields in a
different order writes a different file. That is not pedantry to be normalised away -- it is
the cheapest possible detector for a migration that quietly re-orders a record, and
`load_duckdb.py` downstream reads some of these files positionally. So the gate is SHA-256 of
each emitted file, key order included.

    uv run python tests/assert_identical.py --record   # take the baseline, before you change anything
    uv run python tests/assert_identical.py            # after a commit: must print IDENTICAL

Four saves, chosen to span the file's regimes rather than to be many:

    frem-2021-07-01       day one -- preallocated grids are EMPTY here, so a walk that depends
                          on rows existing fails on this save and nothing else
    frem-2023-07-02       the day after a July rollover -- 0 matches, transfer band collapsed
    frem-2026-06-11       late career, full grids, and the save every in-game ground truth
                          screenshot was taken against
    bucaspor-2023-03-25   the other career, in another country -- the only guard we have that
                          a decode generalises instead of fitting Denmark

Determinism was measured before this was written (2026-09-20): two extracts of
`frem-2023-07-02` agreed on all 20 emitted files, with `summary.json` differing only by the
`--label` string. The harness therefore passes a FIXED label per save, and a difference in
`summary.json` is a real difference.

The baseline lives in `.oracle/` (gitignored) and records the commit it was taken at, so a
baseline from before an intentional output change reports as STALE rather than as a failure
you have to think about. Phases 4 and 5 of the refactor change output on purpose: re-record
there, in the same commit, and say so in the message.
"""
import argparse
import concurrent.futures
import hashlib
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORACLE_DIR = os.path.join(REPO, ".oracle")
BASELINE = os.path.join(ORACLE_DIR, "baseline.json")
SAVES_DIR = os.environ.get("FM_SAVES_DIR", os.path.expanduser("~/fm-saves"))

# (career key, save basename). The career cannot be derived from the file name in general --
# `careers.py` is the registry -- but our naming convention puts the key first, so this stays
# a list of names rather than a parser.
DEFAULT_SAVES = [
    ("frem", "frem-2021-07-01.fms"),
    ("frem", "frem-2023-07-02.fms"),
    ("frem", "frem-2026-06-11.fms"),
    ("bucaspor", "bucaspor-2023-03-25.fms"),
]


def save_path(career, name):
    return os.path.join(SAVES_DIR, career, name)


def label_for(name):
    return "oracle-" + name[:-len(".fms")] if name.endswith(".fms") else "oracle-" + name


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def extract(career, name, quiet=True):
    """Run extract.py for one save and return {filename: sha256} over everything it wrote."""
    path = save_path(career, name)
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    label = label_for(name)
    dest = os.path.join(REPO, "output", label)
    cmd = [sys.executable, os.path.join(REPO, "extract.py"), path,
           "--career", career, "--label", label]
    r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"extract failed for {name}:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    if not quiet:
        print(r.stdout.strip())
    return {f: sha256(os.path.join(dest, f)) for f in sorted(os.listdir(dest))}


def git_head():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                              capture_output=True, text=True).stdout.strip()
    except Exception:
        return None


def run_all(saves, workers):
    """Extract every save and return {save name: {file: hash}}. Parallel by default: the
    extracts are independent processes over separate mmaps, so the wall clock is one save's
    ~25s rather than four."""
    out = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(extract, c, n): n for c, n in saves}
        for f in concurrent.futures.as_completed(futs):
            name = futs[f]
            out[name] = f.result()
            print(f"  extracted {name}  ({len(out[name])} files)")
    return out


def compare(base, now):
    """Return a list of human-readable difference lines. Empty means identical."""
    diffs = []
    for name in sorted(set(base) | set(now)):
        b, n = base.get(name), now.get(name)
        if b is None:
            diffs.append(f"{name}: NEW save, no baseline")
            continue
        if n is None:
            diffs.append(f"{name}: MISSING from this run")
            continue
        for f in sorted(set(b) | set(n)):
            if f not in b:
                diffs.append(f"{name}/{f}: file is NEW")
            elif f not in n:
                diffs.append(f"{name}/{f}: file DISAPPEARED")
            elif b[f] != n[f]:
                diffs.append(f"{name}/{f}: CHANGED  {b[f][:12]} -> {n[f][:12]}")
    return diffs


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--record", action="store_true",
                    help="take a new baseline instead of comparing against one")
    ap.add_argument("--save", action="append", dest="only",
                    help="limit to one save basename (repeatable) -- faster while iterating, "
                         "but a pass over a subset is NOT the acceptance gate")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--note", default="", help="recorded with a baseline, e.g. why it moved")
    args = ap.parse_args()

    saves = DEFAULT_SAVES
    if args.only:
        saves = [(c, n) for c, n in saves if n in args.only]
        missing = set(args.only) - {n for _, n in saves}
        if missing:
            sys.exit(f"not in the oracle set: {', '.join(sorted(missing))}")
    for c, n in saves:
        if not os.path.exists(save_path(c, n)):
            sys.exit(f"missing save: {save_path(c, n)}\n"
                     f"fetch it with scripts/rebuild.py, or set FM_SAVES_DIR")

    print(f"extracting {len(saves)} saves ({args.workers} at a time)...")
    now = run_all(saves, args.workers)

    if args.record:
        os.makedirs(ORACLE_DIR, exist_ok=True)
        with open(BASELINE, "w") as f:
            json.dump({"commit": git_head(), "note": args.note, "hashes": now}, f, indent=1)
        total = sum(len(v) for v in now.values())
        print(f"\nbaseline recorded: {len(now)} saves, {total} files -> {BASELINE}")
        print(f"  at commit {git_head()}")
        return 0

    if not os.path.exists(BASELINE):
        sys.exit(f"no baseline at {BASELINE} -- run with --record first")
    with open(BASELINE) as f:
        rec = json.load(f)
    # Compare only what we ran. Without this a `--save` subset reports every save it did not
    # extract as MISSING, which reads as four failures when nothing is wrong.
    base = {k: v for k, v in rec["hashes"].items() if k in now} if args.only else rec["hashes"]
    diffs = compare(base, now)
    if not diffs:
        total = sum(len(v) for v in now.values())
        print(f"\nIDENTICAL -- {total} files across {len(now)} saves match the baseline")
        print(f"  baseline taken at {rec.get('commit')}"
              + (f" ({rec['note']})" if rec.get("note") else ""))
        if args.only:
            print(f"  SUBSET ONLY -- {len(rec['hashes']) - len(now)} save(s) not run. "
                  f"Run the full set before you commit.")
        return 0
    print(f"\nDIFFERENT -- {len(diffs)} difference(s) against the baseline "
          f"taken at {rec.get('commit')}:")
    for d in diffs:
        print("  " + d)
    print("\nIf this change was INTENTIONAL, re-record in the same commit that makes it\n"
          "and say so in the message:  scripts/assert_identical.py --record --note '<why>'")
    return 1


if __name__ == "__main__":
    sys.exit(main())
