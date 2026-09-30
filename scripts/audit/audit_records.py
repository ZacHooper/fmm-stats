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
  PADDING    every byte declared PAD reads the same on every record a table walk reads. A PAD
             span that varies is data we are not reading: declare it UNKNOWN with a kind
             (RAW) instead, so it counts as undecoded rather than as filler.

Run:  uv run python scripts/audit/audit_records.py [path/to/save.fms]
      uv run python scripts/audit/audit_records.py --map     # print the per-byte schema

Exits non-zero on a failure, so it can gate a merge. Declaring a byte UNKNOWN is a normal,
honest outcome -- the point is that it is written down rather than skipped by accident.
"""
import mmap
import os
import sys
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from fmparser.tables import player_attributes as A          # noqa: E402
from fmparser.tables import staff as ST       # noqa: E402
from fmparser.tables import cities as PL_CITIES, stadiums as PL_STADIUMS  # noqa: E402
from fmparser.tables import currencies, languages, nations  # noqa: E402
from fmparser import clubs_comps as R           # noqa: E402
from fmparser.tables.contracts import CONTRACT_DETAIL  # noqa: E402
from fmparser.tables.person_info import INFO_LAYOUT, scrape_person_info   # noqa: E402
from fmparser.tables.player_attributes import scrape_player_attributes     # noqa: E402
from fmparser.tables import fixtures as FX           # noqa: E402
from fmparser.tables import comp_stages as CS          # noqa: E402
from fmparser.tables import comp_honours as CH         # noqa: E402
from fmparser.tables import comp_rules as CRU          # noqa: E402
from fmparser.tables import rule_files as RF           # noqa: E402
from fmparser import tables as _all_tables                # noqa: E402,F401  (registers every Record)
from fmparser.core import (PAD, REGISTRY, TAGGED_REGISTRY,  # noqa: E402
                           record_instances, tag_map)


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


# Every packed Record registers itself on import (the modules above import them all), so the
# layouts audited are the registry -- never a hand-kept list that a new record can miss.
LAYOUTS = {name: _from_record(rec) for name, rec in REGISTRY.items()}


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


def _table_sources(mm, table, members):
    """The buffers a table is read from: the save, or each of its archive members."""
    if not getattr(table, "member", None):
        yield mm
        return
    from fmparser.core import archive as ARCH
    for name in ARCH.member_names(table.member, members):
        yield ARCH.read_member(mm, members[name])


def _padding(mm):
    """Every PAD span of every record a table walk reads, measured on every instance."""
    from fmparser.core import archive as ARCH
    try:
        members = ARCH.members(mm)
    except (ImportError, ARCH.ArchiveError) as e:
        print(f"  SKIP archive tables: {e} (uv sync --extra archive)")
        members = {}
    values = collections.defaultdict(collections.Counter)    # (record, field) -> values
    count = collections.Counter()
    for table in _all_tables.TABLES.values():
        for buf in _table_sources(mm, table, members):
            for rec, off in record_instances(buf, table):
                count[rec.name] += 1
                for f in rec.fields:
                    if f.kind is PAD:
                        at = off + f.offset
                        values[(rec.name, f.offset, f.width)][bytes(buf[at:at + f.width])] += 1
    ok = True
    for (name, off, width), vals in sorted(values.items()):
        span = f"+{off}" if width == 1 else f"+{off}..{off + width - 1}"
        good = len(vals) == 1
        ok &= good
        top = ", ".join(f"{v.hex()} x{n}" for v, n in vals.most_common(3))
        print(f"  {'ok  ' if good else 'FAIL'} {name:<24} {span:>10}  {count[name]:>7} records, "
              f"{len(vals)} value{'s' if len(vals) > 1 else ''}: {top}")
    unmeasured = sorted(r.name for r in REGISTRY.values()
                        if any(f.kind is PAD for f in r.fields) and r.name not in count)
    if unmeasured:
        print(f"  (not walked by a table, so not measured: {', '.join(unmeasured)})")
    if not ok:
        print("    -> a PAD span that varies is data: declare it UNKNOWN with kind RAW.")
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


# TAGGED records -- key-value, so COVERAGE is per tag rather than per byte: every tag a
# row carries must be read or declared unread, and every required tag present. Every
# TaggedRecord registers itself on import, so the list is the registry, never hand-kept.
TAGGED = tuple(TAGGED_REGISTRY.values())


def _print_tagged(report):
    ok = True
    for rec in TAGGED:
        r = report.get(rec.name)
        if r is None:
            continue
        bad = r["undeclared"] or r["missing"]
        ok &= not bad
        print(f"  {'ok  ' if not bad else 'FAIL'} {rec.name:<32} {r['n']:>6} elements"
              + (f"  UNDECLARED {r['undeclared']}" if r["undeclared"] else "")
              + (f"  MISSING {r['missing']}" if r["missing"] else ""))
    return ok


def _dictionary_coverage(mm):
    """Every rule file of the tagged data dictionary against its declared schema, plus the
    share of the dictionary's span the rule files read."""
    ok = _print_tagged(RF.RULE_FILES_TABLE.coverage(mm))
    t = RF.tiling(mm)
    framing = RF.framing_problems(mm)
    ok &= not t["other_blocks"] and not framing
    print(f"  {'ok  ' if ok else 'FAIL'} {t['n_rule_files']} rule files read "
          f"{t['rule_files']} of {t['span']} bytes; {t['unread']} unread "
          f"({100 * t['unread'] / t['span']:.2f}%), {t['other_blocks']} in unread blocks")
    for p in framing:
        print(f"  FAIL {p}")
    return ok


def _tagged_coverage(mm):
    """Walk every comp_<uid>.dat member of the save against the declared schemas."""
    from fmparser.core import archive as ARCH
    report = {}
    for name, ent in ARCH.members(mm).items():
        if CRU.MEMBER_PATTERN.match(name):
            CRU.COMP_RULES_TABLE.coverage(ARCH.read_member(mm, ent), report)
    return _print_tagged(report)


def main():
    if "--map" in sys.argv:
        for name, (stride, fields) in LAYOUTS.items():
            _print_map(name, stride, fields)
        for rec in TAGGED:
            print()
            print("\n".join(tag_map(rec)))
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
        attrs = scrape_player_attributes(mm)
        ok &= _stride("player_attribute", [v["offset"] for v in attrs.values()], A.RECORD)
        # info_head has no stride to check: variable-length records, only the head is declared
        info = scrape_person_info(mm)
        sa = ST.scrape_staff_attributes(
            mm, (p["id2"] for p in info.values() if p["sid"] == "ffffffff"))
        ok &= _stride("staff_attribute", [r["offset"] for r in sa.values()], 39)

        cities = PL_CITIES.scrape_cities(mm)
        ok &= _stride("city", [v["offset"] for v in cities.values()], PL_CITIES.CITY_RECORD)
        ok &= _extent("city", cities.keys())

        stadiums = PL_STADIUMS.scrape_stadiums(mm)
        ok &= _extent("stadium", stadiums.keys())

        print("\npadding -- every PAD span constant on every record a table reads:")
        ok &= _padding(mm)

        print("\ntagged records (archive comp_<uid>.dat) -- tag coverage:")
        try:
            ok &= _tagged_coverage(mm)
        except ImportError as e:
            print(f"  SKIP: {e} (uv sync --extra archive)")

        print("\ntagged records (data dictionary rule files) -- tag coverage + tiling:")
        ok &= _dictionary_coverage(mm)

    print("\n" + ("PASS: every record fully accounted for" if ok
                  else "FAIL: see UNACCOUNTED / MISMATCH / CHECK / FAIL above"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
