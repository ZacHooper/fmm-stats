#!/usr/bin/env python3
"""
Evidence for `player_form` (the Player Form page), read from 2026-11-13, on truro-2026-11-16.

`tests/fixtures/player_form_evidence.json` holds Omar Bogle's form page: the six matches
the table shows and the chart's goals, star and yellow card for all 20. Checked:

  - the table locates and reads its declared count; FMM22 saves do not locate it;
  - Bogle's 20 lines are the page's 20 matches: rating, goals, assists, substitution arrow
    and morale arrow for the six on screen, and the chart's goals, star and yellow card;
  - against the match table (an independent table), joined on player, opponent and meeting:
    every line with a rating 1-10 of a player in that match's 16 agrees on rating, goals
    (conceded for a goalkeeper), assists and yellow cards.

    uv run python tests/test_player_form_evidence.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.harness import find_save, skip  # noqa: E402

from fmparser.save import Save  # noqa: E402
import statistics  # noqa: E402

from fmparser.tables import (clubs as CL, player_ability_scales, player_form,  # noqa: E402
                             tables_for)
from fmparser.tables.person_info import scrape_person_info  # noqa: E402
from fmparser.tables.player_attributes import scrape_player_attributes  # noqa: E402
from fmparser.tables import matches as MT  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "player_form_evidence.json")
ARROWS = {"green": range(15, 21), "yellow": range(12, 15), "orange": range(10, 12),
          "red": range(1, 10)}

failures = []


def check(cond, what):
    print(f"  {'ok  ' if cond else 'FAIL'} {what}")
    if not cond:
        failures.append(what)


def main():
    fx = json.load(open(FIXTURE, encoding="utf-8"))
    path = find_save(fx["save"])
    if not path:
        return skip(f"{fx['save']} not found")
    mm = Save(path).mm
    print(fx["save"])
    lines = player_form.scrape_player_form(mm)
    check(len(lines) == fx["lines"], f"{fx['lines']} lines read")
    clubs = {c["tid"]: c["short"] for c in tables_for(mm)["clubs"].scrape(mm)}

    print(" BOGLE'S FORM PAGE")
    mine = [x for x in lines if x["tid"] == fx["player"]]
    chart = fx["chart"]
    check(len(mine) == chart["matches"], f"{chart['matches']} lines, one per match")
    for want, got in zip(fx["screen_last_six"], mine[-6:]):
        name = clubs.get(got["opponent_tid"], "")
        check(name.startswith(want["opponent"].split()[0]), f"opponent {want['opponent']}")
        for k in ("rating", "goals", "assists", "substitution"):
            check(got[k] == want[k], f"{want['opponent']}: {k} {want[k]}")
        check(got["morale"] in ARROWS[want["arrow"]],
              f"{want['opponent']}: morale {got['morale']} fits the {want['arrow']} arrow")
    for i, x in enumerate(mine, 1):
        check(x["goals"] == chart["goals"].get(str(i), 0), f"match {i}: {x['goals']} goals")
        check((x["rating"] == 0) == (i in chart["no_bar"]), f"match {i}: bar drawn as rated")
        check(bool(x["player_of_match"]) == (i in chart["star"]), f"match {i}: star")
        check(bool(x["yellow_cards"]) == (i in chart["yellow"]), f"match {i}: yellow card")

    print(" V THE MATCH TABLE")
    meetings, seen, agree, total = {}, {}, 0, 0
    for m in sorted(MT.scrape_matches(mm), key=lambda m: m["date"]):
        for side, opp in (("home_xi", m["away_tid"]), ("away_xi", m["home_tid"])):
            for p in m[side]:
                meetings.setdefault((p["tid"], opp), []).append(p)
    for x in lines:
        key = (x["tid"], x["opponent_tid"])
        k = seen.get(key, 0)
        seen[key] = k + 1
        if not 1 <= x["rating"] <= 10:
            continue
        found = meetings.get(key, [])
        if k >= len(found):
            continue
        p = found[k]
        goals = p["conceded"] if p["posOrder"] == 1 else p["goals"]
        total += 1
        agree += (x["rating"], x["goals"], x["assists"], x["yellow_cards"]) == \
                 (p["rating"], goals, p["assists"], p["yellow"])
    check(total > 300 and agree == total,
          f"rated lines agree with the match table: {agree} of {total}")

    print(" PLAYER ROWS: league_ability")
    full = player_ability_scales.scrape_player_ability_scales(mm)
    rows = {r["tid"]: r["league_ability"] for r in full}
    youth = {r["tid"]: r["youth_international_rating"] for r in full}
    check(len(rows) == player_ability_scales.locate_player_ability_scales(mm)[1],
          f"{len(rows):,} rows read")
    cr = fx["coach_report"]
    by_star = {}
    for tid, star in cr["stars"].items():
        by_star.setdefault(star, []).append(rows[int(tid)])
    stars = sorted(by_star)
    check(all(max(by_star[a]) < min(by_star[b]) for a, b in zip(stars, stars[1:])),
          f"the Coach Report's ability stars order by league_ability: "
          f"{ {k: sorted(v) for k, v in by_star.items()} }")
    # within a league, league_ability is current ability (joined on tid -> sid; the field
    # under test comes out)
    persons, attrs = scrape_person_info(mm), scrape_player_attributes(mm)
    clubs_league = {t: c.get("league_cid") for t, c in CL.scrape_clubs(mm).items()}
    leagues = {}
    for tid, v in rows.items():
        p = persons.get(tid)
        a = attrs.get(p["sid"]) if p else None
        if a:
            leagues.setdefault(clubs_league.get(p["club_tid"]), []).append((v, a["ca"]))
    rs = [statistics.correlation([x for x, _ in l], [y for _, y in l]) for l in leagues.values()
          if len(l) >= 100 and len({x for x, _ in l}) > 3]
    check(len(rs) > 50 and statistics.median(rs) > 0.9,
          f"within a league it tracks ability: median r {statistics.median(rs):.3f} "
          f"over {len(rs)} leagues")

    print(" PLAYER ROWS: youth_international_rating")
    eng = fx["england_u21"]
    pool = sorted((v for t, v in youth.items() if v is not None
                   and persons.get(t, {}).get("nationality_id") == eng["nation_id"]), reverse=True)
    cut = pool[eng["top"] - 1]
    check(all(youth[t] is not None and youth[t] >= cut for t in eng["tids"]),
          f"England U21's eleven are in the top {eng['top']} of {len(pool):,} English "
          f"young players by it")
    olds = [t for t, p in persons.items() if p.get("dob") and p["dob"] < "2004-01-01"
            and t in youth]
    check(all(youth[t] is None for t in olds), f"None for all {len(olds):,} players born "
                                               f"before 2004")

    fmm22 = find_save("frem-2026-06-11.fms")
    if fmm22:
        check(player_form.locate_player_form(Save(fmm22).mm) is None
              and player_ability_scales.locate_player_ability_scales(Save(fmm22).mm) is None,
              "frem-2026-06-11 (FMM22): neither located")

    print(f"\n{'FAIL' if failures else 'PASS'}: {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
