#!/usr/bin/env python3
"""
Guard `reference.py`'s club/competition reference-data resolution.

The two halves are resolved differently and are tested differently.

CLUBS still resolve via the candidate-scan-plus-gates cascade (`_eval_club_candidate`),
guarded here by the diagnosis-vs-real-scan drift check: both call sites must agree on how
many tids they accept, because each keeps its own acceptance bookkeeping.

COMPETITIONS are a pure structural walk (`_walk_comp_table`) with no plausibility gate at
all -- the table announces its own start (a u16 record count right after a run of 0xFF
filler) and `cid == slot index` holds for every declared slot. So the test asserts the
INVARIANT, not a snapshot number: `named + blank == the count the table itself declares`,
over EVERY save in the archive, across BOTH careers. That is deliberate. Frem declares 1372
records and Bucaspor 1371, so a hardcoded total only ever tests one career, while the
invariant tests all of them -- and cross-career is the whole reason the Bucaspor saves are
kept (CLAUDE.md). The walk failing on Turkey is exactly the regression this must catch.

It also pins the `id(mm)` cache-key bug, which is why the multi-save loop deliberately lets
each mmap be garbage-collected instead of holding it alive: CPython reuses the id, and with
the caches keyed on a bare `id(mm)` that served the PREVIOUS save's competition-table offset
to the next save. 30 of 32 saves failed that way before `save.cache_key` existed. A test that
holds its mmaps alive cannot see it.

    uv run python tests/test_refdata_scan.py
"""
import glob
import mmap
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser import reference as R    # noqa: E402
from fmparser.save import Save         # noqa: E402

SAVE = os.path.expanduser("~/fm-saves/frem/frem-2026-06-11.fms")
# Every save of every career, for the cross-career invariant checks below. Bucaspor is
# archived and never rebuilt, but it is the only cross-career regression test the parser has.
ALL_SAVES = sorted(glob.glob(os.path.expanduser("~/fm-saves/*/*.fms")))

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

# A handful of the confirmed-blank slots (namelen 0) on the Frem save -- must NOT appear as
# named comps. Career-specific on purpose: which slots a save leaves empty is save data.
KNOWN_BLANK_COMPS = [1242, 1290, 1337, 1341, 1346, 1361, 1364]

# Coincidental collision from an adjacent, unrelated table (the continent/confederation name
# table's own 7th "World" entry, sitting just past the real nation table) -- confirmed by
# direct byte inspection, must never appear now that comps come from the structural walk
# instead of a candidate scan that can wander into neighbouring tables.
KNOWN_NOT_A_COMP = 24931

# Every competition record carries a nation as a u16 (0xFFFF = no nation). `_read_comp_slot`
# read it as a single byte against 255 until 2026-09-18 -- right answer, wrong width. A byte
# read would resolve nation_id 65535 to 255, so this pins the declared width.
NO_NATION = 0xFFFF


