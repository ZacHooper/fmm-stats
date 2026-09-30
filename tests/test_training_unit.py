#!/usr/bin/env python3
"""Synthetic unit tests for the training table (fmparser/tables/training.py). No save needed.

  LOCATE    found from rows 0-3 holding tids 0-3 behind the count, past bytes that look
            like a table with the wrong count; the span includes the count
  SCRAPE    players only (unused rows and staff left out), with intensity, role, attribute
            focus and the position decoded from its (band, column) pair
  STATUS    squad status for players under contract only; a free agent's byte is not read
  FRAMING   a row whose tid is neither its index nor unused fails both scrapes
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser.tables import training as T  # noqa: E402

STRIDE = 61                         # the row width measured on every save, not T.TRAINING_ROW
COUNT = 12_000


def row(tid, role=0xFFFF, attr=0, intensity=2, band=0, column=0, staff_flag=0,
        contracted=0, status=0):
    r = bytearray(STRIDE)
    struct.pack_into("<IIBIIIHHHHBB", r, 0, tid, 1000 + (tid & 0xFFFF), 7, 50_000, 47_000, 0,
                     intensity, role, staff_flag, attr, band, column)
    r[37], r[39] = contracted, status
    return bytes(r)


def table(overrides):
    rows = []
    for k in range(COUNT):
        rows.append(overrides.get(k, row(k, staff_flag=0xFFFF)))
    return struct.pack("<I", COUNT) + b"".join(rows)


def build():
    body = table({
        0: row(0, role=1, attr=6, band=0x01, column=0x00,                # GK, Sweeper Keeper
               contracted=T.CONTRACTED, status=3),
        1: row(1, role=4, attr=18, intensity=3, band=0x84, column=0x00,  # DL, Wing-Back
               contracted=T.CONTRACTED, status=T.LOAN_STATUS),
        2: row(2, role=21, attr=17, band=0x40, column=0x02, status=92),  # ST, a free agent
        3: row(3, role=10, attr=18, band=0x10, column=0x08,              # MR, Inv. Winger
               contracted=T.CONTRACTED, status=0),
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
    assert rows[1]["focus_role"] == 4
    print("  PASS players only; role, attribute, intensity and the decoded position")


def test_status():
    print("TESTING the squad status scrape")
    T._CACHE.clear()
    buf, _ = build()
    status = T.scrape_squad_status(buf)
    assert list(status.items()) == [(0, 3), (1, T.LOAN_STATUS), (3, 0)], status
    print("  PASS contracted players only, in tid order; a free agent's status byte unread")


def test_framing():
    print("TESTING a row out of place fails the scrape")
    buf, base = build()
    broken = bytearray(buf)
    struct.pack_into("<I", broken, base + 7 * STRIDE, 9)           # row 7 claims tid 9
    for scrape in (T.scrape_training, T.scrape_squad_status):
        T._CACHE.clear()
        try:
            scrape(bytes(broken))
        except ValueError:
            pass
        else:
            raise AssertionError(f"{scrape.__name__}: a row out of place must fail the scrape")
    print("  PASS")


def main():
    test_locate()
    test_scrape()
    test_status()
    test_framing()
    return 0


if __name__ == "__main__":
    sys.exit(main())
