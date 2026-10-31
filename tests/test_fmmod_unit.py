#!/usr/bin/env python3
"""Synthetic unit tests for the tagged-format writer (fmmod/tagged.py), with zero
save dependency.

  ROUND TRIP  a block mixing tagged and tagless fields, a container, a list, a pair, a
              string and an arbitrary-u32 tag encodes back to its exact bytes
  EDITS       a scalar keeps its width; a value too wide for it raises; counts follow the
              children after a list grows
  BUILDERS    tag() pads and reverses as stored ('crk' -> b' krc')
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser.core.types import read_tree  # noqa: E402
from fmmod import tagged as T              # noqa: E402

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


def raw(t, typ, payload):
    head = (t.ljust(4)[::-1].encode("latin-1") if t else b"") + bytes([0x01, typ])
    return head + payload


def block():
    kids = raw("ngps", 0x11, b"\x08") + raw("cash", 0x01, struct.pack("<I", 20_000_000))
    return (raw("comp", 0x01, struct.pack("<I", 1301394))
            + raw("stgs", 0x0a, struct.pack("<I", 2) + kids)
            + raw("gpis", 0x0b, struct.pack("<I", 2) + raw(None, 0x11, b"\x00") + raw(None, 0x11, b"\x01"))
            + raw("stgn", 0x0f, struct.pack("<II", 28, 28))
            + raw("file", 0x1a, struct.pack("<I", 4) + b"eur_")
            + b"\x20\x7d\x96\x16\x01\x11\x05")                 # an arbitrary-u32 tag


def main():
    b = block()
    nodes, end = T.parse_block(b, 0, 6)
    check(end == len(b), "parse_block reads the whole block")
    check(T.encode_block(nodes) == b, "round trip is byte-identical")
    check([n.tag for n in nodes] == ["comp", "stgs", "gpis", "stgn", "file", "#16967d20"],
          f"tags read as fmparser names them: {[n.tag for n in nodes]}")
    q, i = 0, 0
    while q < len(b):                          # fmparser's reader agrees field by field
        (t, _, _), q = read_tree(b, q, len(b))
        check(t == nodes[i].tag, f"read_tree tag {t!r} vs {nodes[i].tag!r}")
        i += 1

    stgs = nodes[1]
    stgs["ngps"].int = 4
    check(stgs["ngps"].value == b"\x04", "u8 stays one byte")
    try:
        stgs["ngps"].int = 300
        check(False, "300 fitted in a u8")
    except OverflowError:
        pass
    nodes[3].int = 73
    check(nodes[3].value == struct.pack("<II", 73, 73), "a pair keeps both halves equal")
    nodes[2].value.append(T.u8(None, 2))
    again, _ = T.parse_block(T.encode_block(nodes), 0, 6)
    check(len(again[2].kids) == 3 and again[1]["ngps"].int == 4, "counts follow the children")

    check(T.tag("crk") == b" krc" and T.tag("id") == b"  di", "tag() pads then reverses")

    for f in failures:
        print("FAIL", f)
    print("fmmod unit:", "OK" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
