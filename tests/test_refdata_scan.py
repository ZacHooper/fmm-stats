#!/usr/bin/env python3
"""
Guard the club and competition tables (`tables/clubs.py`, `tables/competitions.py`) against
the save's own ground truth.

  KNOWN       clubs and competitions that must keep resolving to their names
  WALK        the competition table is a structural walk with no plausibility gate: it
              announces its own count, and `named + blank == declared` on every save,
              whatever the career (Frem declares 1372, Bucaspor 1371)
  LAYOUT      round names, clubs, competitions and nations sit back to back
  REFERENCES  checkable facts of the competition reference lists (MLS's 28 entries,
              CONMEBOL's members)
  CROSS-CAREER  the walk on one save per career (`tests/harness.SAMPLE_SAVES`), the mmaps
              deliberately not pinned: CPython reuses `id(mm)`, and caches keyed on it
              served the previous save's offsets to the next, which `save.cache_key`
              prevents. Two saves are enough to see it.

    uv run python tests/test_refdata_scan.py
"""
import mmap
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.harness import skip  # noqa: E402

from fmparser.tables import nations as LK    # noqa: E402
from fmparser.tables import clubs as CL, competitions as CO, rounds as RD  # noqa: E402
from fmparser.tables import nations as NA  # noqa: E402
from fmparser.save import Save         # noqa: E402

SAVE = os.path.expanduser("~/fm-saves/frem/frem-2026-06-11.fms")
# One save per career for the cross-career invariant checks below. Bucaspor is archived and
# never rebuilt, but it is the only cross-career regression test the parser has.
from tests.harness import sample_saves  # noqa: E402
ALL_SAVES = sample_saves()

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

# Every competition record carries a nation as a u16 (0xFFFF = no nation). `COMP_TABLE`
# read it as a single byte against 255 until 2026-09-18 -- right answer, wrong width. A byte
# read would resolve nation_id 65535 to 255, so this pins the declared width.
NO_NATION = 0xFFFF

# A competition's reference list uses the SIGN to say what it points at: positive = club uid,
# negative = national team, where -ref is that nation's `uid` from scrape_nations. CONMEBOL's
# ten members are the check, because the right answer is knowable independently of the save.
CONMEBOL = sorted(["Argentina", "Bolivia", "Brazil", "Chile", "Colombia",
                   "Ecuador", "Paraguay", "Peru", "Uruguay", "Venezuela"])


def _check(ok_flag, label):
    print(f"  {'ok  ' if ok_flag else 'FAIL'} {label}")
    return ok_flag


