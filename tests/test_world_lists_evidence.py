#!/usr/bin/env python3
"""
Evidence for seven tables read from 2026-11-12: the awards, nation unions, derbies and
regions between the cities and the currencies; the id list before the languages; the
per-person rows after the languages; the per-person stamps after our matches. On one save
of each game (frem-2026-06-11, FMM22; truro-2026-08-08, FMM27).

`tests/fixtures/world_lists_evidence.json` pins each walk's start and count, the raw bytes
behind a few rows and the values the parser reads from them. The rest is checked against
tables we already trust, joining on an id and letting the field under test come out:

  - each walk reads its declared count and the chain lands on the next table's frame:
    regions on the currencies, the id list on the languages, the per-person rows on the
    staff count;
  - every award winner is a person, and on FMM27 his name ids are the person's own;
  - every derby club is a club or ffffffff; derby 0 is Everton v Liverpool;
  - every region's nation is a nation, and 99% of cities with a region sit in its nation
    (the rest are Spanish cities in "Pays Basque", a French region);
  - every player of the managed club has stamp knowledge 3 (its staff need not).

    uv run python tests/test_world_lists_evidence.py
"""
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.harness import find_save, skip  # noqa: E402

from fmparser.save import Save  # noqa: E402
from fmparser.tables import (awards, cities, derbies, id_list, languages,  # noqa: E402
                             nations, person_index, person_stamps, regions, staff,
                             tables_for, unions)
from fmparser.tables.currencies import locate_currencies  # noqa: E402
from fmparser.tables.person_info import scrape_person_info  # noqa: E402
from fmparser.tables.save_header import FMM27, save_format  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "world_lists_evidence.json")
NONE32 = 0xFFFFFFFF

failures = []


def check(cond, what):
    print(f"  {'ok  ' if cond else 'FAIL'} {what}")
    if not cond:
        failures.append(what)


def lands_on_frame(mm, end, base, width):
    """True when `end` is followed by >= 8 0xFF and then the count in front of `base`."""
    frame = base - width
    return frame - end >= 8 and all(b == 0xFF for b in mm[end:frame])


