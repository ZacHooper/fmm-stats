#!/usr/bin/env python3
"""Synthetic unit tests for the club-records table (fmparser/tables/club_records.py) and the
`FixedList` segment under it. No save needed.

  WALK      each club row is read by its own counts: a club with a league list and one
            without land at the right offsets, every block labelled overall/season
  SLOTS     a written slot is emitted with its category; an unwritten one is not, whatever
            the rest of its block holds
  LEAGUES   a league list reads as one row per filled season slot
  FRAMING   a table whose club tids do not ascend, or whose walk reads fewer clubs than
            its count declares, is refused
  AUDIT     `record_instances` yields every element of every fixed list
"""
import dataclasses
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser.core import record_instances  # noqa: E402
from fmparser.tables import club_records as CR  # noqa: E402


def team(cid=0xFFFF, value=0.0, season=0x07E4, day=0, club=0xFFFF, opp=0xFFFF, sf=0xFF,
         sa=0xFF):
    return struct.pack("<fHHHHHBHHBB", value, cid, season, day, 0x0187, 0xFFFF, 4, club, opp,
                       sf, sa)


def player(tid=0xFFFFFFFF, value=0.0, season=0x07E4):
    return struct.pack("<IfIIIH", tid, value, 0 if tid != 0xFFFFFFFF else 0xFFFFFFFF,
                       0xFFFFFFFF, 0xFFFFFFFF, season)


def block(rows, make):
    return b"".join(rows.get(k, make()) for k in range(12))


def league_list(cid, seasons):
    body = [struct.pack("<HBHH", cid, pos, year, teams) for year, pos, teams in seasons]
    return struct.pack("<H", cid) + b"".join(body) + b"\xff" * 7 * (30 - len(seasons))


def club(tid, lists, t_over=None, p_over=None, t_season=None, p_season=None):
    return (struct.pack("<HB", tid, len(lists)) + b"".join(lists)
            + block(t_over or {}, team) + block(p_over or {}, player)
            + block(t_season or {}, team) + block(p_season or {}, player))


def build(clubs):
    head = b"\x00" * 16
    body = struct.pack("<H", len(clubs)) + b"".join(clubs)
    buf = head + body + b"\x00" * 16
    table = dataclasses.replace(CR.CLUB_RECORDS_TABLE,
                                locator=lambda mm: (len(head) + 2, len(clubs)))
    return buf, table


def test_walk():
    print("TESTING the club-records walk")
    a = club(10, [league_list(7, [(2023, 3, 12), (2024, 1, 12)])],
             t_over={4: team(cid=7, value=4.0, season=2024, day=100, club=10, opp=20, sf=4,
                             sa=0),
                     8: team(cid=7, value=5.0, season=2024, club=10, opp=21, sf=1, sa=1)},
             p_season={0: player(tid=555, value=17.0, season=2024)})
    b = club(20, [], p_over={11: player(tid=777, value=1e6, season=2023)})
    buf, table = build([a, b])
    got = CR.scrape_club_records(buf, table)

    t = got["team_records"]
    assert [(r["club_tid"], r["table"], r["slot"], r["category"]) for r in t] == [
        (10, "overall", 4, "biggest_win"), (10, "overall", 8, "most_consecutive_wins")], t
    base_a = 16 + 2 + 3 + CR.LEAGUE_LIST.span
    assert t[0]["offset"] == base_a + 4 * 21 and t[0]["value"] == 4.0
    assert (t[0]["opponent_tid"], t[0]["score_for"], t[0]["score_against"]) == (20, 4, 0)
    assert t[1]["opponent_tid"] is None, "a streak carries no fixture"

    p = got["player_records"]
    assert [(r["club_tid"], r["table"], r["slot"], r["player_tid"]) for r in p] == [
        (10, "season", 0, 555), (20, "overall", 11, 777)], p
    assert p[0]["offset"] == base_a + 12 * 21 + 12 * 22 + 12 * 21
    base_b = 16 + 2 + len(a) + 3
    assert p[1]["offset"] == base_b + 12 * 21 + 11 * 22
    assert p[1]["category"] == "highest_transfer_fee_received"

    assert got["league_history"] == [
        {"club_tid": 10, "cid": 7, "year": 2023, "position": 3, "teams": 12},
        {"club_tid": 10, "cid": 7, "year": 2024, "position": 1, "teams": 12}]

    spans = [(s - 2, e) for s, e in table.spans(buf, include_count_header=False)]
    assert spans == [(16, 16 + 2 + len(a) + len(b))], spans
    n = sum(1 for _ in record_instances(buf, table))
    assert n == (1 + 1 + 48) + (1 + 0 + 48), n     # per club: head, league lists, block rows
    print("  PASS both clubs at their offsets; only written slots; league seasons; audit rows")


def test_framing():
    print("TESTING a misframed table is refused")
    buf, table = build([club(20, []), club(10, [])])
    try:
        CR.scrape_club_records(buf, table)
    except ValueError:
        pass
    else:
        raise AssertionError("descending club tids must fail the scrape")
    buf, table = build([club(10, []), club(20, [])])
    short = dataclasses.replace(table, locator=lambda mm: (18, 3))    # one club more than held
    try:
        CR.scrape_club_records(buf, short)
    except ValueError:
        pass
    else:
        raise AssertionError("a walk that reads fewer clubs than the count must fail")
    print("  PASS descending tids and a short walk both refused")


def main():
    test_walk()
    test_framing()
    return 0


if __name__ == "__main__":
    sys.exit(main())
