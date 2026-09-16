#!/usr/bin/env python3
"""
Reference-data resolvers: club names, competition names, and the player info field.

- Club records (~10-14 MB): [TID:u32][UID:u32][len][long][len][short][len][code].
- Competition records (~13 MB): [cid:u16][UID:u32][len][long][len][short][len][code];
  a match's cid is a u16 at date_off-3.
- Info field (~2.8 MB, rough-guide Step 2): TID, UID, name IDs, DOB, nationality,
  club TID, and the SID at +60 that links a player to their global attribute record
  and their per-match stat blocks.
"""
from datetime import date, timedelta
import struct

import numpy as np

from . import regions as RG

NATIONS = {173: "Turkey"}


# A club's uid is NOT bounded by the 400,000,000 that gated this scan for its whole life.
# Ground truth, confirmed against two in-game player profiles (2026-09-12): Shawn Beeckaert
# plays for tid 6863, which the game shows as "EM United" -- Erpe-Mere United, uid
# 2,000,004,399, a perfectly well-formed record at byte 10,104,532 that the ceiling threw
# away. Jesús Bernal plays for tid 7153, "Paracuellos" = C.D. Paracuellos Antamira, uid
# 2,000,112,622. We were keeping "Erpe-Mere United Reserves" (uid 200,010,882, under the
# ceiling) while dropping the first team.
#
# This is the THIRD uid gate in this file to be wrong the same way -- see find_comp_record on
# the old `uid >= 1000` rule that silently skipped every top division. The uid is not a range
# to guess at; it is an identifier.
#
# The ceiling is not simply raised, because widening it in place CORRUPTS three real clubs:
# person records match the club shape and win low tids on file order (C Cerro Porteño ->
# 'Ultee', Club Sporting Cristal -> 'Boujemaoui', Club Centro Deportivo Municipal ->
# 'Leemans'). So the band below admits records only for tids nothing else resolved, and only
# with the club trailer marker present. Measured on frem-2026-03-22: 327 clubs recovered,
# 0 existing names changed, 0 person records admitted.
_CLUB_UID_FILL_LO, _CLUB_UID_FILL_HI = 1_900_000_000, 2_100_000_000


def _refdata_window(mm):
    """(lo, hi) for the club/comp reference-data band. Trusted outright, same as every
    other region in regions.py (ATTR_LO/HI, LIGHT_LO/HI, ...) — no runtime fallback to a
    full-file scan. That fallback was tried and measured SLOWER in practice: most
    club_record lookups here are misses (obscure historical/foreign clubs with no record
    in this save at all — extract.py's club_ids includes every club named in every
    player's full career history), and a miss means scanning to end-of-range either way,
    so "windowed, then whole file" costs window-scan PLUS full-file-scan on every miss —
    strictly more work than the unbounded original for the common case. Measured on a real
    4742-club lookup set: fallback version 123s vs unbounded original 116s (SLOWER); window-
    only (this version) is bounded to ~20 MB regardless of hit or miss. See regions.py for
    where the bound comes from (the actual filler-delimited section, not sampled hits) and
    what to do if a future save drifts past it."""
    return RG.REFDATA_LO, min(RG.REFDATA_HI, len(mm))


