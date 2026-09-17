#!/usr/bin/env python3
"""
Guard `reference.py`'s club/competition candidate scan against two things: that the
observability refactor (`_eval_club_candidate`/`_eval_comp_candidate`/
`diagnose_refdata_scan`, added alongside docs/TODO.md item #10) never drifts from what
`_build_refdata_index` actually accepts, and that the two bugs the instrumentation surfaced
(the reputation floor, the empty-CODE name-walk abort) STAY fixed -- both are now fixed in
`reference.py` itself (a tier-1 fill for low-reputation competitions, and accepting a
length-0 short-name/code for name slots 1/2), so this test pins the fix rather than the bug.

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
    comp_total = diag.comp_accepted_tier0 + diag.comp_accepted_tier1
    good = comp_total == len(comps)
    ok &= good
    print(f"  {'ok  ' if good else 'FAIL'} diagnosed comp accepts ({comp_total}) == "
          f"_build_refdata_index comps ({len(comps)})")

    # ---- the two docs/TODO.md item #10 bugs are FIXED -- pin the fix, not the bug ----
    print("\nFIXED BUGS STAY FIXED (docs/TODO.md item #10)")
    # The reputation floor no longer drops a structurally-valid low-reputation competition:
    # it is admitted at tier 1 instead, so a solo reputation-floor reject should never happen.
    solo_rep = diag.comp_reject_solo_ids[R.COMP_REJECT_REPUTATION_FLOOR]
    good = solo_rep == 0
    ok &= good
    print(f"  {'ok  ' if good else 'FAIL'} {solo_rep} cids solo-rejected by the reputation "
          f"floor (gate < {R._MIN_COMP_REP}) -- expected 0, they're tier-1 accepts now")
    # cid 1342 ("Danish Reserves Group 1", Zac's own motivating example) is the confirmed,
    # named instance of the empty-CODE bug -- it and every "Reserves Group" competition must
    # resolve now that a length-0 short-name/code is accepted for slots 1/2.
    rec_1342 = R.find_comp_record(mm, 1342)
    good = bool(rec_1342) and rec_1342["name"] == "Danish Reserves Group 1" and rec_1342["code"] == ""
    ok &= good
    print(f"  {'ok  ' if good else 'FAIL'} comp cid=1342 -> {rec_1342['name'] if rec_1342 else None} "
          f"(expected 'Danish Reserves Group 1' with code=='')")

    print("\n" + ("PASS: refdata scan diagnosis matches the real scan and known bugs are "
                  "tracked" if ok else "FAIL: see above"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
