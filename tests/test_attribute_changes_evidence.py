#!/usr/bin/env python3
"""
Evidence for `attribute_changes`, on truro-2026-11-16.

`tests/fixtures/attribute_changes_evidence.json` holds seven Player Profile screens: every
arrow beside an attribute, and the player's 23 stored bytes. Checked:

  - each player's row byte for byte;
  - read through the parser, every arrow is its attribute's change with the arrow's sign (a
    double arrow 2 or more), and every attribute without an arrow reads 0, the goalkeeper's
    screen over his own attributes;
  - the locator refuses a span that is not one row per person;
  - the table locates on every sample save, all zero on a day-one save.

    uv run python tests/test_attribute_changes_evidence.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.harness import find_save, sample_saves, skip  # noqa: E402

from fmparser.save import Save  # noqa: E402
from fmparser.tables import attribute_changes as AC  # noqa: E402
from fmparser.tables import training as TR  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "attribute_changes_evidence.json")
OUTFIELD = ("Aerial Crossing Dribbling Passing Shooting Tackling Technique Aggression "
            "Creativity Decisions Leadership Movement Positioning Teamwork Pace Stamina "
            "Strength").split()
KEEPER = ("Aerial Agility Communication Handling Kicking Reflexes Technique Aggression "
          "Creativity Decisions Leadership Throwing Positioning Teamwork Pace Stamina "
          "Strength").split()

failures = []


def check(cond, what):
    print(f"  {'ok  ' if cond else 'FAIL'} {what}")
    if not cond:
        failures.append(what)


def shown(value):
    """A change as its arrow: 1 or -1 for one step, 2 or -2 for two or more."""
    return max(-2, min(2, value))


def main():
    fx = json.load(open(FIXTURE, encoding="utf-8"))
    path = find_save(fx["save"])
    if not path:
        return skip(f"{fx['save']} not found")
    mm = Save(path).mm
    base, n = AC.locate_attribute_changes(mm)
    rows = {r["tid"]: r for r in AC.scrape_attribute_changes(mm)}
    print(f"{fx['save']}: {n} rows at {base}, {len(rows)} set")

    for p in fx["players"]:
        o = base + p["tid"] * AC.STRIDE
        check(bytes(mm[o:o + AC.STRIDE]).hex() == p["row_hex"], f"{p['name']}: stored bytes")
        row = rows.get(p["tid"], {})
        screen = KEEPER if p.get("goalkeeper") else OUTFIELD
        named = [a for a in screen if a in AC.COLUMNS]
        got = {a: shown(row.get(a, 0)) for a in named if row.get(a, 0)}
        check(got == p["arrows"], f"{p['name']}: arrows {p['arrows']} (read {got})")

    for sp in sample_saves():
        m = Save(sp).mm
        loc = AC.locate_attribute_changes(m)
        tr = TR.locate_training(m)
        check(loc is not None and loc[1] == tr[1],
              f"{os.path.basename(sp)}: one row per person ({loc and loc[1]})")

    day_one = find_save("truro-2026-07-22.fms")
    if day_one:
        check(AC.scrape_attribute_changes(Save(day_one).mm) == [],
              "truro-2026-07-22 (day one): no row set")

    # Refusal: a byte too many between player progress and training.
    buf = bytearray(mm)
    tr_base = TR.locate_training(mm)[0]
    shifted = bytes(buf[:base]) + b"\0" + bytes(buf[base:])
    AC._CACHE.clear()
    TR._CACHE.clear()
    check(TR.locate_training(shifted) is not None and tr_base + 1 == TR.locate_training(shifted)[0],
          "refusal: training still locates one byte later")
    check(AC.locate_attribute_changes(shifted) is None, "refusal: the span is refused")

    print(f"\n{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
