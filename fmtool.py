#!/usr/bin/env python3
"""
fmtool — exploration toolkit for FMM save files (uncompressed .fms).

Design goals:
  - Keep a *breadcrumb trail*: every interesting offset we find gets logged to
    breadcrumbs.json with a note, so we can re-find our place in the bytes.
  - Fast searching over a 64MB file (mmap).
  - Little/big-endian helpers matching the FMM conventions from the rough guide.

Usage (CLI):
  python3 fmtool.py dump   <offset> [length]      # hex dump around an offset
  python3 fmtool.py find   <hexstring>            # find hex bytes (e.g. 4F45350 2)
  python3 fmtool.py finds  <ascii>                # find an ASCII string
  python3 fmtool.py uid    <decimal_uid>          # convert UID->LE hex and find it
  python3 fmtool.py mark   <offset> <note...>     # add a breadcrumb
  python3 fmtool.py trail                         # print all breadcrumbs
  python3 fmtool.py strings <offset> <length>     # readable strings in a range

Or import it: from fmtool import Save; s = Save("fm_save1.fms")
"""
import sys, os, json, mmap, struct

SAVE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fm_save1.fms")
TRAIL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "breadcrumbs.json")


def uid_to_le_hex(uid: int) -> bytes:
    """FMM stores IDs little-endian, 4 bytes. Google gives big-endian.
    e.g. UID 37045583 -> 02 35 45 4F (BE) -> 4F 45 35 02 (LE)."""
    return struct.pack("<I", uid)


def le_hex_to_int(b: bytes) -> int:
    return int.from_bytes(b, "little")


class Save:
    def __init__(self, path=SAVE):
        self.path = path
        self.f = open(path, "rb")
        self.mm = mmap.mmap(self.f.fileno(), 0, access=mmap.ACCESS_READ)
        self.size = len(self.mm)

    def read(self, offset, length):
        return self.mm[offset:offset + length]

    def find_all(self, needle: bytes, start=0, limit=50):
        """Yield offsets of every occurrence of needle."""
        out = []
        pos = start
        while len(out) < limit:
            i = self.mm.find(needle, pos)
            if i == -1:
                break
            out.append(i)
            pos = i + 1
        return out

    def dump(self, offset, length=64):
        data = self.read(offset, length)
        lines = []
        for i in range(0, len(data), 16):
            chunk = data[i:i + 16]
            hexpart = " ".join(f"{b:02x}" for b in chunk)
            # group into 4-byte columns for readability
            asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            lines.append(f"{offset + i:>10} (0x{offset + i:08x})  {hexpart:<48}  {asc}")
        return "\n".join(lines)

    # --- breadcrumb trail ---
    def marks(self):
        if os.path.exists(TRAIL):
            with open(TRAIL) as fh:
                return json.load(fh)
        return []

    def mark(self, offset, note, **extra):
        crumbs = self.marks()
        entry = {"offset": int(offset), "hex": f"0x{int(offset):08x}", "note": note}
        entry.update(extra)
        # de-dup on (offset, note)
        crumbs = [c for c in crumbs if not (c["offset"] == entry["offset"] and c["note"] == note)]
        crumbs.append(entry)
        crumbs.sort(key=lambda c: c["offset"])
        with open(TRAIL, "w") as fh:
            json.dump(crumbs, fh, indent=2)
        return entry


def _cli():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    s = Save()
    cmd = sys.argv[1]
    if cmd == "dump":
        off = int(sys.argv[2], 0)
        length = int(sys.argv[3]) if len(sys.argv) > 3 else 64
        print(s.dump(off, length))
    elif cmd == "find":
        hexstr = sys.argv[2].replace(" ", "")
        needle = bytes.fromhex(hexstr)
        hits = s.find_all(needle)
        print(f"{len(hits)} hit(s) for {hexstr}:")
        for h in hits:
            print(f"  {h} (0x{h:08x})")
    elif cmd == "finds":
        needle = sys.argv[2].encode("latin-1")
        hits = s.find_all(needle)
        print(f"{len(hits)} hit(s) for {sys.argv[2]!r}:")
        for h in hits:
            print(f"  {h} (0x{h:08x})")
    elif cmd == "uid":
        uid = int(sys.argv[2])
        le = uid_to_le_hex(uid)
        print(f"UID {uid} -> LE bytes {le.hex()}")
        hits = s.find_all(le)
        for h in hits:
            print(f"  {h} (0x{h:08x})")
    elif cmd == "mark":
        off = int(sys.argv[2], 0)
        note = " ".join(sys.argv[3:])
        print(s.mark(off, note))
    elif cmd == "trail":
        for c in s.marks():
            print(f"{c['offset']:>10} (0x{c['offset']:08x})  {c['note']}")
    elif cmd == "strings":
        off = int(sys.argv[2], 0)
        length = int(sys.argv[3])
        data = s.read(off, length)
        cur = []
        start = off
        for i, b in enumerate(data):
            if 32 <= b < 127:
                if not cur:
                    start = off + i
                cur.append(chr(b))
            else:
                if len(cur) >= 4:
                    print(f"{start:>10} (0x{start:08x})  {''.join(cur)}")
                cur = []
    else:
        print(__doc__)


if __name__ == "__main__":
    _cli()
