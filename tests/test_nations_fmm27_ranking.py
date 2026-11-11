#!/usr/bin/env python3
"""
FMM27 national teams carry a world-ranking history, `[u16 n][n × u16]` after the 17-byte team
body. truro-2026-07-25 holds no ranking update yet, so every history is empty; by
truro-2026-08-08 one update has run, and each team's single entry is its current ranking.
Algeria (id 0) pins the bytes: men 29th, women 74th.

    uv run python tests/test_nations_fmm27_ranking.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.harness import find_save, skip  # noqa: E402

from fmparser.save import Save  # noqa: E402
from fmparser.tables import nations  # noqa: E402

failures = []


def check(cond, what):
    print(f"  {'ok  ' if cond else 'FAIL'} {what}")
    if not cond:
        failures.append(what)


def histories(na):
    for prefix, sex in (("", "men"), ("women_", "women")):
        for n in na.values():
            if n[f"has_{sex}_team"]:
                yield sex, n, n[f"{prefix}ranking_history"], n[f"{prefix}world_ranking"]


def main():
    before, after = find_save("truro-2026-07-25.fms"), find_save("truro-2026-08-08.fms")
    if not (before and after):
        return skip("truro-2026-07-25.fms / truro-2026-08-08.fms not found")

    print("truro-2026-07-25: no ranking update yet")
    na = nations.scrape_nations(Save(before).mm)
    check(len(na) == 251, f"{len(na)} nations")
    check(all(h == [] for _, _, h, _ in histories(na)), "every history is empty")

    print("\ntruro-2026-08-08: one update")
    mm = Save(after).mm
    na = nations.scrape_nations(mm)
    check(len(na) == 251, f"{len(na)} nations")
    alg = na[0]
    off = alg["offset"]
    check(off == 14_752_586, f"Algeria at {off:,}")
    # men: is_ranked 01, world_ranking 1d 00 (29), points 28 06 (1,576), then [n = 1][29]
    check(bytes(mm[off + 74:off + 86]) == bytes.fromhex("01 1d 00 28 06 01 00 1d 00 06 00 00"),
          "men's team bytes: ranked, 29th, 1,576 points, history [29], then 6 coefficients")
    check(bytes(mm[off + 132:off + 144]) == bytes.fromhex("01 4a 00 26 05 01 00 4a 00 00 00 01"),
          "women's team bytes: ranked, 74th, 1,318 points, history [74]")
    check(alg["ranking_history"] == [29] and alg["world_ranking"] == 29, "Algeria men [29]")
    check(alg["women_ranking_history"] == [74] and alg["women_world_ranking"] == 74,
          "Algeria women [74]")
    rows = list(histories(na))
    filled = [(h, r) for _, _, h, r in rows if h]
    check(all(len(h) <= 1 for _, _, h, _ in rows), "no history longer than one entry")
    check(len(filled) == 416, f"{len(filled)} teams with an entry (211 men, 205 women)")
    check(all(h[-1] == r for h, r in filled), "each entry equals the team's world ranking")

    print("\nFAIL" if failures else "\nPASS: FMM27 ranking history")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
