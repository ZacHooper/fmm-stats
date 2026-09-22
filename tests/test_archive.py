#!/usr/bin/env python3
"""
Guard the tail archive: LOCATION, COUNT, EXTENT, TILING and the member set.

The claim this test defends is that the last 1-1.6 MB of every save is a named archive of
zstd-compressed members (fmparser/archive.py), not the "most TEXT-dense unparsed span in
the file" the old map called it. The distinction is measurable and this is where it is
measured: high-entropy compressed bytes are 95/256 = 37.1% printable by chance, which is
exactly what that span measures, so a printable-fraction argument cannot tell the two
apart and an entropy + magic-number argument can.

Every assertion is structural. None of them names an offset:

  LOCATE    the first zstd magic in the file opens a `[u32 stored][frame]` chain that ends
            on a `.fmf` record header whose declared size lands on the LAST byte of the
            file. This is the extent proof: nothing before, between or after is stray.
  COUNT     the directory's declared entry count is exact.
  TILING    entries tile the member area with no gap, no overlap, and their `stored` sizes
            sum to the measured area.
  UNPACKED  every member decompresses to exactly its declared size.
  MEMBERS   the twelve named subsystems are present in BOTH careers -- the cross-career
            check that makes this the format's shape rather than Frem's.

    uv sync --extra archive
    uv run python tests/test_archive.py
"""
import mmap
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser import archive as A        # noqa: E402

SAVES = os.environ.get("FM_SAVES_DIR", os.path.expanduser("~/fm-saves"))

# Present in all 34 saves of both careers. `comp_man` is a subsystem, not a competition --
# the per-competition members are `comp_<digits>.dat`, which is why the filter below is on
# the digits and not on the prefix.
NAMED_MEMBERS = {
    "comp_hosts.dat", "comp_man.dat", "discipline.dat", "fifa_rankings.dat",
    "fix_man.dat", "friend_man.dat", "national_teams.dat", "reserves.dat",
    "rgman.dat", "rule_group.dat", "squad_man.dat", "stadium.dat",
}
_IS_COMP = re.compile(r"comp_\d+\.dat$")

# One save per career is enough for the per-member decompression (it is the slow part).
CASES = [("frem", "frem-2026-06-11.fms"), ("bucaspor", "bucaspor-2023-05-20.fms")]


def check(path):
    with open(path, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            start, dhdr, dframe = A.locate(mm)
            assert start < dhdr < dframe < len(mm), (start, dhdr, dframe, len(mm))

            name, ents = A.directory(mm)
            assert name == "sicomps", name
            assert len(ents) > 100, len(ents)

            area = dhdr - start
            assert sum(e.stored for e in ents) == area, (sum(e.stored for e in ents), area)

            cursor = 0
            for e in sorted(ents, key=lambda x: x.offset):
                assert e.offset == cursor, f"{e.filename}: offset {e.offset} != {cursor}"
                cursor += e.stored
            assert cursor == area, (cursor, area)

            for e in ents:                       # raises ArchiveError on a size mismatch
                blob = A.read_member(mm, e)
                assert blob[:6] == A.MEMBER_HEADER, (e.filename, blob[:6])

            names = {e.filename for e in ents}
            missing = NAMED_MEMBERS - names
            assert not missing, f"missing named members: {sorted(missing)}"
            comps = {n for n in names if _IS_COMP.match(n)}
            assert names == NAMED_MEMBERS | comps, sorted(names - NAMED_MEMBERS - comps)
            return len(ents), len(comps), sum(e.unpacked for e in ents)
        finally:
            mm.close()


def main():
    ran = 0
    for career, fname in CASES:
        path = os.path.join(SAVES, career, fname)
        if not os.path.exists(path):
            print(f"SKIP {career}: {path} not present")
            continue
        n, comps, unpacked = check(path)
        print(f"ok  {fname:26} {n} members ({comps} competitions), "
              f"{unpacked:,} B unpacked")
        ran += 1
    if not ran:
        print("SKIP: no saves available — nothing was verified")
        return 0
    print(f"\n{ran} save(s) checked, all assertions hold")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
