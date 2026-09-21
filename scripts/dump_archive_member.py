#!/usr/bin/env python3
"""Dump or inspect a member of the save's zstd tail archive (`sicomps`).

Usage:
    uv run python scripts/dump_archive_member.py <save> <member> [options]
    uv run python scripts/dump_archive_member.py <save> --list
    uv run python scripts/dump_archive_member.py <save> --survey

Options:
    --hex              Print formatted hex dump
    --tagged           Walk and parse tagged fields (fmparser/tagged.py)
    --stride N         Print records at fixed stride N
    --strings          Extract printable ASCII strings (>= 4 chars)
    --offset N         Start offset within decompressed payload (default: 6, after member header)
    --limit N          Maximum bytes / records / fields to display
    --out PATH         Write raw decompressed member payload to disk
"""
import argparse
import glob
import mmap
import os
import re
import string
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fmparser import archive as A
from fmparser import tagged as TG

SAVES_DIR = os.environ.get("FM_SAVES_DIR", os.path.expanduser("~/fm-saves"))


def resolve_save(name):
    if os.path.exists(name):
        return name
    for pat in (
        os.path.join(SAVES_DIR, "*", name + ".fms"),
        os.path.join(SAVES_DIR, "*", name),
    ):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[0]
    return None


def hexdump(blob, offset=0, limit=256):
    end = min(len(blob), offset + limit)
    for i in range(offset, end, 16):
        chunk = blob[i:min(i + 16, end)]
        hex_str = " ".join(f"{b:02x}" for b in chunk)
        ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        print(f"{i:06x}  {hex_str:<48}  |{ascii_str}|")
    if end < len(blob):
        print(f"... ({len(blob) - end} more bytes; total {len(blob)} bytes)")


def dump_tagged(blob, offset=6, limit=100):
    count = 0
    for p, tag, typ, val in TG.walk_fields(blob, offset, len(blob)):
        if isinstance(val, bytes):
            val_repr = f"bytes[{len(val)}]: " + " ".join(f"{b:02x}" for b in val[:16])
            if len(val) > 16:
                val_repr += "..."
        else:
            val_repr = repr(val)
        print(f"{p:06x}  tag={tag!r:<6} type={typ:#04x}  val={val_repr}")
        count += 1
        if limit and count >= limit:
            print(f"... reached limit of {limit} tagged fields")
            break
    print(f"Total tagged fields scanned: {count}")


def dump_stride(blob, stride, offset=6, limit=50):
    n_recs = (len(blob) - offset) // stride
    print(f"Payload {len(blob)} B; offset {offset}; stride {stride} -> {n_recs:,} records")
    count = min(n_recs, limit if limit else n_recs)
    for i in range(count):
        base = offset + i * stride
        rec = blob[base:base + stride]
        hex_str = " ".join(f"{b:02x}" for b in rec[:min(32, stride)])
        if stride > 32:
            hex_str += "..."
        print(f"[{i:4d}] @{base:06x}: {hex_str}")
    if n_recs > count:
        print(f"... ({n_recs - count} more records)")


def dump_strings(blob, offset=0, min_len=4):
    text = ""
    start_pos = 0
    hits = []
    for i in range(offset, len(blob)):
        b = blob[i]
        if 32 <= b < 127:
            if not text:
                start_pos = i
            text += chr(b)
        else:
            if len(text) >= min_len:
                hits.append((start_pos, text))
            text = ""
    if len(text) >= min_len:
        hits.append((start_pos, text))
    for p, s in hits:
        print(f"{p:06x}: {s}")
    print(f"Total strings found: {len(hits)}")


def list_members(mm):
    name, ents = A.directory(mm)
    print(f"Archive '{name}': {len(ents)} members\n")
    print(f"{'filename':<28} {'offset':>10} {'stored':>10} {'unpacked':>10}")
    print("-" * 62)
    for e in sorted(ents, key=lambda x: x.offset):
        print(f"{e.filename:<28} {e.offset:>10,d} {e.stored:>10,d} {e.unpacked:>10,d}")