# ---------------- clubs + competitions: single-pass reference index ----------------
# club_record/find_comp_record used to be independent `mm.find`-per-call scans of the
# ~20 MB REFDATA window — cheap individually, but extract.py resolves ~4700+ club tids
# (every club named in every player's full career history) plus a few hundred comp cids
# in one run, and MOST of those calls are misses that scan to the end of the window
# regardless. That's O(lookups x window) — tens of seconds in a real extract.
#
# _build_refdata_index scans the window ONCE and returns {tid: club_record} and
# {cid: comp_record} for every record it holds, so every lookup after that is an O(1)
# dict.get(). The candidate search itself is vectorized with numpy (same technique as
# history.py's column-wise scan of the history slab): both record shapes put a
# length-prefixed name's length field (u32, small — [2,60] for a club long name, subsuming
# the comp range [3,45]) 4 bytes after their UID, so `np.flatnonzero` on the whole window's
# u32-at-every-offset view finds every plausible record start in one vectorized pass
# (~350k candidates out of 20M positions, <0.1s) before any per-candidate Python
# validation runs. Only the reduced candidate set pays Python-level cost.
#
# No range check on the tid read back from each candidate (an earlier draft guessed
# `100 < tid < 70000` to cut candidate volume and shipped it uncommitted with an unverified
# "validated identical" claim in this comment — it silently dropped 26 real clubs in one
# real save, including Boca Juniors and River Plate, tid 51-78). Trust the same structural
# checks the old per-tid scan always relied on (uid range, decodable name, valid short
# name) instead of a second guess about what a tid can be.
def _valid_name(b, min_alpha=2):
    """Decode a length-prefixed name, or None if it can't be one.

    `min_alpha` guards against random bytes that happen to decode. It is 2 for LONG names,
    but SHORT names are abbreviations and are legitimately allowed a single letter — real
    example: B.93 (tid 334), whose short name "B.93" was being rejected, which threw away the
    club record entirely and left only an unrelated "Player of the Month" award record that
    shares the tid. That surfaced as an award appearing as a player's club in career history.
    """
    try:
        txt = b.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if any(ord(c) < 0x20 for c in txt):
        return None
    if sum(c.isalpha() for c in txt) < min_alpha:
        return None
    return txt


def _short_after(mm, j):
    for pad in (0, 1):
        ln = int.from_bytes(mm[j + pad:j + pad + 4], "little")
        if 2 <= ln <= 60:
            sh = _valid_name(mm[j + pad + 4:j + pad + 4 + ln], min_alpha=1)
            if sh:
                return sh
    return None


# competition type byte (immediately after the 3 name strings). Calibrated on Turkey:
# top-flight league(0), league(228)/play-off(227)=1, cup(117)=2, reserve league(1370)=8,
# friendly(65)=9. type_id 0 and 1 are BOTH round-robin leagues (0 = a nation's top flight,
# e.g. 3F Superliga / Bundesliga / Serie A; 1 = the divisions below it).
COMP_TYPES = {0: "league", 1: "league", 2: "cup", 8: "reserve_league", 9: "friendly"}
_COMP_VALID_TYPES = frozenset(COMP_TYPES)
_MIN_COMP_REP = 500          # real loaded comps have reputation >> this (min seen ~12k for a
                             # 6th-tier league; friendlies ~2.6k). ROUND-label records that
                             # collide on small cids ('First Leg', 'Playoff') carry rep 0.

_REFDATA_INDEX_CACHE = {}   # id(mm) -> ({tid: club_record}, {cid: comp_record})


