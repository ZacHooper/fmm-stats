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


def cache_key(mm):
    """The key to use for ANY per-save cache keyed on an mmap. Lives here, in the mmap
    layer, because every parsing module takes the raw mmap and so every one of them needs
    the same key -- there is exactly one definition on purpose.

    `(id(mm), len(mm))`, NOT `id(mm)` alone: CPython reuses the id of a freed object, so a
    loop that opens one save after another (`scripts/rebuild.py`, a cross-save audit, an
    agent poking at two careers in one REPL) gets an id collision and is served the PREVIOUS
    save's answer for the next save.

    This has bitten twice. `tagged.py`'s region cache first -- Bucaspor came back with Frem's
    bounds and lost 829 records. Then `clubs_comps.py`, which cached an ABSOLUTE FILE OFFSET
    (the competition table's anchor), where a stale hit is worse than a wrong answer: it
    sends the table walk into the middle of an unrelated record and it raises. Measured
    2026-09-18 before the fix, walking 32 real saves in one process: 30 failed that way
    (ValueError misaligned at slot 0, or UnicodeDecodeError on 0xff), and all 32 passed once
    every mmap was held alive to keep its id unique.

    `len(mm)` disambiguates in practice because two saves of byte-identical length are the
    same snapshot. If that ever stops holding, key on the save PATH instead -- do not go
    back to a bare id.
    """
    return id(mm), len(mm)


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
