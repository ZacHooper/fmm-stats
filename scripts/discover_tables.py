#!/usr/bin/env python3
"""
Find every WALKABLE table in the save, without knowing what any of them mean.

Background: `scripts/audit_table_headers.py` established that this file frames its tables as
`[8 bytes of 0xFF][record count][record 0]`, and that the count is exact -- the competition,
city, stadium, language, currency, player-attribute, staff-attribute and both name id-tables
all declare theirs. See docs/table-framing.md.

This script uses that convention as a SEARCH strategy. The goal is an inventory: where the
tables are, how many records each holds, how wide a record is. Naming them is a separate job,
done one at a time, and nothing here guesses at meaning.

Two detectors run, because they fail on different tables and neither subsumes the other:

  INDEX  the table is a dense array whose first field IS the slot index. Validated by
         reading `id == k` for every one of the declared records -- with `count` coming from
         the header and `stride` derived from where id 1 and id 2 sit, so the only input is
         the file. This is the strong one: a full-table index check is not something noise
         survives, and it needs no idea what the other bytes are.

  TILE   `count * stride` lands exactly on the NEXT sentinel. Catches fixed-width tables with
         no index field (the player attribute grid is keyed by a sid handle, not an ordinal),
         but it is much weaker on its own -- see docs/table-framing.md for the 5 award-record
         false positives it produces on Frem, where the "stride" is a numeric accident.

WHAT THIS CANNOT FIND, so absence here is not evidence:
  * VARIABLE-LENGTH tables. Competitions, stadiums, languages and currencies are all
    length-prefixed-string records; they have real headers and neither detector sees them,
    because there is no stride to find. Walking those needs a record parser, i.e. the thing
    we are trying to avoid needing.
  * Tables whose index is not dense. The 888-record list at ~13.99 MB has strictly ascending
    but GAPPY ids (1..3221 with 2,333 absent), so INDEX rejects it and only TILE finds it.
  * Anything not introduced by the sentinel convention at all.

Usage:
  uv run python scripts/discover_tables.py [save.fms]        # inventory one save
  uv run python scripts/discover_tables.py --stable          # only what recurs across saves
"""
import collections
import glob
import mmap
import os
import sys

import numpy as np

MIN_COUNT = 8              # below this a "count" is satisfied by chance constantly
MAX_COUNT = 5_000_000
MIN_STRIDE, MAX_STRIDE = 3, 2048
SENTINEL = 8               # the 0xFF run length that introduces a table
# The id field sits at the record's front, but not always at byte 0: the two name id-tables
# put the browse ordinal first and the id at +4. Anything deeper than this is not a header
# field and admitting it would just widen the search for noise.
ID_OFFSETS = (0, 2, 4)
# An index may start at 0 or at 1 -- both occur here (the staff grid is 0-based, the gappy
# 888-record list at ~13.99 MB starts at 1). Requiring 0 alone was leaving 1-based tables to
# the much weaker TILE detector.
ID_BASES = (0, 1)


def _u(mm, o, w):
    return int.from_bytes(mm[o:o + w], "little")


def sentinels(mm):
    """Offsets just past every run of >= SENTINEL 0xFF bytes.

    `>=`, not `== 8`, and that is load-bearing: the sentinel is 8 bytes, but the record in
    front of it can end in 0xFF of its own. Requiring exactly 8 was measured to drop the
    currency table (run of 10) and the first-name id-table (run of 9).
    """
    buf = np.frombuffer(mm, dtype=np.uint8)
    d = np.diff(np.concatenate(([0], (buf == 0xFF).view(np.int8), [0])))
    starts, ends = np.flatnonzero(d == 1), np.flatnonzero(d == -1)
    keep = (ends - starts) >= SENTINEL
    return starts[keep], ends[keep]


class Found(collections.namedtuple("Found", "start hdr count stride how id_off id_w")):
    __slots__ = ()

    @property
    def nbytes(self):
        return self.count * self.stride

    def __str__(self):
        idtxt = (f"id u{self.id_w * 8}@+{self.id_off}" if self.how == "INDEX" else "-")
        return (f"@{self.start:>12,}  {self.count:>8,} x {self.stride:>5}B "
                f"= {self.nbytes:>11,} B  hdr u{self.hdr * 8:<2} {self.how:<6} {idtxt}")


def _index_table(mm, start, count, hdr, n_file):
    """(stride, id_off, id_w) if the records at `start` form a dense index-keyed array.

    The stride is DERIVED, not searched over blindly: slot 0's id must read 0, so the first
    position after it holding 1 at the same relative offset fixes the candidate stride, and
    slot 2 then has to agree before anything expensive runs. Every one of the declared
    records is checked before this returns -- a partial check is how the `id == slot index`
    walks elsewhere in this project ended up short (see docs/table-framing.md on the name
    id-tables, where the invariant breaks at the first free slot).
    """
    for id_w in (4, 2):
        for id_off in ID_OFFSETS:
            base = _u(mm, start + id_off, id_w)
            if base not in ID_BASES:
                continue
            for stride in range(MIN_STRIDE, MAX_STRIDE + 1):
                if start + stride * count > n_file:
                    break
                if _u(mm, start + stride + id_off, id_w) != base + 1:
                    continue
                if count > 2 and _u(mm, start + 2 * stride + id_off, id_w) != base + 2:
                    continue
                if all(_u(mm, start + stride * k + id_off, id_w) == base + k
                       for k in range(count)):
                    return stride, id_off, id_w, base
    return None


