#!/usr/bin/env python3
"""
Evidence for `club_seasons` and `club_titles` (docs/parser/club_seasons.md, club_titles.md).

On every save found among the eight below: the pool is found after the tactic history, every
stored season names the managed club, and points = 3 x won + drawn on every league line.
On frem-2026-06-11 the 2025/26 line is checked against the world fixture list (both league
stages, 22 + 10 games): 32 played, 14 won, 7 lost, 11 drawn, 44-27, 53 points. Frem's four
league titles (3. Division 2021, 2. Division 2022, NordicBet Liga 2023, 3F Superliga 2028,
club_titles) read position index 0, and every title year club_titles holds is a position-0
season in club_seasons. On truro-2026-08-08 the
season in progress is the National League South after the 1-0 opener: played 1, won
1, 3 points.

    uv run python tests/test_club_seasons_evidence.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.harness import find_save, skip  # noqa: E402

from fmparser.save import Save  # noqa: E402
from fmparser.tables import (extract_world_fixtures, scrape_club_seasons,  # noqa: E402
                             scrape_club_titles)

SAVES = ["frem-2021-06-27.fms", "frem-2023-07-02.fms", "frem-2026-06-11.fms",
         "frem-2030-06-22.fms", "bucaspor-2023-04-01.fms", "truro-2026-07-22.fms",
         "truro-2026-07-25.fms", "truro-2026-08-08.fms"]
CLUB = {"frem": 346, "bucaspor": 6567, "truro": 3125}
TITLES = {2021: 1147, 2022: 4, 2023: 3, 2028: 2}

failures = []


def check(cond, what):
    print(f"  {'ok  ' if cond else 'FAIL'} {what}")
    if not cond:
        failures.append(what)


def league_from_fixtures(mm, club, season, stage_keys):
    w = d = l = gf = ga = 0
    for x in extract_world_fixtures(mm):
        if x["season_year"] != season or x["stage_key"] not in stage_keys or x["home_goals"] is None:
            continue
        if club not in (x["home_tid"], x["away_tid"]):
            continue
        home = x["home_tid"] == club
        f, a = (x["home_goals"], x["away_goals"]) if home else (x["away_goals"], x["home_goals"])
        gf, ga, w, d, l = gf + f, ga + a, w + (f > a), d + (f == a), l + (f < a)
    return {"played": w + d + l, "won": w, "lost": l, "drawn": d, "goals_for": gf,
            "goals_against": ga, "points": 3 * w + d}


def check_save(name):
    path = find_save(name)
    if not path:
        return False
    mm = Save(path).mm
    print(f"\n{name}")
    rows = scrape_club_seasons(mm)
    club = CLUB[name.split("-")[0]]
    check(rows and all(r["club_tid"] == club for r in rows), f"{len(rows)} seasons, all the managed club's")
    check(all(r["league"]["points"] == 3 * r["league"]["won"] + r["league"]["drawn"] for r in rows),
          "points = 3 x won + drawn on every line")
    titles = scrape_club_titles(mm)
    got = {(r["league"]["cid"], r["year"]): r["league"]["position_index"] for r in rows}
    won = [(t["cid"], y) for t in titles for y in t["years"]]
    check(all(t["club_tid"] == club for t in titles) and all(got.get(w) == 0 for w in won),
          f"club_titles: {len(won)} title seasons, each position index 0 in club_seasons")
    if name == "frem-2030-06-22.fms":
        check([(t["cid"], t["years"]) for t in titles] == [(1147, [2021]), (4, [2022]), (3, [2023]), (2, [2028, 2029])],
              "titles: 3. Division 2021, 2. Division 2022, NordicBet Liga 2023, 3F Superliga 2028-29")
    if name == "frem-2026-06-11.fms":
        line = {k: v for k, v in rows[-1]["league"].items() if k not in ("cid", "position_index")}
        check(rows[-1]["year"] == 2025 and line == league_from_fixtures(mm, club, 2025, {45, 133}),
              f"2025/26 line = the fixture list's two league stages: {line}")
    if name == "frem-2030-06-22.fms":
        got = {r["year"]: (r["league"]["cid"], r["league"]["position_index"]) for r in rows}
        check(all(got[y] == (cid, 0) for y, cid in TITLES.items()),
              "the four league titles read position index 0 in their league")
    if name == "truro-2026-08-08.fms":
        lg = rows[-1]["league"]
        check(rows[-1]["year"] == 2026 and lg["cid"] == 331
              and (lg["played"], lg["won"], lg["goals_for"], lg["goals_against"], lg["points"]) == (1, 1, 1, 0, 3),
              "2026/27 National League South after the 1-0 opener")
    return True


def main():
    ran = [check_save(n) for n in SAVES]
    if not any(ran):
        return skip("none of the club seasons evidence saves found")
    print(f"\n{'FAIL' if failures else 'PASS'}: {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
