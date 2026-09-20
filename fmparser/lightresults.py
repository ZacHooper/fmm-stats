#!/usr/bin/env python3
"""
Light results — the simulated games of NON-managed clubs in the loaded leagues.

    !! THIS REGION IS THE CLUB RECORDS TABLES, NOT A RESULTS LIST. !!

    Identified 2026-09-17 against in-game screenshots: the rows are the Club History
    screens (biggest win, biggest defeat, highest scoring match, streaks), parsed properly
    by `fmparser/clubrecords.py`. Consequences for everything below:
      * a club has ~12 rows because there are ~12 record CATEGORIES;
      * the ">=2 copies" this module relies on is the two-slot pattern ("Highest scoring
        match" and "Highest scoring LEAGUE match" are one game), not redundancy;
      * `league_table()` computes standings from record-holding matches, which is why they
        read 5-13 games played;
      * the club tid is at the END of the 21-byte record, so this module's forward reads of
        cid/year/day take the NEXT record's fields on every second copy.
    What still holds: these ARE real matches with real club tids and real competition ids,
    so `club_leagues()` / `leagues()` remain sound as a MEMBERSHIP source. Do not build a
    fixture list or a league table from this module. See docs/light-results-record.md.

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
Each fixture is stored in SEVERAL near-identical copies (empirically always an even
count: 2/4/6/8...). The old note "twin copies exactly 516 bytes apart" is an
oversimplification — records pack ~21 bytes apart and whole BLOCKS repeat at mixed
strides (516 is common but not the only one, and a block can recur 4/6/8x). We don't
depend on the stride at all: we dedup purely by fixture identity (home, away, cid,
score). DUP_STRIDE below is documentation only, not used by the code. Validated:
comp_cid cleanly separates league / cup / European (e.g. Galatasaray -> 118 league +
117 cup + 258 EURO), so no fragile clustering is needed.

COVERAGE: partial by nature, now that the region is known to be the Club History tables --
a club contributes its record-setting matches, not its fixtures. League MEMBERSHIP is still
complete and robust because every club holds records; standings computed from this list are
not approximate so much as meaningless, and `league_table()` should not be trusted.

The "second result list at ~49.36 MB" this docstring used to claim DOES NOT EXIST. Checked
2026-09-17: 49.36 MB is an UNSET table -- every field 0xff on a 70-byte stride, carrying the
same `e4 07` (2020) season sentinel that clubrecords.py's empty slots use. There is no
`0x42xx` value and no repeated home team. Do not go looking there again.
"""
from collections import Counter, defaultdict

from . import regions as RG
from . import reference as R
from .save import cache_key as _cache_key

# nation ids (player/club space) -> name. These are FMM22 game constants (stable across saves
# and careers — Turkey 173 holds for Bucaspor too), curated by cross-referencing each id's loaded
# league names (e.g. 131 -> "Belgian Pro League" -> Belgium). Covers every nation that has a
# loaded league; add more here as new nations appear. The parsed nation-record table (name +
# reputation) is a separate reverse-engineering TODO — see docs.
NATION_NAMES = {
    64: "Kazakhstan", 126: "Albania", 127: "Andorra", 128: "Armenia", 129: "Austria",
    130: "Azerbaijan", 131: "Belgium", 133: "Bosnia and Herzegovina", 134: "Bulgaria",
    135: "Croatia", 136: "Cyprus", 137: "Czech Republic", 138: "Denmark", 139: "England",
    140: "Estonia", 141: "Faroe Islands", 142: "Finland", 143: "France", 144: "Georgia",
    145: "Germany", 146: "Greece", 147: "Hungary", 148: "Iceland", 149: "Israel", 150: "Italy",
    153: "Lithuania", 154: "Luxembourg", 156: "Malta", 158: "Netherlands",
    159: "Northern Ireland", 160: "Norway", 161: "Poland", 162: "Portugal",
    163: "Republic of Ireland", 164: "Romania", 165: "Russia", 167: "Scotland",
    168: "Slovakia", 170: "Spain", 171: "Sweden", 172: "Switzerland", 173: "Turkey",
    174: "Ukraine", 175: "Wales", 176: "Serbia", 247: "Montenegro",
}