def _build_refdata_index(mm):
    key = id(mm)
    cached = _REFDATA_INDEX_CACHE.get(key)
    if cached is not None:
        return cached
    lo, hi = _refdata_window(mm)
    n = hi - lo
    buf = np.frombuffer(mm, dtype=np.uint8, count=n, offset=lo)
    # u32 LE at every offset q within the window (q relative to lo)
    u32 = (buf[:-3].astype(np.uint32) | (buf[1:-2].astype(np.uint32) << 8)
           | (buf[2:-1].astype(np.uint32) << 16) | (buf[3:].astype(np.uint32) << 24))
    # candidate = position of a plausible name-length field: club needs [2,60], comp
    # needs [3,45] — [2,60] covers both, so this one filter serves either branch below.
    cand = np.flatnonzero((u32 >= 2) & (u32 <= 60))
    cand = cand[cand >= 8]      # room to look back 8 bytes for the club header (TID+UID)

    clubs, comps = {}, {}
    tiers = {}                  # tid -> which gate admitted the stored record (0 beats 1)
    nmax = len(mm)
    for off in cand.tolist():
        q = off + lo             # absolute offset of the length field

        # ---- club branch: [TID u32]@q-8 [UID u32]@q-4 [len][long][len][short][len][code] ----
        # No range check on tid itself (an earlier version guessed `100 < tid < 70000` to
        # cut candidate volume, but real club tids go as low as 51 — Boca Juniors, River
        # Plate and 24 others in one real save all sit in [51,78] and would have been
        # silently dropped). Structural validation only, matching the old per-tid scan.
        tid = int.from_bytes(mm[q - 8:q - 4], "little")
        uid = int.from_bytes(mm[q - 4:q], "little")
        # TIER 0 is the long-standing gate; TIER 1 is a strictly gap-FILLING second tier for
        # the ~2-billion uid band (see _CLUB_UID_FILL_LO below). A tier-1 record can never
        # displace a tier-0 one, so this cannot change a club name that resolves today.
        primary = 1 <= uid <= 400_000_000
        fill = (not primary
                and _CLUB_UID_FILL_LO <= uid <= _CLUB_UID_FILL_HI
                and tid <= 0xFFFF)
        if primary or fill:
            ln = int.from_bytes(mm[q:q + 4], "little")
            if 2 <= ln <= 60:
                long_name = _valid_name(mm[q + 4:q + 4 + ln])
                if long_name:
                    short_name = _short_after(mm, q + 4 + ln)
                    if short_name:
                        p = q                # walk past the 3 length-prefixed strings
                        for _ in range(3):
                            sl = int.from_bytes(mm[p:p + 4], "little")
                            if not (2 <= sl <= 60):
                                p += 1
                                sl = int.from_bytes(mm[p:p + 4], "little")
                            if not (2 <= sl <= 60):
                                p = None
                                break
                            p = p + 4 + sl
                        rec = {"name": long_name, "short": short_name,
                               "league": None, "country": None,
                               # offset of the trailer (first byte after the 3 names), so
                               # club_details() can read the rest of the record without
                               # re-locating it. See parse_club_trailer.
                               "trailer": p}
                        marker = p is not None and mm[p + 160:p + 162] == b"\xff\xff"
                        if p is not None:
                            rec["country"] = int.from_bytes(mm[p:p + 2], "little")
                            if marker:
                                code = int.from_bytes(mm[p + 158:p + 160], "little")
                                if code and code != 0xffff:
                                    rec["league"] = code
                        # A tier-1 candidate must carry the club trailer marker. Person
                        # records match the [tid][uid][len][long][len][short] shape too --
                        # a first name followed by a surname -- and without this they fill
                        # empty tids with surnames ('Kjell', 'De Vriese', 'Sickinger' at
                        # tids 867-876). The marker costs 9 of 336 fills and removes all 9
                        # of those. A wrong club name is worse than a missing one.
                        if fill and not marker:
                            continue
                        tier = 0 if primary else 1
                        existing = clubs.get(tid)
                        # prefer the lower tier; within a tier prefer a copy that carries
                        # the league field, else keep the first valid copy (secondary
                        # copies read 0 / ff ff)
                        if (existing is None
                                or (tier < tiers[tid])
                                or (tier == tiers[tid]
                                    and existing["league"] is None and rec["league"] is not None)):
                            clubs[tid] = rec
                            tiers[tid] = tier

        # ---- comp branch: [cid u16]@q-6 [UID u32]@q-4 [len][long][len][short][len][code] ----
        cid = int.from_bytes(mm[q - 6:q - 4], "little")
        if cid not in comps:     # first valid record wins, same as the old per-cid scan
            uid = int.from_bytes(mm[q - 4:q], "little")
            ln = int.from_bytes(mm[q:q + 4], "little")
            if 3 <= ln <= 45:
                try:
                    long = mm[q + 4:q + 4 + ln].decode("utf-8")
                except UnicodeDecodeError:
                    long = None
                # league names can start with a digit ('3. Division', '2. Bundesliga')
                if long and (long[0].isupper() or long[0].isdigit()) and sum(c.isalpha() for c in long) >= 3:
                    p = q
                    names = []
                    for _ in range(3):
                        sl = int.from_bytes(mm[p:p + 4], "little")
                        if not (1 <= sl <= 45):
                            p += 1
                            sl = int.from_bytes(mm[p:p + 4], "little")
                        if not (1 <= sl <= 45) or p + 4 + sl > nmax:
                            break
                        try:
                            names.append(mm[p + 4:p + 4 + sl].decode("utf-8"))
                        except UnicodeDecodeError:
                            names.append(None)
                        p = p + 4 + sl
                    if len(names) == 3 and p + 14 <= nmax:
                        typ, nation = mm[p], mm[p + 3]
                        # `gate` is the ORIGINAL reputation expression. It is NOT the
                        # reputation (see below) — it is kept verbatim, and only as an
                        # acceptance test, so that which competitions resolve is unchanged
                        # by the fix. Retuning it is a separate, riskier change: this value
                        # decides whether a league gets a name at all.
                        gate = int.from_bytes(mm[p + 8:p + 10], "little")
                        # The real trailer, per fmm-editor's FMM26 `Competition`:
                        #   p+0 type u8 | p+1 continent u16 | p+3 nation u16
                        #   p+5 fg colour u16 | p+7 bg colour u16
                        #   p+9 REPUTATION u16 | p+11 LEVEL u8 | p+12 parent cid u16
                        # `gate` reads one byte early, so it is the bg colour's high byte
                        # plus reputation<<8 -- roughly 256x the real value and contaminated
                        # by a colour. It stays monotonic only while reputation < 256, so
                        # ordering by it was luck, not design.
                        rep = int.from_bytes(mm[p + 9:p + 11], "little")
                        level = mm[p + 11]
                        parent = int.from_bytes(mm[p + 12:p + 14], "little")
                        # trailer signature: nation-bound leagues/cups are [type][02][00]
                        # [nation]; friendlies (type 9) are [9][ff][ff][ff]. Anything else
                        # is a colliding non-comp record. The gate floor kills rep-0
                        # round-label collisions ('First Leg', 'Playoff').
                        #
                        # NOTE: that `[02][00]` is not a magic signature, it is
                        # ContinentId == 2 (Europe). It works because this save loads only
                        # European competitions, so treat it as a continent filter — it will
                        # not generalise if a non-European league is ever loaded.
                        if (typ in _COMP_VALID_TYPES
                                and ((mm[p + 1] == 2 and mm[p + 2] == 0) or typ == 9)
                                and ((1 <= nation <= 250) or nation == 255)
                                and gate >= _MIN_COMP_REP):
                            comps[cid] = {"cid": cid, "uid": uid, "name": names[0], "short": names[1],
                                          "code": names[2], "type": COMP_TYPES.get(typ, f"type_{typ}"),
                                          "type_id": typ, "nation_id": None if nation == 255 else nation,
                                          "reputation": rep,
                                          # 0 = top flight of its nation. Verified: Turkish
                                          # Super League 0, NordicBet Liga 1, 2. Division 2,
                                          # 3. Division 3. Confederation-style records carry
                                          # junk here (100/112) — filter on type before use.
                                          "level": level,
                                          "parent_cid": None if parent == 0xFFFF else parent}
    result = (clubs, comps)
    _REFDATA_INDEX_CACHE[key] = result
    return result


