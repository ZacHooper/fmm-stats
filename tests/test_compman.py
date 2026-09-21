#!/usr/bin/env python3
"""Test suite for fmparser/compman.py (comp_man.dat parser)."""
import mmap
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser import archive as A
from fmparser import compman as CM

SAVES_DIR = os.environ.get("FM_SAVES_DIR", os.path.expanduser("~/fm-saves"))
CASES = [
    ("frem", "frem-2021-07-01.fms", 2157),
    ("frem", "frem-2026-06-11.fms", 2316),
    ("frem", "frem-2026-07-02.fms", 2181),
    ("bucaspor", "bucaspor-2023-05-20.fms", 2269),
]


def test_compman_cases():
    print("TESTING comp_man.dat ACROSS CAREERS & SEASONS")
    for career, fname, expected_stages in CASES:
        p = os.path.join(SAVES_DIR, career, fname)
        if not os.path.exists(p):
            print(f"  SKIP {fname} (not on disk)")
            continue

        with open(p, "rb") as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            blob = CM.load_blob(mm)

        hdr = CM.header(blob)
        assert hdr["n_stages"] == expected_stages, f"{fname}: expected {expected_stages}, got {hdr['n_stages']}"

        stg = CM.stages(blob)
        assert len(stg) == expected_stages, f"{fname}: stage count mismatch {len(stg)} != {expected_stages}"

        hon = CM.honours(blob)
        if "2021-07-01" in fname:
            assert len(hon) == 0, f"{fname}: day-one should have 0 honours, got {len(hon)}"
            print(f"  PASS {fname:<25} header ok, {len(stg):,} stages, 0 honours (day one)")
        else:
            assert len(hon) > 100, f"{fname}: expected >100 honours records, got {len(hon)}"
            cids = {h["comp_cid"] for h in hon}
            if career == "frem":
                assert 2 in cids, f"{fname}: Superliga (cid=2) missing from honours"
                assert 5 in cids, f"{fname}: Premier Division (cid=5) missing from honours"
            print(f"  PASS {fname:<25} header ok, {len(stg):,} stages, {len(hon):,} honours across {len(cids)} competitions")


if __name__ == "__main__":
    test_compman_cases()
