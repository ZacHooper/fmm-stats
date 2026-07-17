#!/usr/bin/env python3
"""
Ground-truth guard for the light-results parser (fmparser/lightresults.py).

Asserts the record format stays pinned: known games decode with the right competition CID,
club->league is correct for known clubs, the Turkish Super League has its real membership,
and the league/cup discriminator (the +10 CID) still works.

Requires a 21-22 save (gitignored):
    python3 tests/test_lightresults.py [path/to/21-22-save.fms]
Skips cleanly if none is found.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fmparser.save import Save                        # noqa: E402
from fmparser import staging as S                     # noqa: E402
from fmparser import lightresults as L                # noqa: E402

CANDIDATES = ["21-22-end.fms", "21-22-mid.fms", "fm_save1.fms"]

# ground truth (docs/IDS.md + screenshots)
SUPER_LEAGUE = 118          # Turkish Super League (top division)
OUR_LEAGUE = 228            # Turkish 2. League White Group
TURKISH_CUP = 117
SL_CLUBS = {955: "Galatasaray", 954: "Fenerbahce", 951: "Besiktas", 961: "Trabzonspor",
            1693: "Alanyaspor", 1368: "Basaksehir", 1400: "Sivasspor", 1363: "Goztepe"}
OUR_CLUBS = {6567: "Bucaspor", 6353: "Karacabey"}
# Super League results day, 28 May 2022 (a known fixture with exact score)
KNOWN_GAME = (1693, 1368, 1, 0, 118)     # Alanyaspor 1-0 Basaksehir, cid 118


def _check(cond, msg, fails):
    if not cond:
        fails.append(msg)


def _find_save(argv):
    if len(argv) > 1 and os.path.exists(argv[1]):
        return argv[1]
    for c in CANDIDATES:
        p = os.path.join(ROOT, c)
        if os.path.exists(p):
            return p
    return None


def run(save_path=None):
    save_path = save_path or _find_save(sys.argv)
    if not save_path:
        print("SKIP: no 21-22 save found")
        return 0

    fails = []
    s = Save(save_path)
    mm = s.mm
    info = S.scrape_players(mm)
    valid = {p["club_tid"] for p in info.values() if p["club_tid"] != S.NO_CLUB}
    data = L.build(mm, valid)
    records, lgs, club_league = data["records"], data["leagues"], data["club_league"]

    # 1. records swept
    _check(len(records) > 2000, f"only {len(records)} fixtures swept", fails)

    # 2. the known Super League game decodes with the right teams/score/cid
    fixtures = {(r["home"], r["away"], r["scoreH"], r["scoreA"], r["cid"]) for r in records}
    _check(KNOWN_GAME in fixtures,
           "Alanyaspor 1-0 Basaksehir (cid 118) not found", fails)

    # 3. club -> league correct for known clubs
    for tid, nm in SL_CLUBS.items():
        _check(club_league.get(tid) == SUPER_LEAGUE,
               f"{nm} ({tid}) -> {club_league.get(tid)}, expected {SUPER_LEAGUE}", fails)
    for tid, nm in OUR_CLUBS.items():
        _check(club_league.get(tid) == OUR_LEAGUE,
               f"{nm} ({tid}) -> {club_league.get(tid)}, expected {OUR_LEAGUE}", fails)

    # 4. Super League membership: the real 20-team division (allow a little slack)
    sl = lgs.get(SUPER_LEAGUE, {})
    _check(18 <= sl.get("member_count", 0) <= 22,
           f"Super League member_count {sl.get('member_count')} not ~20", fails)
    for tid in SL_CLUBS:
        _check(tid in sl.get("members", []),
               f"Super League missing member {SL_CLUBS[tid]} ({tid})", fails)

    # 5. league/cup discriminator: a Super League club also has a Turkish Cup (117) fixture
    gala_cids = {r["cid"] for r in records if 955 in (r["home"], r["away"])}
    _check(SUPER_LEAGUE in gala_cids and TURKISH_CUP in gala_cids,
           f"Galatasaray cids {sorted(gala_cids)} miss league+cup split", fails)

    # 6. standings computable and points-ordered
    table = L.league_table(mm, records, SUPER_LEAGUE, members=set(sl.get("members", [])))
    pts = [row["points"] for row in table]
    _check(pts == sorted(pts, reverse=True), "Super League table not points-ordered", fails)

    if fails:
        print("FAIL:")
        for f in fails:
            print("  -", f)
        s.close()
        return 1
    print(f"PASS: light results {len(records)} fixtures, {len(club_league)} clubs->league; "
          f"Super League {sl.get('member_count')} clubs; known game + cup split OK")
    s.close()
    return 0


if __name__ == "__main__":
    sys.exit(run())
