#!/usr/bin/env python3
"""
Whole-file coverage audit: which bytes of the save do we actually read?

`scripts/audit_records.py` proves we read a whole RECORD and a whole TABLE. This proves
the complement: that we know what every MEGABYTE of the file is. The two questions it
answers, both of which we have been guessing at:

  * how much of the save is padding, how much do we claim, and how much is real content
    that no parser touches;
  * where, specifically, the unclaimed content is -- so "pick a region we aren't sweeping"
    is a lookup rather than a hunch.

The honesty rule here matters, because a coverage number is trivially inflated by declaring
a generous window and calling it read. So every claim is tagged:

  MEASURED   the parser reported a byte offset per record; we claim exactly those spans.
  DECLARED   the parser scans a window without reporting offsets; we claim the window, which
             OVERSTATES coverage. Treat a DECLARED region as unproven, not as read.

Padding is a run of >= 16 identical 0x00 or 0xff bytes. Shorter runs are counted as content
on purpose: a two-byte `ff ff` inside a record is a sentinel field, not filler.

Run:  uv run python scripts/audit_coverage.py [save.fms] [--granularity BYTES] [--top N]
"""
import argparse
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser.save import Save                # noqa: E402
from fmparser import mapregions as MR         # noqa: E402

MEASURED, DECLARED = "MEASURED", "DECLARED"
PAD_RUN = 16


def padding_mask(arr):
    """Boolean per byte: True where the byte is inside a >=PAD_RUN run of 00 or ff.

    Done with a cumulative-run trick rather than a Python loop -- the loop version took
    minutes on a 64 MB save, which is long enough that nobody runs the audit.
    """
    flat = (arr == 0x00) | (arr == 0xFF)
    same = np.empty(arr.size, dtype=bool)
    same[0] = False
    same[1:] = (arr[1:] == arr[:-1]) & flat[1:]
    # run id increments wherever the run breaks
    run_id = np.cumsum(~same)
    lengths = np.bincount(run_id)
    long_run = lengths >= PAD_RUN
    return flat & long_run[run_id]


