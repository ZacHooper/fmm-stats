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
managers, matched against `frem-2024-11-10.fms`. Run:

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

from fmparser import staff as ST                      # noqa: E402
from fmparser import staging as S                     # noqa: E402
from fmparser import lookups as LK                    # noqa: E402
from fmparser import places as PL                     # noqa: E402

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

# In-game Style from the same screenshots, and the attacking_intent (+14) it is banded from.
STYLE = {1619: "Attacking", 1134: "Attacking", 2506: "Attacking",
         1686: "Normal", 1486: "Normal", 1833: "Normal",
         329: "Defensive"}

# Out-of-sample anchors for +14 from the save's licensed real-world manager database. These
# are database tids, not career state, and they read the same on the Turkish save. The point
# is that nobody chose them to fit: Klopp is the most famously attacking manager in the pool
# and Mourinho/Simeone the two most famously defensive, and +14 puts them at the extremes.
FAMOUS = {223: ("Klopp", 16, 20), 2938: ("Mourinho", 1, 9), 1094: ("Simeone", 1, 9)}

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
        print(f"SKIP: {SAVE_NAME} not found")
        return 0
    with open(path, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

    fails = []

    catalog = ST.formation_catalog(mm)
    if catalog != CATALOG:
        fails.append(f"formation catalog changed: {catalog}")
    else:
        print(f"  OK  formation catalog: {len(catalog)} templates in declaration order")

    info = S.scrape_players(mm)
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
    attrs = S.scrape_attributes(mm)
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

    # ---- reference tables (fmparser/places.py, fmparser/lookups.py) ----------
    stadiums, cities = PL.scrape_stadiums(mm), PL.scrape_cities(mm)
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

    langs = LK.scrape_languages(mm)
    for lid, want in ((7, "English"), (10, "German"), (21, "Norwegian"),
                      (29, "Swedish"), (31, "Danish")):
        got = (langs.get(lid) or {}).get("name")
        if got != want:
            fails.append(f"language {lid}: {got!r}, expected {want!r}")

    nations = LK.scrape_nations(mm)
    for nid, want in ((131, "Belgium"), (138, "Denmark"), (139, "England"), (173, "Turkey")):
        got = (nations.get(nid) or {}).get("name")
        if got != want:
            fails.append(f"nation {nid}: {got!r}, expected {want!r}")
    # the ranking is near-unique across nations: a mis-read field cannot produce that
    ranks = [r["world_ranking"] for r in nations.values() if r.get("is_ranked")
             and 1 <= (r["world_ranking"] or 0) <= 400]
    uniq = len(set(ranks)) / max(len(ranks), 1)
    if uniq < 0.8:
        fails.append(f"world_ranking only {uniq:.0%} distinct — field is probably mis-read")
    else:
        print(f"  OK  {len(nations)} nations, world_ranking {uniq:.0%} distinct over "
              f"{len(ranks)} ranked")
    # coefficients are UEFA-only: South American sides must have none
    for nid in (r["id"] for r in nations.values() if r["name"] in ("Brazil", "Argentina")):
        if nations[nid]["coefficients"]:
            fails.append(f"{nations[nid]['name']} should have no UEFA coefficient")
    euro = [r for r in nations.values() if r["coefficients"]]
    print(f"  OK  {len(euro)} nations carry UEFA coefficients, none of them South American")

    if fails:
        print("\nFAIL:")
        for f_ in fails:
            print("  -", f_)
        return 1
    print("\nPASS: staff records + player record tail match ground truth")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
