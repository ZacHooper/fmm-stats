#!/usr/bin/env python3
"""
Evidence for `player_season_stats` (the Player History screen's This Season panel), read from
2026-11-13, on truro-2026-11-16.

`tests/fixtures/player_season_stats_evidence.json` holds Omar Bogle's and Ben Starkie's
Player History screens (`docs/parser/img/player_season_stats-fmm27-*.png`). Checked:

  - each player's six rows, at block * players + sid, byte for byte;
  - each block read as the screen's line: Pld, Gls, Ast, Yel, Red, PoM, and Av R as
    rating_total / apps truncated to two places; block 0 as the 2026/27 history line;
  - Jahrel McKoy's red card (a reserves match in our match table) in his non-competitive row;
  - the locator refuses the table when a row's rating total leaves apps..10 x apps, or when
    block 0 falls short of league + cup + continental;
  - the table locates on every sample save, FMM22 too.

    uv run python tests/test_player_season_stats_evidence.py
"""
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.harness import find_save, sample_saves, skip  # noqa: E402

from fmparser.save import Save, cache_key  # noqa: E402
from fmparser.tables import player_season_stats as PS  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "player_season_stats_evidence.json")

failures = []


def check(cond, what):
    print(f"  {'ok  ' if cond else 'FAIL'} {what}")
    if not cond:
        failures.append(what)


def av_r(row):
    """The screen's Av R: the rating total over apps, truncated to two places."""
    hundredths = row["rating_total"] * 100 // row["apps"]
    return f"{hundredths // 100}.{hundredths % 100:02d}"


def reads_as(row, line):
    """Whether a parsed row (or None, an empty row) shows as the screen's line."""
    if line["apps"] == 0:
        return row is None
    return row is not None and all(row[k] == v for k, v in line.items() if k != "av_r") \
        and av_r(row) == line["av_r"]


def main():
    fx = json.load(open(FIXTURE, encoding="utf-8"))
    path = find_save(fx["save"])
    if not path:
        return skip(f"{fx['save']} not found")
    mm = Save(path).mm
    print(fx["save"])
    rows = PS.scrape_player_season_stats(mm)
    base, players, _ = PS._CACHE[cache_key(mm)]
    by = {(r["sid"], r["block"]): r for r in rows}

    print(" SCREENS")
    for tid, p in fx["players"].items():
        sid = struct.unpack("<I", bytes.fromhex(p["sid"]))[0]
        raw = [mm[base + (b * players + sid) * PS.W:][:PS.W].hex(" ") for b in range(6)]
        check(raw == p["rows"], f"{p['name']}: six rows' bytes")
        for block, line in p["screen"].items():
            check(reads_as(by.get((p["sid"], block)), line), f"{p['name']}: {block} as on screen")

    s = fx["sent_off"]
    row = by.get((s["sid"], s["block"]))
    sid = struct.unpack("<I", bytes.fromhex(s["sid"]))[0]
    check(row is not None and row["reds"] == 1
          and mm[base + (PS.BLOCKS.index(s["block"]) * players + sid) * PS.W:][:PS.W].hex(" ")
          == s["row"], "a red card in a reserves match: one red, non_competitive")

    print(" REFUSES")
    check(PS._check(mm, base, players) is not None, "the save's own blocks pass")
    buf = bytearray(mm[:base + 6 * players * PS.W])
    o = base + (1 * players + 2812) * PS.W
    buf[o + 4:o + 6] = struct.pack("<H", 200)
    check(PS._check(buf, base, players) is None, "a rating total above 10 x apps")
    buf[o + 4:o + 6] = mm[o + 4:o + 6]
    buf[base + 2812 * PS.W] = 18
    check(PS._check(buf, base, players) is None, "block 0 short of league + cup + continental")

    print(" EVERY SAVE")
    for path in sample_saves():
        m = Save(path).mm
        got = PS.scrape_player_season_stats(m) if PS.locate_player_season_stats(m) is not None \
            else None
        check(got is not None, f"{os.path.basename(path)}: located, "
              f"{len(got) if got is not None else '-'} rows")

    if failures:
        print(f"\n{len(failures)} failure(s)")
        return 1
    print("\nall ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