# ---------------- club record trailer ----------------
# Everything after the three name strings. Field order from nyongrand/fmm-editor's FMM26
# `Club`; see docs/agent-context/fmm-editor-record-comparison.md. Verified on the Danish
# Superliga: LeagueId reads 2 for every top-flight club (and we know Superliga is cid 2),
# attendances rank the clubs by real size, and the colours decode to the right kits.
#
# A Color is a u16 in RGB555 (r = (c >> 10) & 0x1f, each channel << 3). That is what the
# 0x7FFF flood in this region is -- 0x7FFF is white -- NOT the "sentinel" that BUGS #15
# originally read it as, and not stadium/finance data.
_CLUB_SQUAD_SLOTS = 40      # fixed-size array: exactly 40 for all 10,788 clubs in the save
_CLUB_STAFF_SLOTS = 11
_AFFILIATE_SIZE = 21        # [unk u32][club1 u32][club2 u32][start d/y u16][end d/y u16][unk u8]
_NO_ID = (0, 0xFFFF, 0xFFFFFFFF)


def _rgb(c):
    """RGB555 u16 -> '#rrggbb'."""
    return "#%02x%02x%02x" % (((c >> 10) & 0x1f) << 3, ((c >> 5) & 0x1f) << 3, (c & 0x1f) << 3)