FLAG_HI = (0x40, 0xC0)        # high byte of the +8 marker on a real record
YEARS = (0x07E4, 0x07E5, 0x07E6)   # +12 field: 2020/2021/2022 — a strong record gate
DUP_STRIDE = 516              # a COMMON block-repeat distance; documentation only (not used)
_YEAR_MARKERS = (b"\xe4\x07", b"\xe5\x07", b"\xe6\x07")   # YEARS as +12 little-endian bytes


def _u16(mm, o):
    return int.from_bytes(mm[o:o + 2], "little")


def find_light_regions(mm, valid_clubs=None, margin=30_000, merge_gap=200_000, min_hits=50):
    """DERIVE ALL light-results regions [(lo, hi), ...] from content.
    
    The game maintains multiple schedule/results blocks across the save (e.g. partitioned
    by tier or continent), not just one. This function scans for the structural signature
    and returns boundaries for every dense cluster of valid fixtures it finds."""
    def _club_ok(t):
        return t in valid_clubs if valid_clubs is not None else (1 <= t < 70000)
    hits = []
    for ym in _YEAR_MARKERS:
        i = mm.find(ym)
        while i != -1:
            o = i - 12
            if o >= 0 and o + 16 < len(mm):
                home, away = _u16(mm, o), _u16(mm, o + 2)
                if _club_ok(home) and _club_ok(away) and home != away \
                   and mm[o + 4] <= 30 and mm[o + 5] <= 30 and 0 < _u16(mm, o + 10) < 20000:
                    hits.append(o)
            i = mm.find(ym, i + 1)
    if not hits:
        return []
    hits.sort()
    clusters, cur = [], [hits[0]]
    for o in hits[1:]:
        if o - cur[-1] <= merge_gap:
            cur.append(o)
        else:
            clusters.append(cur)
            cur = [o]
    clusters.append(cur)
    
    regions = []
    for cluster in clusters:
        if len(cluster) >= min_hits:
            regions.append((max(0, cluster[0] - margin), min(len(mm), cluster[-1] + margin)))
    return regions


def sweep(mm, valid_clubs, lo=RG.LIGHT_LO, hi=RG.LIGHT_HI, min_copies=2):
    """Every light-result fixture in the region, deduped. `valid_clubs` gates false
    positives (both teams must be real club TIDs). Returns a list of dicts:
    {home, away, scoreH, scoreA, cid, copies, off}. Records seen `min_copies`+ times
    are the confirmed ones; set min_copies=1 to keep all.

    MIRROR DEDUP: the light list stores a fixture from BOTH clubs' perspectives — the
    same game appears as `A h-a B` and `B a-h A`. The dedup key is therefore the
    UNORDERED pair + score (lower-tid perspective), so mirror copies collapse into one
    fixture instead of being double-counted in the standings (this was inflating W/D/L —
    e.g. Frem's league record read 5-1-4 with the phantom copies, ~4-1-2 without). The
    first-seen orientation is kept for display. Caveat: a genuine home-AND-away double
    leg with an exactly mirrored scoreline would also merge, but that's rare and the
    error is one game; partial coverage is the far bigger inaccuracy anyway."""
    agg = {}
    o = lo
    end = hi - 16
    while o < end:
        home = _u16(mm, o)
        away = _u16(mm, o + 2)
        if home in valid_clubs and away in valid_clubs and home != away:
            sH, sA = mm[o + 4], mm[o + 5]
            cid = _u16(mm, o + 10)
            if sH <= 30 and sA <= 30 and 0 < cid < 20000 and _u16(mm, o + 12) in YEARS:
                lo_tid, hi_tid = min(home, away), max(home, away)
                s_lo, s_hi = (sH, sA) if home == lo_tid else (sA, sH)
                k = (lo_tid, hi_tid, cid, s_lo, s_hi)      # unordered -> mirrors merge
                r = agg.get(k)
                if r:
                    r["copies"] += 1
                else:
                    agg[k] = {"home": home, "away": away, "scoreH": sH,
                              "scoreA": sA, "cid": cid, "copies": 1, "off": o}
        o += 1
    return [r for r in agg.values() if r["copies"] >= min_copies]


