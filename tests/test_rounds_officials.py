#!/usr/bin/env python3
"""Test suite for fmparser/rounds.py and fmparser/officials.py."""
import mmap
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser.tables import officials as OF
from fmparser.tables import rounds as RO

SAVES_DIR = os.environ.get("FM_SAVES_DIR", os.path.expanduser("~/fm-saves"))
CASES = [
    ("frem", "frem-2021-07-01.fms", 273, 622),
    ("frem", "frem-2023-07-02.fms", 273, 622),
    ("frem", "frem-2026-06-11.fms", 273, 622),
    ("bucaspor", "bucaspor-2023-03-25.fms", 273, 1109),
]


def test_rounds_and_officials():
    print("TESTING rounds.py AND officials.py ACROSS CAREERS")
    for career, fname, exp_rounds, exp_officials in CASES:
        p = os.path.join(SAVES_DIR, career, fname)
        if not os.path.exists(p):
            print(f"  SKIP {fname} (not on disk)")
            continue

        with open(p, "rb") as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

        # 1. Rounds
        r_info = RO.rounds_table(mm)
        assert r_info is not None, f"{fname}: failed to locate rounds table"
        r_base, r_count = r_info
        assert r_count == exp_rounds, f"{fname}: expected {exp_rounds} rounds, got {r_count}"

        r_list = RO.scrape_rounds(mm)
        assert len(r_list) == exp_rounds, f"{fname}: scraped {len(r_list)} != {exp_rounds}"
        assert r_list[0]["name"] == "Replay", f"{fname}: record 0 should be 'Replay', got {r_list[0]['name']!r}"
        assert r_list[2]["name"] == "First Leg", f"{fname}: record 2 should be 'First Leg'"
        assert r_list[3]["name"] == "Second Leg", f"{fname}: record 3 should be 'Second Leg'"

        # 2. Officials
        o_info = OF.officials_table(mm)
        assert o_info is not None, f"{fname}: failed to locate officials table"
        o_base, o_count = o_info
        assert o_count == exp_officials, f"{fname}: expected {exp_officials} officials, got {o_count}"

        o_list = OF.scrape_officials(mm)
        assert len(o_list) == exp_officials, f"{fname}: scraped {len(o_list)} != {exp_officials}"
        
        # In Frem saves, slot 2 is Mike Dean (TID 444, UID 103857, CA 159, PA 170)
        if career == "frem":
            dean = o_list[2]
            assert dean["slot_id"] == 2
            assert dean["uid"] == 103857
            assert dean["tid"] == 444
            assert dean["ca"] == 159
            assert dean["pa"] == 170
            assert dean["reputation"] == 7950
            assert dean["null_year"] == 1900

        print(f"  PASS {fname:<25} {len(r_list)} rounds, {len(o_list):,} officials")


if __name__ == "__main__":
    test_rounds_and_officials()