def parse_club_trailer(mm, p):
    """Parse the club record trailer at `p`, or None if it runs off the end.

    NOTE `country` (p+0) and `nation_id` (p+2) are equal for 10,716 of 10,788 clubs and
    differ for 72 — consistent with a based-in vs competes-in split (a Monaco/Derry City
    case), but which is which is NOT verified, so both are kept verbatim.
    """
    u16 = lambda o: int.from_bytes(mm[o:o + 2], "little")
    u32 = lambda o: int.from_bytes(mm[o:o + 4], "little")
    if p is None or p + 200 > len(mm):
        return None
    d = {
        "based_id": u16(p), "nation_id": u16(p + 2),
        "colours": [_rgb(u16(p + 4 + 2 * i)) for i in range(6)],
        # 6 kits of [2 flag bytes][10 colours]; stored whole because which slot is home vs
        # away is not established.
        "kits": [[_rgb(u16(p + 16 + 22 * k + 2 + 2 * i)) for i in range(10)]
                 for k in range(6)],
        "status": mm[p + 148], "academy": mm[p + 149], "facilities": mm[p + 150],
        "att_avg": u16(p + 151), "att_min": u16(p + 153), "att_max": u16(p + 155),
        "reserves": mm[p + 157],
        "league_id": u16(p + 158),
        "other_division": u16(p + 160), "other_last_position": mm[p + 162],
        "stadium_id": u16(p + 163), "last_league": u16(p + 165),
    }
    q = p + 167
    n5 = u32(q)
    if n5 > 4096:
        return d
    q += 4 + n5
    d["league_pos"] = mm[q]; q += 1
    d["reputation"] = u16(q); q += 2
    q += 20
    naff = u16(q); q += 2
    if naff > 64:
        return d
    affs = []
    for _ in range(naff):
        affs.append({"club1_tid": u32(q + 4), "club2_tid": u32(q + 8),
                     "start_day": u16(q + 12), "start_year": u16(q + 14),
                     "end_day": u16(q + 16), "end_year": u16(q + 18)})
        q += _AFFILIATE_SIZE
    d["affiliates"] = affs
    npl = u16(q); q += 2
    if npl != _CLUB_SQUAD_SLOTS:
        return d                       # shape we do not recognise: stop rather than guess
    d["squad"] = [t for t in (u32(q + 4 * i) for i in range(npl)) if t not in _NO_ID]
    q += 4 * npl
    # The club's STAFF list -- and it EXCLUDES the manager, which is what makes
    # mart.club_managers exact rather than a reputation heuristic: of the staff whose info
    # record points at this club, the one missing from here is the man in charge. Verified
    # on all 7 ground-truth clubs, exactly one candidate each.
    d["staff"] = [t for t in (u32(q + 4 * i) for i in range(_CLUB_STAFF_SLOTS))
                  if t not in _NO_ID]
    q += 4 * _CLUB_STAFF_SLOTS
    main = u32(q)
    # Parent club. EVERY reserve side (club_type 2) carries one and it resolves exactly --
    # "KAA Gent Reserves" -> "KAA Gent", Frem's 7296 -> 346 -- so this is the structural
    # replacement for the hardcoded reserve_tid in careers.py. 186 of 4,291 first teams carry
    # one too (B-teams and the like). The rest hold a negative value we have not decoded
    # (-7298 for Frem, -2685 for AaB), so anything outside a plausible tid range is dropped
    # rather than guessed at.
    d["main_club_tid"] = main if 0 < main < 70000 else None
    d["club_type"] = mm[q + 4]
    return d


