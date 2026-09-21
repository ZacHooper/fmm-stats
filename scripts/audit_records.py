#!/usr/bin/env python3
"""
Record-coverage audit: prove we read the WHOLE record, and the WHOLE table.

Every parser bug this repo has hit in the last few rounds is one of three shapes, and none
of them is caught by "the values look right" -- a truncated record decodes its first fields
perfectly:

  1. TRUNCATED RECORD -- we know where a record starts and guess where it ends. The player
     attribute record ran to P+35 and we stopped at P+22, losing height, weight, shirt
     number and two reputations for four years.
  2. MIS-STRIDDEN WALK  -- a `+= stride` sweep across a multi-segment table desynchronises at
     the first segment break and silently drops most of the rows (2 of 7 managers found).
  3. TRUNCATED TABLE    -- the walk is bounded by a tuned constant (a miss counter, a
     plausibility test) rather than by the table's own structure, so the row count is a
     function of the constant. The city walk emitted 3 rows that were not cities and dropped
     31 that were.

This script asserts against all three, from the bytes, on a real save:

  STRIDE     the gap between consecutive record offsets has a single dominant value, and that
             value is the stride we claim. This is the measurement that settled the staff
             record at 39 bytes; it is the cheapest proof that a record ends where we say.
  COVERAGE   every byte in [0, stride) is either decoded into a named field or declared
             UNKNOWN in the layout. A byte that is neither is a byte we are stepping over
             without having decided to -- which is how the record tail went missing.
  EXTENT     a keyed table is contiguous in its own id space. Gaps and overshoot both mean
             the walk's boundary is wrong.

Run:  uv run python scripts/audit_records.py [path/to/save.fms]
      uv run python scripts/audit_records.py --map     # print the per-byte schema

Exits non-zero on a failure, so it can gate a merge. Declaring a byte UNKNOWN is a normal,
honest outcome -- the point is that it is written down rather than skipped by accident.
"""
import mmap
import os
import sys
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser import attributes as A          # noqa: E402
from fmparser.tables import staff as ST       # noqa: E402
from fmparser.tables import cities as PL_CITIES, stadiums as PL_STADIUMS  # noqa: E402
from fmparser import lookups as LK            # noqa: E402
from fmparser import reference as R           # noqa: E402
from fmparser import clubrecords as CR        # noqa: E402
from fmparser import history as H             # noqa: E402
from fmparser import matches as MT            # noqa: E402
from fmparser import staging as S             # noqa: E402
from fmparser import fixtures as FX           # noqa: E402
from fmparser import compman as CM            # noqa: E402


# ---------------------------------------------------------------------------
# Layouts. Offsets are relative to the RECORD START, not to whatever internal
# landmark the parser happens to anchor on -- that difference is the bug in (1).
# Every entry is (offset, width, name). `UNKNOWN` names a byte we have decided we
# cannot yet name; it counts as covered, but it is visible in the report.
# ---------------------------------------------------------------------------
UNKNOWN = "UNKNOWN"


def _from_record(rec):
    """A `fmparser.schema.Record` in this module's `(stride, [(off, width, name)])` shape.

    The audit's own vocabulary predates `schema.py` and drops `kind`, so it stays as it is;
    what matters is that a migrated record is DECLARED ONCE and this reads that declaration.
    `schema.UNKNOWN` is mapped onto the local string so `_coverage` keeps working unchanged.
    """
    return (rec.stride or rec.span,
            [(f.offset, f.width, f.name if f.emits else UNKNOWN)
             for f in rec.fields if not f.alias])


