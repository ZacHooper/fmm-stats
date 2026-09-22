#!/usr/bin/env python3
"""
Guards for everything decoded on 2026-09-16:
  * the STAFF attribute record - coaching ability and the manager formation triple;
  * the tail of the PLAYER attribute record - reputations, shirt number, height, weight;
  * the reference tables - stadiums, cities, languages, nations and UEFA coefficients.

Most checks are ground truth. Two are structural properties that a mis-read field cannot
fake: the formation triple must be catalog-valid across the whole staff population (against
a 57% base rate for three random adjacent bytes), and world ranking must be near-unique
across nations.

Ground truth is the 25 Nov 2024 Manager Profile screenshots for the seven Danish Superliga
managers, matched against `frem-2024-11-10.fms`, plus a second Style-only set read off
`frem-2026-07-02.fms` (checked only if that save is present). Run:

    python3 tests/test_staff_records.py [path/to/frem-2024-11-10.fms]

Skips cleanly if the save is not present (it is gitignored; fetch with rclone or
scripts/rebuild.py).
"""
import mmap
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.harness import skip  # noqa: E402

from fmparser.tables import staff as ST                      # noqa: E402
from fmparser.tables.person_info import PERSON_FIELDS, scrape_person_info  # noqa: E402
from fmparser.tables.player_attributes import scrape_player_attributes     # noqa: E402
from fmparser.tables import languages, nations                    # noqa: E402
from fmparser.tables import cities as PL_CITIES, stadiums as PL_STADIUMS  # noqa: E402

SAVE_NAME = "frem-2024-11-10.fms"

# tid -> (preferred formation, reputation tier, the 10 coaching attributes)
MANAGERS = {
    1619: ("5-2-2-1", "Regional", dict(discipline=16, financial_control=12,
           judging_ability=11, judging_potential=13, people_management=10, motivating=11,
           tactical_knowledge=13, goalkeeping_coaching=4, outfield_coaching=10,
           youth_coaching=18)),
    1134: ("4-1-2-2-1", "National", dict(discipline=16, financial_control=16,
           judging_ability=11, judging_potential=15, people_management=13, motivating=16,
           tactical_knowledge=13, goalkeeping_coaching=6, outfield_coaching=12,
           youth_coaching=12)),
    329: ("4-2-3-1", "National", dict(discipline=14, financial_control=12,
          judging_ability=14, judging_potential=9, people_management=7, motivating=12,
          tactical_knowledge=13, goalkeeping_coaching=6, outfield_coaching=10,
          youth_coaching=5)),
    2506: ("4-1-2-2-1", "Continental", dict(discipline=7, financial_control=10,
           judging_ability=11, judging_potential=10, people_management=15, motivating=13,
           tactical_knowledge=12, goalkeeping_coaching=1, outfield_coaching=11,
           youth_coaching=15)),
    1686: ("4-4-2", "National", dict(discipline=13, financial_control=2,
           judging_ability=15, judging_potential=13, people_management=16, motivating=15,
           tactical_knowledge=14, goalkeeping_coaching=1, outfield_coaching=13,
           youth_coaching=14)),
    1486: ("4-1-2-2-1", "Regional", dict(discipline=13, financial_control=9,
           judging_ability=11, judging_potential=11, people_management=14, motivating=15,
           tactical_knowledge=12, goalkeeping_coaching=1, outfield_coaching=9,
           youth_coaching=12)),
    1833: ("5-2-1-2", "National", dict(discipline=14, financial_control=11,
           judging_ability=13, judging_potential=11, people_management=15, motivating=13,
           tactical_knowledge=13, goalkeeping_coaching=4, outfield_coaching=11,
           youth_coaching=12)),
}