def club_details(mm, tid):
    """Full club record (names + the whole trailer) for a tid, or None."""
    rec = _build_refdata_index(mm)[0].get(tid)
    if not rec:
        return None
    out = {"tid": tid, "name": rec["name"], "short": rec["short"],
           "league_cid": rec["league"], "country": rec["country"]}
    t = parse_club_trailer(mm, rec.get("trailer"))
    if t:
        out.update(t)
    return out


def resolve_club(mm, tid, want="long"):
    """Club name for a TID, or None. Requires the full club shape (long name
    followed by a valid short name) so regions/stadiums/collisions are rejected."""
    rec = _build_refdata_index(mm)[0].get(tid)
    if not rec:
        return None
    return rec["short"] if want == "short" else rec["name"]


def club_map(mm, tids, want="long"):
    return {t: resolve_club(mm, t, want) for t in tids}


def club_record(mm, tid, want="long"):
    """A club's record: {'name','short','league','country'} or None.

    `league` is the club's league code, read from `[code u16][ff ff]` at +158 past the
    three name strings (the club.dat model — see docs; verified: Man City=5 English Prem,
    Boldklubben Frem=1147 Danish 3. Division). This is club->league membership that exists
    on day-1, before any match is played. The club DB is split across several file
    segments; the index prefers the copy carrying the league field (secondary copies read
    0 / ff ff), same as the old per-tid scan. `country` is the compete-in country code
    (Denmark=138/0x8a, England=139/0x8b)."""
    rec = _build_refdata_index(mm)[0].get(tid)
    if not rec:
        return None
    return {"name": rec["name"] if want == "long" else rec["short"],
            "short": rec["short"], "league": rec["league"], "country": rec["country"]}


# ---------------- competitions ----------------
def comp_id_at(mm, date_off):
    return int.from_bytes(mm[date_off - 3:date_off - 1], "little")


_COMP_CACHE = {}


def find_comp_record(mm, cid):
    """VALID competition record for `cid` -> full detail dict (with reputation), or None.

    A comp record is `[cid u16][uid u32][len u32][long][len][short][len][code]` then a
    trailer whose bytes we read relative to `p` (the first byte after the 3 strings):
    type @p+0, nation @p+3, REPUTATION (u16) @p+8.

    Small cids (2 = Superliga, 3, 4 ...) collide all over the file, so we cannot trust the
    first byte-match — and the UID is NOT a reliable gate (top divisions carry a tiny UID
    like 6/7/22, lower leagues a ~2-billion one, so the old `uid >= 1000` rule silently
    skipped every top flight and fell through to a bogus record, e.g. cid 2 -> 'Belfort'
    instead of '3F Superliga'). Instead we VALIDATE the record structurally: 3 decodable
    length-prefixed names, a known type byte, and the competition-record TRAILER SIGNATURE
    `[type][0x02][0x00][nation]` (bytes p+1==2, p+2==0) — nation-bound leagues/cups all carry
    it, and it's what separates them from nation/confederation records that would otherwise
    validate (e.g. cid 24 -> 'Ivory Coast' rep 54399, above the Premier League). Friendlies
    (type 9) carry no nation and no signature (`[9,255,255,255]`), so they're allowed through
    a type-9 exception. Reputation (u16 @p+8) must be >= _MIN_COMP_REP, which also kills the
    rep-0 round-label collisions ('First Leg', 'Playoff'). First record passing all of that
    (in file order) wins — see `_build_refdata_index`, which builds this alongside the club
    index in the same single pass over the reference-data window.
    """
    return _build_refdata_index(mm)[1].get(cid)


def league_name(mm, code, want="long"):
    """Name for a club-record league code (e.g. 1147 -> '3. Division', 2 -> '3F Superliga').
    League names can start with a digit ('3. Division', '2. Bundesliga')."""
    r = find_comp_record(mm, code)
    if not r:
        return None
    return (r["short"] or r["name"]) if want == "short" else r["name"]


