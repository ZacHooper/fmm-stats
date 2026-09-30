#!/usr/bin/env python3
"""Synthetic unit tests for the training table (fmparser/tables/training.py). No save needed.

  LOCATE    found from rows 0-3 holding tids 0-3 behind the count, past bytes that look
            like a table with the wrong count; the span includes the count
  SCRAPE    players only (unused rows and staff left out), with intensity, role, attribute
            focus and the position decoded from its (band, column) pair
  FRAMING   a row whose tid is neither its index nor unused fails the scrape
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser.tables import training as T  # noqa: E402

STRIDE = 61                         # the row width measured on every save, not T.TRAINING_ROW
COUNT = 12_000


def row(tid, role=0xFFFF, attr=0, intensity=2, band=0, column=0, staff_flag=0):
    r = bytearray(STRIDE)
    struct.pack_into("<IIBIIIHHHHBB", r, 0, tid, 1000 + (tid & 0xFFFF), 7, 50_000, 47_000, 0,
                     intensity, role, staff_flag, attr, band, column)
    return bytes(r)


def table(overrides):
    rows = []
    for k in range(COUNT):
        rows.append(overrides.get(k, row(k, staff_flag=0xFFFF)))
    return struct.pack("<I", COUNT) + b"".join(rows)


def build():
    body = table({
        0: row(0, role=1, attr=6, band=0x01, column=0x00),               # GK, Sweeper Keeper
        1: row(1, role=4, attr=18, intensity=3, band=0x84, column=0x00),  # DL, Wing-Back
        2: row(2, role=21, attr=17, band=0x40, column=0x02),              # ST, Adv. Forward
        3: row(3, role=10, attr=18, band=0x10, column=0x08),              # MR, Inv. Winger
        5: b"\xff" * 4 + bytes(STRIDE - 4),                               # an unused row
    })
    # a decoy: tids 0-3 in place behind an implausible count
    decoy = struct.pack("<I", 7) + b"".join(row(k) for k in range(4))
    junk = bytes(range(256)) * 20
    return junk + decoy + junk + body + junk, len(junk) * 2 + len(decoy) + 4


def test_locate():
    print("TESTING the training locator")
    T._CACHE.clear()
    buf, base = build()
    assert T.locate_training(buf) == (base, COUNT), T.locate_training(buf)
    assert T.training_table_spans(buf) == [(base - 4, base + COUNT * STRIDE)]
    print("  PASS the count-framed table past a decoy with an implausible count")


def test_scrape():
    print("TESTING the training scrape")
    T._CACHE.clear()
    buf, _ = build()
    rows = T.scrape_training(buf)
    assert [r["tid"] for r in rows] == [0, 1, 2, 3], [r["tid"] for r in rows]
    assert rows[0] == {"tid": 0, "intensity": 2, "focus_role": 1, "focus_attribute": 6,
                       "focus_position": "GK"}, rows[0]
    assert [r["focus_position"] for r in rows] == ["GK", "DL", "ST", "MR"]
    assert rows[1]["intensity"] == 3 and rows[2]["focus_attribute"] == 17
    assert T.ROLES[rows[1]["focus_role"]] == "Wing-Back"
    print("  PASS players only; role, attribute, intensity and the decoded position")


def test_framing():
    print("TESTING a row out of place fails the scrape")
    T._CACHE.clear()
    buf, base = build()
    broken = bytearray(buf)
    struct.pack_into("<I", broken, base + 7 * STRIDE, 9)           # row 7 claims tid 9
    try:
        T.scrape_training(bytes(broken))
    except ValueError:
        pass
    else:
        raise AssertionError("a row out of place must fail the scrape")
    print("  PASS")


def main():
    test_locate()
    test_scrape()
    test_framing()
    return 0


if __name__ == "__main__":
    sys.exit(main())