def discover(mm):
    """Every table both detectors can find, best evidence first."""
    n_file = len(mm)
    run_starts, run_ends = sentinels(mm)
    starts_arr = run_starts
    out, seen = [], set()
    for i, e in enumerate(run_ends.tolist()):
        nxt = int(starts_arr[i + 1]) if i + 1 < len(starts_arr) else n_file
        counts = [(hdr, _u(mm, e, hdr)) for hdr in (4, 2)]
        counts = [(h, c) for h, c in counts if MIN_COUNT <= c <= MAX_COUNT]
        # INDEX is tried for BOTH header widths before TILE gets a turn. An earlier version
        # broke out of the header loop on the first TILE hit, so a u32 tile coincidence could
        # mask a real u16 index table at the same sentinel.
        hit = None
        for hdr, count in counts:
            idx = _index_table(mm, e + hdr, count, hdr, n_file)
            if idx:
                stride, id_off, id_w, base = idx
                hit = Found(e + hdr, hdr, count, stride, "INDEX", id_off, id_w)
                break
        if hit is None:
            for hdr, count in counts:
                span = nxt - (e + hdr)
                if span > 0 and span % count == 0 \
                        and MIN_STRIDE <= span // count <= MAX_STRIDE:
                    hit = Found(e + hdr, hdr, count, span // count, "TILE", None, None)
                    break
        if hit and (hit.start, hit.stride) not in seen:
            seen.add((hit.start, hit.stride))
            out.append(hit)
    # A table whose RECORDS contain 0xFF runs holds sentinels of its own, so the same table
    # gets re-detected part-way in: the 622-record 99-byte table at ~6.27 MB has a 64-byte FF
    # block inside every record, and turned up a second time as "132 x 99B" starting 97 bytes
    # later (record 0.98), its count read from a day-of-year field. Accept the strongest
    # evidence first and drop anything starting inside an already-accepted span.
    out.sort(key=lambda f: (f.how != "INDEX", -f.nbytes))
    kept = []
    for f in out:
        if any(g.start <= f.start < g.start + g.nbytes for g in kept):
            continue
        kept.append(f)
    return kept


# Tables this project already parses, so the inventory can say what is genuinely NEW. Keyed
# by (count, stride) rather than by offset, because every section drifts per save -- keying
# an earlier version of this on the offset matched nothing at all.
KNOWN_SHAPES = {
    78: "player attributes (staging.scrape_attributes)",
    39: "staff attributes (staff.scrape_staff_attributes)",
    20: "cities (places.scrape_cities)",
    16: "name id-table (reference._discover_id_tables)",
}


def report(save):
    print(f"\n=== {os.path.basename(save)} ===")
    with open(save, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        found = discover(mm)
        idx = [f for f in found if f.how == "INDEX"]
        tile = [f for f in found if f.how == "TILE"]
        print(f"{len(idx)} index-validated tables, {len(tile)} tile-only candidates\n")
        for f in found:
            known = KNOWN_SHAPES.get(f.stride, "")
            print(f"  {f}   {known or '<- unidentified'}")
        mm.close()
    return found


def stable(saves):
    """Only shapes that recur in EVERY save of a career, grouped by section drift.

    Both filters exist because a single save cannot tell a table from a coincidence, and they
    catch different kinds of accident: recurrence kills a one-off numeric fluke, and shared
    drift kills a shape that recurs but lands somewhere unrelated each time (real tables in
    one section move together -- 23,584 bytes across Frem's 27 saves for the attribute
    section, 84,317 for the reference section).
    """
    per = collections.defaultdict(lambda: collections.defaultdict(list))
    for sv in saves:
        career = os.path.basename(os.path.dirname(sv))
        with open(sv, "rb") as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            for fd in discover(mm):
                per[career][(fd.count, fd.stride, fd.how)].append(fd.start)
            mm.close()
        print(f"  scanned {os.path.basename(sv)}", file=sys.stderr)
    n_by = collections.Counter(os.path.basename(os.path.dirname(s)) for s in saves)
    for career, d in per.items():
        total = n_by[career]
        keep = {k: v for k, v in d.items() if len(v) >= total}
        sections = collections.defaultdict(list)
        for (count, stride, how), offs in keep.items():
            sections[max(offs) - min(offs)].append((min(offs), count, stride, how))
        print(f"\n=== {career}: {len(d)} shapes, {len(keep)} in all {total} saves")
        for drift, items in sorted(sections.items(), key=lambda kv: -len(kv[1])):
            tag = ("section" if len(items) > 1 else
                   "LONE DRIFT -- treat as unconfirmed")
            print(f"\n  drift {drift:,} ({tag}):")
            for off, count, stride, how in sorted(items):
                known = KNOWN_SHAPES.get(stride, "")
                print(f"    @{off:>12,}  {count:>8,} x {stride:>5}B "
                      f"= {count * stride:>11,} B  {how:<6} {known or '<- unidentified'}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if "--stable" in sys.argv:
        stable(args or sorted(glob.glob(os.path.expanduser("~/fm-saves/*/*.fms"))))
        return 0
    save = args[0] if args else os.path.expanduser("~/fm-saves/frem/frem-2023-07-02.fms")
    if not os.path.exists(save):
        print(f"SKIP: {save} not found")
        return 0
    report(save)
    return 0


if __name__ == "__main__":
    sys.exit(main())
