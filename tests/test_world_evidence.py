#!/usr/bin/env python3
"""
Evidence for the world tables: what the game shows, the bytes behind it, and what the
parser makes of them, on one save.

`tests/fixtures/world_evidence.json` holds values read off in-game screens of frem-2030-06-22
(the screenshots are in docs/parser/img/, and each table's doc in docs/parser/ maps them). This
test asserts two things for each: the raw bytes at the recorded offset are what the doc says,
and the parsed field equals the value on screen. The first catches a different save; the second
catches a parser change that reads the right bytes into the wrong field.

    uv run python tests/test_world_evidence.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.harness import find_save, skip  # noqa: E402

from fmparser.save import Save  # noqa: E402
from fmparser.tables import (cities, club_records, clubs, currencies, languages,  # noqa: E402
                             nations, save_header, stadiums)

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "world_evidence.json")

failures = []


def check(cond, what):
    print(f"  {'ok  ' if cond else 'FAIL'} {what}")
    if not cond:
        failures.append(what)


def close(a, b, tol=0.0005):
    return a is not None and abs(a - b) <= tol


def main():
    fx = json.load(open(FIXTURE, encoding="utf-8"))
    path = find_save(fx["save"])
    if not path:
        return skip(f"{fx['save']} not found (fetch it with rclone, or rebuild.py)")
    mm = Save(path).mm

    print("RAW BYTES at the recorded offsets")
    for off, hexstr, what in fx["raw"]:
        want = bytes.fromhex("".join(hexstr.split()))
        check(bytes(mm[off:off + len(want)]) == want, f"@{off} {what}")

    print("\nSAVE HEADER (Load Game screen)")
    hdr = save_header.read_save_header(mm)
    for k, v in fx["save_header"].items():
        check(hdr[k] == v, f"{k} = {v!r} (got {hdr[k]!r})")

    print("\nCLUBS (Club Information, squad screen)")
    got = clubs.scrape_clubs(mm)
    for tid, want in fx["clubs"].items():
        c = got[int(tid)]
        for k, v in want.items():
            if k.startswith("_"):
                continue
            if k == "squad_includes":
                check(set(v) <= set(c["squad"]), f"{tid} squad holds the {len(v)} players on screen")
            elif k == "kit_first_colours":
                check([kit[0] for kit in c["kits"][:3]] == v, f"{tid} home/away/third kits {v}")
            elif k == "manager_not_in_staff":
                check(v not in c["staff"], f"{tid} manager {v} is not in the staff list")
            else:
                check(c[k] == v, f"{tid} {k} = {v!r} (got {c[k]!r})")

    print("\nSTADIUMS")
    got = stadiums.scrape_stadiums(mm)
    for sid, want in fx["stadiums"].items():
        for k, v in want.items():
            check(got[int(sid)][k] == v, f"{sid} {k} = {v!r} (got {got[int(sid)][k]!r})")

    print("\nCITIES (real-world coordinates)")
    got = cities.scrape_cities(mm)
    for cid, want in fx["cities"].items():
        c = got[int(cid)]
        check(c["nation_id"] == want["nation_id"], f"{cid} nation_id {want['nation_id']}")
        for k in ("latitude", "longitude"):
            check(close(c[k], want[k], 0.001), f"{cid} {k} {want[k]} (got {c[k]})")

    print("\nNATIONS (League Standards - Coefficients)")
    got = nations.scrape_nations(mm)
    for nid, want in fx["nations"].items():
        n = got[int(nid)]
        co = n["coefficients"]
        check(n["name"] == want["name"], f"{nid} is {want['name']}")
        check(all(close(co[2 + i], v) for i, v in enumerate(want["season_columns"])),
              f"{want['name']}: season columns {want['season_columns']} are slots 2-3")
        check(close(sum(co), want["total"], 0.001),
              f"{want['name']}: total {want['total']} is the sum (got {sum(co):.4f})")
        for k in ("capital_city_id", "national_stadium_id", "continent_id", "is_ranked",
                  "world_ranking", "ranking_points"):
            if k in want:
                check(n[k] == want[k], f"{want['name']} {k} = {want[k]} (got {n[k]})")
        if "youth_squad" in want:
            name, u21, senior = want["youth_squad"]
            c = clubs.scrape_clubs(mm)
            check(c[u21]["name"] == name and c[u21]["main_club_tid"] == senior
                  and c[senior]["uid"] == -n["uid"],
                  f"{want['name']}'s youth squad {name} hangs off its national team {senior}")
    # every national team's club record carries the nation's uid, negated
    nat_uids = {n["uid"] for n in got.values()}
    teams = [c for c in clubs.scrape_clubs(mm).values() if c["uid"] < 0]
    check(len(teams) == len(got) and all(-c["uid"] in nat_uids for c in teams),
          f"{len(teams)} national-team club records carry -(nation uid)")

    print("\nLANGUAGES (nation language lists)")
    got = languages.scrape_languages(mm)
    for lid, want in fx["languages"].items():
        for k, v in want.items():
            check(got[int(lid)][k] == v, f"{lid} {k} = {v!r}")
    check(nations.scrape_nations(mm)[138]["languages"][0] == {"language_id": 31, "proficiency": 100},
          "Denmark's list leads with Danish at 100")

    print("\nCURRENCIES")
    got = {c["name"]: c for c in currencies.scrape_currencies(mm).values()}
    check(got["United Kingdom Pound"]["exchange_rate"] == 1.0, "United Kingdom Pound = 1.0")
    check(len(got) == 173, f"173 currencies (got {len(got)})")
    rate = got["Danish Krone"]["exchange_rate"]
    check(close(rate, fx["currencies"]["Danish Krone"], 1e-6), f"Danish Krone = {rate}")
    worst = max(abs(gbp * rate - dkk) / dkk for gbp, dkk in fx["currencies"]["pairs"])
    check(worst < 0.02, f"every DKK wage on screen is the GBP wage x {rate} within 2% "
                        f"(worst {worst:.1%})")

    print("\nCLUB RECORDS (Club History)")
    cr = fx["club_records"]
    recs = club_records.scrape_club_records(mm)
    team = {r["slot"]: r for r in recs["team_records"]
            if r["club_tid"] == cr["club_tid"] and r["table"] == "overall"}
    for slot, value, cid, season, day, opp, sf, sa in cr["team"]:
        r = team.get(slot)
        good = r is not None and close(r["value"], value) and all(
            want is None or r[k] == want
            for k, want in (("comp_cid", cid), ("season", season), ("day", day),
                            ("opponent_tid", opp), ("score_for", sf), ("score_against", sa)))
        check(good, f"team slot {slot} ({r and r['category']}): {value}")
    player = {r["slot"]: r for r in recs["player_records"]
              if r["club_tid"] == cr["club_tid"] and r["table"] == "overall"}
    for slot, tid, value, season in cr["player"]:
        r = player.get(slot)
        good = (r is not None and close(r["value"], value, max(0.005, abs(value) * 1e-6))
                and (tid is None or r["player_tid"] == tid)
                and (season is None or r["season"] == season))
        check(good, f"player slot {slot} ({r and r['category']}): {value}")
    hist = {(r["cid"], r["year"]): (r["position"], r["teams"])
            for r in recs["league_history"] if r["club_tid"] == cr["club_tid"]}
    for cid, year, pos, teams in cr["league_history"]:
        check(hist.get((cid, year)) == (pos, teams),
              f"league history {year}/{(year + 1) % 100:02d} cid {cid}: {pos} of {teams}")

    print(f"\n{'ALL OK' if not failures else f'{len(failures)} FAILED'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
