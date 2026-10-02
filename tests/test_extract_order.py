#!/usr/bin/env python3
"""extract.py's steps are in the order the save stores its tables, on both careers.

  ORDER   every located table's first record sits at or after the end of the table before
          it -- the cursor extract walks with (`extract.steps`), measured here without
          extracting anything, so a step put in the wrong place fails here first
  EMPTY   a table that is not there leaves the cursor where it was (the match table on a
          0-match save, frem-2023-07-02)
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import extract as X                                                   # noqa: E402
from fmparser.save import Save                                        # noqa: E402
from fmparser.tables import save_header as HDR                        # noqa: E402
from tests.harness import FAIL, PASS, sample_saves, skip              # noqa: E402


def check(path):
    print(f"TESTING table order on {os.path.basename(path)}")
    mm = Save(path).mm
    cursor, previous, ok, absent = HDR.SAVE_HEADER.span, "the save header", True, []
    for step in X.steps():
        span = X.located(step, mm)
        if span is None:
            absent.append(step.name)
            continue
        good = span[0] >= cursor and span[1] > span[0]
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} {step.name:<20} {span[0]:>12,} .. {span[1]:>12,}"
              f"{'' if good else f'  (before {previous} ends at {cursor:,})'}")
        cursor, previous = span[1], step.name
    if absent:
        print(f"  not located: {', '.join(absent)}")
    # every table but the match table is in every save; the match table is empty only
    # between the rollover and the first match
    ok &= set(absent) <= {"matches"}
    return ok


def main():
    saves = sample_saves()
    if not saves:
        return skip("no sample saves found (fetch with rclone or rebuild.py)")
    ok = all([check(p) for p in saves])
    print("PASS" if ok else "FAIL")
    return PASS if ok else FAIL


if __name__ == "__main__":
    sys.exit(main())
