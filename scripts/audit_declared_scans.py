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

from fmparser import reference as R    # noqa: E402
from fmparser import staging as S      # noqa: E402
from fmparser import matches as M      # noqa: E402


def report_refdata(mm):
    diag = R.diagnose_refdata_scan(mm)
    print(f"reference.clubs_comps: {diag.n_window_bytes:,} window bytes, "
          f"{diag.n_candidates:,} name-length candidates "
          f"({diag.n_candidates / diag.n_window_bytes * 100:.2f}% of window -- see "
          f"diagnose_refdata_scan's docstring for what the other ~98% means)\n")

    print("CLUBS")
    print(f"  accepted tier0 (primary uid band)        {diag.club_accepted_tier0:>8,}")
    print(f"  accepted tier1 (fill uid band)            {diag.club_accepted_tier1:>8,}")
    print(f"  superseded (valid, lost tid arbitration)  {diag.club_superseded:>8,}")
    total_rej = sum(diag.club_reject_candidates.values())
    print(f"  rejected candidates                       {total_rej:>8,}")
    print("    candidates / cids touching this reason        solo (only-this-reason) count")
    for reason, c in diag.club_reject_candidates.most_common():
        pct = c / total_rej * 100 if total_rej else 0
        print(f"    {c:>8,} ({pct:>5.1f}%)  {diag.club_reject_ids[reason]:>6,} cids  -- {reason}")

    return diag


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


def report_cross_reference(mm, diag, comps, declared):
    """Of the ids something else in the save actually references, how many resolve, and what
    explains the ones that don't. This is what turns a count into a real, actionable gap.

    The two halves now explain a miss DIFFERENTLY, which is the whole point of the walk.
    A club miss is attributed to the gate that rejected it (there is still a gate cascade to
    blame). A competition miss cannot be a gate any more, so it is classified structurally:
    either the cid is past the end of the table the save itself declares, or the table says
    that slot is blank. Both are statements about the save, not about our tuning -- and a
    referenced cid that lands on a blank slot is the interesting case, because it means
    something in the save points at a competition the save never populated."""
    print("\nCROSS-REFERENCE: ids real matches/players reference, that fail to resolve")

    def comp_miss_reason(cid):
        if cid >= declared:
            return f"cid >= the {declared} records the table declares (dangling reference)"
        return "the table declares this slot BLANK (namelen 0) -- nothing to resolve"

    club_reject_reason = {}
    for _off, tid, reason in diag.club_rejections:
        club_reject_reason.setdefault(tid, reason)

    print("  parsing the season and squads to collect referenced ids "
          "(this is the slow part) ...", file=sys.stderr)
    season = M.extract_season(mm)
    clubs, _comps = R._build_refdata_index(mm)
    # Two very different referenced-id sources, deliberately both included: extract_season's
    # comp_id is "a competition we have actual matches for" (narrow -- Frem's own history,
    # 4 cids on a real save). Every accepted club's own `league` field is "a competition
    # SOMETHING claims membership in" (broad -- 17k+ clubs' worth) and is exactly how the
    # 47 reputation-floor cids were originally found: they're real leagues that real (if not
    # our own) clubs belong to, invisible to extract_season entirely.
    needed_cids = {m["comp_id"] for m in season if m.get("comp_id")}
    needed_cids |= {c["league"] for c in clubs.values() if c.get("league")}
    resolved_cids = {cid for cid in needed_cids if R.find_comp_record(mm, cid)}
    missing_cids = sorted(needed_cids - resolved_cids)

    players = S.scrape_players(mm)
    needed_tids = ({m["home_tid"] for m in season if m.get("home_tid")}
                   | {m["away_tid"] for m in season if m.get("away_tid")}
                   | {p["club_tid"] for p in players.values()
                      if p.get("club_tid") and p["club_tid"] != S.NO_CLUB})
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
        reason = club_reject_reason.get(tid, "no candidate found for this tid at all")
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
    diag = report_refdata(mm)
    comps, declared = report_comp_table(mm)
    report_cross_reference(mm, diag, comps, declared)
    return 0


if __name__ == "__main__":
    sys.exit(main())
