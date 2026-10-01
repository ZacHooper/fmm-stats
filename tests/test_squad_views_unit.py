#!/usr/bin/env python3
"""Synthetic unit tests for the squad views (fmstats/models/people.py). No save needed.

  EXACT     a player in our first-team or reserve squad array takes his name from his
            latest entry in the Manager's Best Eleven lists, and his feet, value and 16
            entangled attributes from it while it is at most a year old; the 7 plain
            attributes always come from his own record
  ESTIMATE  a player outside both arrays keeps his own record, whatever the lists say
  LOAN      a player in our array whose own record names another club is on loan to us
            from it; one whose record names ours is not
  LISTS     the World Best XI lists are not our squad's
"""
import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import duckdb  # noqa: E402

import load_duckdb as L  # noqa: E402
from fmparser.model import ATTR_ORDER  # noqa: E402

S, P = 2026, "2026-06-11"
FIRST, RESERVE, OTHER = 346, 7296, 900


def raw(con, tid, name, club, pace):
    # his name is his common name: nicknames id `tid` -> browse ordinal `tid`
    con.execute("INSERT INTO raw.players_raw (season, phase, tid, common_name_id, is_staff,"
                " club_tid, club, foot_left, foot_right) VALUES (?, ?, ?, ?, FALSE, ?, ?, 5, 20)",
                [S, P, tid, tid, club, f"club {club}"])
    con.execute("INSERT INTO raw.name_ids VALUES (?, ?, 'nicknames', ?, ?)", [S, P, tid, tid])
    con.execute("INSERT INTO raw.name_strings VALUES (?, ?, ?, ?)", [S, P, tid, name])
    cols = ", ".join(f'"{a}"' for a in ATTR_ORDER)
    vals = [pace if a == "Pace" else None for a in ATTR_ORDER]
    con.execute(f"INSERT INTO raw.player_attributes_exact_raw (season, phase, tid, {cols}) "
                f"VALUES (?, ?, ?, {', '.join('?' * len(ATTR_ORDER))})", [S, P, tid] + vals)


def entry(con, lst, tid, name, day, attr, value, club=FIRST, loan=0xFFFF):
    cols = ["season", "phase", "list", "slot", "player_tid", "full_name", "club_tid",
            "loan_club_tid", "scrapbook_date", "value", "foot_left", "foot_right"]
    cols += list(ATTR_ORDER)
    vals = [S, P, lst, tid, tid, name, club, loan, datetime.date(2026, 1, 1)
            + datetime.timedelta(day), value, 20, 1] + [attr] * len(ATTR_ORDER)
    con.execute(f"INSERT INTO raw.player_scrapbook ({', '.join(chr(34) + c + chr(34) for c in cols)}) "
                f"VALUES ({', '.join('?' * len(cols))})", vals)


def build():
    con = duckdb.connect()
    L.create_schema(con)
    con.execute("INSERT INTO raw.app_config VALUES ('career_managed_tid', ?)", [str(FIRST)])
    con.execute("INSERT INTO raw.extracts (season, phase, label, source_dir, loaded_at) "
                "VALUES (?, ?, 'x', 'x', now())", [S, P])
    con.execute("INSERT INTO raw.club_details (season, phase, tid, main_club_tid) "
                "VALUES (?, ?, ?, ?)", [S, P, RESERVE, FIRST])
    for tid, name in ((FIRST, "Frem"), (RESERVE, "Frem Reserves"), (OTHER, "Other FC")):
        con.execute("INSERT INTO raw.clubs VALUES (?, ?, ?, ?)", [S, P, tid, name])
    squad = [(FIRST, 1), (FIRST, 2), (RESERVE, 3), (FIRST, 5), (RESERVE, 6)]
    con.executemany("INSERT INTO raw.club_squad VALUES (?, ?, ?, ?, 0)",
                    [(S, P, c, t) for c, t in squad])
    raw(con, 1, "Owned One", FIRST, 11)          # first team, two entries
    raw(con, 2, "Loanee Two", OTHER, 12)         # in our array, owned by OTHER
    raw(con, 3, "Reserve Three", RESERVE, 13)    # reserve side
    raw(con, 4, "Ghost Four", OTHER, 14)         # in our old lists, not in an array
    raw(con, 5, "No Entry Five", FIRST, 15)      # in the array, no entry yet
    raw(con, 6, "Old Six", RESERVE, 16)          # in the array, entry over a year old
    entry(con, 31, 1, "Owned One", 30, 6, 100)
    entry(con, 32, 1, "Owned One", 150, 7, 200)             # the latest: wins
    entry(con, 32, 2, "Loanee Two", 150, 8, 300, club=OTHER, loan=FIRST)
    entry(con, 32, 3, "Reserve Three", 150, 9, 400, club=RESERVE)
    entry(con, 31, 4, "Ghost Four", 30, 10, 500, club=OTHER, loan=FIRST)
    entry(con, 0, 1, "World One", 300, 19, 999)             # a World Best XI list
    entry(con, 33, 6, "Old Six", -230, 12, 600, club=RESERVE)  # 2025-05-16: 391 days
    return con


def main():
    con = build()
    rows = {r[0]: r[1:] for r in con.execute(
        "SELECT tid, name, club_tid, club, foot_left, player_value, loaned_in, parent_club_tid,"
        " parent_club, scrapbook_date FROM raw.players ORDER BY tid").fetchall()}
    pace = dict(con.execute('SELECT tid, "Pace" FROM raw.player_attributes_exact').fetchall())
    teamwork = dict(con.execute('SELECT tid, "Teamwork" FROM raw.player_attributes_exact')
                    .fetchall())

    print("TESTING a squad player takes his latest Manager's list entry")
    assert rows[1][:6] == ("Owned One", FIRST, "club 346", 20, 200, False), rows[1]
    assert rows[1][8] == datetime.date(2026, 5, 31), rows[1]
    assert teamwork[1] == 7, "entangled from the latest entry, not the World list"
    assert pace[1] == 11, "plain attributes from his own record"
    assert rows[3][:2] == ("Reserve Three", RESERVE) and teamwork[3] == 9, rows[3]
    print("  PASS latest entry; plain from the record; the reserve side is ours; World lists ignored")

    print("TESTING an entry over a year old")
    assert rows[6] == ("Old Six", RESERVE, "club 7296", 5, None, False, None, None, None), rows[6]
    assert teamwork[6] is None and pace[6] == 16
    print("  PASS his name from it; feet, value and entangled attributes from his record and the estimate")

    print("TESTING a player outside our arrays keeps his own record")
    assert rows[4] == ("Ghost Four", OTHER, "club 900", 5, None, False, None, None, None), rows[4]
    assert pace[4] == 14 and teamwork[4] is None
    assert rows[5][4] is None and pace[5] == 15, "in the array, no entry: his own record"
    print("  PASS the ghost is at his own club, not loaned in; no entry means no exact values")

    print("TESTING a loanee")
    assert rows[2][1:8] == (FIRST, "Frem", 20, 300, True, OTHER, "club 900"), rows[2]
    assert teamwork[2] == 8 and pace[2] == 12
    print("  PASS under our club, parent club from his own record")
    return 0


if __name__ == "__main__":
    sys.exit(main())
