#!/usr/bin/env python3
"""Shared exit-code vocabulary for the test suite.

Every test here is save-dependent by nature, and every one of them handled a missing save the
same way: print `SKIP: ...` and `return 0`. Run the suite on a clean clone and it is green,
having tested nothing (docs/TODO.md #15). The problem is not the skipping -- a save is 64 MB
and lives in R2, so skipping is correct -- it is that a skip and a pass are the same answer.

So a skip exits **77**, the long-standing autotools convention for exactly this. `scripts/
run_tests.py` counts the three outcomes separately and FAILS when nothing actually ran, which
is the case that used to read as success.

    from tests.harness import SKIP, skip
    if not os.path.exists(SAVE):
        return skip(f"{os.path.basename(SAVE)} not found (fetch with rclone or rebuild.py)")
"""
import os

PASS = 0
FAIL = 1
SKIP = 77

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAVES_DIR = os.environ.get("FM_SAVES_DIR", os.path.expanduser("~/fm-saves"))


def skip(reason):
    """Print the reason and return the skip exit code, for `return skip(...)`."""
    print(f"SKIP: {reason}")
    return SKIP


def find_save(*names):
    """The first of `names` that exists, or None.

    Looks in `$FM_SAVES_DIR/<career>/` (deriving the career from our own naming convention,
    `<career>-<YYYY-MM-DD>.fms`) and then in the repo root, which is where saves used to sit
    before `scripts/archive_save.py` existed.

    Both locations on purpose. Three tests looked ONLY in the repo root, for names
    (`21-22-end.fms`, `21-22-mid.fms`) that `scripts/canonicalise_names.py` retired -- so they
    had been skipping on every machine, for however long, and reporting exit 0 while doing it.
    That is the failure this module exists to make visible, and it turned up the moment a skip
    stopped looking like a pass.
    """
    for n in names:
        career = n.split("-", 1)[0] if "-" in n else None
        for cand in ([os.path.join(SAVES_DIR, career, n)] if career else []) + \
                    [os.path.join(SAVES_DIR, n), os.path.join(ROOT, n)]:
            if os.path.exists(cand):
                return cand
    return None