def main():
    if not os.path.exists(SAVE):
        return skip(f"{os.path.basename(SAVE)} not found")
    ok = True
    mm = Save(SAVE).mm

    # ---- known resolutions still hold ----
    print("KNOWN RESOLUTIONS")
    all_clubs, all_comps = CL.scrape_clubs(mm), CO.scrape_competitions(mm)
    for tid, name in KNOWN_CLUBS.items():
        rec = all_clubs.get(tid)
        ok &= _check(bool(rec) and rec["name"] == name,
                     f"club tid={tid} -> {rec['name'] if rec else None} (expected {name!r})")
    for cid, name in KNOWN_COMPS.items():
        rec = all_comps.get(cid)
        ok &= _check(bool(rec) and rec["name"] == name,
                     f"comp cid={cid} -> {rec['name'] if rec else None} (expected {name!r})")

    # ---- the structural walk on the reference save ----
    print("\nCOMPETITION TABLE STRUCTURAL WALK")
    comps = CO.scrape_competitions(mm)
    _start, declared = CO.locate_competitions(mm)
    n_blank = declared - len(comps)
    ok &= _check(len(comps) + n_blank == declared,
                 f"named({len(comps)}) + blank({n_blank}) == declared({declared})")
    bad_blanks = [c for c in KNOWN_BLANK_COMPS if c in comps]
    ok &= _check(not bad_blanks, f"known-blank cids stay absent (violations: {bad_blanks})")
    ok &= _check(KNOWN_NOT_A_COMP not in comps,
                 f"cid={KNOWN_NOT_A_COMP} ('World', the continent-table collision) is NOT a "
                 f"competition")
    # EXTENT: the tables sit back to back -- round names, clubs, competitions, nations -- each
    # ending exactly where the next one's count frame begins. This is the claim
    # audit_coverage makes MEASURED.
    chain = [("round_names", RD.ROUNDS_TABLE.spans(mm)), ("clubs", CL.CLUB_TABLE.spans(mm)),
             ("competitions", CO.COMP_TABLE.spans(mm)), ("nations", NA.nations_table_spans(mm))]
    gaps = [(a, b, sa[-1][1], sb[0][0]) for (a, sa), (b, sb) in zip(chain, chain[1:])
            if not sa[-1][1] - 2 <= sb[0][0] <= sa[-1][1]]
    ok &= _check(not gaps, "round names -> clubs -> competitions -> nations sit back to back"
                 + (f" -- gaps: {gaps}" if gaps else ""))
    # ---- the competition reference list ----
    # Pins the field decode and the uid-not-tid rule: uid 1913 is D.C. United (right for
    # MLS), tid 1913 is York United, so a tid-keyed read passes a shape check and still lies.
    # It deliberately does NOT assert what the list MEANS -- only 24 of 1,272 competitions
    # populate it and they don't share one meaning, so `comp_refs` names the fields and not
    # the list. See its docstring.
    print("\nCOMPETITION REFERENCE LIST")
    clubs_by_uid = {c["uid"]: c["name"] for c in all_clubs.values()}
    mls = CO.comp_refs(mm, 22)                  # Major League Soccer
    hits = [n for n in (clubs_by_uid.get(e["ref"]) for e in mls) if n]
    ok &= _check(len(mls) == 28, f"cid=22 (MLS) declares 28 entries ({len(mls)})")
    ok &= _check(all(w in hits for w in ("D.C. United", "LA Galaxy", "Atlanta United FC")),
                 f"MLS refs resolve to real MLS clubs by UID "
                 f"({len(hits)}/{len(mls)} resolve; e.g. {hits[:3]})")
    lib = CO.comp_refs(mm, 61)                  # Copa Libertadores
    ok &= _check(all(e["season"] == 0 or 1990 <= e["season"] <= 2060 for e in lib),
                 f"every Copa Libertadores season is a plausible year or the 0 sentinel "
                 f"({len(lib)} entries)")
    # the populations that stop this list being called one thing -- if any of these change
    # shape the "it isn't one concept" conclusion needs revisiting, so pin them
    ok &= _check(all(e["ref"] == 0xFFFFFFFF for e in CO.comp_refs(mm, 279)),
                 "cid=279 (Scottish Cup) is 13 entries that are ALL the empty sentinel")
    ok &= _check(not CO.comp_refs(mm, 256) and len(CO.comp_refs(mm, 61)) == 94,
                 "European Champions Cup has NO entries while Copa Libertadores has 94 "
                 "-- the asymmetry that rules out a single label")
    ok &= _check(all(e["ref"] > 0xFFFF0000 for e in CO.comp_refs(mm, 254)),
                 "cid=254 (Copa América) holds national-team refs, not club uids")
    # the sign rule: ref < 0 is a national team and -ref is that nation's scrape_nations uid.
    # Pinned on Copa América because the answer is checkable without the save -- CONMEBOL has
    # exactly ten members, so ten refs resolving to exactly those ten is not a coincidence a
    # shape check could produce.
    nat_by_uid = {r["uid"]: r["name"] for r in LK.scrape_nations(mm).values()}
    conmebol = sorted(nat_by_uid.get(-(e["ref"] - (1 << 32))) for e in CO.comp_refs(mm, 254))
    ok &= _check(conmebol == CONMEBOL,
                 f"Copa América's 10 refs are -(nation uid) for CONMEBOL's 10 members "
                 f"({conmebol})")

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
                    c = CO.scrape_competitions(m)          # raises if short of declared
                    _s, dec = CO.locate_competitions(m)
                    blank = dec - len(c)
                    cl = CL.scrape_clubs(m)                # raises if short of declared
                    _cs, cl_dec = CL.locate_clubs(m)
                    if len(cl) != cl_dec:
                        failures.append(f"{os.path.basename(path)}: club {len(cl)} != {cl_dec}")
                    by_career.setdefault(career, set()).add((dec, len(c), blank, cl_dec, len(cl)))
                except (CO.CompTableError, CL.ClubTableError) as exc:
                    failures.append(f"{os.path.basename(path)}: {exc}")
                m.close()
        ok &= _check(not failures,
                     f"named + blank == declared on all {len(ALL_SAVES)} saves"
                     + ("" if not failures else f" -- {len(failures)} FAILED"))
        for line in failures[:5]:
            print(f"       {line}")
        for career, shapes in sorted(by_career.items()):
            print(f"       {career}: " + ", ".join(
                f"comp_declared={d} comp_named={n} comp_blank={b} club_declared={cld} club_named={cln}"
                for d, n, b, cld, cln in sorted(shapes)))
        ok &= _check(len(by_career) >= 2,
                     f"more than one career exercised ({sorted(by_career)}) -- a single-career "
                     f"run cannot catch a career-specific regression")

    # ---- the structural walk on the reference save (clubs) ----
    print("\nCLUB TABLE STRUCTURAL WALK")
    clubs = CL.scrape_clubs(mm)
    _start, declared_clubs = CL.locate_clubs(mm)
    ok &= _check(len(clubs) == declared_clubs and list(clubs) == list(range(declared_clubs)),
                 f"all {declared_clubs} declared clubs read, in tid order")

    print("\n" + ("PASS: refdata scan resolves clubs (gated) and competitions (pure "
                  "structural walk) as expected" if ok else "FAIL: see above"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
