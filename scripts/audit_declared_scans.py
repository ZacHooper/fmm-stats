#!/usr/bin/env python3
"""
Per-candidate disposition audit for DECLARED-tier parsers: for each candidate position a
scan considers, is it accepted (and at what tier), rejected (with which named reason), or
superseded by an earlier/better candidate for the same key? Closes the gap `DECLARED` leaves
open in `scripts/audit_coverage.py` -- "a parser scanned this window" is not "every candidate
is accounted for."

Currently covers `reference.py`'s CLUB scan (`_build_refdata_index` /
`diagnose_refdata_scan`). `staging.py`'s `scrape_attributes`/`scrape_contracts` share the same
shape and are the next candidates once they get the equivalent `_eval_*_candidate` refactor --
see docs/TODO.md.

COMPETITIONS ARE NO LONGER AUDITED THIS WAY, because they are no longer a candidate scan:
`reference._walk_comp_table` reads the table's own declared slots by arithmetic, so there are
no candidates, no gates and no reject reasons to tally. This script printed exactly such a
tally until 2026-09-18 -- tier counts, per-gate reject costs, "fixing this gate alone would
recover exactly this many" -- for a code path `_build_refdata_index` had already stopped
calling. Numbers about a dead path read as an audit and are worse than no audit. What replaces
them is the walk's own structural summary (declared == named + blank) plus the cross-reference
below, which is the half that still answers a real question.

Two things this script exists specifically to avoid getting wrong, both caught while building
it against the comp gates (see `reference.diagnose_refdata_scan`'s docstring), and both of
which now apply to the CLUB gates:

  1. A raw reject-reason count is not "how many real records are we losing" -- a candidate
     that fails 3 gates at once counts against all 3, so a gate's raw count is dominated by
     hopeless noise. Report the SOLO count too (candidates whose only failure is this gate)
     for the actionable number.
  2. Even a solo reject count is not proof of need -- most rejected candidates aren't records
     anyone asked for. Cross-reference rejected ids against ids something else in the save
     actually REFERENCES (a match's comp_id/home_tid/away_tid, a player's club_tid) before
     calling a gap real.

Run: uv run python scripts/audit_declared_scans.py [save.fms]
"""
import mmap
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser import clubs_comps as R    # noqa: E402
from fmparser.tables.person_info import NO_CLUB as _NO_CLUB, scrape_person_info as _scrape_players  # noqa: E402
from fmparser import matches as M      # noqa: E402


def report_club_table(mm):
    """The club table has no candidates to diagnose -- it is walked. So the report is
    the walk's own invariant: the table's declared record count equals what came out of it.
    Returns (clubs, declared) for the cross-reference below."""
    start, declared = R._club_table_anchor(mm)
    clubs, n_blank = R._walk_club_table(mm)
    print("CLUBS (structural walk -- no candidates, no gates, nothing to reject)")
    print(f"  table start offset                        {start:>8,}")
    print(f"  records the table declares                {declared:>8,}")
    print(f"  named                                     {len(clubs):>8,}")
    agree = "ok" if len(clubs) + n_blank == declared else "MISMATCH"
    print(f"  named + blank == declared                 {agree:>8}")
    return clubs, declared


def report_comp_table(mm):
    """The competition table has no candidates to diagnose -- it is walked. So the report is
    the walk's own invariant: the table's declared record count equals what came out of it.
    Returns (comps, declared) for the cross-reference below."""
    start, declared = R._comp_table_anchor(mm)
    comps, n_blank = R._walk_comp_table(mm)
    print("\nCOMPETITIONS (structural walk -- no candidates, no gates, nothing to reject)")
    print(f"  table start offset                        {start:>8,}")
    print(f"  records the table declares                {declared:>8,}")
    print(f"  named                                     {len(comps):>8,}")
    print(f"  blank slots (namelen 0, placeholder uid)  {n_blank:>8,}")
    agree = "ok" if len(comps) + n_blank == declared else "MISMATCH"
    print(f"  named + blank == declared                 {agree:>8}")
    return comps, declared


def report_cross_reference(mm, clubs, declared_clubs, comps, declared_comps):
    """Of the ids something else in the save actually references, how many resolve, and what
    explains the ones that don't."""
    print("\nCROSS-REFERENCE: ids real matches/players reference, that fail to resolve")

    def comp_miss_reason(cid):
        if cid >= declared_comps:
            return f"cid >= the {declared_comps} records the table declares (dangling reference)"
        return "the table declares this slot BLANK (namelen 0) -- nothing to resolve"

    def club_miss_reason(tid):
        if tid >= declared_clubs:
            return f"tid >= the {declared_clubs} records the table declares (dangling reference)"
        return "the table slot is unpopulated"

    print("  parsing the season and squads to collect referenced ids "
          "(this is the slow part) ...", file=sys.stderr)
    season = M.extract_season(mm)
    all_clubs, _comps = R._build_refdata_index(mm)

    needed_cids = {m["comp_id"] for m in season if m.get("comp_id")}
    needed_cids |= {c["league"] for c in all_clubs.values() if c.get("league")}
    resolved_cids = {cid for cid in needed_cids if R.find_comp_record(mm, cid)}
    missing_cids = sorted(needed_cids - resolved_cids)

    players = _scrape_players(mm)
    needed_tids = ({m["home_tid"] for m in season if m.get("home_tid")}
                   | {m["away_tid"] for m in season if m.get("away_tid")}
                   | {p["club_tid"] for p in players.values()
                      if p.get("club_tid") and p["club_tid"] != _NO_CLUB})
    resolved_tids = {tid for tid in needed_tids if R.club_record(mm, tid)}
    missing_tids = sorted(needed_tids - resolved_tids)

    print(f"\n  competitions: {len(needed_cids)} referenced, {len(resolved_cids)} resolve, "
          f"{len(missing_cids)} missing")
    by_reason = {}
    for cid in missing_cids:
        reason = comp_miss_reason(cid)
        by_reason.setdefault(reason, []).append(cid)
    for reason, cids in sorted(by_reason.items(), key=lambda kv: -len(kv[1])):
        shown = ", ".join(str(c) for c in cids[:15])
        more = f" (+{len(cids) - 15} more)" if len(cids) > 15 else ""
        print(f"    {len(cids):>4}  {reason}: {shown}{more}")

    print(f"\n  clubs: {len(needed_tids)} referenced, {len(resolved_tids)} resolve, "
          f"{len(missing_tids)} missing")
    for tid in missing_tids[:40]:
        reason = club_miss_reason(tid)
        print(f"    tid={tid:<6} {reason}")
    if len(missing_tids) > 40:
        print(f"    ... and {len(missing_tids) - 40} more")


def main():
    save = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
        "~/fm-saves/frem/frem-2026-06-11.fms")
    if not os.path.exists(save):
        print(f"SKIP: {save} not found")
        return 0
    with open(save, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    clubs, declared_clubs = report_club_table(mm)
    comps, declared_comps = report_comp_table(mm)
    report_cross_reference(mm, clubs, declared_clubs, comps, declared_comps)
    return 0


if __name__ == "__main__":
    sys.exit(main())
