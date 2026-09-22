#!/usr/bin/env python3
"""
Profile a save by BLOCK ENTROPY — the first thing to run on an unexplored region.

Why this and not a printable-byte count: `docs/savefile-map.md`'s 2026-09-19 gap ranking
put the file's tail second because it measured "25.8% printable" and read that as text
density. **95 of 256 byte values are printable, so uniform random bytes measure 37.1%
printable** — compressed data scores HIGH on exactly the statistic that was meant to mean
"text". Entropy does not confuse the two, and it separates the file's four regimes in one
pass:

    ~0.0 - 1.5   filler (runs of 00 / ff)
    ~2   - 5     ordinary fixed-width records; most of this file
    ~6   - 7.5   dense records, string tables, pointer slabs
    > 7.9        COMPRESSED OR ENCRYPTED -- no stride search will ever bite here

Measured on this file that last band is the `sicomps` zstd archive at the tail
(`fmparser/archive.py`) and **nothing else**: on frem-2021-07-01, frem-2026-06-11 and
bucaspor-2023-05-20 every 4 KB block above 7.5 bits lies inside the archive. So the save
holds exactly one compressed region, which is a useful negative to have on record.

    uv run python scripts/entropy_profile.py <save.fms>            # runs, coarse
    uv run python scripts/entropy_profile.py <save.fms> --all      # every block
    uv run python scripts/entropy_profile.py <save.fms> --lo 6e7   # window
"""
import argparse
import mmap
import os
import sys

import numpy as np

BANDS = [(1.5, "filler"), (5.0, "records"), (7.5, "dense"), (9.0, "COMPRESSED")]


def band(e):
    for hi, nm in BANDS:
        if e < hi:
            return nm
    return "?"


def profile(a, bs):
    n = len(a) // bs
    if not n:
        return np.empty(0)
    b = a[:n * bs].reshape(n, bs)
    out = np.empty(n)
    for i in range(n):
        h = np.bincount(b[i], minlength=256).astype(np.float64)
        h /= bs
        h = h[h > 0]
        out[i] = -(h * np.log2(h)).sum()
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("save")
    ap.add_argument("--block", type=int, default=4096, help="block size (default 4096)")
    ap.add_argument("--lo", type=float, default=0)
    ap.add_argument("--hi", type=float, default=None)
    ap.add_argument("--all", action="store_true", help="one line per block, not per run")
    args = ap.parse_args()

    with open(args.save, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        a = np.frombuffer(mm, dtype=np.uint8)
        lo = int(args.lo)
        hi = int(args.hi) if args.hi else len(a)
        e = profile(a[lo:hi], args.block)
        print(f"{args.save}  {len(a):,} B   {len(e)} blocks of {args.block} B\n")
        if args.all:
            for i, v in enumerate(e):
                print(f"  {lo + i * args.block:>10} {v:5.2f}  {band(v)}")
        else:
            print(f"  {'start':>10} {'end':>10} {'size':>10}  {'mean':>5}  band")
            print("  " + "-" * 52)
            names = [band(v) for v in e]
            s = 0
            for i in range(1, len(e) + 1):
                if i == len(e) or names[i] != names[s]:
                    st, en = lo + s * args.block, lo + i * args.block
                    print(f"  {st:>10} {en:>10} {en - st:>10,}  "
                          f"{e[s:i].mean():5.2f}  {names[s]}")
                    s = i
        del a
        mm.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
