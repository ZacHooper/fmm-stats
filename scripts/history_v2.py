#!/usr/bin/env python3
"""Inspect the career-history pool of any save, against in-game Player-History screens.

The parse is `fmparser/tables/history.py`; reading a player's chain is the loader's SQL
(`load_duckdb.load_history`), run here on an in-memory database, so what this prints is
exactly what the store holds.

    python3 scripts/history_v2.py <save.fms>                    # locate + forest check
    python3 scripts/history_v2.py <save.fms> --player 10224     # one player's full career
    python3 scripts/history_v2.py <save.fms> --chain 66162      # raw chain from a record index

Regression anchors (denmark-24-start.fms, in-game 30 Jun 2023) — career Pld/Gls/Ast TOTALS
that must reproduce exactly: Dirksen 9328 = 198/10/0, Andersson 9400 = 286/16/2,
Thrane 9430 = 195/26/4, Fugl 10272 = 46/8/12, Erenbjerg 10224 = 82/19/3.
"""
import argparse
import mmap
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fmparser.core import follow            # noqa: E402
from fmparser.tables import history as H   # noqa: E402
from fmparser.tables.person_info import scrape_person_info  # noqa: E402
from fmparser.tables.player_attributes import scrape_player_attributes  # noqa: E402


def club_names(db):
    try:
        import duckdb
        con = duckdb.connect(db, read_only=True)
        rows = con.execute("SELECT tid, arg_max(name, phase) FROM staging.clubs "
                           "WHERE name IS NOT NULL GROUP BY tid").fetchall()
        con.close()
        return dict(rows)
    except Exception as e:                                   # names are a nicety, not required
        print(f"# (no club names: {e})", file=sys.stderr)
        return {}


def player_lines(hist, tid):
    """[season lines] for one player, debut line first, read by the loader's own SQL."""
    import duckdb
    import load_duckdb as L
    con = duckdb.connect()
    con.execute("CREATE SCHEMA staging")
    for ddl in L.DDL:
        if "staging.player_history" in ddl:
            con.execute(ddl)
    L.load_history(con, 0, "", hist)
    lines = con.execute("SELECT end_year, club_tid, apps, goals, assists, rating, fee "
                        "FROM staging.player_history_seasons WHERE tid = ? ORDER BY seq",
                        [tid]).fetchall()
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("save")
    ap.add_argument("--player", type=int, help="tid to dump")
    ap.add_argument("--chain", type=int, help="record index to walk directly")
    ap.add_argument("--db", default="fm-frem.duckdb", help="store to read club names from")
    a = ap.parse_args()

    with open(a.save, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        print(f"{a.save}\n  {H.locate_history(mm)}  {H.HISTORY_TABLE.check(mm)}")
        if a.player is None and a.chain is None:
            return
        names = club_names(a.db)
        info, attrs = scrape_person_info(mm), scrape_player_attributes(mm)
        hist = H.scrape_history(mm, info, attrs)
        rows = hist["rows"]
        if a.chain is not None:
            for k in follow(rows["next"], a.chain, H.END):
                print(f"    {k:7d}  " + "  ".join(f"{c}={rows[c][k]}" for c in rows))
            return
        print(f"  tid {a.player} -> head record {hist['heads'].get(str(a.player))}")
        lines = player_lines(hist, a.player)
        if not lines:
            print(f"  tid {a.player}: no history"); return
        tot = [0, 0, 0]
        for yr, club, apps, goals, assists, rating, fee in lines:
            club = names.get(club, f"club {club}")
            rat = f"{rating:.2f}" if rating else "    "
            print(f"    {yr-1}/{str(yr)[2:]}  {club[:30]:<30s} {apps:3d} apps "
                  f"{goals:3d} gls {assists:3d} ast  {rat}  [{fee}]")
            tot = [tot[0] + apps, tot[1] + goals, tot[2] + assists]
        print(f"    {'TOTAL':<38s} {tot[0]:3d} apps {tot[1]:3d} gls {tot[2]:3d} ast")


main()