LAYOUTS = {
    # From the parser's declaration. `_from_record` drops alias fields, which is how
    # `PLAIN_OFFSETS` can finally be DECLARED alongside `ATTR_OFFSETS` -- the two name the
    # identical nine bytes, so the old hand-built layout had to omit one of them or trip its
    # own overlap check, and it silently omitted the one the parser reads.
    "player_attribute": _from_record(A.PLAYER),
    # NOT a stride -- the info record is variable-length; this is the fixed head we decode,
    # which is what `Record(is_head=True)` declares.
    "info_head": _from_record(S.INFO_LAYOUT),
    "staff_attribute": _from_record(ST.STAFF),
    # NEW to the audit. This record was read by `matches.decode_block` and audited by
    # nothing -- 29 of its 54 bytes named, the other 25 neither named nor declared, and no
    # entry here at all. Its stride is not measurable the way a grid's is (blocks sit inside
    # a match, found by delimiter, not on a file-wide grid), so COVERAGE is what this buys.
    "match_player_block": _from_record(MT.BLOCK_REC),
    # Also new to the audit. The slab is read COLUMN-WISE with numpy (265,423 rows), so its
    # stride is a property of the locator rather than of a gap histogram -- COVERAGE is the
    # check that matters, and it is what surfaces `+12..+13` as declared-unknown instead of
    # as two bytes nobody had looked at.
    "history_row": _from_record(H.ROW),
    # The Club History tables, both new to the audit. These walk in whole 12-slot BLOCKS --
    # the slot index IS the category, there is no category id in the record -- so the modal
    # gap a STRIDE check measures is the block stride, not the row stride. COVERAGE is the
    # useful part: 21 and 22 bytes, fully claimed.
    "club_team_record": _from_record(CR.TEAM_ROW),
    "club_player_record": _from_record(CR.PLAYER_ROW),
    # Both contract records: found by KEY SEARCH, so neither has a stride and the span is
    # what we read rather than what the record is. The status record's 29 unnamed middle
    # bytes become visible here for the first time.
    "contract_status": _from_record(S.CONTRACT_STATUS),
    "contract_detail": _from_record(S.CONTRACT_DETAIL),
    # The three SEEDED-CHAIN tables (shape E): variable-length records with no count and no
    # index, so each contributes a fixed head and a fixed tail rather than a stride. None of
    # these was in the audit before, which is why the fixed parts were only ever described in
    # prose.
    "stadium_head": _from_record(PL_STADIUMS.STADIUM_HEAD),
    "language_head": _from_record(LK.LANGUAGE_HEAD),
    "language_tail": _from_record(LK.LANGUAGE_TAIL),
    "currency_head": _from_record(LK.CURRENCY_HEAD),
    "currency_tail": _from_record(LK.CURRENCY_TAIL),
    "nation_head": _from_record(LK.NATION_HEAD),
    "nation_tail": _from_record(LK.NATION_TAIL),
    # Read FROM the parser's own declaration rather than retyped here. This entry used to be
    # a second, hand-maintained copy of the same 8 fields -- the exact drift the audit exists
    # to prevent, sitting inside the audit.
    "city": _from_record(PL_CITIES.CITY),
    # NOT strides -- variable-length names precede the trailer and a variable-length entries
    # array sits inside the part after it. Together these four cover the competition record
    # in full, in file order:
    #   [cid u16][uid u32]
    #   [len u32][long name][1 terminator][len u32][short name][1 terminator][len u32][code]
    #   comp_trailer            14
    #   comp_ref_count           4   -> n_refs
    #   comp_ref_entry           8   x n_refs
    #   comp_history_tail       21
    # = 25 + 8 * n_refs after the code name, which is exactly what
    # reference._walk_comp_table steps by -- and scripts/audit_coverage.py claims the whole
    # table MEASURED per record on the strength of it.
    "comp_trailer": _from_record(R.COMP_TRAILER),
    "comp_ref_count": _from_record(R.COMP_REF_COUNT),
    "comp_ref_entry": _from_record(R.COMP_REF_ENTRY),
    "comp_history_tail": _from_record(R.COMP_HISTORY_TAIL),
    # From the save's zstd ARCHIVE, not the save body -- the only entry here that is, so the
    # STRIDE and EXTENT checks below cannot reach it (they walk the mmap) and COVERAGE is the
    # whole point. 13 of its 92 bytes are named and the other 79 are declared UNKNOWN in one
    # place, which is the honest statement of where that record stands: the goals block and
    # the round counter are deliberately unread, not overlooked.
    "world_fixture": _from_record(FX.FIXTURE),
    "comp_man_header": _from_record(CM.HEADER),
    "comp_man_stage": _from_record(CM.STAGE),
    "comp_man_honour": _from_record(CM.HONOUR),
}


def _coverage(name, stride, fields):
    """Every byte in [0, stride) accounted for?"""
    owner = [None] * stride
    clash = []
    for off, width, fname in fields:
        for b in range(off, off + width):
            if not (0 <= b < stride):
                clash.append(f"{fname} byte {b} outside [0,{stride})")
                continue
            if owner[b] is not None and owner[b] != fname:
                clash.append(f"byte {b}: {owner[b]} vs {fname}")
            owner[b] = fname
    gaps = [b for b in range(stride) if owner[b] is None]
    unknown = sorted({owner[b] for b in range(stride) if owner[b] == UNKNOWN})
    n_unknown = sum(1 for b in range(stride) if owner[b] == UNKNOWN)
    ok = not gaps and not clash
    print(f"  COVERAGE {name}: stride {stride}, "
          f"{stride - len(gaps) - n_unknown} named + {n_unknown} declared-unknown "
          f"+ {len(gaps)} UNACCOUNTED")
    for c in clash:
        print(f"    OVERLAP {c}")
    if gaps:
        print(f"    UNACCOUNTED BYTES {gaps}")
        print("    -> name them, or declare them UNKNOWN in LAYOUTS. A byte that is neither "
              "is a byte we are stepping over by accident.")
    return ok


