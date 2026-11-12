#!/usr/bin/env python3
"""
Evidence for `award_history` and `team_history` (docs/parser/award_history.md,
team_history.md), on every save found among the eight below.

award_history: every edition names an award the awards table has, every placed person and
club resolves (club ffffffff: none), and each award's latest edition names the same 1st as the awards table
(which the award screens confirm, docs/parser/awards.md). On truro-2026-08-08 the World
Footballer of the Year 2025 is Dembélé, Yamal, Mbappé, as on the International Awards
screen (docs/parser/img/awards-fmm27-1.jpg).

team_history: every team names a team award (Team of the Week / Year, Squad of the Season,
Dream Team, Players' Select, Best XI, All-Star XI), every picked player and club resolves, ratings are
6.0-10.0, and a day-one save has none.

    uv run python tests/test_award_history_evidence.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.harness import find_save, skip  # noqa: E402

from fmparser.save import Save  # noqa: E402
from fmparser.tables import (scrape_award_history, scrape_awards,  # noqa: E402
                             scrape_team_history, tables_for)
from fmparser.tables.person_info import scrape_person_info  # noqa: E402

SAVES = ["frem-2021-06-27.fms", "frem-2023-07-02.fms", "frem-2026-06-11.fms",
         "frem-2030-06-22.fms", "bucaspor-2023-04-01.fms", "truro-2026-07-22.fms",
         "truro-2026-07-25.fms", "truro-2026-08-08.fms"]
COUNTS = {"frem-2021-06-27.fms": (807, 0), "frem-2026-06-11.fms": (1364, 845),
          "truro-2026-08-08.fms": (1124, 4)}
TEAM_WORDS = ("Team of the", "Squad of the", "Dream Team", "Players' Select", "Best XI",
              "All-Star XI")
NONE = 0xFFFFFFFF

failures = []


def check(cond, what):
    print(f"  {'ok  ' if cond else 'FAIL'} {what}")
    if not cond:
        failures.append(what)


def check_save(name):
    path = find_save(name)
    if not path:
        return False
    mm = Save(path).mm
    print(f"\n{name}")
    awards = scrape_awards(mm)
    hist = scrape_award_history(mm)
    teams = scrape_team_history(mm)
    if name in COUNTS:
        check((len(hist), len(teams)) == COUNTS[name], f"{len(hist):,} editions, {len(teams):,} teams")
    persons = scrape_person_info(mm)
    clubs = {c["tid"] for c in tables_for(mm)["clubs"].scrape(mm)}
    placed = [p for e in hist for p in e["places"] if p["person_tid"] != NONE]
    check(all(p["person_tid"] in persons and (p["club_tid"] in clubs or p["club_tid"] == NONE)
              for p in placed), f"all {len(placed):,} placed people and their clubs resolve")
    latest = {}
    for e in hist:
        latest[e["award_id"]] = e
    with_winner = [a for a in awards if a["entries"][0]["person_tid"] != NONE and a["id"] in latest]
    same = sum(latest[a["id"]]["places"][0]["person_tid"] == a["entries"][0]["person_tid"]
               for a in with_winner)
    check(same == len(with_winner), f"latest edition's 1st = the awards table's ({same}/{len(with_winner)})")
    picked = [p for t in teams for p in t["players"] if p["person_tid"] != NONE]
    check(all(any(w in awards[t["award_id"]]["long_name"] for w in TEAM_WORDS) for t in teams),
          "every team names a team award")
    check(all(p["person_tid"] in persons and (p["club_tid"] in clubs or p["club_tid"] == NONE)
              and 6.0 <= p["rating"] <= 10.0
              for p in picked), f"all {len(picked):,} picked players resolve, ratings 6-10")
    if name == "truro-2026-08-08.fms":
        wf = [e for e in hist if e["award_id"] == 0 and e["date"] == "2025-01-01"]
        check([p["person_tid"] for p in wf[0]["places"]] == [21612, 33234, 21609]
              and [p["score"] for p in wf[0]["places"]] == [50, 39, 34],
              "World Footballer 2025: Dembélé 50, Yamal 39, Mbappé 34")
    return True


def main():
    ran = [check_save(n) for n in SAVES]
    if not any(ran):
        return skip("none of the award history evidence saves found")
    print(f"\n{'FAIL' if failures else 'PASS'}: {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
