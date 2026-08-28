#!/usr/bin/env python3
"""
Decode every starter's on-pitch position for every match in a save.

    uv run python scripts/decode_match_positions.py <save.fms> [--date YYYY-MM-DD] [--verify]

The position of each of the 11 starting slots is stored as 2 bytes, immediately after the
formation string (see docs/agent-context/match-position-encoding.md):

    pair = [band_byte][column_byte]
    band_byte & 0x7f : 0x01 GK  0x04 D  0x08 DM  0x10 M  0x20 AM  0x40 ST
    band_byte & 0x80 : wide-LEFT flag
    column_byte      : 0x08 = wide-right  (centre otherwise)

`--verify` runs the self-check: collapse the decoded bands back into a formation string and
assert it equals the formation string the save itself stores. That needs no screenshots and
passed 34/34 on frem-2024-11-10.fms, so it is the regression test to run after touching this.

NOTE: the save stores ONE formation per match. If the manager changed shape mid-match, this
decode is the stored moment and will legitimately differ from the post-match stats screen.
Reserve/AI fixtures carry a default array (byte-identical across matches) — not a real lineup.
"""
import argparse
import os
import sys
from datetime import date, timedelta

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from fmparser.save import Save                                        # noqa: E402
from fmparser import matches as M                                     # noqa: E402

BAND = {0x01: "GK", 0x04: "D", 0x08: "DM", 0x10: "M", 0x20: "AM", 0x40: "ST"}
LEFT_FLAG = 0x80
WIDE_RIGHT = 0x08


def fm_position(band_byte, col_byte):
    """One (band, column) pair -> an FM position code, or None if the band is unknown."""
    band = BAND.get(band_byte & ~LEFT_FLAG)
    if band is None:
        return None
    if band == "GK":
        return "GK"
    if band == "ST":
        return "FC"
    if col_byte == WIDE_RIGHT:
        return band + "R"
    return band + ("L" if band_byte & LEFT_FLAG else "C")


def slot_positions(mm, anchor, end):
    """(formation_string, [11 position codes]) for the match at `anchor`, or (None, None)."""
    i = mm.find(M.FORMATION_MARKER, anchor, end)
    if i == -1:
        return None, None
    j = i + 4
    while j < end and (48 <= mm[j] <= 57 or mm[j] == 45):
        j += 1
    formation = mm[i + 4:j].decode("ascii")
    tail = mm[j:j + 160]
    k = 0
    while k < len(tail) and tail[k] == 0:      # skip the zero padding
        k += 1
    seq = tail[k:k + 22]                        # 11 pairs
    if len(seq) < 22:
        return formation, None
    slots = [fm_position(seq[2 * n], seq[2 * n + 1]) for n in range(11)]
    return formation, (None if any(s is None for s in slots) else slots)


def shape_string(slots):
    """Collapse decoded slots back into an FM formation string (the self-check)."""
    order = ["D", "DM", "M", "AM", "ST"]
    counts = {o: 0 for o in order}
    for s in slots:
        if s == "GK":
            continue
        band = "ST" if s == "FC" else s[:-1]
        counts[band] = counts.get(band, 0) + 1
    return "-".join(str(counts[o]) for o in order if counts[o] > 0)


def iter_matches(mm):
    region = M.find_match_region(mm)
    anchors = M.match_anchors(mm, lo=region[0], hi=region[1]) if region else M.match_anchors(mm)
    for n, a in enumerate(anchors):
        hdr = M.parse_header(mm, a)
        if not hdr:
            continue
        nxt = anchors[n + 1] if n + 1 < len(anchors) else None
        if not nxt:
            continue
        try:
            d = (date(hdr["year"], 1, 1) + timedelta(days=hdr["day"])).isoformat()
        except ValueError:
            d = None
        yield d, hdr, a, nxt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("save")
    ap.add_argument("--date", help="only this match date (YYYY-MM-DD)")
    ap.add_argument("--verify", action="store_true",
                    help="assert decoded shape == the save's own formation string")
    args = ap.parse_args()

    s = Save(args.save)
    ok = bad = 0
    for d, hdr, a, nxt in iter_matches(s.mm):
        if args.date and d != args.date:
            continue
        formation, slots = slot_positions(s.mm, a, nxt)
        if not slots:
            print(f"{d}  {formation or '?':11} DECODE FAILED")
            bad += 1
            continue
        if args.verify:
            got = shape_string(slots)
            good = got == formation
            ok, bad = ok + good, bad + (not good)
            flag = "OK" if good else f"MISMATCH (decoded {got})"
            print(f"{d}  {formation:11} {flag:24} {' '.join(slots)}")
        else:
            print(f"{d}  {formation:11} {' '.join(slots)}")
    s.close()

    if args.verify:
        print(f"\ndecoded shape == stored formation string: {ok}/{ok + bad}")
        return 0 if bad == 0 else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