def check_save(name, fx):
    path = find_save(name)
    if not path:
        print(f"  (skipped: {name} not found)")
        return False
    mm = Save(path).mm
    v27 = save_format(mm) == FMM27
    print(f"\n{name} ({'FMM27' if v27 else 'FMM22'})")

    print(" RAW BYTES")
    for off, hexstr, what in fx["raw"]:
        want = bytes.fromhex("".join(hexstr.split()))
        check(bytes(mm[off:off + len(want)]) == want, f"@{off} {what}")

    print(" WALKS: start, declared count, rows read")
    locators = {"awards": awards.locate_awards, "unions": unions.locate_unions,
                "derbies": derbies.locate_derbies, "regions": regions.locate_regions,
                "id_list": id_list.locate_id_list,
                "person_index": person_index.locate_person_index,
                "person_stamps": person_stamps.locate_person_stamps}
    scrapes = {"awards": awards.scrape_awards, "unions": unions.scrape_unions,
               "derbies": derbies.scrape_derbies, "regions": regions.scrape_regions,
               "id_list": id_list.scrape_id_list,
               "person_index": person_index.scrape_person_index,
               "person_stamps": person_stamps.scrape_person_stamps}
    rows = {}
    for t, want in fx["walks"].items():
        loc = locators[t](mm)
        check(loc == (want["base"], want["count"]), f"{t} at {want['base']:,}, {want['count']:,} declared")
        rows[t] = scrapes[t](mm)
        check(len(rows[t]) == want["count"], f"{t} reads {want['count']:,} rows")

    print(" CHAIN: each walk ends on the next table")
    check(lands_on_frame(mm, regions.regions_end(mm), locate_currencies(mm)[0], 2),
          "regions end on the currencies' frame")
    lst = id_list.locate_id_list(mm)
    check(lands_on_frame(mm, lst[0] + lst[1] * id_list.ID_LIST_ROW.span,
                         languages.locate_languages(mm)[0], 2), "id list ends on the languages' frame")
    pi = person_index.locate_person_index(mm)
    stride = (person_index.PERSON_INDEX_FMM27 if v27 else person_index.PERSON_INDEX).span
    check(struct.unpack_from("<I", mm, pi[0] + pi[1] * stride)[0] == staff.locate_staff(mm)[1],
          f"per-person rows ({stride} B) end on the staff count")
    persons = scrape_person_info(mm)
    check(pi[1] == len(persons), "one per-person row per person")
    check(person_stamps.locate_person_stamps(mm)[1] == len(persons) - 1,
          "person stamps count = persons - 1")

    print(" VALUES")
    a0 = rows["awards"][0]
    for k, v in fx["award_0"].items():
        check(a0.get(k) == v if k != "entry_0" else a0["entries"][0] == v, f"award 0 {k} = {v}")
    clubs = {c["tid"]: c["name"] for c in tables_for(mm)["clubs"].scrape(mm)}
    d0 = rows["derbies"][0]
    check(d0["name"] == fx["derby_0"]["name"], f"derby 0 is {fx['derby_0']['name']}")
    check([clubs.get(d0["club_a_tid"]), clubs.get(d0["club_b_tid"])] == fx["derby_0"]["clubs"],
          f"derby 0 is {' v '.join(fx['derby_0']['clubs'])}")
    nat = nations.scrape_nations(mm)
    r0 = rows["regions"][0]
    check(r0["name"] == fx["region_0"]["name"] and nat[r0["nation_id"]]["name"] == fx["region_0"]["nation"],
          f"region 0 is {fx['region_0']['name']}, {fx['region_0']['nation']}")
    check([u["id"] for u in rows["unions"]] == list(range(1, 7)), "six unions, ids 1-6")

    print(" CROSS-TABLE")
    entries = [e for a in rows["awards"] for e in a["entries"] if e["person_tid"] != NONE32]
    check(entries and all(e["person_tid"] in persons for e in entries),
          f"all {len(entries)} award winners are persons")
    if v27:
        same = sum((persons[e["person_tid"]]["first_name_id"], persons[e["person_tid"]]["last_name_id"],
                    persons[e["person_tid"]]["common_name_id"])
                   == (e["first_name_id"], e["last_name_id"], e["common_name_id"]) for e in entries)
        check(same == len(entries), f"FMM27: every winner's name ids are his own ({same}/{len(entries)})")
    dclubs = [t for d in rows["derbies"] for t in (d["club_a_tid"], d["club_b_tid"])]
    check(all(t in clubs or t == NONE32 for t in dclubs), "every derby club is a club or ffffffff")
    check(all(r["nation_id"] in nat for r in rows["regions"]), "every region's nation resolves")
    reg = rows["regions"]
    placed = [c for c in cities.scrape_cities(mm).values() if c["region_id"] < len(reg)]
    same = sum(reg[c["region_id"]]["nation_id"] == c["nation_id"] for c in placed)
    check(same / len(placed) > 0.99, f"cities sit in their region's nation ({same}/{len(placed)})")
    squad = [t for t, p in persons.items()
             if p["club_tid"] == fx["managed_tid"] and p["sid"] != "ffffffff"]
    stamps = rows["person_stamps"]
    check(squad and all(stamps[t]["knowledge"] == 3 for t in squad),
          f"stamp knowledge 3 on all {len(squad)} of the managed club's players")
    last = max(persons)
    check(persons[last]["sid"] == "ffffffff" and persons[last]["club_tid"] == fx["managed_tid"],
          f"the one person with no stamp, tid {last}, is non-playing staff at the managed club")
    return True


def main():
    fx = json.load(open(FIXTURE, encoding="utf-8"))
    ran = [check_save(name, s) for name, s in fx["saves"].items()]
    if not any(ran):
        return skip("neither frem-2026-06-11.fms nor truro-2026-08-08.fms found")
    print(f"\n{'FAIL' if failures else 'PASS'}: {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
