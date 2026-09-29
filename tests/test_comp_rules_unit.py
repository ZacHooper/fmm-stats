#!/usr/bin/env python3
"""Synthetic unit tests for the competition-rules reader (fmparser/tables/comp_rules.py).

Builds a comp_<uid>.dat tagged block in memory -- tagged scalars, a tagless list of
containers, a name stored both as a scalar and as an `stnm` container, a pair-typed name,
a string and the trailer -- with zero save dependency.
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser.core import TaggedTableError  # noqa: E402
from fmparser.tables import comp_rules as CR  # noqa: E402


def tag(t: str, typ: int, payload: bytes) -> bytes:
    return t.ljust(4)[:4][::-1].encode("latin-1") + bytes([0x01, typ]) + payload


def u8(t, v):
    return tag(t, 0x11, struct.pack("<B", v))


def u32(t, v):
    return tag(t, 0x01, struct.pack("<I", v))


def fourcc(s: str) -> int:
    return int.from_bytes(s.ljust(4).encode("latin-1")[::-1], "little")


def container(t, kids):
    head = (tag(t, 0x0a, b"") if t else bytes([0x01, 0x0a]))
    return head + struct.pack("<I", len(kids)) + b"".join(kids)


def lst(t, elements):
    return tag(t, 0x0b, struct.pack("<I", len(elements))) + b"".join(elements)


def string(t, s):
    b = s.encode("latin-1")
    return tag(t, 0x1a, struct.pack("<I", len(b)) + b)


def member(fields, declared=None):
    head = bytearray(CR.HEADER.span)
    head[0:6] = b"\x03\x01tad."
    struct.pack_into("<H", head, CR.HEADER.field("season_year").offset, 2026)
    struct.pack_into("<H", head, CR.HEADER.field("base_year").offset, 2000)
    struct.pack_into("<I", head, CR.HEADER.field("n_fields").offset,
                     len(fields) if declared is None else declared)
    return bytes(head) + b"".join(fields) + b"\xff" * 16


def build():
    path = container(None, [
        u32("id", fourcc("bppr")), u8("indx", 0), u8("ntms", 6), u8("type", 0),
        lst("rnds", [container(None, [
            u8("stnm", 151), u8("ntms", 6), u8("nmmt", 3), u8("nmlg", 2)])]),
        container("stnm", [u32("id", fourcc("stnm")), u32("stgn", 2000016479)]),
    ])
    group = container(None, [
        u32("id", fourcc("grou")), u8("indx", 1), u8("ntms", 32), u8("stnm", 73),
        u8("type", 2), u8("ngps", 8),
    ])
    knockout = container(None, [
        u32("id", fourcc("cup")), u8("indx", 2), u8("type", 0),
        lst("rnds", [
            container(None, [tag("stnm", 0x0f, struct.pack("<II", 164, 164)),
                             u8("ntms", 16), u8("nmlg", 2)]),
            container(None, [u8("stnm", 20), u8("ntms", 2), u8("nmlg", 1)]),
        ]),
    ])
    return member([
        u8("ftye", 1), string("desc", "default"),
        lst("stgs", [path, group, knockout]),
        string("SubF", ".\\europe\\"),
    ])


def main() -> int:
    failures = []

    def check(cond, msg):
        if not cond:
            failures.append(msg)

    blob = build()
    check(CR.HEADER.read(blob, 0)["season_year"] == 2026, "header season_year")
    check(CR.locate_comp_rules(blob) == [(CR.HEADER.span, 4)], "locator [(offset, count)]")
    fields = CR.scrape(blob)
    check([f[0] for f in fields] == ["ftye", "desc", "stgs", "SubF"],
          f"top-level tags {[f[0] for f in fields]}")
    rows = CR.stage_rows(1301396, fields)
    got = [(r["stage_index"], r["stage_code"], r["stage_name_id"], r["round_index"],
            r["round_name_id"], r["round_teams"], r["legs"]) for r in rows]
    want = [
        (0, "bppr", 2000016479, 0, 151, 6, 2),     # name via stnm container
        (1, "grou", 73, None, None, None, None),   # scalar name, no round list
        (2, "cup", None, 0, 164, 16, 2),           # pair-typed name
        (2, "cup", None, 1, 20, 2, 1),
    ]
    check(got == want, f"stage rows\n  got  {got}\n  want {want}")
    check(rows[1]["n_groups"] == 8, "n_groups")
    check(all(r["uid"] == 1301396 for r in rows), "uid carried")

    # a truncated member, an over-declared count and an unknown value type must all raise,
    # never return a shorter list
    for label, bad in (
        ("truncated block", blob[:CR.HEADER.span + 20]),
        ("over-declared count", member([u8("ftye", 1)], declared=3)),
        ("unknown type", member([tag("oops", 0x7e, b"\x00\x00")])),
    ):
        try:
            CR.scrape(bad)
            check(False, f"{label} parsed without error")
        except TaggedTableError:
            pass

    # a stub member (declares 0 fields) reads as empty
    check(CR.scrape(member([])) == [], "stub member")

    for f in failures:
        print("FAIL", f)
    print("comp_rules unit:", "OK" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