def _stride(name, offsets, claimed):
    """Does the gap between consecutive records actually equal the claimed stride?"""
    offs = sorted(offsets)
    if len(offs) < 50:
        print(f"  STRIDE   {name}: only {len(offs)} records, not measuring")
        return True
    gaps = collections.Counter(b - a for a, b in zip(offs, offs[1:]))
    modal, hits = gaps.most_common(1)[0]
    frac = hits / (len(offs) - 1)
    # the rest should be small MULTIPLES of the stride (a skipped record), not noise
    multiples = sum(c for g, c in gaps.items() if g and g % claimed == 0)
    ok = modal == claimed and frac > 0.5
    print(f"  STRIDE   {name}: modal gap {modal} ({frac:.1%} of {len(offs)-1} gaps), "
          f"{multiples/(len(offs)-1):.1%} are multiples of {claimed} "
          f"-- claimed {claimed} {'OK' if ok else 'MISMATCH'}")
    return ok


def _extent(name, ids):
    """A keyed table should be contiguous in its own id space."""
    ids = sorted(ids)
    lo, hi = ids[0], ids[-1]
    missing = sorted(set(range(lo, hi + 1)) - set(ids))
    ok = not missing and lo == 0
    print(f"  EXTENT   {name}: {len(ids)} rows, ids {lo}..{hi}, "
          f"{len(missing)} gaps {'OK' if ok else 'CHECK'}")
    if missing:
        print(f"    gaps: {missing[:20]}{' ...' if len(missing) > 20 else ''}")
        print("    -> a gap is either a real hole in the save or a row the walk dropped. "
              "Decide which; do not leave it to a tolerance constant.")
    return ok


def _print_map(name, stride, fields):
    """The per-byte schema, UNKNOWN rows included. This is the record documentation:
    generated from the layouts the parser actually uses, so it cannot go stale."""
    print(f"\n{name}  ({stride} bytes)")
    print(f"  {'offset':>10}  {'width':>5}  field")
    for off, width, fname in sorted(fields):
        span = f"+{off}" if width == 1 else f"+{off}..{off + width - 1}"
        flag = "   <-- undecoded" if fname == UNKNOWN else ""
        print(f"  {span:>10}  {width:>5}  {fname}{flag}")
    n_unk = sum(w for _, w, n in fields if n == UNKNOWN)
    print(f"  -- {stride - n_unk} of {stride} bytes decoded, {n_unk} undecoded")


def main():
    if "--map" in sys.argv:
        for name, (stride, fields) in LAYOUTS.items():
            _print_map(name, stride, fields)
        return 0
    save = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
        "~/fm-saves/frem/frem-2024-11-10.fms")
    if not os.path.exists(save):
        print(f"SKIP: {save} not found (fetch with rclone or scripts/rebuild.py)")
        return 0
    print(f"auditing {os.path.basename(save)}\n")
    ok = True

    print("static layout checks (no save needed):")
    for name, (stride, fields) in LAYOUTS.items():
        ok &= _coverage(name, stride, fields)
    print()

    with open(save, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

        print("measured against the save:")
        attrs = S.scrape_attributes(mm)
        ok &= _stride("player_attribute", [r["P"] for r in attrs.values()], 78)

        info = S.scrape_players(mm)
        sa = ST.scrape_staff_attributes(
            mm, (p["id2"] for p in info.values() if p["sid"] == "ffffffff"))
        ok &= _stride("staff_attribute", [r["offset"] for r in sa.values()], 39)

        cities = PL_CITIES.scrape_cities(mm)
        ok &= _stride("city", [v["offset"] for v in cities.values()], PL_CITIES.CITY_RECORD)
        ok &= _extent("city", cities.keys())

        stadiums = PL_STADIUMS.scrape_stadiums(mm)
        ok &= _extent("stadium", stadiums.keys())

    print("\n" + ("PASS: every record fully accounted for" if ok
                  else "FAIL: see UNACCOUNTED / MISMATCH / CHECK above"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
