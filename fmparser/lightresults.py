#!/usr/bin/env python3
"""
Light results — the simulated games of NON-managed clubs in the loaded leagues.

Only the managed club's games get rich per-player detail (see matches.py). Every other
loaded game is stored "light": just teams, score, competition and (roughly) a date. This
region (~47-50.5 MB) is where the whole football world's results live, so it's the source
for **club -> league membership across every loaded league** and for **computed standings**.

RECORD LAYOUT (pinned against ground truth — our own games + the Super League results-day
screenshot):
    +0  home_tid   u16   club TID
    +2  away_tid   u16   club TID
    +4  scoreH     u8
    +5  scoreA     u8
    +8  flags      u16   0x40xx / 0xc0xx family (high byte 0x40 or 0xc0) — a record marker,
                         NOT the competition (prior work mistook this for the comp id)
    +10 comp_cid   u16   the match's competition CID  ★ (118=Turkish Super League,
                         228=our 2.League White, 117=Turkish Cup, 275=English FA Cup, ...)
    +12 year/+14 day     coarse date fields (base years 2020/2021; not the exact calendar
                         date — left as raw)
Each fixture is stored in >=2 near-identical copies 516 bytes apart; we dedup by
(home, away, cid, score). Validated: comp_cid cleanly separates league / cup / European
(e.g. Galatasaray -> 118 league + 117 cup + 258 EURO), so no fragile clustering is needed.

COVERAGE: this is ONE of two on-disk result lists. A second list (~49.36 MB) repeats the
home team and carries a 0x42xx value with NO cid, so it can't be league-assigned; it isn't
parsed here. Consequently per-game coverage is partial (~a third of a season), but every
club appears often enough that league MEMBERSHIP is complete and robust. Standings computed
from this list alone are therefore approximate.
"""
from collections import Counter, defaultdict

from . import regions as RG
from . import reference as R

# nation ids (player/club space) for the loaded leagues, confirmed via member club names.
NATION_NAMES = {173: "Turkey", 139: "England", 146: "Greece", 170: "Spain", 145: "Germany"}

FLAG_HI = (0x40, 0xC0)        # high byte of the +8 marker on a real record
YEARS = (0x07E4, 0x07E5, 0x07E6)   # +12 field: 2020/2021/2022 — a strong record gate
DUP_STRIDE = 516              # the twin-copy distance (used only for confirmation)


def _u16(mm, o):
    return int.from_bytes(mm[o:o + 2], "little")


def sweep(mm, valid_clubs, lo=RG.LIGHT_LO, hi=RG.LIGHT_HI, min_copies=2):
    """Every light-result fixture in the region, deduped. `valid_clubs` gates false
    positives (both teams must be real club TIDs). Returns a list of dicts:
    {home, away, scoreH, scoreA, cid, copies, off}. Records seen `min_copies`+ times
    (the 516-apart duplication) are the confirmed ones; set min_copies=1 to keep all."""
    agg = {}
    o = lo
    end = hi - 16
    while o < end:
        if mm[o + 9] in FLAG_HI:
            home = _u16(mm, o)
            away = _u16(mm, o + 2)
            if home in valid_clubs and away in valid_clubs and home != away:
                sH, sA = mm[o + 4], mm[o + 5]
                cid = _u16(mm, o + 10)
                if sH <= 30 and sA <= 30 and 0 < cid < 20000 and _u16(mm, o + 12) in YEARS:
                    k = (home, away, cid, sH, sA)
                    r = agg.get(k)
                    if r:
                        r["copies"] += 1
                    else:
                        agg[k] = {"home": home, "away": away, "scoreH": sH,
                                  "scoreA": sA, "cid": cid, "copies": 1, "off": o}
        o += 1
    return [r for r in agg.values() if r["copies"] >= min_copies]


def _is_league(mm, cid, _cache={}):
    """True for a round-robin league. type_id 1 = league, 0 = top division (Super League);
    both are round-robin. Cups (2), reserve/friendly, and unknowns are excluded here — but
    note comp_detail mis-names some small/foreign cids, so callers should lean on the cid,
    not the resolved name."""
    if cid not in _cache:
        d = R.comp_detail(mm, cid) or {}
        _cache[cid] = d.get("type_id") in (0, 1)
    return _cache[cid]


MIN_LEAGUE_GAMES = 4          # a real league member appears in >= this many of its games;
                              # noise (a club wrongly read into a comp) appears 1-2 times


