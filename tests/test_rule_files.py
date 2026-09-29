#!/usr/bin/env python3
"""
Guard the data dictionary's rule files (fmparser/tables/rule_files.py) on real saves.

  LOCATE    667 rule files, and no other count-framed block in the span: a block that is
            not a rule file is a rule file that failed to read
  FRAMING   every group count equals the files that follow; every bare block is a
            nation's merged `_rules`
  COVERAGE  every tag of every rule file is declared by its schema (read or unread), and
            every required tag is present; every file reads through its schema
  TILING    the unread share of the span stays at or under 1%
  ARCHIVE   every configured comp_<uid>.dat member names a rule file the dictionary holds
  TEAMS     team_counts(): 3F Superliga (uid 6) and 3. Division (uid 2000016262) have 12

    uv sync --extra archive
    uv run python tests/test_rule_files.py
"""
import glob
import mmap
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser.core import TaggedTableError                        # noqa: E402
from fmparser.tables import comp_rules as CR, rule_files as RF  # noqa: E402

SAVES = os.environ.get("FM_SAVES_DIR", os.path.expanduser("~/fm-saves"))
SKIP = 77
N_RULE_FILES = 667
MAX_UNREAD = 0.01
TEAMS = {6: 12, 2000016262: 12}         # 3F Superliga, 3. Division -- both 12-team leagues


def saves():
    return sorted(glob.glob(os.path.join(SAVES, "*", "*.fms")))


def archive_files(mm):
    """`file` of every configured comp_<uid>.dat member, or None without zstandard."""
    try:
        from fmparser import archive as A
        import zstandard  # noqa: F401
    except ImportError:
        return None
    out = set()
    for name, ent in A.members(mm).items():
        if CR.MEMBER_PATTERN.match(name):
            fields = CR.scrape(A.read_member(mm, ent))
            out.update(v for t, _, v in fields if t == "file")
    return out


def main() -> int:
    paths = saves()
    if not paths:
        print(f"SKIP: no saves under {SAVES}")
        return SKIP
    failures = []
    for p in paths:
        base = os.path.basename(p)
        with open(p, "rb") as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            files = RF.RULE_FILES_TABLE.blocks(mm)
            t = RF.tiling(mm)
            if t["n_rule_files"] != N_RULE_FILES or t["other_blocks"]:
                failures.append(f"{base}: {t['n_rule_files']} rule files, "
                                f"{t['other_blocks']} bytes of other blocks")
            if t["unread"] > MAX_UNREAD * t["span"]:
                failures.append(f"{base}: {t['unread']} of {t['span']} bytes unread")
            failures += [f"{base}: {e}" for e in RF.framing_problems(mm)]
            cov = RF.RULE_FILES_TABLE.coverage(mm)
            try:
                RF.RULE_FILES_TABLE.scrape(mm)
            except TaggedTableError as e:
                failures.append(f"{base}: {e}")
            for rec, r in cov.items():
                if r["undeclared"] or r["missing"]:
                    failures.append(f"{base} {rec}: undeclared {r['undeclared']} "
                                    f"missing {r['missing']}")
            tc = RF.team_counts(mm)
            got = {uid: tc.get(uid) for uid in TEAMS}
            if got != TEAMS:
                failures.append(f"{base}: team_counts {got}, want {TEAMS}")
            names = archive_files(mm)
            held = {b.get("file") for b in files}
            if names is not None and names - held:
                failures.append(f"{base}: archive members name files the dictionary lacks: "
                                f"{sorted(names - held)}")
            print(f"  {base}: {len(files)} rule files, {t['unread']} of {t['span']} "
                  f"bytes unread ({100 * t['unread'] / t['span']:.2f}%)")
            mm.close()
    for f in failures:
        print("FAIL", f)
    print("rule_files:", "OK" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
