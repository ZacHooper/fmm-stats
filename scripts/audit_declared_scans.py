#!/usr/bin/env python3
"""
Per-candidate disposition audit for DECLARED-tier parsers: for each candidate position a
scan considers, is it accepted (and at what tier), rejected (with which named reason), or
superseded by an earlier/better candidate for the same key? Closes the gap `DECLARED` leaves
open in `scripts/audit_coverage.py` -- "a parser scanned this window" is not "every candidate
is accounted for."

Currently covers `reference.py`'s club/comp scan (`_build_refdata_index` /
`diagnose_refdata_scan`). `staging.py`'s `scrape_attributes`/`scrape_contracts` share the same
shape and are the next candidates once they get the equivalent `_eval_*_candidate` refactor --
see docs/TODO.md item #10.

Two things this script exists specifically to avoid getting wrong, both caught while building
it (see `reference.diagnose_refdata_scan`'s docstring for the full story):

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


def _reject_table(candidates, ids, solo_candidates, solo_ids, total_rejected_candidates):
    lines = []
    for reason, c in candidates.most_common():
        s = solo_candidates.get(reason, 0)
        si = solo_ids.get(reason, 0)
        lines.append(
            f"    {c:>8,} candidates / {ids[reason]:>6,} cids touch it   "
            f"{s:>8,} candidates / {si:>6,} cids fail ONLY it  -- {reason}")
    return lines


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

    print("\nCOMPETITIONS")
    print(f"  accepted tier0 (primary reputation gate)  {diag.comp_accepted_tier0:>8,}")
    print(f"  accepted tier1 (reputation-floor fill)    {diag.comp_accepted_tier1:>8,}")
    print(f"  superseded (valid, lost cid arbitration)  {diag.comp_superseded:>8,}")
    print(f"  already-resolved skips (not a defect)     {diag.comp_already_resolved:>8,}")
    print("  reject reasons -- gates are tested independently, so a candidate failing")
    print("  multiple gates counts against each; SOLO = this was the only gate it failed")
    print("  (the actionable number: fixing this gate alone would recover exactly this many)")
    for line in _reject_table(diag.comp_reject_candidates, diag.comp_reject_ids,
                               diag.comp_reject_solo_candidates, diag.comp_reject_solo_ids,
                               sum(diag.comp_reject_candidates.values())):
        print(line)
    return diag


def report_cross_reference(mm, diag):
    """Of the ids something else in the save actually references, how many resolve, and for
    the ones that don't, which reject reason (solo if there is one, else the full set)
    explains it. This is what turns a reject count into a real, actionable gap."""
    print("\nCROSS-REFERENCE: ids real matches/players reference, that fail to resolve")

    comp_reject_reason = {}
    for _off, cid, reasons in diag.comp_rejections:
        if cid not in comp_reject_reason or len(reasons) < len(comp_reject_reason[cid]):
            comp_reject_reason[cid] = reasons   # prefer the most specific (fewest reasons) hit

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
        reason = "/".join(comp_reject_reason.get(cid, ["no candidate found for this cid at all"]))
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
    report_cross_reference(mm, diag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
