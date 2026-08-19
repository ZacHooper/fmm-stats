#!/usr/bin/env python3
"""Inspect the career-history slab of any save — a thin CLI over `fmparser.history`.

The decode itself lives in the module; this is the debugging front end used to validate a
rewrite against in-game Player-History screenshots.

    python3 scripts/history_v2.py <save.fms>                    # locate + forest sanity check
    python3 scripts/history_v2.py <save.fms> --player 10224     # one player's full career
    python3 scripts/history_v2.py <save.fms> --chain 66162      # raw chain from a row index

Regression anchors (denmark-24-start.fms, in-game 30 Jun 2023) — career Pld/Gls/Ast TOTALS
that must reproduce exactly: Dirksen 9328 = 198/10/0, Andersson 9400 = 286/16/2,
Thrane 9430 = 195/26/4, Fugl 10272 = 46/8/12, Erenbjerg 10224 = 82/19/3.
"""
import argparse
import mmap
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fmparser import history as H          # noqa: E402
from fmparser import staging as S          # noqa: E402


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("save")
    ap.add_argument("--player", type=int, help="tid to dump")
    ap.add_argument("--chain", type=int, help="row index to walk directly")
    ap.add_argument("--db", default="fm-frem.duckdb", help="store to read club names from")
    a = ap.parse_args()

    with open(a.save, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        table = H.Table(mm)
        print(f"{a.save}\n  {table.sanity()}  forest={table.is_forest()}")
        if a.player is None and a.chain is None:
            return
        names = club_names(a.db)
        head = a.chain
        if head is None:
            info, attrs = S.scrape_players(mm), S.scrape_attributes(mm)
            head = H.head_index(mm, info, attrs).get(a.player)
            if head is None or head >= table.rows:
                print(f"  tid {a.player}: no history"); return
            print(f"  tid {a.player} -> chain head row {head}")
        tot = [0, 0, 0]
        for s in table.seasons(head):
            yr, club = s["end_year"], names.get(s["club_tid"], f"club {s['club_tid']}")
            rat = f"{s['rating']:.2f}" if s["rating"] else "    "
            print(f"    {yr-1}/{str(yr)[2:]}  {club[:30]:<30s} {s['apps']:3d} apps "
                  f"{s['goals']:3d} gls {s['assists']:3d} ast  {rat}  [{s['fee']}]")
            for i, k in enumerate(("apps", "goals", "assists")):
                tot[i] += s[k]
        print(f"    {'TOTAL':<38s} {tot[0]:3d} apps {tot[1]:3d} gls {tot[2]:3d} ast")


main()
