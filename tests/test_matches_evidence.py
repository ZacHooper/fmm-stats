#!/usr/bin/env python3
"""
Evidence for the match tables: what the game shows, the bytes behind it, and what the parser
makes of them, on one save.

`tests/fixtures/matches_evidence.json` holds values read off in-game screens of
frem-2030-06-22 (Vejle 2-4 Frem: the report, the stats and both Player Ratings screens; the
screenshots are in docs/parser/img/, and docs/parser/matches.md, fixtures.md, officials.md
and rounds.md map them). This test asserts two things for each: the raw bytes at the
recorded offset are what the doc says, and the parsed field equals the value on screen. The
first catches a different save; the second catches a parser change that reads the right
bytes into the wrong field.

    uv run python tests/test_matches_evidence.py
"""
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.harness import find_save, skip  # noqa: E402

from fmparser.core import archive as A  # noqa: E402
from fmparser.save import Save  # noqa: E402
from fmparser.tables import fixtures, matches, officials, rounds  # noqa: E402
from fmparser.tables import comp_rules  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "matches_evidence.json")

failures = []


def check(cond, what):
    print(f"  {'ok  ' if cond else 'FAIL'} {what}")
    if not cond:
        failures.append(what)


def appeared(p):
    return p["posOrder"] <= 11 or p["subOn"] != 0xFF


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
    blob = A.extract(mm, fixtures.MEMBER)
    for member, off, hexstr, what in fx["archive_raw"]:
        want = bytes.fromhex("".join(hexstr.split()))
        check(bytes(blob[off:off + len(want)]) == want, f"{member} @{off} {what}")

    print("\nMATCHES (Match Report, Match Stats, Player Ratings)")
    w = fx["match"]
    ms = [m for m in matches.scrape_matches(mm)
          if (m["date"], m["home_tid"], m["away_tid"]) == (w["date"], w["home_tid"], w["away_tid"])]
    check(len(ms) == 1, f"one row for {w['date']} {w['home_tid']} v {w['away_tid']}")
    if not ms:
        return 1
    m = ms[0]
    check(m["comp_id"] == w["comp_id"], f"competition {w['comp_id']} (3F Superliga)")
    check(m["attendance"] == w["attendance"], f"attendance {w['attendance']:,}")
    check([m["score"]["home"], m["score"]["away"]] == w["score"], f"score {w['score']}")
    check(m["player_of_match"] == w["player_of_match"], "Player of the Match is the starred player")
    check(m["formation"] == w["formation"], f"kick-off formation {w['formation']}")
    for side in ("home", "away"):
        check(m[f"{side}_positions"] == w[f"{side}_positions"],
              f"{side} positions as the ratings screen lists them (full time)")
    check(m["kickoff_positions"] != m["away_positions"],
          "kick-off slots differ from the full-time sheet after the change")
    names = {v: k for k, v in matches.EVENT_TYPE.items()}
    got = [[matches.EVENT_TYPE.get(e["type_byte"]), e["minute"] + 1, e["added"], e["side"], e["tid"]]
           for e in m["events"]]
    check(got == w["events"], f"the {len(w['events'])} events, minute + 1 as shown (got {got})")
    check(all(n in names for n, *_ in w["events"]), "every event type is named")

    cols = w["columns"]
    for side in ("home", "away"):
        slots = {p["tid"]: p for p in m[f"{side}_xi"]}
        check(len(slots) == len(w[side]), f"{side}: {len(w[side])} used slots")
        for pos_order, (label, name, tid, line, icon, _goals) in enumerate(w[side], 1):
            p = slots.get(tid)
            if p is None:
                check(False, f"{side} {name} ({tid}) has a slot")
                continue
            ok = p["posOrder"] == pos_order
            if line is None:
                # The screen shows '-': an unused substitute. The slot still holds a
                # condition and a rating of 6, so appearance is read from subOn.
                ok = ok and not appeared(p) and p["rating"] == 6 and p["condition"] == 100
            else:
                ok = ok and [p[c] for c in cols] == line and appeared(p)
            ok = ok and (p["subOn"] != 0xFF) == ("on" in icon)
            ok = ok and (p["subOff"] != 0xFF) == ("off" in icon)
            ok = ok and p["yellow"] == ("yellow" in icon)
            check(ok, f"{side} {label} {name}: the screen's line")

    for k, (a, b) in w["team"].items():
        sums = []
        for side in ("home", "away"):
            xs = m[f"{side}_xi"]
            sums.append(sum(p[k] for p in xs))
        check(sums == [a, b], f"team {k} {a} / {b} = the player slots (got {sums})")
    got = [[sum(p["rating"] for p in m[f"{s}_xi"] if appeared(p)),
            sum(1 for p in m[f"{s}_xi"] if appeared(p))] for s in ("home", "away")]
    check(got == w["rating_sum_count"],
          f"team rating {w['rating_screen']}: ratings {got} over the players who appeared")

    raw = [r for r in matches.MATCHES_TABLE.scrape(mm) if r["offset"] == m["offset"]][0]
    teams = (raw["offset"] + matches.MATCH_HEAD.span + 1 + matches.EVENT.span * len(raw["events"])
             + matches.BODY_HEAD.span + matches.EVENT_SLOTS * matches.EVENT.span)
    for off, want in w["team_head"].items():
        got = [mm[teams + k * matches.TEAM.span + int(off)] for k in range(2)]
        check(got == want, f"team head +{off} = {want} (candidate)")
    heads = b"".join(bytes(mm[teams + k * matches.TEAM.span:teams + k * matches.TEAM.span + 77])
                     for k in range(2))
    check(bytes([50]) not in heads, "possession 50 / 50 is in neither team head")

    print("\nFIXTURES (the same match in the world results list)")
    f = fx["fixture"]
    rows = [r for r in fixtures.scrape(blob)
            if (r["date"], r["home_tid"], r["away_tid"]) == (f["date"], f["home_tid"], f["away_tid"])]
    check(len(rows) == 1, "one fixture record, home-first, dated as on screen (DAY_BASE)")
    if rows:
        r = rows[0]
        for k in ("home_goals", "away_goals", "seq_id", "stage_index", "season_year"):
            check(r[k] == f[k], f"{k} = {f[k]}")
    refs = []
    for s, n in fixtures.segments(blob):
        for o in range(s, s + 92 * n, 92):
            rec = fixtures.read_fixture(blob, o)
            if (rec["date"], rec["home_tid"], rec["away_tid"]) == (f["date"], f["home_tid"], f["away_tid"]):
                refs.append(struct.unpack_from("<I", blob, o + 72)[0])
    check(refs == [f["referee_tid"]], f"fixture +72 is the referee's tid {f['referee_tid']}")

    print("\nOFFICIALS (the referee on the Match Report)")
    o = fx["official"]
    offs = officials.scrape_officials(mm)
    rec = offs[o["slot_id"]]
    check((rec["tid"], rec["uid"]) == (o["tid"], o["uid"]), f"record {o['slot_id']} is tid {o['tid']}")
    comps = [struct.unpack_from("<I", rec["competitions_raw"], 4 * i)[0] for i in range(16)]
    check([c for c in comps if c != 0xFFFFFFFF] == o["competitions"],
          f"he referees competition uid {o['competitions']} (3F Superliga)")

    print("\nROUNDS (the Match Report's stage name)")
    rd = fx["round"]
    check(rounds.round_names_map(mm).get(rd["name_id"]) == rd["stage_name"],
          f"name {rd['name_id']} = {rd['stage_name']!r}")
    stages = [s for s in comp_rules.competition_rounds(mm)
              if s["uid"] == rd["comp_uid"] and s["stage_index"] == rd["stage_index"]]
    check(bool(stages) and stages[0]["stage_name_id"] == rd["name_id"],
          f"the Superliga's stage {rd['stage_index']} is named {rd['name_id']}")

    print()
    if failures:
        print(f"FAIL: {len(failures)} check(s)")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