def resolve_comp(mm, cid, want="long"):
    r = find_comp_record(mm, cid)
    if not r:
        return None
    return (r["short"] or r["name"]) if want == "short" else r["name"]


def comp_name(mm, cid, want="long"):
    key = (id(mm), cid, want)
    if key not in _COMP_CACHE:
        _COMP_CACHE[key] = resolve_comp(mm, cid, want)
    return _COMP_CACHE[key]


def comp_detail(mm, cid):
    """Full competition record: cid, uid, name, short, code, type, type_id, nation_id,
    reputation. See find_comp_record for the structural validation."""
    return find_comp_record(mm, cid)


# ---------------- player info field ----------------
# +16 is the NICKNAME field. FFFFFFFF is the "no nickname" sentinel; a player who HAS one
# carries a real nickname id there. Requiring the sentinel — which this function did for its
# whole life — means only players WITHOUT a nickname can ever be found, which is exactly the
# bug fixed in staging.scrape_players (see docs/agent-context/nickname-players-missing.md).
# It survived there because the fix landed in the spine scraper and this second, independent
# copy of the same anchor was missed. Ground truth, frem-2026-03-22: tids 20905 (Carlos Polo)
# and 19471 (Waldo Rubio) both resolve here now and did not before; 9894 (Christian Tue, no
# nickname) is unchanged.
NO_NICKNAME = b"\xff\xff\xff\xff"
# Nickname ids index the same whole-DB name tables as first/last names; the largest real id
# across a full save is ~32k. Matches staging.NAME_ID_MAX — kept in sync deliberately.
_NICK_ID_MAX = 65536


def info_offset(mm, tid):
    """Offset of a player's info record, or None.

    Located by the TID bytes, then validated on a plausible DOB year at +22 and a nickname
    field at +16 that is either the "no nickname" sentinel or a plausible nickname id. The
    sentinel is NOT required: requiring it hides every player who has a nickname.
    """
    le = struct.pack("<I", tid)
    pos = 0
    while True:
        i = mm.find(le, pos)
        if i == -1:
            return None
        pos = i + 1
        nick = mm[i + 16:i + 20]
        if nick != NO_NICKNAME and int.from_bytes(nick, "little") >= _NICK_ID_MAX:
            continue
        year = int.from_bytes(mm[i + 22:i + 24], "little")
        if 1955 <= year <= 2012:
            return i


def parse_info(mm, tid):
    i = info_offset(mm, tid)
    if i is None:
        return None
    u16 = lambda off: int.from_bytes(mm[i + off:i + off + 2], "little")
    u32 = lambda off: int.from_bytes(mm[i + off:i + off + 4], "little")
    day1, year = u16(20), u16(22)
    try:
        dob = (date(year, 1, 1) + timedelta(days=day1)).isoformat()
    except ValueError:
        dob = None
    nat = u16(24)
    return {
        "tid": u32(0), "uid": u32(4),
        "first_name_id": u32(8), "last_name_id": u32(12),
        "dob": dob,
        "nationality_id": nat, "nationality": NATIONS.get(nat, f"#{nat}"),
        "flag28": mm[i + 28],   # likely 'declared national team' (see docs/BUGS.md #6)
        "club_tid": u16(42),
        "sid": mm[i + 60:i + 62].hex(),
    }


# ---------------- player names (whole DB) ----------------
# Names for EVERY player (not just the managed squad) resolve from the info field's
# first_name_id / last_name_id via two structures near the start of the save:
#   1. the "browse" name table (flat [len u32][utf-8], ~46k entries, nation-grouped) —
#      browse[ordinal] = string;
#   2. two dense id-index tables (16-byte records [browse_ordinal u32][id u32][..][..],
#      sorted by id from 0) — one for first names, one for surnames. name_id indexes these
#      to get the browse ordinal. See docs/agent-context/name-resolution.md.
# The id has no positional relation to the browse table, hence the indirection; the game
# stores names once and links by id. Bases are per-save (offsets differ between careers),
# so everything here is DISCOVERED, not hard-coded.