_LEAGUE_CACHE = {}            # (save cache_key, cid) -> bool


def _is_league(mm, cid):
    """True for a round-robin league. type_id 1 = league, 0 = top division (Super League);
    both are round-robin. Cups (2), reserve/friendly, and unknowns are excluded here — but
    note comp_detail mis-names some small/foreign cids, so callers should lean on the cid,
    not the resolved name.

    The cache key carries the SAVE as well as the cid, even though the answer is currently
    save-invariant. Measured 2026-09-20 over cids 0..1999 in `bucaspor-2023-03-25`,
    `frem-2023-07-02` and `frem-2021-07-01`: the competition table is a FIXED POOL, identical
    across both careers and across five in-game years (974 leagues in each; zero
    disagreements; cid 118 is the Turkish Super League in the Danish career too). So the old
    cid-only key -- a mutable default argument, `mm` absent from the key entirely -- was not
    returning a wrong answer in practice.

    It is keyed properly anyway because nothing enforces that invariant. `comp_detail` reads a
    per-save table located by a per-save anchor, so the moment the pool stops being shared
    (a different game version, a save with different leagues loaded, an edited database) a
    cid-only cache serves the FIRST save's answer to every save after it in the same process
    -- which `scripts/rebuild.py` is, walking both careers in one run. The failure would be
    silent and would land in `extract.py`'s league filter. See `save.cache_key` for why the
    key is `(id(mm), len(mm))` and not a bare id."""
    key = (_cache_key(mm), cid)
    if key not in _LEAGUE_CACHE:
        d = R.comp_detail(mm, cid) or {}
        _LEAGUE_CACHE[key] = d.get("type_id") in (0, 1)
    return _LEAGUE_CACHE[key]


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
                    "reputation": d.get("reputation"),
                    # 0-indexed division tier straight from the comp record: unlike ranking
                    # by reputation it puts PARALLEL divisions on the same tier (Denmark's
                    # Series' four regional groups are all level 4).
                    "level": d.get("level"), "parent_cid": d.get("parent_cid"),
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
    regions = find_light_regions(mm, valid_clubs)          # self-locating, career-agnostic
    
    all_records = []
    if regions:
        # We need a shared dict for global deduping across all regions, 
        # so we modify sweep logic inline here to pass agg, or just merge the results.
        # It's easiest to run sweep for each and then dedup the output.
        raw_fixtures = []
        for lo, hi in regions:
            raw_fixtures.extend(sweep(mm, valid_clubs, lo=lo, hi=hi, min_copies=1))
            
        # Global dedup
        agg = {}
        for r in raw_fixtures:
            # We must use the same dedup key that sweep() uses internally:
            # (lo_tid, hi_tid, cid, s_lo, s_hi)
            lo_tid, hi_tid = min(r['home'], r['away']), max(r['home'], r['away'])
            s_lo, s_hi = (r['scoreH'], r['scoreA']) if r['home'] == lo_tid else (r['scoreA'], r['scoreH'])
            k = (lo_tid, hi_tid, r['cid'], s_lo, s_hi)
            
            if k not in agg:
                agg[k] = r.copy()
                agg[k]['copies'] = 0
            agg[k]['copies'] += r['copies']
            
        # Require 2 copies total globally to be a valid record
        records = [r for r in agg.values() if r["copies"] >= 2]
    else:
        records = sweep(mm, valid_clubs)                  # fall back to hard-coded LIGHT_LO/HI
        
    return {"records": records,
            "leagues": leagues(mm, records, club_nation=club_nation),
            "club_league": club_leagues(mm, records)}
