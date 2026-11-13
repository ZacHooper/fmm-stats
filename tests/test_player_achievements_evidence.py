#!/usr/bin/env python3
"""
Evidence for `player_achievements` (the Player Achievements screen), read from 2026-11-13, on
truro-2026-11-16.

`tests/fixtures/player_achievements_evidence.json` holds seven players' screens, line by
line (newest first). Checked:

  - the table locates on every Truro save and reads its used rows; FMM22 saves do not
    locate it;
  - row 0's raw bytes (Guirassy's African Footballer of the Year);
  - each player's rows, followed from his first by `next_row`, are his screen's lines in
    reverse: the kind (Winner / Runner-Up / Manager Sacked / an award, by the award's name)
    and the club's short name;
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
from fmparser.tables import player_achievements as PA, save_format, tables_for, FMM27  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "player_achievements_evidence.json")

failures = []


def check(cond, what):
    print(f"  {'ok  ' if cond else 'FAIL'} {what}")
    if not cond:
        failures.append(what)


def screen_text(row, awards):
    kind = row["kind_name"]
    if kind == "award":
        return awards[row["award_id"]]["name"]
    return {"winner": "Winner", "runner_up": "Runner-Up", "manager_sacked": "Manager Sacked"}[kind]


def main():
    fx = json.load(open(FIXTURE, encoding="utf-8"))
    path = find_save(fx["save"])
    if not path:
        return skip(f"{fx['save']} not found")
    mm = Save(path).mm
    print(fx["save"])
    rows = PA.scrape_player_achievements(mm)
    check(len(rows) == fx["rows"], f"{fx['rows']} rows read")
    base = PA.locate_player_achievements(mm)[0]
    check(mm[base:base + 24].hex(" ") == fx["row0_bytes"], "row 0's bytes")
    clubs = {c["tid"]: c["short"] for c in tables_for(mm)["clubs"].scrape(mm)}
    awards = {a["id"]: a for a in tables_for(mm)["awards"].scrape(mm)}

    print(" SCREENS")
    for tid, p in fx["players"].items():
        mine = [r for r in rows if r["tid"] == int(tid)]
        heads = {r["row"] for r in mine} - {r["next_row"] for r in mine}
        chain, k = [], (min(heads) if len(heads) == 1 else None)
        while k is not None:
            chain.append(rows[k])
            k = rows[k]["next_row"]
        got = [(screen_text(r, awards), clubs[r["club_tid"]]) for r in reversed(chain)]
        want = [(text, club) for text, club, _ in p["lines"]]
        ok = len(got) == len(want) and all(
            g[1] == w[1] and (w[0].endswith(g[0]) if g[0] in ("Winner", "Runner-Up") else g[0] == w[0])
            for g, w in zip(got, want))
        check(ok and len(chain) == len(mine), f"{p['name']}: {len(want)} line(s) {got}")

    links = [r for r in rows if r["next_row"] is not None]
    check(all(r["row"] < r["next_row"] < len(rows) and rows[r["next_row"]]["tid"] == r["tid"]
              for r in links), f"{len(links)} next_row links, each to a later row of the same player")

    print(" EVERY SAVE")
    for path in sample_saves():
        mm = Save(path).mm
        loc = PA.locate_player_achievements(mm)
        name = os.path.basename(path)
        if save_format(mm) == FMM27:
            check(loc is not None and len(PA.scrape_player_achievements(mm)) == loc[1],
                  f"{name}: located, {loc[1] if loc else '-'} rows")
        else:
            check(loc is None, f"{name}: FMM22, not located")

    if failures:
        print(f"\n{len(failures)} failure(s)")
        return 1
    print("\nall ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