# Style ground truth read off `frem-2026-07-02.fms`, chosen BEFORE it was checked in-game
# specifically to test the band edges -- the 2024 set leaves a gap between the only Defensive
# manager (intent 7) and the lowest Normal (12), so any Defensive cut in 7..11 fitted it.
# All seven came back as predicted, which pins BOTH edges: 8 is Normal, 14 is Attacking.
# tid -> (manager, club, attacking_intent, confirmed Style)
STYLE_2026_SAVE = "frem-2026-07-02.fms"
STYLE_2026 = {
    1542: ("Peter Pedersen", "Odder IGF", 8, "Normal"),          # the Defensive edge: 7|8
    9534: ("Kenneth Kjaersgaard", "Jammerbugt FC", 9, "Normal"),
    1527: ("Johnny Hansen", "Vendsyssel FF", 10, "Normal"),
     179: ("Kim Kristensen", "Hobro IK", 11, "Normal"),
     163: ("Peter Sorensen", "Vejle BK", 6, "Defensive"),
     182: ("Brian Priske", "Brondby IF", 12, "Normal"),
    2015: ("Jon Dahl Tomasson", "AGF", 14, "Attacking"),         # the Attacking edge: 13|14
}

# In-game Style from the same screenshots, and the attacking_intent (+14) it is banded from.
STYLE = {1619: "Attacking", 1134: "Attacking", 2506: "Attacking",
         1686: "Normal", 1486: "Normal", 1833: "Normal",
         329: "Defensive"}

# Out-of-sample anchors for +14 from the save's licensed real-world manager database. These
# are database tids, not career state, and they read the same on the Turkish save. The point
# is that nobody chose them to fit: Klopp is the most famously attacking manager in the pool
# and Mourinho/Simeone the two most famously defensive, and +14 puts them at the extremes.
FAMOUS = {223: ("Klopp", 16, 20), 2938: ("Mourinho", 1, 9), 1094: ("Simeone", 1, 9)}

# The INFO record's personality block (info+52..59) and international record (+38/+39), from
# the same 7 screenshots. Sportsmanship is omitted: it is the one of the eight with no UI to
# check against. tid -> (adaptability, ambition, determination, loyalty, pressure,
#                        professionalism, temperament, caps, goals)
PERSONALITY = {
    1619: (12, 10, 14, 14, 14, 14, 15, 0, 0),
    1134: (10, 19, 15, 13, 15, 19, 17, 0, 0),
     329: (9, 14, 17, 17, 16, 17, 4, 47, 1),
    2506: (17, 11, 16, 18, 17, 14, 17, 0, 0),
    1686: (14, 13, 15, 16, 14, 13, 9, 2, 0),
    1486: (9, 7, 7, 16, 11, 14, 16, 0, 0),
    1833: (11, 13, 14, 9, 13, 14, 9, 0, 0),
}
_PERS_KEYS = ("adaptability", "ambition", "determination", "loyalty", "pressure",
              "professionalism", "temperament", "international_caps", "international_goals")

CATALOG = ['4-4-2', '4-4-2 Diamond', '4-1-2-2-1', '4-1-4-1', '4-2-1-3', '4-2-3-1',
           '4-2-3-1 DM', '4-2-2-2', '4-2-4', '4-3-1-2', '4-3-3', '4-4-1-1', '4-3-2-1',
           '4-5-1', '3-4-3', '3-4-3 DM', '5-1-2-2', '5-2-1-2', '5-2-2-1', '5-3-2', '5-4-1']


def find_save(argv):
    if len(argv) > 1 and os.path.exists(argv[1]):
        return argv[1]
    for d in (os.path.expanduser(os.environ.get("FM_SAVES_DIR", "~/fm-saves/frem")),
              os.path.expanduser("~/fm-saves/frem"), ROOT):
        p = os.path.join(d, SAVE_NAME)
        if os.path.exists(p):
            return p
    return None