def survey_members(mm):
    name, ents = A.directory(mm)
    print(f"=== Archive Survey: '{name}' ({len(ents)} members) ===")
    
    subsystems = []
    comps = []
    for e in sorted(ents, key=lambda x: x.filename):
        if re.match(r"comp_\d+\.dat$", e.filename):
            comps.append(e)
        else:
            subsystems.append(e)
            
    print(f"\n--- Subsystems ({len(subsystems)}) ---")
    for e in subsystems:
        blob = A.extract(mm, e.filename)
        # Check if tagged
        tagged_fields = list(TG.walk_fields(blob, 6, min(len(blob), 1024)))
        n_tagged = len(tagged_fields)
        
        # Check printable strings
        chars = sum(1 for b in blob[6:] if 32 <= b < 127)
        pct_printable = (chars / max(1, len(blob) - 6)) * 100
        
        tag_info = f"{n_tagged}+ tagged fields" if n_tagged > 0 else "binary/untagged"
        print(f"{e.filename:<20} {len(blob):>8,d} B  ({e.stored:>8,d} stored)  "
              f"{pct_printable:5.1f}% print  [{tag_info}]")

    print(f"\n--- Competitions ({len(comps)} files) ---")
    tagged_comps = 0
    rule_files = {}
    stubs = 0
    for e in comps:
        blob = A.extract(mm, e.filename)
        # Check for file= or Name=
        cid_match = re.search(r"comp_(\d+)\.dat", e.filename)
        cid = int(cid_match.group(1)) if cid_match else 0
        rule_file = None
        subf = None
        # Scan for file= and SubF= tags across the file
        m_file = re.search(b"elif\x01\x1a(....)(.*?)(?:(?=[\x00-\x1f])|$)", blob, re.DOTALL)
        m_subf = re.search(b"FbuS\x01\x1a(....)(.*?)(?:(?=[\x00-\x1f])|$)", blob, re.DOTALL)
        
        rule_file = None
        subf = None
        if m_file:
            flen = int.from_bytes(m_file.group(1), "little")
            rule_file = blob[m_file.start() + 6 : m_file.start() + 6 + flen].decode("latin-1", errors="replace")
        if m_subf:
            slen = int.from_bytes(m_subf.group(1), "little")
            subf = blob[m_subf.start() + 6 : m_subf.start() + 6 + slen].decode("latin-1", errors="replace")

        if len(blob) <= 350:
            stubs += 1
        elif rule_file:
            rule_files[e.filename] = (cid, rule_file, subf or "", len(blob))
        else:
            tagged_comps += 1

    print(f"  Total comp files: {len(comps)}")
    print(f"  Stubs (<=350 B, no rules file): {stubs}")
    print(f"  Named with rules file: {len(rule_files)}")
    print(f"  Other loaded comps (no rules file): {len(comps) - stubs - len(rule_files)}")
    print("\nSample named competitions:")
    for fn, (cid, rf, sf, sz) in sorted(rule_files.items(), key=lambda x: x[1][0])[:25]:
        print(f"  {fn:<18} (cid={cid:<10}) {sf}/{rf} ({sz:,d} B)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("save", help="save path or label (e.g. frem-2026-06-11)")
    ap.add_argument("member", nargs="?", help="member filename (e.g. comp_man.dat)")
    ap.add_argument("--list", action="store_true", help="list all archive members")
    ap.add_argument("--survey", action="store_true", help="survey all members in archive")
    ap.add_argument("--hex", action="store_true", help="print hex dump")
    ap.add_argument("--tagged", action="store_true", help="walk tagged fields")
    ap.add_argument("--stride", type=int, help="dump as fixed-stride records")
    ap.add_argument("--strings", action="store_true", help="extract printable strings")
    ap.add_argument("--offset", type=int, default=6, help="start offset in payload (default: 6)")
    ap.add_argument("--limit", type=int, default=100, help="max items to display")
    ap.add_argument("--out", help="extract raw decompressed payload to path")
    args = ap.parse_args()

    save_path = resolve_save(args.save)
    if not save_path:
        print(f"Save not found: {args.save}", file=sys.stderr)
        return 1

    with open(save_path, "rb") as fh:
        mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            if args.list:
                list_members(mm)
                return 0
            if args.survey:
                survey_members(mm)
                return 0

            if not args.member:
                print("Specify a member name or use --list / --survey", file=sys.stderr)
                return 1

            blob = A.extract(mm, args.member)
            print(f"Extracted '{args.member}' from {os.path.basename(save_path)}: {len(blob):,} bytes unpacked")

            if args.out:
                with open(args.out, "wb") as out_f:
                    out_f.write(blob)
                print(f"Wrote {len(blob):,} bytes to {args.out}")

            if args.tagged:
                dump_tagged(blob, offset=args.offset, limit=args.limit)
            elif args.stride:
                dump_stride(blob, args.stride, offset=args.offset, limit=args.limit)
            elif args.strings:
                dump_strings(blob, offset=args.offset)
            elif args.hex or not args.out:
                hexdump(blob, offset=args.offset, limit=args.limit * 16)
        finally:
            mm.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
