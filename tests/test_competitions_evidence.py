#!/usr/bin/env python3
"""
Evidence for the competition tables: what the game shows, the bytes behind it, and what the
parser makes of them, on one save.

`tests/fixtures/competitions_evidence.json` holds values read off in-game screens of
frem-2030-06-22 (Past Winners for the 3F Superliga, Sydbank Pokalen, English Premier Division
and EURO Cup; the Pokalen's Final and the EURO Cup's Third Qualifying Round rules; the
screenshots are in docs/parser/img/, and docs/parser/competitions.md, comp_honours.md,
comp_rules.md, comp_stages.md and rule_files.md map them). For each, the raw bytes at the
recorded offset are what the doc says, and the parsed field equals the value on screen.

A Past Winners list is checked row by row: its top row (2029/30) is the competition record's
holders tail, the other nine are roll-of-honour records, whose `season` is the end year.

    uv run python tests/test_competitions_evidence.py
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
from fmparser.tables import comp_honours, comp_rules, competitions, rule_files  # noqa: E402
from fmparser.tables.clubs import scrape_clubs  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "competitions_evidence.json")
NO_CLUB = 0xFFFFFFFF

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
    ents = A.members(mm)

    print("RAW BYTES at the recorded offsets")
    for off, hexstr, what in fx["raw"]:
        want = bytes.fromhex("".join(hexstr.split()))
        check(bytes(mm[off:off + len(want)]) == want, f"@{off} {what}")
    blobs = {}
    for member, off, hexstr, what in fx["archive_raw"]:
        if member not in blobs:
            blobs[member] = bytes(A.read_member(mm, ents[member]))
        want = bytes.fromhex("".join(hexstr.split()))
        check(blobs[member][off:off + len(want)] == want, f"{member} @{off} {what}")

    print("\nCOMPETITIONS (the 3F Superliga record)")
    comps = competitions.scrape_competitions(mm)
    w = fx["competition"]
    got = comps[w["cid"]]
    for k, v in w.items():
        check(got[k] == v, f"{k} = {v!r}")
    rows = competitions.COMP_TABLE.scrape(mm)

    clubs = scrape_clubs(mm)
    by_uid = {c["uid"]: c["short"] for c in clubs.values()}
    by_tid = {t: c["short"] for t, c in clubs.items()}
    honours = comp_honours.scrape(A.extract(mm, "comp_man.dat"))
    held = competitions.holders(mm)

    for cid_s, screen in fx["past_winners"].items():
        cid = int(cid_s)
        print(f"\nPAST WINNERS: {comps[cid]['name']}, {len(screen)} rows checked one by one")
        top, rest = screen[0], screen[1:]
        h = held[cid]
        raw = struct.unpack_from("<IIIHHH", mm, fx["holders_offsets"][cid_s])
        check(raw == tuple(NO_CLUB if v is None else v for v in
                           (h["first_uid"], h["second_uid"], h["third_uid"]))
              + (h["season"], h["start_year"], h["end_year"]),
              "the parsed holders are the tail's bytes")
        check(f"{h['start_year']}/{h['end_year'] % 100:02d}" == top[0], f"holders season {top[0]}")
        check([by_uid.get(h["first_uid"]), by_uid.get(h["second_uid"])] == top[1:],
              f"{top[0]} {top[1]} / {top[2]} (the holders tail, by club uid)")
        if comps[cid]["type_id"] not in (0, 1):
            check(h["third_uid"] is None, "a cup holds no third")
        recs = {h["season"]: h for h in honours if h["comp_cid"] == cid}
        for label, winner, runner in rest:
            h = recs.get(int(label[:4]) + 1)
            ok = h is not None and [by_tid.get(h["winner_tid"]), by_tid.get(h["runner_up_tid"])] == [winner, runner]
            check(ok, f"{label} {winner} / {runner} (record season {int(label[:4]) + 1})")

    print("\nROLL OF HONOUR framing")
    cm = A.extract(mm, "comp_man.dat")
    at = fx["honours_count_at"]
    count = struct.unpack_from("<I", cm, at)[0]
    check(count == fx["honours_count"], f"declared count {count} at byte {at}")
    check(at + 4 + count * comp_honours.STRIDE == len(cm), "count x 55 tiles to the member's last byte")
    check(comp_honours.locate_comp_honours(cm) == (at + 4, count), "the locator frames it by the count")
    check(len(honours) == count, f"the parser reads all {count} records, record 0 included")
    last = honours[-1]
    check((last["comp_cid"], last["season"], last["start_year"], last["end_year"], last["base_year"])
          == (2, 2029, 2028, 2029, 1900), "the last record is the Superliga's 2028/29, its own years")

    print("\nCOMP_RULES (the stage and round lists)")
    rr = comp_rules.competition_rounds(mm)
    sl = [[r["stage_index"], r["stage_code"], r["stage_type"], r["stage_teams"], r["stage_name_id"]]
          for r in rr if r["uid"] == 6][:3]
    check(sl == fx["superliga_stages"], "Superliga: Preliminary Phase 12, Championship Group 6, Relegation Stage 6")
    pk = [[r["round_index"], r["round_name_id"], r["round_teams"], r["legs"]] for r in rr if r["uid"] == 1301406]
    check(pk == fx["pokalen_rounds"], "Pokalen: seven rounds, quarter- and semi-finals two-legged, a one-leg Final")
    e = fx["euro_third_qualifying"]
    hit = [r for r in rr if r["uid"] == e["uid"] and r["stage_index"] == e["stage_index"]
           and r["round_index"] == e["round_index"]]
    check(len(hit) == 1 and all(hit[0][k] == v for k, v in e.items()),
          "EURO Cup League Path Third Qualifying Round: two legs")

    print("\nCOMP_RULES: the tie-breakers (`sort`, read raw: the parser does not read it yet)")
    for uid, stage_index, want in fx["sort_lists"]:
        fields = comp_rules.scrape(A.read_member(mm, ents[f"comp_{uid}.dat"]))
        stgs = next(v for tag, _, v in fields if tag == "stgs")
        st = next(kids for _, _, kids in stgs if any(t == "indx" and v == stage_index for t, _, v in kids))
        got = [v for _, _, v in next(v for t, _, v in st if t == "sort")]
        check(got == want, f"competition uid {uid}, stage {stage_index}: sort {want}")

    print("\nRULE_FILES")
    tc = rule_files.team_counts(mm)
    for uid, n in fx["team_counts"].items():
        check(tc.get(int(uid)) == n, f"competition uid {uid}: {n} teams")
    check(len(rule_files.RULE_FILES_TABLE.blocks(mm)) == fx["rule_files"], f"{fx['rule_files']} rule files")

    print()
    if failures:
        print(f"FAIL: {len(failures)} check(s)")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
