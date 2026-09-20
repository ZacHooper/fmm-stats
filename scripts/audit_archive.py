#!/usr/bin/env python3
"""
Prove the tail archive's EXTENT and COUNT from the archive's own invariants, every save.

`fmparser/archive.py` claims the file ends in a named archive of zstd-compressed members.
This is the check behind that claim, and it is deliberately structural — no offset, no
window, no plausibility gate. Per save it asserts:

  CHAIN     walking `[u32 stored][zstd frame]` from the FIRST zstd magic in the file lands
            exactly on a `.fmf` record header, whose declared size ends on the last byte
            of the file. Nothing before, between or after is unaccounted for.
  COUNT     the directory's declared entry count is exact -- reading that many entries
            consumes the directory buffer to within 8 bytes.
  TILING    the entries tile [0, members_size) with no gap and no overlap, and the sum of
            their `stored` sizes equals the measured member area.
  UNPACKED  every member's concatenated frames decompress to EXACTLY its declared size.

    uv sync --extra archive
    uv run python scripts/audit_archive.py                 # every save in ~/fm-saves
    uv run python scripts/audit_archive.py <save.fms>      # one save, with the listing
    uv run python scripts/audit_archive.py --names         # member-name set per career
"""
import argparse
import collections
import glob
import re
import mmap
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fmparser import archive as A        # noqa: E402

# `comp_man.dat` is a named subsystem, not a competition file — match the digits.
_IS_COMP = re.compile(r"comp_\d+\.dat$")

SAVES = os.environ.get("FM_SAVES_DIR", os.path.expanduser("~/fm-saves"))


def audit(path, deep=True):
    """(ok, report-dict) for one save."""
    with open(path, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            start, dhdr, dframe = A.locate(mm)          # CHAIN (raises on failure)
            name, ents = A.directory(mm)                # COUNT (raises on failure)
            area = dhdr - start
            stored = sum(e.stored for e in ents)
            ents_by_off = sorted(ents, key=lambda e: e.offset)
            cursor, holes = 0, 0
            for e in ents_by_off:
                if e.offset != cursor:
                    holes += 1
                cursor = e.offset + e.stored
            unpacked = sum(e.unpacked for e in ents)
            bad = []
            if deep:
                for e in ents:
                    try:
                        A.read_member(mm, e)             # UNPACKED (raises on mismatch)
                    except A.ArchiveError as exc:
                        bad.append(str(exc))
            return True, {
                "path": path, "archive": name, "entries": len(ents),
                "members_start": start, "dir_header": dhdr, "dir_frame": dframe,
                "area": area, "stored": stored, "unpacked": unpacked,
                "tiling_holes": holes, "tail_gap": area - cursor, "bad": bad,
                "names": sorted(e.filename for e in ents),
            }
        except A.ArchiveError as exc:
            return False, {"path": path, "error": str(exc)}
        finally:
            mm.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("save", nargs="?", help="one save; default is every save under FM_SAVES_DIR")
    ap.add_argument("--names", action="store_true", help="report the non-comp member set per career")
    ap.add_argument("--shallow", action="store_true", help="skip the per-member decompression")
    args = ap.parse_args()

    paths = [args.save] if args.save else sorted(glob.glob(os.path.join(SAVES, "*", "*.fms")))
    if not paths:
        print(f"no saves under {SAVES}")
        return 1

    fails, per_career = 0, collections.defaultdict(set)
    for p in paths:
        ok, r = audit(p, deep=not args.shallow)
        base = os.path.basename(p)
        if not ok:
            print(f"FAIL {base:28} {r['error']}")
            fails += 1
            continue
        problems = []
        if r["tiling_holes"]:
            problems.append(f"{r['tiling_holes']} tiling holes")
        if r["stored"] != r["area"]:
            problems.append(f"stored {r['stored']} != member area {r['area']}")
        if r["bad"]:
            problems.append(f"{len(r['bad'])} size mismatches")
        flag = "FAIL" if problems else "ok  "
        fails += bool(problems)
        print(f"{flag} {base:28} {r['archive']:>8} {r['entries']:>4} members  "
              f"stored {r['stored']:>9,}  unpacked {r['unpacked']:>10,}  "
              f"{'; '.join(problems)}")
        career = base.split("-")[0]
        per_career[career].add(tuple(n for n in r["names"] if not _IS_COMP.match(n)))

    if args.names:
        print()
        for career, sets in sorted(per_career.items()):
            print(f"{career}: {len(sets)} distinct non-comp member set(s)")
            for s in sets:
                print("   ", ", ".join(s))

    if args.save and not fails:
        with open(args.save, "rb") as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            print()
            print(A.summary(mm))
            mm.close()

    print(f"\n{len(paths) - fails}/{len(paths)} saves pass")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
