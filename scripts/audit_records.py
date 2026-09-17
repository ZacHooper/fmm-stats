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
from fmparser import staff as ST              # noqa: E402
from fmparser import places as PL             # noqa: E402
from fmparser import staging as S             # noqa: E402


# ---------------------------------------------------------------------------
# Layouts. Offsets are relative to the RECORD START, not to whatever internal
# landmark the parser happens to anchor on -- that difference is the bug in (1).
# Every entry is (offset, width, name). `UNKNOWN` names a byte we have decided we
# cannot yet name; it counts as covered, but it is visible in the report.
# ---------------------------------------------------------------------------
UNKNOWN = "UNKNOWN"


def _player_attr_layout():
    """The global player attribute record, anchored on the SID at P-42.

    Built from the parser's own tables rather than retyped, so the audit cannot drift from
    the code it is auditing: ATTR_OFFSETS and record_tail are the source of truth.
    """
    f = [(0, 4, "sid")]
    for rel, name in A.ATTR_OFFSETS.items():        # P-29 .. P-5, the named attributes
        f.append((42 + rel, 1, name))
    for rel, name in A.HIDDEN_OFFSETS.items():      # the 9 unnamed 1-20 attribute bytes
        f.append((42 + rel, 1, name))
    f += [(42, 15, "positions"), (57, 1, "foot_left"), (58, 1, "foot_right"),
          (59, 2, "ca"), (61, 2, "pa"), (63, 2, "home_reputation"),
          (65, 2, "current_reputation"), (67, 2, "world_reputation"),
          (69, 1, "international_retired"),
          (70, 2, UNKNOWN),                          # P+28..29, "always 0" in FMM26
          (72, 1, "squad_number"), (73, 1, "preferred_squad_number"),
          (74, 2, "height_cm"), (76, 2, "weight_kg")]
    # The ENTANGLED source bytes: 0-255, decoded to a displayed 1-20 value by the frozen model
    # rather than read straight. Not unknown -- `attributes.SRC_OFFSETS` names each one and the
    # store now carries them raw -- so `_src` marks that the byte is the SOURCE of the
    # attribute and not the attribute.
    #
    # Worth noting while here: the frozen model needs a PARTNER byte for exactly two
    # attributes, Aerial (P-29 + P-28) and Shooting (P-31 + P-30). Those are precisely the two
    # that fmm-editor's order says are composites -- Heading + Jumping, Finishing + LongShots.
    # A least-squares fit found that years before anyone read Player.cs.
    for rel, name in A.SRC_OFFSETS.items():
        f.append((42 + rel, 1, name))
    # rel 4..7 is the P-38 history link (docs/agent-context/history-chain-pointers.md).
    f += [(4, 4, "history_link_P38")]
    named = set()
    for off, width, _ in f:
        named.update(range(off, off + width))
    f += [(o, 1, UNKNOWN) for o in range(0, 42) if o not in named]
    return f


def _staff_layout():
    f = [(0, 4, "id2"), (4, 2, "ca"), (6, 2, "pa"), (8, 2, "home_reputation"),
         (10, 2, "current_reputation"), (12, 2, "world_reputation")]
    f += [(o, 1, n) for o, n in ST._ATTRS.items()]
    f += [(o, 1, n) for o, n in ST.HIDDEN_OFFSETS.items()]
    f += [(o, 1, n) for o, n in ST.FORMATION_SLOTS.items()]
    # +14..+30 is seventeen attribute bytes and every one is now carried, so nothing in the
    # block should be left over. If this ever adds an entry again, a byte went unparsed.
    named = {o for o, _, _ in f}
    f += [(o, 1, UNKNOWN) for o in range(14, 31) if o not in named]
    f += [(o, 1, UNKNOWN) for o in range(34, 39)]    # five catalog indices, undecoded
    return f


def _info_head_layout():
    """The INFO (person) record's fixed head -- taken straight from staging.INFO_LAYOUT.

    Not retyped: that table is what `_decode_info` reads from, so the audit is checking the
    parser's own declaration rather than a copy that can rot. The record as a whole is
    variable-length (counted language and relationship lists follow), so there is no stride to
    measure and only the head is covered.
    """
    f = [(off, width, name) for off, width, name, _ in S.INFO_LAYOUT]
    named = set()
    for off, width, _ in f:
        named.update(range(off, off + width))
    f += [(o, 1, UNKNOWN) for o in range(0, S.INFO_HEAD) if o not in named]
    return f


LAYOUTS = {
    "player_attribute": (78, _player_attr_layout()),
    # NOT a stride -- the info record is variable-length; this is the fixed head we decode.
    "info_head": (S.INFO_HEAD, _info_head_layout()),
    "staff_attribute": (39, _staff_layout()),
    "city": (PL.CITY_RECORD, [
        (0, 2, "id"), (2, 4, "uid"), (6, 2, "nation_id"),
        (8, 4, "latitude"), (12, 4, "longitude"),
        (16, 1, "attraction"), (17, 2, "region_id"), (19, 1, UNKNOWN)]),
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

        cities = PL.scrape_cities(mm)
        ok &= _stride("city", [v["offset"] for v in cities.values()], PL.CITY_RECORD)
        ok &= _extent("city", cities.keys())

        stadiums = PL.scrape_stadiums(mm)
        ok &= _extent("stadium", stadiums.keys())

    print("\n" + ("PASS: every record fully accounted for" if ok
                  else "FAIL: see UNACCOUNTED / MISMATCH / CHECK above"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