def claims(mm, n):
    """[(start, end, who, how)] for every span a parser reads. Order is irrelevant;
    overlaps are fine and are resolved by the byte mask."""
    out = []

    def measured(who, spans):
        for s, e in spans:
            if e > s:
                out.append((s, e, who, MEASURED))

    def declared(who, s, e):
        out.append((max(0, s), min(n, e), who, DECLARED))

    # ---- MEASURED: parsers that report a per-record offset -------------------
    from fmparser import staging as S
    info = S.scrape_players(mm)
    # scrape_players does not report the record base, so re-derive it the same way it finds
    # them: the FFFFFFFF nickname sentinel at +16. Anchored on the parser's own constants so
    # this cannot drift from what it actually reads.
    bases, i = [], 0
    while True:
        j = mm.find(S.NO_NICKNAME, i)
        if j == -1:
            break
        i, base = j + 1, j - 16
        if base < 0:
            continue
        yr = int.from_bytes(mm[base + 22:base + 24], "little")
        tid = int.from_bytes(mm[base:base + 4], "little")
        if S.DOB_YEAR_LO <= yr <= S.DOB_YEAR_HI and 100 < tid < 70000 \
                and int.from_bytes(mm[base + 20:base + 22], "little") <= 366:
            bases.append(base)
    measured("staging.person_info", [(b, b + S.INFO_HEAD) for b in bases])

    try:
        from fmparser import clubrecords as CR
        valid = {v["club_tid"] for v in info.values()
                 if v.get("club_tid") and v["club_tid"] != S.NO_CLUB}
        rec = CR.build(mm, valid, valid_players=set(info))
        measured("clubrecords.team",
                 [(r["offset"], r["offset"] + CR.TEAM_STRIDE) for r in rec["team_records"]])
        measured("clubrecords.player",
                 [(r["offset"], r["offset"] + CR.PLAYER_STRIDE) for r in rec["player_records"]])
    except Exception as exc:
        print(f"  ! clubrecords failed: {exc}", file=sys.stderr)

    try:
        from fmparser import places as PL
        st = PL.scrape_stadiums(mm)
        rows = st.values() if isinstance(st, dict) else st
        measured("places.stadiums",
                 [(r["offset"], r["offset"] + 40) for r in rows if isinstance(r, dict)])
        ct = PL.scrape_cities(mm)
        rows = ct.values() if isinstance(ct, dict) else ct
        measured("places.cities",
                 [(r["offset"], r["offset"] + 24) for r in rows if isinstance(r, dict)])
    except Exception as exc:
        print(f"  ! places failed: {exc}", file=sys.stderr)

    try:
        from fmparser import staff as ST
        id2s = {v["id2"] for v in info.values() if v.get("id2")}
        sa = ST.scrape_staff_attributes(mm, id2s)
        rows = sa.values() if isinstance(sa, dict) else sa
        measured("staff.attributes",
                 [(r["offset"], r["offset"] + 39) for r in rows
                  if isinstance(r, dict) and r.get("offset")])
    except Exception as exc:
        print(f"  ! staff failed: {exc}", file=sys.stderr)

    # ---- DECLARED: window scans with no per-record offset --------------------
    from fmparser import regions as RG
    declared("reference.name_table", 0, 520_000)
    declared("staging.attributes", RG.ATTR_LO, RG.ATTR_HI)
    declared("staging.contracts", RG.CONTRACTREC_LO, RG.CONTRACTREC_HI)
    declared("attributes.snapshot", RG.SNAPSHOT_LO, RG.SNAPSHOT_HI)

    try:
        from fmparser import matches as M
        reg = M.find_match_region(mm)
        if reg:
            declared("matches.rich", reg[0], reg[1])
    except Exception as exc:
        print(f"  ! matches failed: {exc}", file=sys.stderr)
    try:
        from fmparser import history as H
        cand = H.locate(mm)                    # -> [(rows, start, hits)], best first
        if cand:
            rows, start, _ = cand[0]
            measured("history.slab", [(start, start + H.STRIDE * rows)])
    except Exception as exc:
        print(f"  ! history failed: {exc}", file=sys.stderr)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("save", nargs="?",
                    default=os.path.expanduser("~/fm-saves/frem/frem-2026-06-11.fms"))
    ap.add_argument("--granularity", type=int, default=262_144)
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--bridge", type=int, default=4096,
                    help="merge unclaimed runs separated by <= this much padding")
    ap.add_argument("--min-run", type=int, default=65536)
    args = ap.parse_args()

    mm = Save(args.save).mm
    arr = np.frombuffer(mm, dtype=np.uint8)
    n = arr.size
    print(f"{os.path.basename(args.save)}  {n/1e6:.1f} MB\n")

    print("running parsers to collect claimed spans ...", file=sys.stderr)
    spans = claims(mm, n)

    pad = padding_mask(arr)
    claimed = np.zeros(n, dtype=np.uint8)          # 1 = measured, 2 = declared
    for s_, e_, who, how in spans:
        v = 1 if how == MEASURED else 2
        seg = claimed[s_:e_]
        seg[seg != 1] = v

    content = ~pad
    n_pad = int(pad.sum())
    n_meas = int((content & (claimed == 1)).sum())
    n_decl = int((content & (claimed == 2)).sum())
    n_un = n - n_pad - n_meas - n_decl
    print("WHOLE FILE")
    print(f"  padding (>={PAD_RUN}B runs of 00/ff) {n_pad:>12,}  {n_pad/n*100:>5.1f}%")
    print(f"  content, MEASURED as read           {n_meas:>12,}  {n_meas/n*100:>5.1f}%")
    print(f"  content, inside a DECLARED window   {n_decl:>12,}  {n_decl/n*100:>5.1f}%")
    print(f"  content, UNCLAIMED                  {n_un:>12,}  {n_un/n*100:>5.1f}%   <-- the dig list")

    print("\nPER PARSER (raw span totals, before overlap resolution)")
    per = {}
    for s_, e_, who, how in spans:
        per[(who, how)] = per.get((who, how), 0) + (e_ - s_)
    for (who, how), tot in sorted(per.items(), key=lambda kv: -kv[1]):
        print(f"  {how}  {who:<28} {tot:>12,} bytes")

    unclaimed = content & (claimed == 0)

    # Contiguous runs of unclaimed content, allowing SMALL padding bridges: a table of
    # records separated by short filler is one region, and reporting it as 400 fragments
    # would bury it. A run must also be mostly content, so a padding desert with a few
    # stray bytes does not masquerade as a table.
    bridge = args.bridge
    infill = unclaimed.copy()
    edges = np.flatnonzero(np.diff(unclaimed.astype(np.int8)))
    starts = np.flatnonzero(np.diff(np.concatenate(([0], unclaimed.view(np.int8)))) == 1)
    ends = np.flatnonzero(np.diff(np.concatenate((unclaimed.view(np.int8), [0]))) == -1) + 1
    keep_s, keep_e = [], []
    for a, b in zip(starts, ends):
        if keep_s and a - keep_e[-1] <= bridge:
            keep_e[-1] = b
        else:
            keep_s.append(a)
            keep_e.append(b)
    runs = []
    for a, b in zip(keep_s, keep_e):
        c = int(unclaimed[a:b].sum())
        if b - a >= args.min_run:
            runs.append((c, a, b))
    runs.sort(reverse=True)
    print(f"\nUNCLAIMED CONTIGUOUS REGIONS (>= {args.min_run/1e3:.0f} KB, "
          f"bridging padding gaps <= {bridge} B) — top {args.top}")
    print(f"  {'start':>10} {'end':>10} {'span':>9} {'content':>11}  density")
    for c, a, b in runs[:args.top]:
        print(f"  {a/1e6:>9.3f}M {b/1e6:>9.3f}M {(b-a)/1e6:>8.3f}M {c:>11,}  {c/(b-a)*100:>5.1f}%")
    print(f"\n  {len(runs)} unclaimed regions, {sum(r[0] for r in runs):,} content bytes total")

    print("\nSECTION MAP (zero-gap skeleton) with unclaimed content per section")
    for a, b in MR.sections(mm, 8192):
        if b - a < 65536:
            continue
        c = int(unclaimed[a:b].sum())
        t = int(content[a:b].sum())
        print(f"  {a/1e6:>9.3f}M {b/1e6:>9.3f}M {(b-a)/1e6:>8.3f}M  "
              f"content {t:>11,}  unclaimed {c:>11,}  ({c/max(1,t)*100:>5.1f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
