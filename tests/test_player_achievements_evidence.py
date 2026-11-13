#!/usr/bin/env python3
"""
Evidence for `player_achievements` (the Player Achievements screen), read from 2026-11-13, on
truro-2026-11-16.

`tests/fixtures/player_achievements_evidence.json` holds seven players' screens, line by
line (newest first). Checked:

  - the table locates on every sample save, FMM22 too, and reads every used slot;
  - row 0's raw bytes (Guirassy's African Footballer of the Year);
  - each player's rows, followed from his first by `next_row`, are his screen's lines in
    reverse: the kind (Winner / Runner-Up / Manager Sacked / an award, by the award's name)
    and the club's short name; on frem-2030-06-30 (FMM22) too, when that save is here;
  - every `next_row` is a later row of the same player.

    uv run python tests/test_player_achievements_evidence.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.harness import find_save, sample_saves, skip  # noqa: E402

from fmparser.save import Save  # noqa: E402
from fmparser.tables import player_achievements as PA, tables_for  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "player_achievements_evidence.json")

failures = []


def check(cond, what):
    print(f"  {'ok  ' if cond else 'FAIL'} {what}")
    if not cond:
        failures.append(what)


def matches(row, text, awards):
    """Whether a row reads as the screen's line `text`."""
    kind = row["kind_name"]
    if kind == "award":
        return awards[row["award_id"]]["name"] == text
    return {"winner": text.endswith(" Winner"), "league_won": text.endswith(" Winner"),
            "runner_up": text.endswith(" Runner-Up"),
            "promoted": text.startswith("Promoted from "),
            "relegated": text.startswith("Relegated from "),
            "manager_sacked": text == "Manager Sacked", "club_bankrupt": text == "Club Bankrupt",
            "global_team_of_the_year": text == "Global Team of the Year"}.get(kind, False)


def check_screens(mm, players):
    rows = PA.scrape_player_achievements(mm)
    clubs = {c["tid"]: c["short"] for c in tables_for(mm)["clubs"].scrape(mm)}
    awards = {a["id"]: a for a in tables_for(mm)["awards"].scrape(mm)}
    by_row = {r["row"]: r for r in rows}
    for tid, p in players.items():
        mine = [r for r in rows if r["tid"] == int(tid)]
        heads = {r["row"] for r in mine} - {r["next_row"] for r in mine}
        chain, k = [], (min(heads) if len(heads) == 1 else None)
        while k is not None:
            chain.append(by_row[k])
            k = by_row[k]["next_row"]
        got = list(reversed(chain))
        ok = len(got) == len(p["lines"]) == len(mine) and all(
            matches(r, text, awards) and clubs[r["club_tid"]] == club
            for r, (text, club, _) in zip(got, p["lines"]))
        check(ok, f"{p['name']}: {len(p['lines'])} line(s), newest first, text and club")
    return rows


def main():
    fx = json.load(open(FIXTURE, encoding="utf-8"))
    path = find_save(fx["save"])
    if not path:
        return skip(f"{fx['save']} not found")
    mm = Save(path).mm
    print(fx["save"])
    base = PA.locate_player_achievements(mm)[0][0]
    check(mm[base:base + 24].hex(" ") == fx["row0_bytes"], "row 0's bytes")
    print(" SCREENS")
    rows = check_screens(mm, fx["players"])
    check(len(rows) == fx["rows"], f"{fx['rows']} rows read")
    links = [r for r in rows if r["next_row"] is not None]
    check(all(r["row"] < r["next_row"] < len(rows) and rows[r["next_row"]]["tid"] == r["tid"]
              for r in links), f"{len(links)} next_row links, each to a later row of the same player")

    for more in fx["more"]:
        path = find_save(more["save"])
        if not path:
            print(f"  skip {more['save']}: not found")
            continue
        print(f" SCREENS {more['save']}")
        check_screens(Save(path).mm, more["players"])

    print(" EVERY SAVE")
    for path in sample_saves():
        mm = Save(path).mm
        loc = PA.locate_player_achievements(mm)
        name = os.path.basename(path)
        rows = PA.scrape_player_achievements(mm) if loc is not None else None
        check(rows is not None and len(rows) == len(loc), f"{name}: located, "
              f"{len(rows) if rows is not None else '-'} rows")

    if failures:
        print(f"\n{len(failures)} failure(s)")
        return 1
    print("\nall ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
