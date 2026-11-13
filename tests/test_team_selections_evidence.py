#!/usr/bin/env python3
"""
Evidence for `team_selections` and `formations`, on truro-2026-11-16.

`tests/fixtures/team_selections_evidence.json` holds Truro's Tactics – Captain screen
(`docs/parser/img/captains-fmm27-1.png`). Checked:

  - Truro's slot (team tid 3125) byte for byte, and read as the screen: the XI and the five
    substitutes in the screen's order, then four empty places, then the captain on the pitch
    and the screen's five captains;
  - the 21 formation names, and the 4-4-2 Diamond's eleven position codes, which Truro's
    saved 4-1-2-1-2 carries too;
  - four teams' Tactics - Formation screens (Truro, Maidenhead 4-2-4, Tonbridge 3-4-3,
    Dorking 5-1-2-2): each XI in stored order, Maidenhead's seven substitutes in places 11-17, every starter at the lane the formation's
    code i puts him in (row bit + lane bit, lanes right to left);
  - the locator refuses the pool when a place holds a number no tid can be;
  - both tables locate on every sample save, FMM22 too, with a fixed slot count per career.

    uv run python tests/test_team_selections_evidence.py
"""
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.harness import find_save, sample_saves, skip  # noqa: E402

from fmparser.save import Save  # noqa: E402
from fmparser.tables import formations as FM  # noqa: E402
from fmparser.tables import team_selections as TS  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "team_selections_evidence.json")
COUNTS = {"truro": 17804, "frem": 14506, "bucaspor": 15288}

failures = []


def check(cond, what):
    print(f"  {'ok  ' if cond else 'FAIL'} {what}")
    if not cond:
        failures.append(what)


ROWS = {0x01: "GK", 0x04: "D", 0x08: "DM", 0x10: "M", 0x20: "AM", 0x40: "ST"}
LANES = {0x800: "R", 0x400: "RC", 0x200: "C", 0x100: "LC", 0x080: "L"}


def lane(code):
    """A position code as the row and the lane, right to left: 0x0404 -> 'DRC'. Goalkeeper
    alone; a lone centre striker or midfielder reads 'C'."""
    row = ROWS[code & 0x7F]
    return row if row == "GK" else row + LANES[code & 0xF80]


def main():
    fx = json.load(open(FIXTURE, encoding="utf-8"))
    path = find_save(fx["save"])
    if not path:
        return skip(f"{fx['save']} not found")
    mm = Save(path).mm
    print(fx["save"])

    print(" TRURO'S SLOT")
    base, n = TS.locate_team_selections(mm)
    o = base + fx["team_tid"] * (1 + 4 * TS.places(mm))
    check(bytes(mm[o:o + 65]).hex() == fx["slot_head_hex"], "the u8 and first 16 places' bytes")
    row = {r["team_tid"]: r for r in TS.scrape_team_selections(mm)}[fx["team_tid"]]
    p = row["places"]
    check(row["unknown_0"] == fx["unknown_0"], "the u8 in front")
    check(p[:11] == fx["starting"], "places 0-10: the XI in the screen's order")
    check(p[11:16] == fx["substitutes"], "places 11-15: the five substitutes")
    check(p[16:20] == [None] * 4, "places 16-19: empty (Truro names five substitutes)")
    check(p[20:26] == fx["captains"], "places 20-25: the captains")

    print(" FORMATIONS")
    fms = FM.scrape_formations(mm)
    check([f["name"] for f in fms] == fx["formations_fmm27"], "the 21 names in stored order")
    diamond = next(f for f in fms if f["name"] == "4-4-2 Diamond")
    check(diamond["positions"] == fx["diamond_positions"], "4-4-2 Diamond's eleven codes")
    check(FM.locate_formations(mm)[0] + 21 * FM.STRIDE + 2 == base,
          "the slot count follows the last formation")

    print(" LINEUPS")
    by_name = {f["name"]: f["positions"] for f in fms}
    sel = {r["team_tid"]: r["places"] for r in TS.scrape_team_selections(mm)}
    for tid, team in fx["lineups"].items():
        if tid == "note":
            continue
        codes = by_name[team["formation"]]
        check(sel[int(tid)][:11] == [t for t, _, _ in team["xi"]],
              f"{team['team']}: the XI in the screen's order")
        check([lane(c) for c in codes] == [ln for _, ln, _ in team["xi"]],
              f"{team['team']} ({team['formation']}): every starter where the screen puts him")
        if "bench" in team:
            bench = [t for t, _, _ in team["bench"]]
            check(sel[int(tid)][11:20] == bench + [None] * (9 - len(bench)),
                  f"{team['team']}: places 11-19, the bench S1-S{len(bench)} in order")

    print(" REFUSES")
    buf = bytearray(mm)
    TS._CACHE.clear()
    check(TS.locate_team_selections(bytes(buf)) == (base, n), "a byte copy of the save locates")
    buf[o + 1:o + 5] = struct.pack("<I", 0x12345678)
    TS._CACHE.clear()
    check(TS.locate_team_selections(bytes(buf)) is None, "a place that cannot be a tid")
    TS._CACHE.clear()

    print(" EVERY SAVE")
    for path in sample_saves():
        m = Save(path).mm
        fm, loc = FM.locate_formations(m), TS.locate_team_selections(m)
        career = os.path.basename(path).split("-")[0]
        check(fm is not None and fm[1] == 21 and loc is not None and loc[1] == COUNTS[career],
              f"{os.path.basename(path)}: 21 formations, {loc[1] if loc else '-'} slots")

    if failures:
        print(f"\n{len(failures)} failure(s)")
        return 1
    print("\nall ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
