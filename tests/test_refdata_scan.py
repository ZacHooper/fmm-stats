#!/usr/bin/env python3
"""
Guard `reference.py`'s club/competition candidate scan against two things: that the
observability refactor (`_eval_club_candidate`/`_eval_comp_candidate`/
`diagnose_refdata_scan`, added alongside docs/TODO.md item #10) never drifts from what
`_build_refdata_index` actually accepts, and that the two known bugs it was built to surface
(the reputation floor, the empty-CODE name-walk abort) keep showing up with a real, non-zero
count rather than silently going back to zero.

The trap this guards against is specific: `_build_refdata_index` and `diagnose_refdata_scan`
each maintain their OWN acceptance bookkeeping (one dict, one set of counters) even though
both call the same `_eval_*_candidate` functions. Nothing stops a future edit to one of
those two call sites from silently disagreeing with the other -- only asserting that their
accepted counts match, every time, catches it.

    uv run python tests/test_refdata_scan.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser import reference as R    # noqa: E402
from fmparser.save import Save         # noqa: E402

SAVE = os.path.expanduser("~/fm-saves/frem/frem-2026-06-11.fms")

# tid -> expected long name, for clubs that must keep resolving.
KNOWN_CLUBS = {
    346: "Boldklubben Frem",       # the managed club -- if this breaks, nothing else works
}

# cid -> expected long name, for competitions that must keep resolving.
KNOWN_COMPS = {
    2: "3F Superliga",
    263: "Sydbank Pokalen",
}


def main():
    if not os.path.exists(SAVE):
        print(f"SKIP: {os.path.basename(SAVE)} not found")
        return 0
    ok = True
    mm = Save(SAVE).mm

    # ---- known resolutions still hold ----
    print("KNOWN RESOLUTIONS")
    for tid, name in KNOWN_CLUBS.items():
        rec = R.club_record(mm, tid)
        good = bool(rec) and rec["name"] == name
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} club tid={tid} -> {rec['name'] if rec else None} "
              f"(expected {name!r})")
    for cid, name in KNOWN_COMPS.items():
        rec = R.find_comp_record(mm, cid)
        good = bool(rec) and rec["name"] == name
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} comp cid={cid} -> {rec['name'] if rec else None} "
              f"(expected {name!r})")

    # ---- diagnosis cannot drift from the real scan ----
    print("\nDIAGNOSIS-VS-REAL-SCAN DRIFT GUARD")
    clubs, comps = R._build_refdata_index(mm)
    diag = R.diagnose_refdata_scan(mm)
    club_total = diag.club_accepted_tier0 + diag.club_accepted_tier1
    good = club_total == len(clubs)
    ok &= good
    print(f"  {'ok  ' if good else 'FAIL'} diagnosed club accepts ({club_total}) == "
          f"_build_refdata_index clubs ({len(clubs)})")
    good = diag.comp_accepted == len(comps)
    ok &= good
    print(f"  {'ok  ' if good else 'FAIL'} diagnosed comp accepts ({diag.comp_accepted}) == "
          f"_build_refdata_index comps ({len(comps)})")

    # ---- the two known bugs keep showing up, not silently fixed or silently zeroed ----
    print("\nKNOWN BUGS STILL SURFACE (docs/TODO.md item #10 -- if these hit 0, the bug")
    print("  was fixed and this assertion should be updated, not deleted)")
    solo_rep = diag.comp_reject_solo_ids[R.COMP_REJECT_REPUTATION_FLOOR]
    good = solo_rep > 0
    ok &= good
    print(f"  {'ok  ' if good else 'FAIL'} {solo_rep} cids solo-rejected by the reputation "
          f"floor (gate < {R._MIN_COMP_REP})")
    slot3 = diag.comp_reject_ids[R.COMP_REJECT_NAME_WALK_SLOT3_EMPTY]
    good = slot3 > 0
    ok &= good
    print(f"  {'ok  ' if good else 'FAIL'} {slot3} cids rejected by the empty-CODE "
          f"name-walk abort")
    # cid 1342 ("Danish Reserves Group 1") is the confirmed, named instance of the
    # empty-CODE bug -- if it ever starts resolving, the bug is fixed; if it disappears
    # from the reject list without resolving, something else broke instead.
    reject_reasons_1342 = [r for _off, cid, r in diag.comp_rejections if cid == 1342]
    resolves_1342 = R.find_comp_record(mm, 1342) is not None
    good = resolves_1342 or any(R.COMP_REJECT_NAME_WALK_SLOT3_EMPTY in r
                                 for r in reject_reasons_1342)
    ok &= good
    print(f"  {'ok  ' if good else 'FAIL'} cid 1342 either resolves now, or is still "
          f"rejected specifically by the empty-CODE bug (not something else)")

    print("\n" + ("PASS: refdata scan diagnosis matches the real scan and known bugs are "
                  "tracked" if ok else "FAIL: see above"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
