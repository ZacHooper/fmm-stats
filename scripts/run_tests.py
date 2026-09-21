#!/usr/bin/env python3
"""Run every test in `tests/` and report PASS / FAIL / SKIP separately.

There was no runner, and there did not obviously need to be one -- each test is a `main()`
returning 0 or 1 and `for t in tests/test_*.py; do uv run python "$t"; done` runs them. What
that loop cannot do is notice that NOTHING RAN. Every test here is save-dependent, a missing
save returned 0, and so a clean clone printed a wall of SKIP lines and exited green
(docs/TODO.md #15).

So: a skip exits 77 (`tests/harness.py`), and this runner fails when the whole suite skipped.
Green now means something ran.

    uv run python scripts/run_tests.py
    uv run python scripts/run_tests.py -k layouts        # substring filter
    uv run python scripts/run_tests.py -v                # stream each test's own output

Exit codes: 0 all good, 1 something failed, 2 nothing ran at all.
"""
import argparse
import concurrent.futures
import glob
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = 77

UNIT_TESTS = {
    "test_club_comp_unit.py",
    "test_compman_unit.py",
    "test_layouts.py",
    "test_places_unit.py",
    "test_rounds_officials.py",
    "test_staff_unit.py",
    "test_tables.py",
}


def _run_single_test(t, verbose):
    name = os.path.basename(t)
    t0 = time.time()
    r = subprocess.run([sys.executable, t], cwd=ROOT,
                       capture_output=not verbose, text=True)
    dt = time.time() - t0
    return name, dt, r


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-k", dest="filter", help="only tests whose filename contains this")
    ap.add_argument("-u", "--unit", action="store_true",
                    help="run only fast, zero-save-dependency unit tests")
    ap.add_argument("-j", "--jobs", type=int, default=1,
                    help="number of parallel test worker processes (default: 1)")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="stream each test's output instead of only its verdict")
    args = ap.parse_args()

    tests = sorted(glob.glob(os.path.join(ROOT, "tests", "test_*.py")))
    if args.unit:
        tests = [t for t in tests if os.path.basename(t) in UNIT_TESTS]
    if args.filter:
        tests = [t for t in tests if args.filter in os.path.basename(t)]
    if not tests:
        print("no tests matched")
        return 2

    passed, failed, skipped = [], [], []

    if args.jobs > 1 and not args.verbose:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as ex:
            futs = [ex.submit(_run_single_test, t, False) for t in tests]
            results = [f.result() for f in futs]
    else:
        results = [_run_single_test(t, args.verbose) for t in tests]

    for name, dt, r in results:
        if r.returncode == 0:
            passed.append(name)
            verdict, extra = "PASS", ""
        elif r.returncode == SKIP:
            skipped.append(name)
            line = next((ln for ln in (r.stdout or "").splitlines()
                         if ln.startswith("SKIP:")), "")
            verdict, extra = "SKIP", line[len("SKIP:"):].strip()
        else:
            failed.append(name)
            verdict, extra = "FAIL", f"exit {r.returncode}"
        print(f"  {verdict}  {name:<28} {dt:5.1f}s  {extra}")
        if r.returncode not in (0, SKIP) and not args.verbose:
            for ln in (r.stdout or "").splitlines()[-25:]:
                print(f"         | {ln}")
            if r.stderr:
                for ln in r.stderr.splitlines()[-10:]:
                    print(f"         ! {ln}")

    print(f"\n{len(passed)} passed, {len(failed)} failed, {len(skipped)} skipped "
          f"of {len(tests)}")
    if failed:
        print("FAILED: " + ", ".join(failed))
        return 1
    if not passed:
        print("NOTHING RAN -- every test skipped, which is not a pass.\n"
              "  Fetch the saves (scripts/rebuild.py, or drop .fms files in ~/fm-saves/) "
              "and run again.")
        return 2
    if skipped:
        print("Skipped tests did not run. A green line above covers only what executed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