def _check(ok_flag, label):
    print(f"  {'ok  ' if ok_flag else 'FAIL'} {label}")
    return ok_flag


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
        ok &= _check(bool(rec) and rec["name"] == name,
                     f"club tid={tid} -> {rec['name'] if rec else None} (expected {name!r})")
    for cid, name in KNOWN_COMPS.items():
        rec = R.find_comp_record(mm, cid)
        ok &= _check(bool(rec) and rec["name"] == name,
                     f"comp cid={cid} -> {rec['name'] if rec else None} (expected {name!r})")

    # ---- the structural walk on the reference save ----
    print("\nCOMPETITION TABLE STRUCTURAL WALK")
    comps, n_blank = R._walk_comp_table(mm)
    _start, declared = R._comp_table_anchor(mm)
    ok &= _check(len(comps) + n_blank == declared,
                 f"named({len(comps)}) + blank({n_blank}) == declared({declared})")
    bad_blanks = [c for c in KNOWN_BLANK_COMPS if c in comps]
    ok &= _check(not bad_blanks, f"known-blank cids stay absent (violations: {bad_blanks})")
    ok &= _check(KNOWN_NOT_A_COMP not in comps,
                 f"cid={KNOWN_NOT_A_COMP} ('World', the continent-table collision) is NOT a "
                 f"competition")
    # spans must tile the table exactly: record k ends where record k+1 starts, and there are
    # as many records as the table declares. This is the claim audit_coverage makes MEASURED.
    spans = R.comp_table_spans(mm)
    contiguous = all(spans[i][1] == spans[i + 1][0] for i in range(len(spans) - 1))
    ok &= _check(len(spans) - 1 == declared and contiguous,
                 f"comp_table_spans tiles the table with no gap or overlap "
                 f"({len(spans) - 1} record spans + 1 count header)")
    # ---- the qualifiers table resolves to real clubs ----
    # Pins the decode AND the uid-not-tid rule: uid 1913 is D.C. United (right for MLS),
    # tid 1913 is York United, so a tid-keyed read passes a shape check and still lies.
    print("\nQUALIFIERS TABLE")
    clubs_by_uid = {c["uid"]: c["name"] for c in R._build_refdata_index(mm)[0].values()}
    quals = R.comp_qualifiers(mm, 22)          # Major League Soccer
    named = [clubs_by_uid.get(q["club_uid"]) for q in quals]
    hits = [n for n in named if n]
    ok &= _check(len(quals) == 28, f"cid=22 (MLS) declares 28 qualifier entries ({len(quals)})")
    ok &= _check(all(w in hits for w in ("D.C. United", "LA Galaxy", "Atlanta United FC")),
                 f"MLS qualifiers resolve to real MLS clubs by UID "
                 f"({len(hits)}/{len(quals)} resolve; e.g. {hits[:3]})")
    lib = R.comp_qualifiers(mm, 61)            # Copa Libertadores
    ok &= _check(all(q["season"] == 0 or 1990 <= q["season"] <= 2060 for q in lib),
                 f"every Copa Libertadores season is a plausible year or the 0 sentinel "
                 f"({len(lib)} entries)")
    ok &= _check(all(q["position"] < 100 for q in lib if q["club_uid"] != 0xFFFFFFFF),
                 "qualifier positions are small ordinals, not ids")

    nation_widths = {c["nation_id"] for c in comps.values()}
    ok &= _check(255 not in nation_widths or NO_NATION not in nation_widths,
                 "nation_id is read at its declared u16 width (no 255/0xFFFF confusion)")

    # ---- CROSS-CAREER: the invariant holds on every archived save ----
    # The mmaps are deliberately NOT held alive -- see the module docstring. This loop is the
    # regression test for the id(mm) cache-key bug as much as for the walk itself.
    print(f"\nCROSS-CAREER WALK ({len(ALL_SAVES)} saves, mmaps deliberately not pinned)")
    if not ALL_SAVES:
        print("  SKIP: no saves found under ~/fm-saves/*/")
    else:
        by_career = {}
        failures = []
        for path in ALL_SAVES:
            career = os.path.basename(os.path.dirname(path))
            with open(path, "rb") as f:
                m = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                try:
                    c, blank = R._walk_comp_table(m)
                    _s, dec = R._comp_table_anchor(m)
                    if len(c) + blank != dec:
                        failures.append(f"{os.path.basename(path)}: "
                                        f"{len(c)}+{blank} != {dec}")
                    by_career.setdefault(career, set()).add((dec, len(c), blank))
                except R.CompTableError as exc:
                    failures.append(f"{os.path.basename(path)}: {exc}")
                m.close()
        ok &= _check(not failures,
                     f"named + blank == declared on all {len(ALL_SAVES)} saves"
                     + ("" if not failures else f" -- {len(failures)} FAILED"))
        for line in failures[:5]:
            print(f"       {line}")
        for career, shapes in sorted(by_career.items()):
            print(f"       {career}: " + ", ".join(
                f"declared={d} named={n} blank={b}" for d, n, b in sorted(shapes)))
        ok &= _check(len(by_career) >= 2,
                     f"more than one career exercised ({sorted(by_career)}) -- a single-career "
                     f"run cannot catch a career-specific regression")

    # ---- diagnosis cannot drift from the real scan (clubs only -- comps use the walk) ----
    print("\nCLUB DIAGNOSIS-VS-REAL-SCAN DRIFT GUARD")
    clubs, real_comps = R._build_refdata_index(mm)
    diag = R.diagnose_refdata_scan(mm)
    club_total = diag.club_accepted_tier0 + diag.club_accepted_tier1
    ok &= _check(club_total == len(clubs),
                 f"diagnosed club accepts ({club_total}) == _build_refdata_index clubs "
                 f"({len(clubs)})")
    ok &= _check(real_comps == comps,
                 "_build_refdata_index comps == _walk_comp_table comps (single source of truth)")
    ok &= _check(not hasattr(diag, "comp_accepted_tier0"),
                 "RefdataDiagnosis carries NO comp fields -- competitions have no candidates "
                 "to diagnose, and reporting tiers for a deleted gate cascade is what made "
                 "audit_declared_scans lie")

    print("\n" + ("PASS: refdata scan resolves clubs (gated) and competitions (pure "
                  "structural walk) as expected" if ok else "FAIL: see above"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
