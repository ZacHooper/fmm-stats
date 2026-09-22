#!/usr/bin/env python3
"""Per-byte profile of the world-fixture record -- the check COVERAGE cannot make.

`scripts/audit_records.py` asks "is every byte in [0, stride) named or declared UNKNOWN?".
`world_fixture` passed that from the day it shipped, and it was still hiding a competition key
at +31 inside `Field(16, 25, UNKNOWN, PAD)`. **COVERAGE catches a byte you are stepping over by
accident; it cannot catch a byte you have declared unknown and then stopped looking at.** A
declared-PAD span is a promise to come back, and nothing was measuring whether we had.

So this asks the other question: for every offset, does the DATA look like a field?

Three signals, and the third is the one that found +31:

  DISTINCT   how many values the byte takes. 1 means constant -- real padding. 256 means it is
             the low byte of something wider. Anything in between is a column.

  TOP        the most common values. A 255-dominated byte is a sentinel column, not filler;
             filler does not have a long tail.

  CONST/GRP  how many GROUPS the byte is constant within, for some grouping column. Group by
             the competition key and a byte that is constant in all 409 groups is an attribute
             of the COMPETITION, while one that varies inside groups belongs to the MATCH. That
             split is not visible in any single-byte statistic -- it needs the grouping -- and
             it is what separates the stage attributes (+76/+77/+80/+81/+83) from the per-fixture
             columns (+35/+36, the second date, the second club pair) at a glance.

`--group-by` is therefore the argument that matters. It defaults to the competition key, but
the technique is general: any column you suspect is a record's "which thing does this belong
to" key can be tested by whether OTHER columns go constant under it.

The output is deliberately a table per save and a CROSS-SAVE agreement column, because a
distinct-value count measured on one save of one career is how a career-specific artefact gets
mistaken for structure -- the mistake `regions.py` documents at the top of the file.

    uv run python scripts/profile_fixture_bytes.py                     # the default four saves
    uv run python scripts/profile_fixture_bytes.py <save.fms> ...      # specific saves
    uv run python scripts/profile_fixture_bytes.py --group-by 78       # group by round instead
    uv run python scripts/profile_fixture_bytes.py --wide              # u16/u32 candidates too
"""
import argparse
import collections
import glob
import mmap
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fmparser import archive as A
from fmparser.tables import fixtures as FX
from fmparser.core import PAD, UNKNOWN

# The saves the acceptance gate uses: day one (empty grids), mid-career, the ground-truth
# fixture, and the other career. Same set as scripts/assert_identical.py, for the same reason --
# a structure that holds on all four is structure and not a career's accident.
DEFAULT_SAVES = ["frem-2021-07-01", "frem-2026-06-11", "frem-2026-06-29",
                 "bucaspor-2023-05-20"]

GROUP_KEY_OFFSET = 31         # the competition/stage key; see fixtures.FIXTURE
GROUP_KEY_WIDTH = 4


def _saves_dir():
    return os.environ.get("FM_SAVES_DIR", os.path.expanduser("~/fm-saves"))


def resolve_save(name):
    """A bare label like `frem-2026-06-11` -> its path under FM_SAVES_DIR, or a path as given."""
    if os.path.exists(name):
        return name
    for pat in (os.path.join(_saves_dir(), "*", name + ".fms"),
                os.path.join(_saves_dir(), "*", name)):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[0]
    return None


def records(path):
    """Every 92-byte record in the save's `fix_man`, as a list of bytes objects."""
    with open(path, "rb") as fh:
        mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            blob = A.extract(mm, FX.MEMBER)
        finally:
            mm.close()
    out = []
    for start, count in FX.segments(blob):
        for k in range(count):
            base = start + k * FX.STRIDE
            out.append(blob[base:base + FX.STRIDE])
    return out


def declared():
    """{offset: name} from the parser's own layout -- PAD/UNKNOWN spans map to None.

    Read FROM the declaration rather than retyped, so the profile cannot drift from the
    parser the way a hand-maintained offset table would.
    """
    out = {}
    for f in FX.FIXTURE.fields:
        nm = None if (f.name is UNKNOWN or f.kind == PAD) else f.name
        for o in range(f.offset, f.offset + f.width):
            out[o] = nm
    return out


def group_ids(recs, offset, width):
    fmt = {1: "<B", 2: "<H", 4: "<I"}[width]
    return [struct.unpack_from(fmt, r, offset)[0] for r in recs]


def profile(recs, gkey):
    """[(offset, n_distinct, top3, n_groups_constant)] plus the group count."""
    groups = collections.defaultdict(list)
    for i, g in enumerate(gkey):
        groups[g].append(i)
    rows = []
    for o in range(FX.STRIDE):
        counts = collections.Counter(r[o] for r in recs)
        const = sum(1 for idx in groups.values()
                    if len({recs[i][o] for i in idx}) == 1)
        rows.append((o, len(counts), counts.most_common(3), const))
    return rows, len(groups)