def club_leagues(mm, records, min_games=MIN_LEAGUE_GAMES):
    """{club_tid: league_cid} — each club's league is the LEAGUE-type competition its games
    are tagged with (modal). A club is only assigned if its winning league has >= min_games
    votes, which drops false-positive reads. Cup-only / foreign-unloaded clubs are omitted."""
    votes = defaultdict(Counter)
    for r in records:
        if _is_league(mm, r["cid"]):
            votes[r["home"]][r["cid"]] += 1
            votes[r["away"]][r["cid"]] += 1
    out = {}
    for club, c in votes.items():
        cid, n = c.most_common(1)[0]
        if n >= min_games:
            out[club] = cid
    return out


def league_table(mm, records, cid, members=None):
    """Compute a standings table for one competition cid from its results. Returns rows
    sorted by (points, goal difference, goals for) desc: each row is
    {club, played, won, drawn, lost, gf, ga, gd, points}. If `members` is given, only those
    clubs are tabulated (drops false-positive reads). NOTE: partial coverage (see module
    docstring) means points/played are a lower bound, so ordering is approximate."""
    st = defaultdict(lambda: dict(played=0, won=0, drawn=0, lost=0, gf=0, ga=0, points=0))
    for r in records:
        if r["cid"] != cid:
            continue
        if members is not None and (r["home"] not in members or r["away"] not in members):
            continue
        h, a, sh, sa = r["home"], r["away"], r["scoreH"], r["scoreA"]
        for club, gf, ga in ((h, sh, sa), (a, sa, sh)):
            row = st[club]
            row["played"] += 1
            row["gf"] += gf
            row["ga"] += ga
            if gf > ga:
                row["won"] += 1
                row["points"] += 3
            elif gf == ga:
                row["drawn"] += 1
                row["points"] += 1
            else:
                row["lost"] += 1
    rows = []
    for club, row in st.items():
        row["club"] = club
        row["gd"] = row["gf"] - row["ga"]
        rows.append(row)
    rows.sort(key=lambda x: (x["points"], x["gd"], x["gf"]), reverse=True)
    return rows


def leagues(mm, records, club_nation=None, min_games=MIN_LEAGUE_GAMES):
    """{cid: {cid, name, type, nation_id, nation, members:[...], fixtures}} for every
    competition in the swept records. For league-type comps `members` is filtered to clubs
    appearing in >= min_games fixtures; cups keep every appearing club.

    NAMING: comp_detail mis-names some small/foreign cids (cids are per-nation, so a small
    cid collides with a bogus record). When `club_nation` is given, the comp's authoritative
    nation is the members' modal nationality, and comp_detail's name is trusted ONLY if its
    nation byte agrees — otherwise the name is dropped (better unnamed than "Angola" for an
    English league). Some foreign leagues have no name record at all and stay unnamed."""
    by_cid = defaultdict(list)
    for r in records:
        by_cid[r["cid"]].append(r)
    out = {}
    for cid, recs in by_cid.items():
        appear = Counter()
        for r in recs:
            appear[r["home"]] += 1
            appear[r["away"]] += 1
        d = R.comp_detail(mm, cid) or {}
        is_lg = _is_league(mm, cid)
        members = sorted(c for c, n in appear.items() if (n >= min_games or not is_lg))
        nation_id = d.get("nation_id")
        name = d.get("name")
        if club_nation:
            modal = Counter(club_nation.get(c) for c in members if club_nation.get(c))
            if modal:
                nation_id = modal.most_common(1)[0][0]
                if d.get("nation_id") != nation_id:   # comp_detail matched a bogus record
                    name = None
        out[cid] = {"cid": cid, "name": name, "type": d.get("type"),
                    "nation_id": nation_id, "nation": NATION_NAMES.get(nation_id),
                    "members": members, "member_count": len(members),
                    "fixtures": len(recs)}
    return out


def club_nations(info, no_club):
    """{club_tid: modal player nationality_id} from the info spine — the authoritative
    nation for each club (comp_detail's nation byte is unreliable for foreign comps)."""
    votes = defaultdict(Counter)
    for p in info.values():
        if p["club_tid"] != no_club:
            votes[p["club_tid"]][p["nationality_id"]] += 1
    return {c: v.most_common(1)[0][0] for c, v in votes.items()}


def build(mm, valid_clubs, club_nation=None):
    """Whole pipeline: sweep -> {records, leagues, club_league}. `records` are the deduped
    fixtures; `leagues` the per-cid summary (nation-validated names if `club_nation` given);
    `club_league` the {club_tid: league_cid} map."""
    records = sweep(mm, valid_clubs)
    return {"records": records,
            "leagues": leagues(mm, records, club_nation=club_nation),
            "club_league": club_leagues(mm, records)}
