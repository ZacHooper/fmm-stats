#!/usr/bin/env python3
"""
Evidence for the FMM27 reference chain, player_attributes -> staff -> staff roles ->
officials -> round names -> clubs -> competitions -> nations -> stadiums, on truro-2026-07-25: each walk, the raw bytes at recorded offsets, and what
the parser makes of them.

`tests/fixtures/reference_fmm27_evidence.json` holds the walks' extents, the bytes behind
each value, and the values: Truro City's from its Club Information screen
(docs/parser/img/clubs-fmm27-1.jpg). The raw bytes catch a different save; the parsed values
a parser change that reads the right bytes into the wrong field; the walks a table that
stops short or drifts onto the next.

    uv run python tests/test_reference_fmm27_evidence.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.harness import find_save, skip  # noqa: E402

from fmparser.save import Save  # noqa: E402
from fmparser.tables import (clubs, competitions, nations, officials,  # noqa: E402
                             player_attributes, rounds, rule_files, stadiums, staff,
                             staff_roles, tables_for)
from fmparser.tables.save_header import FMM27, save_format  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "reference_fmm27_evidence.json")

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
    walks = fx["walks"]

    print("FORMAT")
    check(save_format(mm) == FMM27, f"{fx['save']} declares fmm27")
    reg = tables_for(mm)
    check(reg["player_attributes"] is player_attributes.PLAYER_ATTRIBUTES_TABLE_FMM27,
          "player_attributes reads with the FMM27 declaration")
    check(reg["round_names"] is rounds.ROUNDS_TABLE_FMM27, "round_names reads with FMM27's")
    check(reg["clubs"] is clubs.CLUB_TABLE_FMM27, "clubs reads with FMM27's")

    print("\nRAW BYTES at the recorded offsets")
    for off, hexstr, what in fx["raw"]:
        want = bytes.fromhex("".join(hexstr.split()))
        check(bytes(mm[off:off + len(want)]) == want, f"@{off} {what}")

    print("\nTHE WALKS")
    pa = player_attributes.player_attributes_table(mm).scrape(mm)
    want = walks["player_attributes"]
    check(len(pa) == want["count"] and all(int.from_bytes(bytes.fromhex(r["sid"]), "little") == k
                                           for k, r in enumerate(pa)),
          f"player_attributes: {len(pa):,} of {want['count']:,} records, sid == slot")
    check(player_attributes.player_attributes_end(mm) == want["end"],
          f"player_attributes ends at {want['end']:,}, staff's frame")
    st = staff.STAFF_TABLE.scrape(mm)
    want = walks["staff"]
    check(staff.locate_staff(mm) == (want["base"], want["count"]), f"staff at {want['base']:,}")
    check([r["id2"] for r in st] == list(range(want["count"])),
          f"staff: {len(st):,} of {want['count']:,}, id2 == slot")
    of = officials.scrape_officials(mm)
    want = walks["match_officials"]
    check(officials.locate_officials(mm) == (want["base"], want["count"]),
          f"officials at {want['base']:,}")
    check([r["slot_id"] for r in of] == list(range(want["count"])),
          f"officials: {len(of):,} of {want['count']:,}, slot_id == slot")
    rr = rounds.scrape_rounds(mm)
    want = walks["round_names"]
    check(rounds.locate_rounds(mm) == (want["base"], want["count"]), f"round names at {want['base']:,}")
    check(len(rr) == want["count"], f"round names: {len(rr)} of {want['count']}")
    cl = clubs.scrape_clubs(mm)
    want = walks["clubs"]
    check(clubs.locate_clubs(mm) == (want["base"], want["count"]), f"clubs at {want['base']:,}")
    check(sorted(cl) == list(range(want["count"])), f"clubs: {len(cl):,} of {want['count']:,}, tid == slot")
    check(clubs.clubs_end(mm) == want["end"], f"clubs end at {want['end']:,}, competitions' frame")

    co = competitions.scrape_competitions(mm)
    want = walks["competitions"]
    check(len(competitions._comp_rows(mm)) == want["count"] and len(co) == want["named"],
          f"competitions: {want['count']:,} slots, {want['named']:,} named")
    check(sum(c["is_women"] for c in co.values()) == want["women"], f"{want['women']} women's competitions")
    na = nations.scrape_nations(mm)
    check(sorted(na) == list(range(walks["nations"]["count"])), f"nations: {len(na)}, id == slot")
    sd = stadiums.scrape_stadiums(mm)
    want = walks["stadiums"]
    check(stadiums.locate_stadiums(mm) == (want["base"], want["count"]) and sorted(sd) == list(range(want["count"])),
          f"stadiums at {want['base']:,}: {len(sd):,}, id == slot")

    want = walks["rule_files"]
    rf = rule_files.rule_files_table(mm)
    check(rf is rule_files.RULE_FILES_TABLE_FMM27 and len(rf.blocks(mm)) == want["files"],
          f"rule files: {want['files']} read with FMM27's schemas")
    check(len(rule_files.team_counts(mm)) == want["team_counts"],
          f"team_counts: {want['team_counts']} competitions")
    wp = rule_files.work_permits(mm)
    check(len(wp) == want["work_permit_rules"], f"work_permits: {want['work_permit_rules']} rules")
    uk = sorted({r["file"] for r in wp if r["scheme"] == 21})
    check(uk == want["scheme_21"], f"scheme 21 on {want['scheme_21']} only")
    for file, rule, fields in want["work_permits"]:
        got = next((r for r in wp if r["file"] == file and r["set"] == "wkpm"
                    and r["rule"] == rule), {})
        check({k: got.get(k) for k in fields} == fields, f"{file} {rule}: {fields}")

    print("\nUNAVAILABILITY (player_attributes +78)")
    by_sid = {int.from_bytes(bytes.fromhex(r["sid"]), "little"): r for r in pa}
    check(sum(bool(r["unavailability"]) for r in pa) == fx["with_unavailability"],
          f"{fx['with_unavailability']} players carry one")
    for sid, items in fx["unavailability"].items():
        got = [{k: v for k, v in it.items() if k in items[0]} for it in by_sid[int(sid)]["unavailability"]]
        check(got == items, f"sid {sid}: {items}" + ("" if got == items else f" (got {got})"))

    print("\nSTAFF (Staff Profile)")
    by_id2 = {r["id2"]: r for r in st}
    catalog = staff.formation_catalog(mm)
    for id2, want in fx["staff"].items():
        r = by_id2[int(id2)]
        got = {"formation": catalog[r["formation_preferred"]], "reputation_tier": r["reputation_tier"]}
        check(got == want, f"id2 {id2}: {want}" + ("" if got == want else f" (got {got})"))

    print("\nSTAFF ROLES (Staff Profile: Specialism, Aptitude)")
    roles = staff_roles.scrape_staff_roles(mm)
    for role, n in walks["staff_roles"].items():
        check(len(roles[role]) == n and all(r["tid"] is not None for r in roles[role]),
              f"{role}: {n:,} rows, each with its person")
    by_tid = {r["tid"]: (role, r) for role, rows in roles.items() for r in rows}
    for tid, want in fx["staff_roles"].items():
        role, r = by_tid.get(int(tid), (None, {}))
        got = [role] + ([r["specialism"], r["aptitude"]] if len(want) > 1 else [])
        check(got == want, f"tid {tid}: {want}" + ("" if got == want else f" (got {got})"))
    for tid in fx["no_role"]:
        check(tid not in by_tid, f"tid {tid} (an AI manager) has no role row")

    print("\nROUND NAMES")
    by_id = {r["id"]: r for r in rr}
    for rid, names in fx["rounds"].items():
        r = by_id[int(rid)]
        got = [r["name"], r["short_name"], r["plural_name"]]
        check(got == names, f"round {rid}: {names}" + ("" if got == names else f" (got {got})"))

    print("\nCLUBS (Club Information)")
    for tid, want in fx["club"].items():
        c = cl[int(tid)]
        for k, v in want.items():
            check(c[k] == v, f"{want['name']}: {k} = {v!r}" + ("" if c[k] == v else f" (got {c[k]!r})"))

    print("\nLEAGUE, STADIUM, NATION (Club Information)")
    for cid, want in fx["competition"].items():
        got = {k: co[int(cid)][k] for k in want}
        check(got == want, f"competition {cid}: {want}" + ("" if got == want else f" (got {got})"))
    for sid, want in fx["stadium"].items():
        got = {k: sd[int(sid)][k] for k in want}
        check(got == want, f"stadium {sid}: {want}" + ("" if got == want else f" (got {got})"))
    for nid, name in fx["nation"].items():
        check(na[int(nid)]["name"] == name, f"nation {nid}: {name}")

    for tid, man in fx["managers_not_listed"].items():
        check(man not in cl[int(tid)]["staff"], f"club {tid}: its AI manager {man} is not in the staff list")
    for tid, man in fx["managers_listed"].items():
        check(man in cl[int(tid)]["staff"], f"club {tid}: the user's manager {man} is in the staff list")

    print()
    if failures:
        print(f"FAIL: {len(failures)} check(s)")
        return 1
    print("PASS: FMM27 reference chain evidence")
    return 0


if __name__ == "__main__":
    sys.exit(main())
