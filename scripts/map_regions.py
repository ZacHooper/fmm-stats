#!/usr/bin/env python3
"""
Print the discovered section map of an .fms save (pure-stdlib; run with python3).

    python3 scripts/map_regions.py <save.fms> [--min-gap 8192] [--json]

Sections are split on long zero-runs (the save's own delimiters) and labelled by
content detectors in fmparser/mapregions.py. Use it to sanity-check / derive the
byte windows that regions.py currently hard-codes. See docs/agent-context
savefile-boundary-map for the running map + what each region is.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fmparser import mapregions as MR


def main():
    ap = argparse.ArgumentParser(description="Discover the section layout of an .fms save.")
    ap.add_argument("save", help="path to the .fms save file")
    ap.add_argument("--min-gap", type=int, default=8192,
                    help="min zero-run length that counts as a section delimiter (default 8192)")
    ap.add_argument("--min-section", type=int, default=2048,
                    help="drop sections smaller than this (default 2048)")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = ap.parse_args()

    regions = MR.discover_path(args.save, min_gap=args.min_gap, min_section=args.min_section)

    if args.json:
        print(json.dumps(MR.as_dicts(regions), indent=1))
        return

    total = os.path.getsize(args.save)
    print(f"{args.save}  ({total/1e6:.1f} MB)   sections split on zero-gaps >= {args.min_gap}\n")
    print(f"  {'start':>9} {'end':>9} {'size':>8}  {'kind':13} detail")
    print("  " + "-" * 78)
    covered = 0
    for r in regions:
        covered += r.size
        print(f"  {r.start/1e6:8.3f}M {r.end/1e6:8.3f}M {r.size/1e6:7.3f}M  {r.kind:13} {r.detail}")
    print("  " + "-" * 78)
    print(f"  {len(regions)} sections, {covered/1e6:.1f} MB content "
          f"({(total-covered)/1e6:.1f} MB in zero-gaps / dropped fragments)")

    subs = MR.sub_regions_path(args.save)
    if subs:
        print("\n  content-located sub-regions (inside the sections above):")
        for s, e, kind, detail in subs:
            print(f"  {s/1e6:8.3f}M {e/1e6:8.3f}M {(e-s)/1e6:7.3f}M  {kind:13} {detail}")


if __name__ == "__main__":
    main()
