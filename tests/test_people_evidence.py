#!/usr/bin/env python3
"""
Evidence for the people tables: what the game shows, the bytes behind it, and what the
parser makes of them, on one save.

`tests/fixtures/people_evidence.json` holds values read off in-game screens of
frem-2030-06-22 (the screenshots are in docs/parser/img/, and each table's doc in
docs/parser/ maps them). This test asserts two things for each: the raw bytes at the recorded
offset are what the doc says, and the parsed field equals the value on screen. The first
catches a different save; the second catches a parser change that reads the right bytes into
the wrong field.

    uv run python tests/test_people_evidence.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.harness import find_save, skip  # noqa: E402

from fmparser.save import Save  # noqa: E402
from fmparser.tables import (contracts, history, names, person_info,  # noqa: E402
                             player_attributes, player_lists, player_progress, training)

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "people_evidence.json")

failures = []


def check(cond, what):
    print(f"  {'ok  ' if cond else 'FAIL'} {what}")
    if not cond:
        failures.append(what)


def screen_value(rec, name):
    """The value the Player Profile shows for `name`, from the attribute record."""
    if name == "Teamwork":
        return (rec["unselfishness_src"] + rec["work_rate"]) // 2
    if name == "Aerial":
        return int(0.3 * rec["heading_src"] + 0.7 * rec["jumping"] + 1.0)
    return rec[f"{name.lower()}_src"]


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

    print("\nPERSON_INFO (Player Profile, Player Personal)")
    recs = person_info.PERSON_INFO_TABLE.scrape(mm)
    for tid, want in fx["persons"].items():
        r = recs[int(tid)]
        for k, v in want.items():
            if k == "languages":
                got = {str(x["language_id"]): x["level"] for x in r["languages"] if x["level"]}
                check(got == v, f"{tid} languages {v} (got {got})")
            elif k == "favoured_club":
                check(any(x["target_kind"] == 1 and x["target_id"] == v
                          for x in r["relationships"]), f"{tid} links club {v}")
            elif k == "favoured_person":
                check(any(x["target_kind"] == 3 and x["target_id"] == v
                          for x in r["relationships"]), f"{tid} links person {v}")
            elif k == "relationships":
                check(len(r["relationships"]) == v, f"{tid} has {v} relationships")
            else:
                check(r[k] == v, f"{tid} {k} = {v!r} (got {r[k]!r})")

    print("\nPLAYER_ATTRIBUTES (Player Profile)")
    attrs = player_attributes.scrape_player_attributes(mm)
    spine = person_info.scrape_person_info(mm)
    for tid, want in fx["attributes"].items():
        sid = spine[int(tid)]["sid"]
        a = attrs[sid]
        rec = player_attributes.PLAYER.read(mm, a["offset"])
        for k in ("squad_number",):
            check(a[k] == want[k], f"{tid} {k} = {want[k]} (got {a[k]})")
        check((a["feet"]["left"], a["feet"]["right"]) == (want["foot_left"], want["foot_right"]),
              f"{tid} feet {want['foot_left']}/{want['foot_right']}")
        if "positions" in want:
            check(a["positions"] == want["positions"], f"{tid} positions {want['positions']}")
        for name, v in want["screen"].items():
            got = screen_value(rec, name)
            check(got == v, f"{tid} {name} {v} (got {got})")

    print("\nCONTRACTS (Club Squad - Contract)")
    grid = {k["tid"]: k for k in contracts.scrape_contracts(mm)}
    for tid, val in fx["contracts"].items():
        if tid.startswith("_"):
            continue
        gbp, expiry = val
        k = grid[int(tid)]
        yearly = k["wage_units"] * 520
        shown = f"{int(k['expiry'][5:7])}/{k['expiry'][:4]}"
        check(k["marker"] & 1 and abs(yearly - gbp) / gbp < 0.03 and shown == expiry,
              f"{tid} £{gbp:,} {expiry} (got £{yearly:,} {shown}, marker {k['marker']})")
    for tid, want in fx["contract_exact"].items():
        for k, v in want.items():
            check(grid[int(tid)][k] == v, f"{tid} {k} = {v}")

    print("\nHISTORY (Player History)")
    pool = history.scrape_history(mm)
    rows = pool["rows"]

    def chain(head):
        out, i = [], head
        while i != history.END:
            out.append({c: rows[c][i] for c in rows})
            i = rows["next"][i]
        return out

    for tid, want in fx["history"].items():
        lines = chain(attrs[spine[int(tid)]["sid"]]["history_head"])
        got = [[1971 + r["season"], r["club"], r["apps"], r["goals"], r["assists"],
                r["rating"], r["fee"]] for r in lines]
        for line in want.get("lines", []):
            check(line in got, f"{tid} line {line}")
        if "lines" in want:
            check(got[-1] == want["lines"][-1], f"{tid} chain ends on {want['lines'][-1]}")
        if "order_tail" in want:
            n = want["order_tail"]
            check(got[-n:] == want["lines"], f"{tid} the last {n} lines in chain order, as the screen lists them")
        for season, club, fee in want.get("fees", []):
            check([season, club, fee] in [[g[0], g[1], g[6]] for g in got],
                  f"{tid} {season} club {club} fee {fee:#x}")
        if "total" in want:
            for k, v in want["total"].items():
                s = sum(r[k] for r in lines) + want["this_season"].get(k, 0)
                check(s == v, f"{tid} TOTAL {k} {v} = chain + this season (got {s})")

    print("\nTRAINING (Training Report, Player Contract)")
    trows = {r["tid"]: r for r in training.scrape_training(mm)}
    for tid, want in fx["training"].items():
        for k, v in want.items():
            check(trows[int(tid)][k] == v, f"{tid} {k} = {v!r} (got {trows[int(tid)][k]!r})")

    print("\nPLAYER_PROGRESS (Player Progress, reserves' Contract screen)")
    prog = player_progress.scrape_player_progress(mm)
    pw = fx["progress"]
    for tid, want in pw.items():
        if not tid.isdigit():
            continue
        season = [r for r in prog if r["tid"] == int(tid) and r["week"] >= want["from"]]
        check(season and all({k: r[k] for k in want["lines"]} == want["lines"] for r in season),
              f"{tid} every week from {want['from']}: {want['lines']}")
        for week, pts in want.get("points", {}).items():
            row = [r for r in season if r["week"] == week]
            check(row and all({k: r[k] for k in pts} == pts for r in row), f"{tid} {week}: {pts}")
        marks = {r["week"]: r["status"] for r in season if r["status"]}
        check(marks == want["markers"], f"{tid} markers {want['markers']} (got {marks})")
    latest = {r["tid"]: r["status"] for r in prog if r["week"] == pw["week"]}
    check(all(latest.get(t, 0) & 32 for t in pw["on_loan"]),
          f"the {len(pw['on_loan'])} players marked unavailable have the loan bit on {pw['week']}")
    check(not any(latest.get(t, 0) & 32 for t in pw["not_on_loan"]),
          f"{pw['not_on_loan']} do not")

    print("\nNAMES (every screen)")
    browse = names.walk_browse(mm)
    ids = names.scrape_name_ids(mm)
    ordinal = {t: {r["id"]: r["ordinal"] for r in rows_} for t, rows_ in ids.items()}
    for tid, want in fx["names"].items():
        p = spine[int(tid)]
        if p["common_name_id"] in ordinal["nicknames"]:
            got = browse[ordinal["nicknames"][p["common_name_id"]]]
        else:
            got = (f"{browse[ordinal['first_names'][p['first_name_id']]]} "
                   f"{browse[ordinal['surnames'][p['last_name_id']]]}")
        check(got == want, f"{tid} {want!r} (got {got!r})")

    print("\nPLAYER_LISTS (Player Profile vs the season's Manager's Best Eleven entry)")
    lists = player_lists.scrape_player_lists(mm)
    sb = fx["scrapbook"]
    entries = {e["player_tid"]: e for e in lists[sb["list"]]["entries"]}
    check(lists[sb["list"]]["season"] == 0xFFFF, f"list {sb['list']} is the season in progress")
    for tid, want in sb.items():
        if not tid.isdigit():
            continue
        e = entries.get(int(tid))
        if not e:
            check(False, f"{tid} has an entry in list {sb['list']}")
            continue
        bad = {k: (v, e[k]) for k, v in want.items() if e[k] != v}
        check(not bad, f"{tid} {len(want)} fields as on screen {bad or ''}")

    print()
    if failures:
        print(f"FAIL: {len(failures)} check(s)")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
