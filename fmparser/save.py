#!/usr/bin/env python3
"""
Save loader for uncompressed FMM .fms files: mmap + search + endian helpers.

`Save(path)` memory-maps the file read-only. All parsing modules take the raw
mmap (`save.mm`) so nothing here is save-specific.
"""
import mmap
import os
import struct

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SAVE = os.path.join(REPO_ROOT, "fm_save1.fms")


def uid_to_le(uid: int) -> bytes:
    """FMM stores IDs little-endian, 4 bytes (Google gives big-endian; reverse)."""
    return struct.pack("<I", uid)


class Save:
    def __init__(self, path=DEFAULT_SAVE):
        self.path = path
        self.f = open(path, "rb")
        self.mm = mmap.mmap(self.f.fileno(), 0, access=mmap.ACCESS_READ)
        self.size = len(self.mm)

    def close(self):
        self.mm.close()
        self.f.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def read(self, offset, length):
        return self.mm[offset:offset + length]

    def find_all(self, needle: bytes, start=0, limit=50):
        out, pos = [], start
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
            asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            lines.append(f"{offset + i:>10} (0x{offset + i:08x})  {hexpart:<48}  {asc}")
        return "\n".join(lines)
