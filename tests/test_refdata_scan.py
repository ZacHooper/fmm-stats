#!/usr/bin/env python3
"""
Guard `reference.py`'s club/competition reference-data resolution.

Clubs still resolve via the candidate-scan-plus-gates cascade (`_eval_club_candidate`),
guarded here by the diagnosis-vs-real-scan drift check (both call sites must agree on how
many tids they accept).

Competitions no longer do (2026-09-18): the whole gate cascade (`_eval_comp_candidate`,
retained only as a same-save-family fallback) has been replaced by `_walk_comp_table`, a
PURE structural walk with no plausibility gate at all. The table announces its own start
(a u16 record count sitting right after a run of 0xFF filler, found directly in a hex dump)
and its own extent (cid always equals the walk's own loop index, all 1372 slots on this
save, no exceptions) -- so every record, named or genuinely blank, is read by arithmetic,
never guessed at or filtered. This test pins that walk: the exact total, the named/blank
split, and every competition the gate cascade used to drop before today's fixes.

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

# cid -> expected long name, for competitions that must keep resolving. Includes every
# competition a since-fixed bug used to drop, each annotated with the bug that dropped it.
KNOWN_COMPS = {
    2: "3F Superliga",
    263: "Sydbank Pokalen",
    13: "French Regional Divisions",           # dropped by the old `type` whitelist
    172: "Welsh First Division",               # dropped by the terminator heuristic
                                                 # (empty code following a 0x00 terminator)
    24: "cinch Premiership",                    # dropped by the "starts uppercase" shape gate
    78: "Club World Championship",              # dropped by the Europe-only continent gate
    139: "Confederations Cup",                  # same -- continent==0xFFFF (global) sentinel
    108: "Northern Amateur Football League Premier Division",   # dropped by the 45-char cap
}

# Total record count the table itself declares (a u16 right before cid 0's own record) --
# see _comp_table_anchor. 1272 named + 100 confirmed-genuinely-blank (namelen 0, a
# structured 2,000,000,000+n placeholder uid) == 1372 exactly, on this save.
EXPECT_COMP_TOTAL = 1372
EXPECT_COMP_NAMED = 1272
EXPECT_COMP_BLANK = 100

# A handful of the confirmed-blank slots (namelen 0) -- must NOT appear as named comps.
KNOWN_BLANK_COMPS = [1242, 1290, 1337, 1341, 1346, 1361, 1364]

# Coincidental collision from an adjacent, unrelated table (the continent/confederation name
# table's own 7th "World" entry, sitting just past the real nation table) -- confirmed by
# direct byte inspection, must never appear now that comps come from the structural walk
# instead of a candidate scan that can wander into neighbouring tables.
KNOWN_NOT_A_COMP = 24931


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

    # ---- the pure structural walk: exact counts, no gate involved ----
    print("\nCOMPETITION TABLE STRUCTURAL WALK")
    comps, n_blank = R._walk_comp_table(mm)
    good = comps is not None
    ok &= good
    print(f"  {'ok  ' if good else 'FAIL'} table anchor found (start + declared count)")
    if comps is not None:
        total = len(comps) + n_blank
        good = total == EXPECT_COMP_TOTAL
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} total slots walked: {total} "
              f"(expected {EXPECT_COMP_TOTAL})")
        good = len(comps) == EXPECT_COMP_NAMED and n_blank == EXPECT_COMP_BLANK
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} named={len(comps)} blank={n_blank} "
              f"(expected named={EXPECT_COMP_NAMED} blank={EXPECT_COMP_BLANK})")
        bad_blanks = [c for c in KNOWN_BLANK_COMPS if c in comps]
        good = not bad_blanks
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} known-blank cids stay absent "
              f"(violations: {bad_blanks})")
        good = KNOWN_NOT_A_COMP not in comps
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} cid={KNOWN_NOT_A_COMP} ('World', the "
              f"continent-table collision) is NOT a competition")

    # ---- diagnosis cannot drift from the real scan (clubs only -- comps use the walk) ----
    print("\nCLUB DIAGNOSIS-VS-REAL-SCAN DRIFT GUARD")
    clubs, real_comps = R._build_refdata_index(mm)
    diag = R.diagnose_refdata_scan(mm)
    club_total = diag.club_accepted_tier0 + diag.club_accepted_tier1
    good = club_total == len(clubs)
    ok &= good
    print(f"  {'ok  ' if good else 'FAIL'} diagnosed club accepts ({club_total}) == "
          f"_build_refdata_index clubs ({len(clubs)})")
    good = real_comps == comps
    ok &= good
    print(f"  {'ok  ' if good else 'FAIL'} _build_refdata_index comps == "
          f"_walk_comp_table comps (single source of truth)")

    print("\n" + ("PASS: refdata scan resolves clubs (gated) and competitions (pure "
                  "structural walk) as expected" if ok else "FAIL: see above"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
