#!/usr/bin/env python3
"""Check stage key stability across different saves."""
import collections
import glob
import mmap
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fmparser import archive as A
from fmparser.tables import fixtures as FX

SAVES_DIR = os.environ.get("FM_SAVES_DIR", os.path.expanduser("~/fm-saves"))

def get_club_fixtures(save_path, club_tid):
    with open(save_path, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        blob = A.extract(mm, "fix_man.dat")
        recs = []
        for start, count in FX.segments(blob):
            for k in range(count):
                base = start + k * FX.STRIDE
                h = struct.unpack_from("<I", blob, base + 41)[0]
                a = struct.unpack_from("<I", blob, base + 47)[0]
                if h == club_tid or a == club_tid:
                    sk = struct.unpack_from("<I", blob, base + 31)[0]
                    day_raw = struct.unpack_from("<H", blob, base + 53)[0]
                    yr = struct.unpack_from("<H", blob, base + 55)[0]
                    rnd = blob[base + 78]
                    recs.append((yr, (day_raw % 512) - FX.DAY_BASE, h, a, sk, rnd))
        return recs

def main():
    # Let's compare Liverpool (471) and Man City (473) across saves:
    # frem-2026-06-11, frem-2026-06-29, frem-2026-07-02
    saves = ["frem-2026-06-11.fms", "frem-2026-06-29.fms", "frem-2026-07-02.fms", "frem-2023-06-26.fms"]
    print("Checking stage key agreement across saves for common matches...")
    all_fixtures = {}
    for s in saves:
        p = os.path.join(SAVES_DIR, "frem", s)
        if os.path.exists(p):
            mancity = get_club_fixtures(p, 473)
            # key matches by (yr, day, h, a)
            all_fixtures[s] = {(r[0], r[1], r[2], r[3]): (r[4], r[5]) for r in mancity}
            print(f"{s}: {len(all_fixtures[s])} Man City fixtures")

    # Check matches common between frem-2026-06-11 and frem-2026-07-02
    s1 = "frem-2026-06-11.fms"
    s2 = "frem-2026-07-02.fms"
    if s1 in all_fixtures and s2 in all_fixtures:
        common = set(all_fixtures[s1].keys()) & set(all_fixtures[s2].keys())
        print(f"\nCommon matches between {s1} and {s2}: {len(common)}")
        mismatches = 0
        for m in common:
            sk1, rnd1 = all_fixtures[s1][m]
            sk2, rnd2 = all_fixtures[s2][m]
            if sk1 != sk2 or rnd1 != rnd2:
                mismatches += 1
                print(f"  Mismatch on match {m}: s1=(sk={sk1}, rnd={rnd1}) vs s2=(sk={sk2}, rnd={rnd2})")
        if mismatches == 0:
            print("PERFECT MATCH: 100% agreement on stage_key and round across saves for the same matches!")

    # Now let's check frem-2023-06-26 vs frem-2026-06-11 for the SAME competition stages
    # In 2022/23: What stage_key did Premier Division, FA Cup, Carabao have?
    s3 = "frem-2023-06-26.fms"
    if s3 in all_fixtures:
        print(f"\nAnalyzing Man City stages in {s3}:")
        f3 = all_fixtures[s3]
        stages_by_rnd = collections.defaultdict(set)
        for (yr, day, h, a), (sk, rnd) in f3.items():
            stages_by_rnd[(yr, sk)].add(rnd)
        for (yr, sk), rnds in sorted(stages_by_rnd.items()):
            print(f"  Year {yr} sk={sk:4d}: {len(rnds)} rounds ({sorted(list(rnds))[:5]}...)")

if __name__ == "__main__":
    main()
