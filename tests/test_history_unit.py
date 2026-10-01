#!/usr/bin/env python3
"""Synthetic unit tests for the career-history pool (fmparser/tables/history.py), the linked
table engine under it (core.LinkedTableDef, core.forest) and the loader's chain reader
(load_duckdb.load_history). No save needed.

  FOREST   a pool of chains passes; a row reached twice, a pointer out of the pool and a
           cycle each fail
  LOCATE   the pool is found inside unrelated bytes from its own pointers and count, with
           no window or threshold
  SCRAPE   every record comes back column-wise, the header with it
  LOAD     a chain reads as its debut line (seq -1) plus one line per later record, fee
           markers and ratings decoded; a head nothing points at is required, a chain of one
           record is a history
"""
import dataclasses
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser.core import LinkedTableError, follow, forest  # noqa: E402
from fmparser.tables import history as H  # noqa: E402

END = H.END


def record(season, club, nxt, fee=0xFFFF, apps=0, goals=0, assists=0, rating=0, reds=0,
           yellows=0):
    return struct.pack("<BBBBBBHHHI", season, apps, goals, assists, reds, yellows, rating, club,
                       fee, nxt)


def pool():
    """Two chains laid out as the game allocates them, then one appended season:
         A: 0 -> 1 -> 2 -> 5      B: 3 -> 4      (5 appended into a recycled slot)
    """
    recs = [record(48, 100, 1),                                        # A debut: origin club
            record(49, 100, 2, apps=10, goals=2, rating=650),
            record(50, 200, 5, fee=0xFFFE, apps=5),                    # loan move
            record(47, 300, 4),                                        # B debut
            record(48, 300, END, apps=3),
            record(51, 400, END, fee=1500, apps=30, goals=9, assists=4, rating=712, reds=1,
                   yellows=6)]
    return struct.pack("<I", len(recs)) + b"".join(recs)


def over(buf):
    return dataclasses.replace(H.HISTORY_TABLE, locator=lambda mm: (4, (len(buf) - 4) // 16))


def test_forest():
    print("TESTING the forest check")
    ok = forest([1, 2, 5, 4, END, END])
    assert ok.ok and ok.heads == 2 and ok.on_chains == 6, ok
    assert list(follow([1, 2, 5, 4, END, END], 0, END)) == [0, 1, 2, 5]
    assert not forest([1, 2, 1, END]).ok, "row 1 reached twice"
    assert not forest([1, 9, END]).ok, "pointer outside the pool"
    cyc = forest([END, 2, 1])                  # a head/end pair plus a 2-cycle
    assert cyc.heads == cyc.ends and cyc.max_indegree == 1 and not cyc.ok, cyc
    print("  PASS chains pass; a double pointer, an out-of-pool pointer and a cycle fail")


def test_locate_and_scrape():
    print("TESTING the locator and the scrape")
    body = pool()
    junk = bytes(range(256)) * 8
    buf = junk + body + b"\x21\x04\x81\x00\x01\x00\x00\x00" + junk
    H._CACHE.clear()
    assert H.locate_history(buf) == (len(junk) + 4, 6), H.locate_history(buf)
    # A pool whose pointers fail is not found at all -- not swapped for a lookalike: here a
    # one-record frame elsewhere that a pair of neighbouring pointers also names, and that is
    # trivially a forest on its own.
    broken = bytearray(body)
    struct.pack_into("<I", broken, 4 + 16 * 3 + 12, 2)        # row 3 -> row 2: reached twice
    decoy = struct.pack("<I", 1) + record(0, 0, END) + record(0, 0, 2) + record(0, 0, 3)
    H._CACHE.clear()
    assert H.locate_history(junk + bytes(broken) + junk + decoy + junk) is None
    got = over(body).scrape(body)
    assert got["count"] == 6 and got["header"] == {"count": 6}
    assert got["rows"]["next"] == [1, 2, 5, 4, END, END]
    assert got["rows"]["club"] == [100, 100, 200, 300, 300, 400]
    assert got["rows"]["rating"][5] == 712
    assert (got["rows"]["reds"][5], got["rows"]["yellows"][5]) == (1, 6)
    assert over(body).spans(body) == [(0, len(body))]
    bad = bytearray(body)
    struct.pack_into("<I", bad, 4 + 16 * 2 + 12, 1)          # row 2 -> row 1: a cycle
    try:
        over(bytes(bad)).scrape(bytes(bad))
    except LinkedTableError:
        pass
    else:
        raise AssertionError("a cycle must fail the scrape")
    print("  PASS found by its own pointers; every record, the header, and a cycle rejected")


def test_load():
    print("TESTING the loader's chain reader")
    try:
        import duckdb
        import load_duckdb as L
    except ImportError as e:
        print(f"  SKIP: {e}")
        return
    body = pool()
    hist = over(body).scrape(body)
    hist["heads"] = {"7": 0, "8": 3, "9": 1, "10": END, "11": 5}
    # 9 is mid-chain and 10 has none: no history. 11 is a chain of one record (5 is a
    # chain end nothing else points at once 2 is cut): a debut line alone is a history.
    hist["rows"]["next"][2] = END
    con = duckdb.connect()
    con.execute("CREATE SCHEMA raw")
    for ddl in L.DDL:
        if "raw.player_history" in ddl:
            con.execute(ddl)
    L.load_history(con, 2027, "2027-08-08", hist)
    ph = con.execute("SELECT tid, origin_club_tid, last_season_club_tid, record_offset, "
                     "debut_season, debut_end_year FROM raw.player_history "
                     "ORDER BY tid").fetchall()
    assert ph == [(7, 100, 200, hist["base"], 48, 2019),
                  (8, 300, 300, hist["base"] + 48, 47, 2018),
                  (11, 400, 400, hist["base"] + 80, 51, 2022)], ph
    s = con.execute("SELECT tid, seq, end_year, club_tid, fee, apps, goals, assists, rating, "
                    "yellows, reds "
                    "FROM raw.player_history_seasons ORDER BY tid, seq").fetchall()
    assert s == [(7, -1, 2019, 100, "stay", 0, 0, 0, None, 0, 0),
                 (7, 0, 2020, 100, "stay", 10, 2, 0, 6.5, 0, 0),
                 (7, 1, 2021, 200, "loan", 5, 0, 0, None, 0, 0),
                 (8, -1, 2018, 300, "stay", 0, 0, 0, None, 0, 0),
                 (8, 0, 2019, 300, "stay", 3, 0, 0, None, 0, 0),
                 (11, -1, 2022, 400, "1500", 30, 9, 4, 7.12, 6, 1)], s
    print("  PASS the debut line as seq -1, then the season lines; a one-record chain is a "
          "history; mid-chain and missing heads read none")


def main():
    test_forest()
    test_locate_and_scrape()
    test_load()
    return 0


if __name__ == "__main__":
    sys.exit(main())