def _u32(mm, o):
    return int.from_bytes(mm[o:o + 4], "little")


def _walk_browse(mm):
    """The flat [len u32][utf-8] name table near the file start -> list of strings."""
    for start in range(200, 3000):
        ln = _u32(mm, start)
        if 2 <= ln <= 40:
            raw = mm[start + 4:start + 4 + ln]
            try:
                s = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if s and s[0].isalpha() and all(ord(c) >= 0x20 for c in s):
                out = []
                o = start
                while o + 4 < len(mm):
                    L = _u32(mm, o)
                    if not (1 <= L <= 40):
                        break
                    raw = mm[o + 4:o + 4 + L]
                    try:
                        t = raw.decode("utf-8")
                    except UnicodeDecodeError:
                        break
                    if any(c < 0x20 for c in raw):
                        break
                    out.append(t)
                    o = o + 4 + L
                if len(out) > 1000:
                    return out
    return []


def _discover_id_tables(mm, browse_len, probe=8192):
    """Find the two dense id->ordinal tables. A record is 16 bytes with the id at +4 and
    the browse ordinal at +0; ids run 0,1,2,… . Anchor on a mid-range id (present in both
    tables), verify the dense run, walk back to base. Returns [(base, count), …] largest
    first."""
    pat = struct.pack("<I", probe)
    bases = {}
    pos = 0
    while True:
        i = mm.find(pat, pos)
        if i == -1:
            break
        pos = i + 1
        o = i - 4                       # i is the +4 id field -> record start
        if o < 0:
            continue
        if (_u32(mm, o + 20) == probe + 1 and _u32(mm, o + 36) == probe + 2
                and _u32(mm, o) < browse_len and _u32(mm, o + 16) < browse_len):
            base = o - probe * 16
            if base >= 0 and _u32(mm, base + 4) == 0 and _u32(mm, base + 20) == 1:
                n = probe
                while _u32(mm, base + n * 16 + 4) == n:
                    n += 1
                bases[base] = n
    return sorted(bases.items(), key=lambda x: -x[1])


_NAME_TABLES = {}   # id(mm) -> (browse_list, base_first, base_surname)


def build_name_resolver(mm, validate=None):
    """Discover the name tables for `mm` and cache them. `validate` is an optional list of
    (first_name_id, last_name_id, expected_full_name) — normally the managed squad, whose
    names we already have from the snapshot — used to orient which id-table is first names
    vs surnames (falls back to size: the larger table is surnames)."""
    browse = _walk_browse(mm)
    tabs = _discover_id_tables(mm, len(browse))
    if len(tabs) < 2:
        _NAME_TABLES[id(mm)] = (browse, None, None)
        return False
    big, small = tabs[0][0], tabs[1][0]
    base_sur, base_first = big, small           # heuristic: more surnames than first names
    if validate:
        def score(bf, bs):
            ok = 0
            for fid, lid, exp in validate:
                try:
                    if f"{browse[_u32(mm, bf + fid * 16)]} {browse[_u32(mm, bs + lid * 16)]}" == exp:
                        ok += 1
                except IndexError:
                    pass
            return ok
        if score(big, small) > score(small, big):
            base_first, base_sur = big, small   # swap only if that orientation fits better
    _NAME_TABLES[id(mm)] = (browse, base_first, base_sur)
    return True


def resolve_name(mm, first_name_id, last_name_id):
    """Full 'First Last' for any player from their info-field name ids, or None. Call
    build_name_resolver(mm) once first (cached per mmap)."""
    t = _NAME_TABLES.get(id(mm))
    if not t or t[1] is None:
        return None
    browse, base_first, base_sur = t
    try:
        return f"{browse[_u32(mm, base_first + first_name_id * 16)]} " \
               f"{browse[_u32(mm, base_sur + last_name_id * 16)]}"
    except IndexError:
        return None
