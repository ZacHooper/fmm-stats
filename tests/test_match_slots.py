#!/usr/bin/env python3
"""
Guard the 25-byte match-slot table: STRIDE, COVERAGE, EXTENT, and the ground truth.

This table was found by dropping an assumption, and the test exists mostly to stop that
assumption creeping back: the record is AWAY-FIRST. Every earlier probe searched for an
oriented home->away club pair and therefore could not have found it, which is why the region
sat unread for months while looking like noise.

The three structural assertions are the ones scripts/audit_records.py makes of every other
record we walk:

  STRIDE    25, and the trailer constant occupies exactly ONE residue class mod 25, by a
            margin over the runners-up that random residues could not produce.
  COVERAGE  every byte in [0, 25) is a named field or an explicit UNKNOWN in the
            declared layout -- checked by schema.validate, the same call
            tests/test_layouts.py makes with no save file at all.
  EXTENT    one contiguous run, and the SLOT COUNT is identical across saves of a career --
            the table is preallocated, so a walk that returns a different count is wrong.

    uv run python tests/test_match_slots.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.harness import skip  # noqa: E402

from fmparser import matchslots as MS      # noqa: E402
from fmparser import primitives as P        # noqa: E402
from fmparser import schema as SC          # noqa: E402
from fmparser import reference as R        # noqa: E402
from fmparser.save import Save             # noqa: E402

SAVES = os.path.expanduser("~/fm-saves/frem")
REF = os.path.join(SAVES, "frem-2026-06-11.fms")

# Slot counts measured per save. Constant within the career; Bucaspor's table is 3,943.
EXPECT_SLOTS = 3975

# Screenshot-verified, from tests/fixtures/light_results_truth.json. day 143 = 2026-05-24.
TRUTH = [
    (404, 518, 0, 5, 143, "Tottenham 5-0 Bournemouth"),
    (471, 523, 2, 0, 143, "West Brom 0-2 Liverpool"),
    # Not in the screenshot set, but independently confirmed by the Club History screen:
    # "Highest scoring match, 3-6 v Newcastle 16/5/2026" -- see tests/test_club_records.py.
    (481, 504, 6, 3, 135, "Southampton 3-6 Newcastle (Club History)"),
]


def main():
    if not os.path.exists(REF):
        return skip(f"{os.path.basename(REF)} not found")
    ok = True
    mm = Save(REF).mm

    # ---- COVERAGE: delegated to schema.validate, which tests/test_layouts.py also runs
    # with no save file. Re-implementing the byte-coverage loop here is what let the three
    # layout dialects drift apart in the first place.
    problems = SC.validate(MS.SLOT)
    named = sum(f.width for f in MS.SLOT.fields if f.emits)
    print("COVERAGE")
    print(f"  {'ok  ' if not problems else 'FAIL'} schema.validate({MS.SLOT.name}): "
          f"{named} bytes named, {MS.STRIDE - named} declared UNKNOWN, span {MS.SLOT.span}")
    for pr in problems:
        print(f"       {pr}")
    ok &= not problems

    # ---- STRIDE: the trailer owns one residue class, by a real margin ----
    buf = mm[:]
    offs, i = [], buf.find(MS.TRAILER)
    while i != -1:
        offs.append(i)
        i = buf.find(MS.TRAILER, i + 1)
    counts = [sum(1 for o in offs if o % MS.STRIDE == r) for r in range(MS.STRIDE)]
    top = max(counts)
    runner = sorted(counts)[-2]
    expect_random = len(offs) / MS.STRIDE
    print("\nSTRIDE")
    print(f"  {'ok  ' if top > runner * 3 else 'FAIL'} trailer on one residue: "
          f"{top:,} vs runner-up {runner:,} (random would give ~{expect_random:,.0f})")
    ok &= top > runner * 3

    # ---- EXTENT: one run, expected slot count, stable across saves ----
    print("\nEXTENT")
    reg = MS.locate(mm)
    if not reg:
        print("  FAIL table not located on the reference save")
        return 1
    lo, hi, n_tr = reg
    slots = (hi - lo) // MS.STRIDE
    good = slots == EXPECT_SLOTS
    ok &= good
    print(f"  {'ok  ' if good else 'FAIL'} {os.path.basename(REF):<24} "
          f"{lo/1e6:.4f}M..{hi/1e6:.4f}M  {slots:,} slots (expected {EXPECT_SLOTS:,}), "
          f"{n_tr:,} trailers")
    for other in ("frem-2026-06-29.fms", "frem-2026-03-22.fms", "frem-2023-07-02.fms"):
        p = os.path.join(SAVES, other)
        if not os.path.exists(p):
            continue
        r2 = MS.locate(Save(p).mm)
        if not r2:
            print(f"  FAIL {other:<24} not located")
            ok = False
            continue
        s2 = (r2[1] - r2[0]) // MS.STRIDE
        g2 = s2 == EXPECT_SLOTS
        ok &= g2
        print(f"  {'ok  ' if g2 else 'FAIL'} {other:<24} "
              f"{r2[0]/1e6:.4f}M..{r2[1]/1e6:.4f}M  {s2:,} slots")

    # ---- the fixture group actually decodes ----
    idx = R._build_refdata_index(mm)[0]
    clubs = set(idx)
    rows = MS.scrape(mm, valid_clubs=clubs)
    raw = MS.scrape(mm)
    resolve = len(rows) / max(1, len(raw))
    print("\nFIXTURE GROUP")
    print(f"  {'ok  ' if resolve > 0.95 else 'FAIL'} {len(raw)} slots carry a club pair; "
          f"{len(rows)} resolve to real clubs ({resolve*100:.1f}%)")
    ok &= resolve > 0.95
    bad = [r for r in rows if r["away_goals"] > 12 or r["home_goals"] > 12]
    bad_day = [r for r in rows if not (1 <= r["day"] <= 366)]
    print(f"  {'ok  ' if not bad else 'FAIL'} no fixture row scores above 12 "
          f"({len(bad)} violations)")
    print(f"  {'ok  ' if not bad_day else 'FAIL'} every fixture row has a valid day-of-year "
          f"({len(bad_day)} violations)")
    ok &= not bad and not bad_day

    # the internal identity: the four i16s hold only three independent numbers
    def i16(o):
        return P.i16(mm, o)
    ident = sum(1 for r in rows
                if i16(r["offset"] + 9) - i16(r["offset"] + 11)
                == i16(r["offset"] + 13) - i16(r["offset"] + 15))
    print(f"  {'ok  ' if ident >= len(rows) - 1 else 'FAIL'} "
          f"(+9 - +11) == (+13 - +15) on {ident}/{len(rows)} rows")
    ok &= ident >= len(rows) - 1

    # ---- NO CID FIELD: pin the negative result, tested the right way ----
    # "does this byte resolve to SOME valid competition" is worthless with 678 real cids
    # packed densely into 0..1400 -- nearly any small value resolves to something by chance.
    # The real test: on a fixture where both clubs share a league (so the correct cid is
    # known independently of the row), does any offset actually EQUAL that cid? A real field
    # would hit ~100% for at least one offset; coincidence tops out under ~10%.
    idx_full, comps = R._build_refdata_index(mm)

    def league_of(tid):
        c = idx_full.get(tid)
        return c.get("league") if c else None

    same_league = [(r, league_of(r["away_tid"])) for r in rows
                   if league_of(r["away_tid"]) is not None
                   and league_of(r["away_tid"]) == league_of(r["home_tid"])]
    max_hit_rate = 0.0
    for off in range(MS.STRIDE):
        for width in (1, 2):
            if off + width > MS.STRIDE:
                continue
            hits = sum(1 for r, lcid in same_league
                       if int.from_bytes(mm[r["offset"] + off:r["offset"] + off + width],
                                          "little") == lcid)
            max_hit_rate = max(max_hit_rate, hits / len(same_league))
    good = max_hit_rate < 0.10
    ok &= good
    print(f"\nNO CID FIELD")
    print(f"  {'ok  ' if good else 'FAIL'} best offset matches its own row's known league cid "
          f"on {max_hit_rate*100:.1f}% of {len(same_league)} same-league fixtures "
          f"(expected <10%, a real field would show ~100%)")

    print("\nGROUND TRUTH (away-first layout)")
    by_pair = {(r["away_tid"], r["home_tid"]): r for r in rows}
    for a, h, ag, hg, day, label in TRUTH:
        r = by_pair.get((a, h))
        good = bool(r) and r["away_goals"] == ag and r["home_goals"] == hg and r["day"] == day
        ok &= good
        got = (f"{r['home_goals']}-{r['away_goals']} day={r['day']}" if r else "not found")
        print(f"  {'ok  ' if good else 'FAIL'} {label:<44} {got}")

    print("\n" + ("PASS: match-slot table matches the bytes and the game"
                  if ok else "FAIL: see above"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
