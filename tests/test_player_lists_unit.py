#!/usr/bin/env python3
"""Synthetic unit tests for the player-list table (fmparser/tables/player_lists.py). No save
needed.

  LOCATE    found from an empty list, then walked back to a populated first list and on
            to the last: 66 lists, each [100 scrapbook entries][trailer]
  SCRAPE    used entries only (player_tid set), with their strings, fields, date and slot;
            the trailer's season
  FRAMING   a region that does not read as 66 lists is refused
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser.tables import player_lists as PL  # noqa: E402

NO_TID = 0xFFFFFFFF
LISTS, PER_LIST = 66, 100             # measured on every save, not PL.LISTS / PL.PER_LIST


def pstr(s):
    b = s.encode("utf-8")
    return struct.pack("<I", len(b)) + b


def tail(tid=NO_TID, club=0xFFFF, loan=0xFFFF, value=0, attr=0, feet=(0, 0), day=0,
         year=2021):
    t = bytearray(168)
    struct.pack_into("<HH", t, 8, day, year)          # the entry's date
    t[28:64] = bytes([attr]) * 36
    struct.pack_into("<IIHHI", t, 79, tid, 0, club, loan, value)
    t[120:122] = bytes(feet)
    if tid == NO_TID:
        t[121:126] = PL.EMPTY_TAIL_MARK
    return bytes(t)


def entry(name=None, **kw):
    if name is None:
        return b"\x00" * 32 + tail()
    first, last = name.split(" ", 1)
    strings = [name, first, last, "", last, "Club", "", "League"]
    return b"".join(pstr(s) for s in strings) + tail(**kw)


def lst(entries=(), season=0xFFFF):
    body = list(entries) + [entry()] * (PER_LIST - len(entries))
    return b"".join(body) + struct.pack("<BH", 2, season) + b"\x00" * 11


def region(overrides):
    return b"".join(overrides.get(i, lst()) for i in range(LISTS))


def build():
    lists = {
        0: lst([entry("World One", tid=5000, club=900, value=10)], season=2022),
        31: lst([entry("Anders Aa", tid=7001, club=346, value=100, attr=5, day=120, year=2022),
                 entry("Bo Bb", tid=7002, club=99, loan=346, value=50, day=90, year=2022)],
                season=2022),
        32: lst([entry("Anders Aa", tid=7001, club=346, value=200, attr=7, feet=(3, 20),
                       day=30, year=2023)]),
    }
    junk = bytes(range(256)) * 40
    return junk + region(lists) + junk, len(junk)


def clear():
    PL._CACHE.clear()


def test_locate_and_scrape():
    print("TESTING the player-list locator and scrape")
    clear()
    buf, first = build()
    runs = PL.locate_player_lists(buf)
    assert runs and len(runs) == LISTS and runs[0] == (first, PER_LIST), runs[:2]
    lists = PL.scrape_player_lists(buf)
    assert [len(l["entries"]) for l in lists if l["entries"]] == [1, 2, 1]
    assert (lists[0]["season"], lists[31]["season"], lists[32]["season"]) == (2022, 2022, 0xFFFF)
    a = lists[31]["entries"][0]
    assert (a["full_name"], a["last_name"], a["player_tid"], a["club_tid"], a["value"]) == \
        ("Anders Aa", "Aa", 7001, 346, 100), a
    assert lists[31]["entries"][1]["slot"] == 1
    assert (a["scrapbook_day"], a["scrapbook_year"]) == (120, 2022)
    assert lists[31]["entries"][1]["loan_club_tid"] == 346
    spans = PL.player_lists_table_spans(buf)
    assert spans[0][0] == first and spans[-1][1] == len(buf) - first, (spans[0], spans[-1])
    print("  PASS 66 lists from an empty anchor, first list populated; entries, seasons")


def test_framing():
    print("TESTING a region that is not 66 lists is refused")
    clear()
    buf, first = build()
    broken = bytearray(buf)
    o = first + len(region({})) // 2                  # somewhere in the middle
    k = broken.index(PL.EMPTY_TAIL_MARK, o) - PL._MARK_AT     # the start of an unused entry
    struct.pack_into("<I", broken, k, 4000)            # a string longer than any
    try:
        PL.scrape_player_lists(bytes(broken))
    except ValueError:
        pass
    else:
        raise AssertionError("a broken list must fail the scrape")
    print("  PASS")


def main():
    test_locate_and_scrape()
    test_framing()
    return 0


if __name__ == "__main__":
    sys.exit(main())
