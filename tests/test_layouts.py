#!/usr/bin/env python3
"""Every declared record layout is sound -- with no save file, in milliseconds.

This is the cheap tier of the parser's test story. The other tests need a 64 MB save and
encode screenshot-verified facts about Frem; this one needs nothing and encodes facts about
the SHAPE of a record. That difference is the point: when FMM26 moves a field, the layouts are
the thing that changes, and a layout that no longer covers its stride should fail here --
instantly, on a clean clone, before anyone goes looking for a save to test against.

Two halves:

  PART 1  `schema.validate()` over every `Record` in the registry. Records auto-register on
          construction, so this covers the whole set by construction rather than by a list
          someone remembers to update.
  PART 2  the checker itself, against synthetic records built to break each rule. A validator
          that has never rejected anything is not evidence, which is the same argument
          `scripts/assert_identical.py` makes about its own red run.

    uv run python tests/test_layouts.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser import records as RD                                        # noqa: E402
from fmparser import schema as SC                                         # noqa: E402
from fmparser.schema import DATE, Field, PAD, Record, U8, U16, U32, UNKNOWN  # noqa: E402

# Importing the record modules is what populates SC.REGISTRY. Added to as Phase 2 migrates
# each record; listed explicitly so an import failure is a test failure rather than a silently
# smaller registry.
RECORD_MODULES = ("matchslots", "places")


def _import_record_modules():
    import importlib
    for name in RECORD_MODULES:
        importlib.import_module(f"fmparser.{name}")


def part1_registry():
    """Every registered layout validates."""
    print("REGISTERED LAYOUTS")
    _import_record_modules()
    if not SC.REGISTRY:
        print("  (registry empty -- no records declared yet; Part 2 still checks the checker)")
        return True
    ok = True
    for name in sorted(SC.REGISTRY):
        rec = SC.REGISTRY[name]
        problems = SC.validate(rec)
        ok &= not problems
        named = sum(f.width for f in rec.fields if not f.alias and f.emits)
        unknown = sum(f.width for f in rec.fields
                      if not f.alias and (f.name is UNKNOWN or f.kind is PAD))
        print(f"  {'ok  ' if not problems else 'FAIL'} {name:<24} span {rec.span:>4}  "
              f"{named} named + {unknown} declared-unknown")
        for p in problems:
            print(f"        {p}")
    return ok


# --------------------------------------------------------------------------------------
# Part 2: each case is (label, record, expected substring in a problem) -- or None for a
# record that must validate clean. Every rule `schema.validate` enforces has a case here.
# --------------------------------------------------------------------------------------
def _cases():
    R = lambda *a, **k: Record(*a, register=False, **k)          # noqa: E731
    return [
        ("sound record validates",
         R("ok", 8, [Field(0, 4, "a", U32), Field(4, 2, "b", U16),
                     Field(6, 2, UNKNOWN, PAD)]),
         None),
        ("a gap is caught",
         R("gap", 8, [Field(0, 4, "a", U32)]),
         "unaccounted"),
        ("an overlap is caught",
         R("ovl", 8, [Field(0, 4, "a", U32), Field(2, 4, "b", U32)]),
         "overlaps"),
        # The check no existing layout could make: `staging._read` ignores `width` for DATE
        # and reads 4 regardless, so a 2-byte DATE declaration passed everything in the repo.
        ("declared width vs kind width is caught",
         R("wk", 4, [Field(0, 2, "d", DATE), Field(2, 2, UNKNOWN, PAD)]),
         "kind date reads 4"),
        ("a field off the end is caught",
         R("oob", 4, [Field(0, 4, "a", U32), Field(4, 1, "b", U8)]),
         "outside"),
        ("a duplicate emitted name is caught",
         R("dup", 4, [Field(0, 2, "a", U16), Field(2, 2, "a", U16)]),
         "duplicate emitted name"),
        ("a field that emits with no kind is caught",
         R("nok", 2, [Field(0, 2, "a", None)]),
         "declares no kind"),
        # An alias re-reads bytes a real field already covers -- how PLAIN_OFFSETS and
        # ATTR_OFFSETS can both be declared over the same nine bytes. It must not become a
        # way to smuggle an undeclared span past the coverage check.
        ("a real alias validates",
         R("al", 4, [Field(0, 4, "whole", U32), Field(0, 1, "first_byte", U8, alias=True)]),
         None),
        # An alias over a PAD is legal: the bytes ARE declared, just not named. This is how a
        # record can carry a second reading of a span it has decided not to name.
        ("an alias over declared-unknown bytes validates",
         R("al2", 4, [Field(0, 2, "a", U16), Field(2, 2, UNKNOWN, PAD),
                      Field(2, 2, "ghost", U16, alias=True)]),
         None),
        ("an alias off the end is caught",
         R("al3", 4, [Field(0, 4, "a", U32), Field(4, 2, "ghost", U16, alias=True)]),
         "does not add them"),
        ("a stride shorter than the span is caught",
         R("str", 8, [Field(0, 4, "a", U32), Field(4, 4, "b", U32)], stride=6),
         "records would overlap"),
        ("an anchor outside the record is caught",
         R("anc", 4, [Field(0, 4, "a", U32)], anchor=9),
         "anchor 9 outside"),
    ]


def part2_checker():
    print("\nTHE CHECKER ITSELF")
    ok = True
    for label, rec, want in _cases():
        problems = SC.validate(rec)
        if want is None:
            good = not problems
            detail = "clean" if good else f"unexpected: {problems}"
        else:
            good = any(want in p for p in problems)
            detail = (f"caught: {[p for p in problems if want in p][0][:70]}" if good
                      else f"NOT caught (problems: {problems})")
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} {label:<46} {detail}")
    return ok


def part3_reader():
    """The reader returns the right values AND the right key order.

    Key order is not a nicety here: `extract.py` dumps without `sort_keys`, so a reader that
    emits in a different order writes different bytes and fails
    `scripts/assert_identical.py`. Asserting `list(d)` rather than `d ==` is what makes that
    a test rather than a hope.
    """
    print("\nTHE READER")
    rec = Record("probe", 12, [
        Field(0, 4, "id", U32),
        Field(4, 2, "code", U16),
        Field(6, 4, "when", DATE),
        Field(10, 1, "flag", U8),
        Field(11, 1, UNKNOWN, PAD),
    ], register=False)
    buf = bytearray(12)
    buf[0:4] = (7).to_bytes(4, "little")
    buf[4:6] = (321).to_bytes(2, "little")
    buf[6:8] = (58).to_bytes(2, "little")        # day-of-year, 0-based -> 28 Feb
    buf[8:10] = (2026).to_bytes(2, "little")
    buf[10] = 3
    buf = bytes(buf)

    ok = True
    got = RD.read(buf, rec, 0)
    checks = [
        ("values", got == {"id": 7, "code": 321, "when": "2026-02-28", "flag": 3},
         str(got)),
        ("PAD is not emitted", "UNKNOWN" not in got and len(got) == 4, str(list(got))),
        ("key order is declaration order",
         list(got) == ["id", "code", "when", "flag"], str(list(got))),
        ("read_fields honours the ORDER IT IS GIVEN, not declaration order",
         list(RD.read_fields(buf, rec, 0, ["flag", "id"])) == ["flag", "id"], ""),
        ("read_into keeps caller keys in front",
         list(RD.read_into({"tid": 1}, buf, rec, 0)) == ["tid", "id", "code", "when", "flag"],
         ""),
        ("read_at_anchor subtracts the anchor",
         RD.read(buf, rec, 0) == RD.read_at_anchor(
             buf, Record("probe2", 12, rec.fields, anchor=4, register=False), 4), ""),
    ]
    for label, good, detail in checks:
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} {label:<58} {detail}")

    # walk over three records, with the table's own invariant supplied by the caller
    grid = buf * 3
    rows = list(RD.walk(grid, rec, 0, len(grid)))
    good = len(rows) == 3 and [o for o, _ in rows] == [0, 12, 24]
    ok &= good
    print(f"  {'ok  ' if good else 'FAIL'} {'walk yields one row per stride':<58} "
          f"{[o for o, _ in rows]}")

    kept = list(RD.walk(grid, rec, 0, len(grid), keep=lambda o, v: o == 12))
    good = len(kept) == 1
    ok &= good
    print(f"  {'ok  ' if good else 'FAIL'} {'walk applies the callers keep predicate':<58} "
          f"{len(kept)} of 3")

    cols = RD.columns(grid, rec, 0, 3, names=["id", "code"])
    good = cols == {"id": [7, 7, 7], "code": [321, 321, 321]} and \
        all(type(v) is int for v in cols["id"])
    ok &= good
    print(f"  {'ok  ' if good else 'FAIL'} "
          f"{'columns reads column-wise and returns builtin ints':<58} {cols}")

    # `columns` has two implementations -- a numpy one for integer kinds and a row-loop
    # fallback for everything else -- and a difference between them would be invisible in
    # normal use. Asking for a DATE forces the fallback; the integer columns must come back
    # the same either way.
    mixed = RD.columns(grid, rec, 0, 3, names=["id", "when"])
    good = mixed == {"id": [7, 7, 7], "when": ["2026-02-28"] * 3} and \
        mixed["id"] == cols["id"]
    ok &= good
    print(f"  {'ok  ' if good else 'FAIL'} "
          f"{'columns fallback path agrees with the numpy path':<58} {mixed['when'][0]}")
    return ok


def main():
    ok = part1_registry() & part2_checker() & part3_reader()
    print("\n" + ("PASS: every declared layout is sound and the checker catches what it must"
                  if ok else "FAIL: see above"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
