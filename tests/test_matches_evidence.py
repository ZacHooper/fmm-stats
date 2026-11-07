#!/usr/bin/env python3
"""
Evidence for the match tables: what the game shows, the bytes behind it, and what the parser
makes of them, on one save.

`tests/fixtures/matches_evidence.json` holds values read off in-game screens of
frem-2030-06-22 (Vejle 2-4 Frem: the report, the stats and both Player Ratings screens;
Hedensted 1-8 Frem: the report and Hedensted's Player Ratings; the
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
from fmparser.tables import comp_rules, fixtures, matches, officials, rounds  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "matches_evidence.json")

failures = []


def check(cond, what):
    print(f"  {'ok  ' if cond else 'FAIL'} {what}")
    if not cond:
        failures.append(what)


COLUMNS = ["passA", "passC", "keyPass", "assists", "tackA", "tackW", "intercept", "headA",
           "headW", "crossA", "crossC", "dribbles", "mistakes", "mistGoal", "shotA", "shotO",
           "condition", "rating"]


def appeared(p):
    return p["posOrder"] <= 11 or p["subOn"] != 0xFF


def check_match(mm, w, all_matches, all_raw):
    ms = [m for m in all_matches
          if (m["date"], m["home_tid"], m["away_tid"]) == (w["date"], w["home_tid"], w["away_tid"])]
    check(len(ms) == 1, "one row")
    if not ms:
        return
    m = ms[0]
    check(m["comp_id"] == w["comp_id"], f"competition {w['comp_id']}")
    check(m["attendance"] == w["attendance"], f"attendance {w['attendance']:,}")
    check([m["score"]["home"], m["score"]["away"]] == w["score"], f"score {w['score']}")
    check(m["player_of_match"] == w["player_of_match"], "Player of the Match is the starred player")
    if "formation" in w:
        check(m["formation"] == w["formation"], f"kick-off formation {w['formation']}")
        check(m["kickoff_positions"] != m["away_positions"],
              "kick-off slots differ from the full-time sheet after the change")
    for side in ("home", "away"):
        if f"{side}_positions" in w:
            check(m[f"{side}_positions"] == w[f"{side}_positions"],
                  f"{side} positions as the ratings screen lists them (full time)")
    got = [[matches.EVENT_TYPE.get(e["type_byte"]), e["minute"] + 1, e["added"], e["side"], e["tid"]]
           for e in m["events"]]
    check(got == w["events"], f"the {len(w['events'])} events, minute + 1 as shown (got {got})")

    cols = COLUMNS
    for side in ("home", "away"):
        if side not in w:
            continue
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
        sums = [sum(p[k] for p in m[f"{s}_xi"]) for s in ("home", "away")]
        check(sums == [a, b], f"team {k} {a} / {b} = the player slots (got {sums})")
    got = [[sum(p["rating"] for p in m[f"{s}_xi"] if appeared(p)),
            sum(1 for p in m[f"{s}_xi"] if appeared(p))] for s in ("home", "away")]
    check(got == w["rating_sum_count"], f"team rating: ratings {got} over the players who appeared")
    trunc = [int(s * 10 // n) / 10 for s, n in got]
    check(trunc == w["rating_screen"], f"the screen's {w['rating_screen']} is that mean truncated")

    raw = [r for r in all_raw if r["offset"] == m["offset"]][0]
    teams = (raw["offset"] + matches.MATCH_HEAD.span + 1 + matches.EVENT.span * len(raw["events"])
             + matches.BODY_HEAD.span + matches.EVENT_SLOTS * matches.EVENT.span)
    for off, want in w["team_head"].items():
        got = [mm[teams + k * matches.TEAM.span + int(off)] for k in range(2)]
        check(got == want, f"team head +{off} = {want}")
    heads = b"".join(bytes(mm[teams + k * matches.TEAM.span:teams + k * matches.TEAM.span + 77])
                     for k in range(2))
    pos = w["not_stored"]["possession"]
    check(not any(bytes([v]) in heads for v in pos), f"possession {pos} is in neither team head")


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

    all_matches = matches.scrape_matches(mm)
    all_raw = matches.MATCHES_TABLE.scrape(mm)
    for w in fx["matches"]:
        print(f"\nMATCHES {w['date']} {w['home_tid']} v {w['away_tid']} "
              "(Match Report, Match Stats, Player Ratings)")
        check_match(mm, w, all_matches, all_raw)
    world = fixtures.scrape(blob)
    offs = officials.scrape_officials(mm)
    names = rounds.round_names_map(mm)
    rules = comp_rules.competition_rounds(mm)
    for f in fx["fixtures"]:
        print(f"\nFIXTURES {f['date']} {f['home_tid']} v {f['away_tid']} (the world results list)")
        rows = [r for r in world
                if (r["date"], r["home_tid"], r["away_tid"]) == (f["date"], f["home_tid"], f["away_tid"])]
        check(len(rows) == 1, "one fixture record, home-first, dated as on screen (DAY_BASE)")
        for k in ("home_goals", "away_goals", "seq_id", "stage_index", "season_year"):
            check(bool(rows) and rows[0][k] == f[k], f"{k} = {f[k]}")
        refs = []
        for s, n in fixtures.segments(blob):
            for o in range(s, s + 92 * n, 92):
                rec = fixtures.read_fixture(blob, o)
                if (rec["date"], rec["home_tid"], rec["away_tid"]) == (f["date"], f["home_tid"], f["away_tid"]):
                    refs.append(struct.unpack_from("<I", blob, o + 72)[0])
        check(refs == [f["referee_tid"]], f"+72 is the referee {f['referee']} (tid {f['referee_tid']})")
    print("\nOFFICIALS (the referee on the Match Report)")
    for o in fx["officials"]:
        rec = offs[o["slot_id"]]
        check((rec["tid"], rec["uid"]) == (o["tid"], o["uid"]), f"record {o['slot_id']} is tid {o['tid']}")
        comps = [struct.unpack_from("<I", rec["competitions_raw"], 4 * i)[0] for i in range(16)]
        check([c for c in comps if c != 0xFFFFFFFF] == o["competitions"],
              f"tid {o['tid']} referees competition uid {o['competitions']}")
    print("\nROUNDS (the Match Report's stage or round name)")
    for rd in fx["rounds"]:
        check(names.get(rd["name_id"]) == rd["name" if "name" in rd else "stage_name"],
              f"name {rd['name_id']} = {rd.get('name', rd.get('stage_name'))!r}")
        hit = [s for s in rules if s["uid"] == rd["comp_uid"] and s["stage_index"] == rd["stage_index"]
               and (rd["kind"] == "stage" or s["round_index"] == rd["round_index"])]
        key = "stage_name_id" if rd["kind"] == "stage" else "round_name_id"
        check(bool(hit) and hit[0][key] == rd["name_id"],
              f"competition uid {rd['comp_uid']}'s {rd['kind']} names {rd['name_id']}")

    print()
    if failures:
        print(f"FAIL: {len(failures)} check(s)")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
