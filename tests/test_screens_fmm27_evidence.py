#!/usr/bin/env python3
"""
Evidence for FMM27's matches, contracts and training on truro-2026-08-08, from the screens
taken that day: Truro 1-0 Maidenhead United in the Enterprise National League South (the
summary, the stats screen, both ratings screens and the match events), Club Squad - Contract,
Caleb Roberts's contract, Individual Training and two training reports
(docs/parser/img/{matches,contracts,training}-fmm27-*.jpg).

`tests/fixtures/screens_fmm27_evidence.json` holds the bytes behind each value and what each
screen shows. The raw bytes catch a different save; the screen values a parser change that
reads the right bytes into the wrong field; the row offsets a walk that stops short.

    uv run python tests/test_screens_fmm27_evidence.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.harness import find_save, skip  # noqa: E402

from fmparser.save import Save  # noqa: E402
from fmparser.tables import contracts, matches, tables_for, training  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "screens_fmm27_evidence.json")

failures = []


def check(cond, what):
    print(f"  {'ok  ' if cond else 'FAIL'} {what}")
    if not cond:
        failures.append(what)


def main():
    fx = json.load(open(FIXTURE, encoding="utf-8"))
    path = find_save(fx["save"])
    if not path:
        return skip(f"{fx['save']} not found (fetch it with rclone, or rebuild.py)")
    mm = Save(path).mm
    mx = fx["matches"]

    print("RAW BYTES at the recorded offsets")
    for off, hexstr, what in mx["raw"]:
        want = bytes.fromhex("".join(hexstr.split()))
        check(bytes(mm[off:off + len(want)]) == want, f"@{off} {what}")

    print("\nMATCHES: the walk")
    check(tables_for(mm)["matches"] is matches.MATCHES_TABLE_FMM27, "matches read with FMM27's")
    check(matches.locate_matches(mm) == (mx["row0"], mx["count"]),
          f"row 0 at {mx['row0']:,}, count byte {mx['count']}")
    ms = matches.scrape_matches(mm)
    check([m["offset"] for m in ms] == mx["rows"], f"{len(ms)} rows at {mx['rows']}")
    check(all(b - a == 5676 + 17 * len(m["events"])
              for a, b, m in zip(mx["rows"], mx["rows"][1:], ms)),
          "each row is 5,676 + 17 n bytes: the next row's head follows it")

    m = ms[-1]
    want = mx["match"]
    print("\nTHE SUMMARY SCREEN: Truro 1-0 Maidenhead, attendance 1,689, Law best performer")
    for k in ("date", "comp_id", "home_tid", "away_tid", "attendance", "player_of_match",
              "formation", "home_positions"):
        check(m[k] == want[k], f"{k} = {want[k]}")
    check([m["score"]["home"], m["score"]["away"]] == want["score"], "score 1-0")

    print("\nTHE STATS SCREEN")
    for side, head in mx["team_head"].items():
        for k, v in head.items():
            check(m["team_head"][side][k] == v, f"{side} {k} = {v}")
    for side, sums in mx["screen_sums"].items():
        xi = m[f"{side}_xi"]
        for k, v in sums.items():
            check(sum(p[k] for p in xi) == v, f"{side} {k}: the slots sum to {v}")
    xg = [sum(p["xg_x100"] for p in m[f"{s}_xi"]) for s in ("home", "away")]
    check(xg == mx["xg"]["slot_sum_x100"],
          f"xG: the slots sum to {xg} x 0.01; the screen shows {mx['xg']['screen']}")
    check(all(abs(x / 100 - s) <= 0.015 for x, s in zip(xg, mx["xg"]["screen"])),
          "xG within rounding of the screen")

    print("\nTHE RATINGS SCREENS")
    cols = mx["slot_columns"]
    for side in ("home", "away"):
        by_tid = {p["tid"]: p for p in m[f"{side}_xi"]}
        for key, vals in mx[side].items():
            tid, nm = key.split(" ", 1)
            p = by_tid.get(int(tid))
            got = [p[c] for c in cols] if p else None
            check(got == vals, f"{side} {nm}: {dict(zip(cols, vals))}" if got != vals
                  else f"{side} {nm}")
    home = {p["tid"]: p for p in m["home_xi"]}
    for tid, minute in mx["subs_on"].items():
        check(home[int(tid)]["subOn"] == minute, f"sub {tid} on at {minute}'")

    print("\nTHE MATCH EVENTS")
    got = [[e["type_byte"], e["minute"], e["added"], e["side"], e["tid"]] for e in m["events"]]
    check(got == mx["events"], "9 events: three bookings, the goal and its assist, three "
                               "clear-cut chances")
    check(got[1][0] == 0x01 and got[1][4] == 4353 and got[1][1] + 1 == 17, "Starkie 17'")
    check(got[3][0] == 0x24 and got[3][4] == 8821, "assist Law")
    check(sum(1 for e in got if e[0] == 0x2F and e[3] == 0)
          == m["team_head"]["home"]["clear_cut_chances"], "one 2f event per clear-cut chance")

    print("\nCLUB SQUAD - CONTRACT")
    con = {r["tid"]: r for r in contracts.scrape_contracts(mm)}
    for tid, (nm, units, expiry, wage, shown) in fx["contracts"]["rows"].items():
        r = con[int(tid)]
        check((r["wage_units"], r["expiry"]) == (units, expiry),
              f"{nm}: {units} x 520 = £{units * 520:,} ({wage}), expires {expiry} ({shown})")

    print("\nINDIVIDUAL TRAINING")
    tr = {r["tid"]: r for r in training.scrape_training(mm)}
    for tid, (nm, role, attr, role_code, attr_code, intensity) in fx["training"]["rows"].items():
        r = tr[int(tid)]
        check((r["focus_role"], r["focus_attribute"], r["intensity"])
              == (role_code, attr_code, intensity),
              f"{nm}: {role} = {role_code}, {attr} = {attr_code}, Normal = {intensity}")

    print("\nFAIL" if failures else "\nPASS: FMM27 screens of 8 August 2026")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
