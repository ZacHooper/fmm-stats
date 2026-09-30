#!/usr/bin/env python3
"""Synthetic unit tests for the match table (fmparser/tables/matches.py). No save needed.

  LOCATE    the table is seeded from any row's formation marker and walked back to row 0,
            whose count byte is the table's; no row, no table
  SCRAPE    every row as stored: the head's events (a row is 5,102 + 17 n bytes), the stored
            score, used player slots only, our formation and starting positions
  INVARIANT a count that declares more rows than walk raises; a body that does not repeat
            its head is not a row
  FIXTURES  the table must hold exactly our clubs' fixtures since the rollover
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser.tables import matches as MT  # noqa: E402

PREFIX = b"\x11" * 3000
AFTER = b"\x8a\x00\x83\x00" * 64
TEAM0 = MT.BODY_HEAD.span + MT.EVENT_SLOTS * MT.EVENT.span
TEAM = MT.TEAM_HEAD.span + MT.PLAYER_SLOTS * MT.PLAYER_SLOT.span + MT.TEAM_TAIL.span
TAIL0 = TEAM0 + 2 * TEAM
# our 3-1-4-2 on the day: GK, then ten outfield (band, column) pairs
POSITIONS = bytes.fromhex("0100040404020401080210089000100410012004")[:20] + b"\x20\x01"


def event(kind, minute, side, tid):
    return struct.pack("<5BI", 8, kind, minute, 0, side, tid) + b"\xff" * 8


def slot(pos_order, tid=None, rating=7, goals=0):
    b = bytearray(b"\x00" * MT.PLAYER_SLOT.span)
    b[3], b[10], b[32], b[41] = 90, goals, rating, pos_order
    b[19] = b[21] = 0xFF
    b[42:46] = struct.pack("<I", MT.NO_PLAYER if tid is None else tid)
    return bytes(b)


def body(home, away, comp, day, year, club, goals, players, formation=b"3-1-4-2"):
    b = bytearray(b"\x00" * MT.BODY_SPAN)
    struct.pack_into("<3HB3HHI", b, 0, club, away if club == home else home, comp,
                     club == home, home, away, day, year, 9000)
    struct.pack_into("<I", b, 63, players[0][0][0])            # Player of the Match
    for side, at in ((0, TEAM0), (1, TEAM0 + TEAM)):
        b[at + 3] = goals[1 - side]
        b[at + 52] = goals[side]
        for k in range(MT.PLAYER_SLOTS):
            used = players[side][k] if k < len(players[side]) else None
            o = at + MT.TEAM_HEAD.span + k * MT.PLAYER_SLOT.span
            b[o:o + MT.PLAYER_SLOT.span] = slot(k + 1, *(used or ()))
    b[MT.MARKER_AT:MT.MARKER_AT + 4] = MT.FORMATION_MARKER
    b[TAIL0 + 37:TAIL0 + 37 + len(formation)] = formation
    b[TAIL0 + 69:TAIL0 + 91] = POSITIONS
    return bytes(b)


def row(home, away, comp, day, events, goals, players, year=2026, club=346):
    return (struct.pack("<4HB", home, away, comp, day, len(events)) + b"".join(events)
            + body(home, away, comp, day, year, club, goals, players))


XI_A = [[(101, 8, 1), (102, 7, 0)], [(201, 6, 1)]]
XI_B = [[(301, 6, 0)], [(101, 7, 0), (102, 9, 2)]]


def rows():
    return [
        row(346, 2426, 65, 190, [event(1, 9, 0, 101), event(1, 51, 1, 201)], (1, 1), XI_A),
        row(344, 346, 2, 200, [event(1, 20, 1, 102), event(1, 70, 1, 102)], (0, 2), XI_B),
        row(346, 368, 2, 210, [], (0, 0), XI_A),
    ]


def table(rs, count=None):
    return PREFIX + bytes([len(rs) if count is None else count]) + b"".join(rs) + AFTER


def test_locate():
    print("TESTING the match-table locator")
    rs = rows()
    MT._CACHE.clear()
    assert MT.locate_matches(table(rs)) == (len(PREFIX) + 1, 3)
    assert [len(r) for r in rs] == [MT.ROW_FIXED + 34, MT.ROW_FIXED + 34, MT.ROW_FIXED]
    MT._CACHE.clear()
    assert MT.locate_matches(PREFIX + b"\x00" + AFTER) is None, "an empty table"
    print("  PASS row 0 and the count, from any row; an empty table is not located")


def test_scrape():
    print("TESTING the scrape")
    MT._CACHE.clear()
    ms = MT.scrape_matches(table(rows()))
    assert [(m["date"], m["home_tid"], m["away_tid"]) for m in ms] == [
        ("2026-07-10", 346, 2426), ("2026-07-20", 344, 346), ("2026-07-30", 346, 368)]
    m = ms[0]
    assert m["offset"] == len(PREFIX) + 1 and m["club_tid"] == 346 and m["home_flag"] == 1
    assert m["score"] == {"home": 1, "away": 1} and m["player_of_match"] == 101
    assert m["events"][1] == {"b0": 8, "type_byte": 1, "minute": 51, "added": 0,
                              "side": 1, "tid": 201}, m["events"]
    assert [p["tid"] for p in m["home_xi"]] == [101, 102], "used slots only"
    assert [p["posOrder"] for p in m["away_xi"]] == [1]
    assert m["formation"] == "3-1-4-2" and len(m["positions"]) == 11
    assert m["positions"][0] == "GK", m["positions"]
    assert ms[1]["home_flag"] == 0 and ms[1]["score"] == {"home": 0, "away": 2}
    assert ms[2]["events"] == []
    print("  PASS events, stored score, used slots, formation and positions per match")


def test_invariant():
    print("TESTING the walk's invariant")
    MT._CACHE.clear()
    try:
        MT.scrape_matches(table(rows(), count=4))
    except MT.MatchTableError:
        pass
    else:
        raise AssertionError("a count the walk cannot reach must raise")
    rs = rows()
    buf = table(rs)
    second = len(PREFIX) + 1 + len(rs[0])                        # row 1, taken for row 0
    MT._CACHE.clear()
    MT._CACHE[MT._cache_key(buf)] = (second, buf[second - 1])
    try:
        MT.scrape_matches(buf)
    except MT.MatchTableError:
        pass
    else:
        raise AssertionError("a later row taken for row 0 must raise, not read as empty")
    bad = bytearray(rs[1])
    at = MT.MATCH_HEAD.span + 1 + 2 * MT.EVENT.span + 7        # the body's home tid
    bad[at:at + 2] = struct.pack("<H", 999)
    buf = table([rs[0], bytes(bad), rs[2]])
    assert MT._body(buf, len(PREFIX) + 1 + len(rs[0])) is None
    MT._CACHE.clear()
    try:
        MT.scrape_matches(buf)
    except MT.MatchTableError:
        pass
    else:
        raise AssertionError("the walk must stop at a row that does not repeat its head")
    print("  PASS an unreachable count raises; a row that does not repeat its head is none")


def test_fixtures():
    print("TESTING the fixture-list check")
    MT._CACHE.clear()
    ms = MT.scrape_matches(table(rows()))
    fx = [{"date": m["date"], "home_tid": m["home_tid"], "away_tid": m["away_tid"]}
          for m in ms] + [{"date": "2026-06-20", "home_tid": 346, "away_tid": 9}]
    MT.check_against_fixtures(ms, fx, {346, 7296}, "2026-06-30", "2026-08-01")
    try:
        MT.check_against_fixtures([], fx, {346, 7296}, "2026-06-30", "2026-08-01")
    except MT.MatchTableError:
        pass
    else:
        raise AssertionError("an empty table while our fixtures were played must raise")
    MT.check_against_fixtures([], fx, {346, 7296}, "2026-07-31", "2026-08-01")
    print("  PASS the same games since the rollover; an empty table only when none were played")


def main():
    test_locate()
    test_scrape()
    test_invariant()
    test_fixtures()
    return 0


if __name__ == "__main__":
    sys.exit(main())