def wide_candidates(recs, gkey):
    """Offsets where a u16/u32 reading is plausible, as a hint -- never as a conclusion.

    Deliberately weak. Adjacent bytes are NOT one field until you show they are, and this
    project has lost two decodes to assuming otherwise (the staff record measured at the player
    record's stride; +78 read as a u32 when it is a u8 beside three separate columns). So this
    reports only the structural precondition -- a low-entropy high byte sitting above a
    high-entropy low byte -- and leaves the claim to a ground-truth check.
    """
    out = []
    for o in range(FX.STRIDE - 1):
        lo = len(collections.Counter(r[o] for r in recs))
        hi = len(collections.Counter(r[o + 1] for r in recs))
        if lo >= 200 and 1 < hi <= 64:
            vals = {struct.unpack_from("<H", r, o)[0] for r in recs}
            out.append((o, lo, hi, len(vals)))
    return out


def report(path, args):
    recs = records(path)
    dec = declared()
    gkey = group_ids(recs, args.group_by, args.group_width)
    rows, n_groups = profile(recs, gkey)

    print(f"\n=== {os.path.basename(path)} ===")
    print(f"{len(recs):,} records x {FX.STRIDE} bytes; "
          f"grouped by u{args.group_width * 8}@+{args.group_by} -> {n_groups:,} groups")
    print(f"\n{'off':>3} {'#val':>5} {'const/grp':>10}  {'declared':<12} top values")
    print("-" * 78)
    for o, ndist, top, const in rows:
        nm = dec.get(o)
        label = nm if nm else "-"
        tops = "  ".join(f"{v}:{n:,}" for v, n in top)
        flag = ""
        if nm is None and ndist > 1:
            # A declared-PAD byte that varies. Constant within every group makes it an
            # attribute of the grouping thing; varying makes it a per-record column. Either
            # way it is data we are not reading.
            flag = " <== STAGE-CONSTANT" if const == n_groups else " <== VARIES"
        print(f"{o:3} {ndist:5} {const:6,}/{n_groups:<6} {label:<12} {tops}{flag}")

    named = sum(1 for o in range(FX.STRIDE) if dec.get(o))
    padvar = sum(1 for o, nd, _, _ in rows if dec.get(o) is None and nd > 1)
    padconst = sum(1 for o, nd, _, _ in rows if dec.get(o) is None and nd == 1)
    print(f"\n  {named} bytes named, {padvar} declared-PAD but VARYING, "
          f"{padconst} declared-PAD and genuinely constant")

    if args.wide:
        print("\n  u16 candidates (high-entropy low byte + low-entropy high byte):")
        for o, lo, hi, nvals in wide_candidates(recs, gkey):
            print(f"    +{o:<3} low={lo:3} high={hi:3} -> {nvals:,} distinct u16")
    return {o: nd for o, nd, _, _ in rows}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("saves", nargs="*", help="save paths or labels (default: the gate's four)")
    ap.add_argument("--group-by", type=int, default=GROUP_KEY_OFFSET,
                    help="offset of the grouping column (default 31, the competition key)")
    ap.add_argument("--group-width", type=int, default=GROUP_KEY_WIDTH, choices=(1, 2, 4))
    ap.add_argument("--wide", action="store_true", help="also report u16 candidates")
    args = ap.parse_args()

    wanted = args.saves or DEFAULT_SAVES
    paths, missing = [], []
    for w in wanted:
        p = resolve_save(w)
        (paths.append(p) if p else missing.append(w))
    if missing:
        print(f"NOTE: not on disk, skipped: {', '.join(missing)}", file=sys.stderr)
    if not paths:
        print("no saves to profile", file=sys.stderr)
        return 2

    per_save = {}
    for p in paths:
        try:
            per_save[os.path.basename(p)] = report(p, args)
        except A.ArchiveError as e:
            print(f"\n=== {os.path.basename(p)} ===\n  no archive: {e}")

    if len(per_save) > 1:
        print("\n=== cross-save agreement ===")
        print("A byte whose distinct-value count swings wildly between saves is career or "
              "era specific.\nOne that holds is structure.\n")
        names = list(per_save)
        print(f"{'off':>3} " + " ".join(f"{n[:18]:>19}" for n in names))
        for o in range(FX.STRIDE):
            vals = [per_save[n].get(o, 0) for n in names]
            if len(set(vals)) == 1 and vals[0] <= 1:
                continue        # constant everywhere: padding, nothing to compare
            print(f"{o:3} " + " ".join(f"{v:>19,}" for v in vals))
    return 0


if __name__ == "__main__":
    sys.exit(main())