def main(argv):
    path = find_save(argv)
    if not path:
        return skip(f"{SAVE_NAME} not found")
    with open(path, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

    fails = []

    catalog = ST.formation_catalog(mm)
    if catalog != CATALOG:
        fails.append(f"formation catalog changed: {catalog}")
    else:
        print(f"  OK  formation catalog: {len(catalog)} templates in declaration order")

    info = scrape_person_info(mm)
    staff_ids = [p["id2"] for p in info.values() if p["sid"] == "ffffffff"]
    recs = ST.scrape_staff_attributes(mm, staff_ids)
    print(f"  OK  {len(recs)} staff attribute records from {len(staff_ids)} staff")

    # The record is 39 bytes: the stride between consecutive real records, which is what
    # bounds where a field can live at all. A different answer here means the record grew or
    # the table changed shape, and every offset above needs re-checking.
    offs = sorted(r["offset"] for r in recs.values())
    same = sum(1 for a, b in zip(offs, offs[1:]) if b - a == 39)
    if same < 0.85 * (len(offs) - 1):
        fails.append(f"staff record stride is not 39: only {same}/{len(offs)-1} gaps match")
    else:
        print(f"  OK  staff record stride 39 ({same}/{len(offs)-1} consecutive gaps)")

    for tid, (formation, tier, attrs) in MANAGERS.items():
        p = info.get(tid)
        r = recs.get(p["id2"]) if p else None
        if not r:
            fails.append(f"tid {tid}: no staff record")
            continue
        got = catalog[r["formation_preferred"]]
        if got != formation:
            fails.append(f"tid {tid}: formation {got!r}, expected {formation!r}")
        if r["reputation_tier"] != tier:
            fails.append(f"tid {tid}: tier {r['reputation_tier']!r}, expected {tier!r}")
        bad = {k: (r[k], v) for k, v in attrs.items() if r[k] != v}
        if bad:
            fails.append(f"tid {tid}: coaching attrs got/want {bad}")
        if not bad and got == formation and r["reputation_tier"] == tier:
            print(f"  OK  tid {tid}: {got} / {catalog[r['formation_attacking']]} / "
                  f"{catalog[r['formation_defensive']]}  ({tier}, 10/10 attrs)")

    # Style is DERIVED from attacking_intent (+14), so this guards the bands as much as the
    # field: a boundary moved by one would break a ground-truth manager.
    for tid, want in STYLE.items():
        p = info.get(tid)
        r = recs.get(p["id2"]) if p else None
        got = r["style"] if r else None
        if got != want:
            fails.append(f"tid {tid}: style {got!r} (intent "
                         f"{r['attacking_intent'] if r else '-'}), expected {want!r}")
    if not any(f.startswith("tid") and "style" in f for f in fails):
        print(f"  OK  7/7 ground-truth managers' Style derives from attacking_intent")

    for tid, (who, lo, hi) in FAMOUS.items():
        p = info.get(tid)
        r = recs.get(p["id2"]) if p else None
        if not r:
            fails.append(f"{who} (tid {tid}): no staff record")
        elif not (lo <= r["attacking_intent"] <= hi):
            fails.append(f"{who}: attacking_intent {r['attacking_intent']}, expected "
                         f"{lo}-{hi} — the +14 reading has moved")
    print(f"  OK  out-of-sample: " + ", ".join(
        f"{w}={recs[info[t]['id2']]['attacking_intent']}"
        for t, (w, _, _) in FAMOUS.items() if info.get(t) and recs.get(info[t]["id2"])))

    # the triple is real, not three coincidental bytes: a random 3 adjacent bytes in this
    # region are all <21 about 57% of the time, so anything near 100% is signal.
    valid = sum(1 for r in recs.values()
                if all(r[s] < len(catalog) for s in ST.FORMATION_SLOTS.values()))
    pct = 100.0 * valid / max(len(recs), 1)
    if pct < 95:
        fails.append(f"only {pct:.1f}% of staff records have a catalog-valid triple")
    else:
        print(f"  OK  {pct:.1f}% of staff records carry a catalog-valid formation triple")

    # player record tail: goalkeepers are materially taller and heavier than outfielders.
    # This is the check that proves height/weight are what we think, not plausible noise.
    attrs = scrape_player_attributes(mm)
    gk, out = [], []
    for r in attrs.values():
        h, w = r["height_cm"], r["weight_kg"]
        if 150 <= h <= 215 and 45 <= w <= 120:
            (gk if r["positions"].get("GK") == 20 else out).append((h, w))
    gh = statistics.mean(h for h, _ in gk)
    oh = statistics.mean(h for h, _ in out)
    gw = statistics.mean(w for _, w in gk)
    ow = statistics.mean(w for _, w in out)
    if not (gh - oh > 4 and gw - ow > 3):
        fails.append(f"GK/outfield split too small: {gh:.1f}/{oh:.1f}cm {gw:.1f}/{ow:.1f}kg")
    else:
        print(f"  OK  GK {gh:.1f}cm/{gw:.1f}kg vs outfield {oh:.1f}cm/{ow:.1f}kg "
              f"(n={len(gk)}/{len(out)})")

    # ---- reference tables (fmparser/tables/stadiums.py, cities.py) ----------
    stadiums, cities = PL_STADIUMS.scrape_stadiums(mm), PL_CITIES.scrape_cities(mm)
    for sid, want_name, want_cap in ((157, "Aalborg Portland Park", 13800),
                                     (177, "Parken", 38065)):
        st = stadiums.get(sid)
        if not st or st["name"] != want_name or st["capacity"] != want_cap:
            fails.append(f"stadium {sid}: {st}")
    for cid, lat, lon in ((51, 57.0488, 9.9217), (58, 55.6761, 12.5683)):
        c = cities.get(cid)
        if not c or abs(c["latitude"] - lat) > 0.01 or abs(c["longitude"] - lon) > 0.01:
            fails.append(f"city {cid}: {c}")
    print(f"  OK  {len(stadiums)} stadiums, {len(cities)} cities (capacities + coords exact)")

    # Both tables are dense arrays keyed by slot index, so a hole means the walk dropped a
    # row and an overshoot means it invented one. This is the check a ground-truth spot-check
    # cannot make: the coordinates for Aalborg and Parken were exact while the city walk was
    # simultaneously emitting 3 records that were not cities and dropping 31 that were --
    # every one of the 31 referenced by a stadium. See scripts/audit_records.py.
    dense = True
    for label, tbl in (("stadium", stadiums), ("city", cities)):
        if min(tbl) != 0 or len(tbl) != max(tbl) + 1:
            missing = sorted(set(range(min(tbl), max(tbl) + 1)) - set(tbl))
            fails.append(f"{label} table not contiguous: {len(tbl)} rows over "
                         f"{min(tbl)}..{max(tbl)}, {len(missing)} gaps {missing[:10]}")
            dense = False
    if dense:
        print("  OK  stadium + city tables dense from id 0 (no dropped or invented rows)")

    unresolved = {s["city_id"] for s in stadiums.values()} - set(cities)
    if len(unresolved) > 1:
        fails.append(f"{len(unresolved)} stadium city_ids resolve to no city: "
                     f"{sorted(unresolved)[:10]}")
    else:
        print(f"  OK  every stadium's city_id resolves ({len(unresolved)} unresolved)")

    langs = languages.scrape_languages(mm)
    for lid, want in ((7, "English"), (10, "German"), (21, "Norwegian"),
                      (29, "Swedish"), (31, "Danish")):
        got = (langs.get(lid) or {}).get("name")
        if got != want:
            fails.append(f"language {lid}: {got!r}, expected {want!r}")

    nations_map = nations.scrape_nations(mm)
    for nid, want in ((131, "Belgium"), (138, "Denmark"), (139, "England"), (173, "Turkey")):
        got = (nations_map.get(nid) or {}).get("name")
        if got != want:
            fails.append(f"nation {nid}: {got!r}, expected {want!r}")
    # the ranking is near-unique across nations: a mis-read field cannot produce that
    ranks = [r["world_ranking"] for r in nations_map.values() if r.get("is_ranked")
             and 1 <= (r["world_ranking"] or 0) <= 400]
    uniq = len(set(ranks)) / max(len(ranks), 1)
    if uniq < 0.8:
        fails.append(f"world_ranking only {uniq:.0%} distinct — field is probably mis-read")
    else:
        print(f"  OK  {len(nations_map)} nations, world_ranking {uniq:.0%} distinct over "
              f"{len(ranks)} ranked")
    # coefficients are UEFA-only: South American sides must have none
    for nid in (r["id"] for r in nations_map.values() if r["name"] in ("Brazil", "Argentina")):
        if nations_map[nid]["coefficients"]:
            fails.append(f"{nations_map[nid]['name']} should have no UEFA coefficient")
    euro = [r for r in nations_map.values() if r["coefficients"]]
    print(f"  OK  {len(euro)} nations carry UEFA coefficients, none of them South American")

    # The info record's personality block + international record, on the same 7 managers.
    ok = 0
    for tid, want in PERSONALITY.items():
        p = info.get(tid)
        got = tuple(p[k] for k in _PERS_KEYS) if p else None
        if got != want:
            fails.append(f"tid {tid}: person block {got}, expected {want}")
        else:
            ok += 1
    print(f"  OK  {ok}/{len(PERSONALITY)} managers' personality + caps/goals exact")

    # An empty person slot has no uid, and blanking the person block on that ONE record-level
    # invariant is what keeps every field on it clean -- no date window, no plausibility test.
    # The check that it works: nothing implausible survives anywhere in the block.
    blank = [p for p in info.values() if p["uid"] == 0]
    leak = [p for p in blank if any(p[k] is not None for k in PERSON_FIELDS)]
    if leak:
        fails.append(f"{len(leak)} empty slots (uid == 0) still carry person data")
    bad_date = [p["joined_date"] for p in info.values()
                if p["joined_date"] and not ("1950" <= p["joined_date"][:4] <= "2100")]
    bad_pers = [p for p in info.values() if p["adaptability"] is not None
                and not all(1 <= p[k] <= 20 for k in ("adaptability", "ambition",
                                                      "loyalty", "temperament"))]
    if bad_date or bad_pers:
        fails.append(f"{len(bad_date)} implausible joined_date(s), "
                     f"{len(bad_pers)} personality value(s) outside 1-20")
    else:
        print(f"  OK  {len(blank)} empty slots blanked on uid == 0; no implausible "
              f"joined_date or personality value survives anywhere")

    # Second save, Style only: the band EDGES, which the 2024 set alone cannot pin.
    other = os.path.join(os.path.dirname(path), STYLE_2026_SAVE)
    if os.path.exists(other):
        with open(other, "rb") as f2:
            mm2 = mmap.mmap(f2.fileno(), 0, access=mmap.ACCESS_READ)
        info2 = scrape_person_info(mm2)
        recs2 = ST.scrape_staff_attributes(
            mm2, [p["id2"] for p in info2.values() if p["sid"] == "ffffffff"])
        ok = 0
        for tid, (who, club, intent, want) in STYLE_2026.items():
            p2 = info2.get(tid)
            r = recs2.get(p2["id2"]) if p2 else None
            if not r:
                fails.append(f"{who} (tid {tid}): no staff record in {STYLE_2026_SAVE}")
            elif r["attacking_intent"] != intent or r["style"] != want:
                fails.append(f"{who} @ {club}: intent {r['attacking_intent']}/"
                             f"{r['style']!r}, expected {intent}/{want!r}")
            else:
                ok += 1
        print(f"  OK  {ok}/{len(STYLE_2026)} band-edge managers on {STYLE_2026_SAVE} "
              f"(intent 6-14, both edges)")
    else:
        print(f"  --  {STYLE_2026_SAVE} absent, band-edge check skipped")

    if fails:
        print("\nFAIL:")
        for f_ in fails:
            print("  -", f_)
        return 1
    print("\nPASS: staff records + player record tail match ground truth")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
