#!/usr/bin/env python3
"""
Guard the competition rules (fmparser/tables/comp_rules.py) on real saves.

  PARSE     every comp_<uid>.dat member of every save parses to its declared field count
  COVERAGE  every tag in every member is declared in comp_rules' schemas (read or unread),
            and every required tag is present
  NAMES     every stage and round name id resolves in the save's round-name catalog
  GROUND    the in-game fixture screens, read back through (uid, stage, round):
            EURO Cup  League Path / Third Qualifying Round, Playoff, Group Stage,
                      First Knockout Round (all two-legged)
            Champions Cup  League Path / Second, Third Qualifying Round, Playoff
            3F Superliga   Preliminary Phase, Championship Group
            Sydbank Pokalen  Third Round (round 2), Quarter/Semi Final two-legged

    uv sync --extra archive
    uv run python tests/test_comp_rules.py
"""
import glob
import mmap
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser import archive as A                              # noqa: E402
from fmparser.tables import comp_rules as CR, rounds as R  # noqa: E402

SAVES = os.environ.get("FM_SAVES_DIR", os.path.expanduser("~/fm-saves"))
SKIP = 77

# (uid, stage_index, round_index) -> (stage name, round name, legs); screenshots 2026-09-28
GROUND = {
    (1301396, 0, 0): ("League Path", "Third Qualifying Round", 2),
    (1301396, 2, 0): (None, "Playoff", 2),
    (1301396, 3, None): ("Group Stage", None, None),
    (1301396, 4, 0): (None, "First Knockout Round", 2),
    (1301394, 1, 0): ("League Path", "Second Qualifying Round", 2),
    (1301394, 1, 1): ("League Path", "Third Qualifying Round", 2),
    (1301394, 1, 2): ("League Path", "Playoff", 2),
    (6, 0, None): ("Preliminary Phase", None, None),
    (6, 1, None): ("Championship Group", None, None),
    (1301406, 0, 2): (None, "Third Round", 1),
    (1301406, 0, 4): (None, "Quarter Final", 2),
    (1301406, 0, 5): (None, "Semi Final", 2),
}


def saves():
    return sorted(glob.glob(os.path.join(SAVES, "*", "*.fms")))


def main() -> int:
    paths = saves()
    if not paths:
        print(f"SKIP: no saves under {SAVES}")
        return SKIP
    try:
        import zstandard  # noqa: F401
    except ImportError:
        print("SKIP: needs `uv sync --extra archive`")
        return SKIP
    failures = []
    ground_seen = False
    for p in paths:
        with open(p, "rb") as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            try:
                rows = CR.competition_rounds(mm)
            except CR.RulesError as e:
                failures.append(f"{os.path.basename(p)}: {e}")
                continue
            cov = {}
            for name, ent in A.members(mm).items():
                if CR.MEMBER_PATTERN.match(name):
                    fields = CR.scrape(A.read_member(mm, ent))
                    if fields:
                        CR.FILE.coverage(fields, cov)
            for rec, r in cov.items():
                if r["undeclared"] or r["missing"]:
                    failures.append(f"{os.path.basename(p)} {rec}: undeclared "
                                    f"{r['undeclared']} missing {r['missing']}")
            names = R.round_names_map(mm)
            unresolved = {i for r in rows for i in (r["stage_name_id"], r["round_name_id"])
                          if i is not None and i not in names}
            if unresolved:
                failures.append(f"{os.path.basename(p)}: unresolved name ids {sorted(unresolved)}")
            by = {(r["uid"], r["stage_index"], r["round_index"]): r for r in rows}
            if os.path.basename(p).startswith("frem-") and all(k[0] in {r["uid"] for r in rows}
                                                                for k in GROUND):
                ground_seen = True
                for k, (stage, rnd, legs) in GROUND.items():
                    r = by.get(k)
                    got = None if r is None else (names.get(r["stage_name_id"]),
                                                  names.get(r["round_name_id"]), r["legs"])
                    if got != (stage, rnd, legs):
                        failures.append(f"{os.path.basename(p)} {k}: got {got}, "
                                        f"want {(stage, rnd, legs)}")
            print(f"  {os.path.basename(p)}: {len(rows)} rows, "
                  f"{len({r['uid'] for r in rows})} competitions")
            mm.close()
    if not ground_seen:
        print("  NOTE: no Frem save with every ground-truth competition loaded")
    for f in failures:
        print("FAIL", f)
    print("comp_rules:", "OK" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
