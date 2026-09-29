#!/usr/bin/env python3
"""Synthetic unit tests for the data dictionary's rule files (fmparser/tables/rule_files.py).

Builds a region in memory in the layout the module docstring describes -- a dated record
and a bare `<nat>_rules`, then a separator, a group count and a group of four tagless
container files (`_comps`, `_reserve_comps`, `_rules` and a competition file with a stage
list) -- with the type codes the strict reader accepts only since the dictionary needed
them: an f64 (`cash`), a u32 id of type 0x15 (`Ttea`) and a tag that is not four printable
characters. Zero save dependency.
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser.core import TreeError, read_tree, scan_tagged_blocks  # noqa: E402
from fmparser.tables import comp_rules as CR, rule_files as RF  # noqa: E402

from test_comp_rules_unit import container, lst, string, tag, u8, u32, fourcc  # noqa: E402


def f64(t, v):
    return tag(t, 0x05, struct.pack("<d", v))


def rule_file(name, extra):
    return [u8("ftye", 1), u8("vers", 12)] + extra + [
        string("file", name), u8("XSvC", 1), string("EdBr", "main"),
        tag("EdDt", 0x20, struct.pack("<I", 0)), string("SubF", ".\\europe\\dan\\")]


def bare(fields):
    return struct.pack("<I", len(fields)) + b"".join(fields)


def group(files, declared=None):
    body = b"".join(container(None, f) for f in files)
    return struct.pack("<I", len(files) if declared is None else declared) + body


def region(declared=None):
    weird = b"\x20\x7d\x96\x16" + bytes([0x01, 0x03]) + b"\x00"      # tag #16967d20, u8 0
    comp = rule_file("den_premier", [
        u32("comp", 6),
        lst("stgs", [container(None, [
            u32("id", fourcc("leag")), u8("indx", 0), u8("type", 1), u8("ntms", 12)])]),
        container("przm", [f64("cash", 150000.0),
                           tag("Ttea", 0x15, struct.pack("<I", 105180)),
                           u32("DBID", 105180)]),
    ])
    rules = rule_file("den_rules", [container("dsrl", [weird])])
    retm = lst("retm", [
        container(None, [u8("nxss", 0), container("comp", [
            u32("id", fourcc("comp")), u32("comp", 2000016262)]), u8("ntms", 12)]),
        container(None, [u8("nxss", 0), u8("comp", 6), u8("ntms", 12)]),
        container(None, [u8("nxss", 1), u8("comp", 6), u8("ntms", 14)]),   # not in force
        container(None, [u8("nxss", 0), u8("mntm", 16)]),                  # names no comp
    ])
    files = [rule_file("den_comps", [u8("dvlv", 1), retm]),
             rule_file("den_reserve_comps", [u8("rsvl", 1)]),
             rules, comp]
    pad = b"\x00" * 64
    dated = b"\x9d\x04\xeb\x07" * 10 + b"\x00"                        # 41 bytes of dates
    sep = b"\xff\xff\xff\xff\x8e\x00\x0c\x00\x0e\x00\x64\x01"
    return pad + dated + bare(rule_file("den_rules", [u8("dvlv", 1), u8("rsvl", 1)])) \
        + sep + group(files, declared) + pad


def main() -> int:
    failures = []

    def check(cond, msg):
        if not cond:
            failures.append(msg)

    mm = region()
    files = RF.RULE_FILES_TABLE.blocks(mm)
    names = [b.get("file") for b in files]
    check(names == ["den_rules", "den_comps", "den_reserve_comps", "den_rules",
                    "den_premier"], f"files {names}")
    check(RF.is_bare(mm, files[0]) and not any(RF.is_bare(mm, b) for b in files[1:]),
          "bare / container framing")
    check(RF.framing_problems(mm) == [], f"framing {RF.framing_problems(mm)}")
    check([RF.schema_for(b).name for b in files] == [
        "rule_file_nation_rules", "rule_file_nation_comps", "rule_file_nation_reserve_comps",
        "rule_file_nation_rules", "comp_rules_file"], "schema_for")

    comp = files[-1]
    przm = next(v for t, _, v in comp.fields if t == "przm")
    check(przm[0] == ("cash", 0x05, 150000.0), f"f64 {przm[0]}")
    check(przm[1] == ("Ttea", 0x15, 105180), f"0x15 id {przm[1]}")
    dsrl = next(v for t, _, v in files[3].fields if t == "dsrl")
    check(dsrl == [("#16967d20", 0x03, 0)], f"non-printable tag {dsrl}")
    check(CR.stage_rows(6, comp.fields)[0]["stage_code"] == "leag", "stage rows")
    check(RF.RULE_FILES_TABLE.read(files[1])["file"] == "den_comps", "nation read")

    check(RF.team_counts(mm) == {2000016262: 12, 6: 12},
          f"team_counts {RF.team_counts(mm)}")

    t = RF.tiling(mm)
    check(t["n_rule_files"] == 5 and t["other_blocks"] == 0, f"tiling {t}")
    # unread = the separator + the group count + four container heads
    check(t["unread"] == 12 + 4 + 4 * 2, f"unread {t['unread']}")

    # a group whose count does not match the files that follow is a framing problem
    bad = region(declared=3)
    probs = RF.framing_problems(bad)
    check(len(probs) == 1 and "declares 3 files, 4 follow" in probs[0], f"bad k {probs}")

    # a tag the schema neither reads nor lists is reported by coverage
    odd = b"\x00" * 8 + bare(rule_file("den_comps", [u8("zzzz", 1)]))
    cov = RF.NATION_COMPS.coverage(scan_tagged_blocks(odd, 0, len(odd))[0].fields)
    check(cov["rule_file_nation_comps"]["undeclared"] == {"zzzz": 1}, "undeclared tag")

    # the strict reader still rejects an unknown type rather than reading past it
    try:
        read_tree(tag("oops", 0x7e, b"\x00\x00"), 0, 8)
        check(False, "unknown type read without error")
    except TreeError:
        pass

    for f in failures:
        print("FAIL", f)
    print("rule_files unit:", "OK" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
