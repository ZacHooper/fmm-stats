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

NATIONS = {173: "Turkey"}


# ---------------- clubs ----------------
def _valid_name(b):
    try:
        txt = b.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if any(ord(c) < 0x20 for c in txt):
        return None
    if sum(c.isalpha() for c in txt) < 2:
        return None
    return txt


def _short_after(mm, j):
    for pad in (0, 1):
        ln = int.from_bytes(mm[j + pad:j + pad + 4], "little")
        if 2 <= ln <= 60:
            sh = _valid_name(mm[j + pad + 4:j + pad + 4 + ln])
            if sh:
                return sh
    return None


def resolve_club(mm, tid, want="long"):
    """Club name for a TID, or None. Requires the full club shape (long name
    followed by a valid short name) so regions/stadiums/collisions are rejected."""
    le = struct.pack("<I", tid)
    pos = 0
    while True:
        i = mm.find(le, pos)
        if i == -1:
            return None
        pos = i + 1
        uid = int.from_bytes(mm[i + 4:i + 8], "little")
        if not (1 <= uid <= 400_000_000):
            continue
        ln = int.from_bytes(mm[i + 8:i + 12], "little")
        if not (2 <= ln <= 60):
            continue
        long_name = _valid_name(mm[i + 12:i + 12 + ln])
        if not long_name:
            continue
        short_name = _short_after(mm, i + 12 + ln)
        if not short_name:            # not a club record (e.g. a region)
            continue
        return short_name if want == "short" else long_name


def club_map(mm, tids, want="long"):
    return {t: resolve_club(mm, t, want) for t in tids}


def club_record(mm, tid, want="long"):
    """Find a club's record and return {'name','short','league','country'} or None.

    `league` is the club's league code, read from `[code u16][ff ff]` at +158 past the
    three name strings (the club.dat model — see docs; verified: Man City=5 English Prem,
    Boldklubben Frem=1147 Danish 3. Division). This is club->league membership that exists
    on day-1, before any match is played. The club DB is split across several file
    segments, so we scan every copy of the record and prefer the one carrying the league
    field (secondary copies read 0 / ff ff). `country` is the compete-in country code
    (Denmark=138/0x8a, England=139/0x8b)."""
    le = struct.pack("<I", tid)
    pos = 0
    best = None
    while True:
        i = mm.find(le, pos)
        if i == -1:
            return best
        pos = i + 1
        uid = int.from_bytes(mm[i + 4:i + 8], "little")
        if not (1 <= uid <= 400_000_000):
            continue
        ln = int.from_bytes(mm[i + 8:i + 12], "little")
        if not (2 <= ln <= 60):
            continue
        long_name = _valid_name(mm[i + 12:i + 12 + ln])
        if not long_name:
            continue
        short_name = _short_after(mm, i + 12 + ln)
        if not short_name:
            continue
        p = i + 8                       # walk past the 3 length-prefixed name strings
        for _ in range(3):
            sl = int.from_bytes(mm[p:p + 4], "little")
            if not (2 <= sl <= 60):
                p += 1
                sl = int.from_bytes(mm[p:p + 4], "little")
            if not (2 <= sl <= 60):
                p = None
                break
            p = p + 4 + sl
        rec = {"name": long_name if want == "long" else short_name,
               "short": short_name, "league": None, "country": None}
        if p is not None:
            rec["country"] = int.from_bytes(mm[p:p + 2], "little")
            if mm[p + 160:p + 162] == b"\xff\xff":
                code = int.from_bytes(mm[p + 158:p + 160], "little")
                if code and code != 0xffff:
                    rec["league"] = code
        if best is None:
            best = rec
        if rec["league"] is not None:
            return rec                  # prefer a copy that carries the league field


# ---------------- competitions ----------------
def comp_id_at(mm, date_off):
    return int.from_bytes(mm[date_off - 3:date_off - 1], "little")


_COMP_CACHE = {}

# competition type byte (immediately after the 3 name strings). Calibrated on Turkey:
# top-flight league(0), league(228)/play-off(227)=1, cup(117)=2, reserve league(1370)=8,
# friendly(65)=9. type_id 0 and 1 are BOTH round-robin leagues (0 = a nation's top flight,
# e.g. 3F Superliga / Bundesliga / Serie A; 1 = the divisions below it).
COMP_TYPES = {0: "league", 1: "league", 2: "cup", 8: "reserve_league", 9: "friendly"}
_COMP_VALID_TYPES = frozenset(COMP_TYPES)
_MIN_COMP_REP = 500          # real loaded comps have reputation >> this (min seen ~12k for a
                             # 6th-tier league; friendlies ~2.6k). ROUND-label records that
                             # collide on small cids ('First Leg', 'Playoff') carry rep 0.


def find_comp_record(mm, cid):
    """First VALID competition record for `cid` -> full detail dict (with reputation), or None.

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
    rep-0 round-label collisions ('First Leg', 'Playoff'). First record passing all of that wins.
    """
    le = struct.pack("<H", cid)
    pos = 0
    n = len(mm)
    while True:
        i = mm.find(le, pos)
        if i == -1:
            return None
        pos = i + 1
        uid = int.from_bytes(mm[i + 2:i + 6], "little")
        ln = int.from_bytes(mm[i + 6:i + 10], "little")
        if not (3 <= ln <= 45):
            continue
        try:
            long = mm[i + 10:i + 10 + ln].decode("utf-8")
        except UnicodeDecodeError:
            continue
        # league names can start with a digit ('3. Division', '2. Bundesliga')
        if not (long and (long[0].isupper() or long[0].isdigit())
                and sum(c.isalpha() for c in long) >= 3):
            continue
        # walk the 3 length-prefixed strings (long/short/code), tolerating a 1-byte pad,
        # to land on the trailer at p.
        p = i + 6
        names = []
        for _ in range(3):
            sl = int.from_bytes(mm[p:p + 4], "little")
            if not (1 <= sl <= 45):
                p += 1
                sl = int.from_bytes(mm[p:p + 4], "little")
            if not (1 <= sl <= 45) or p + 4 + sl > n:
                break
            try:
                names.append(mm[p + 4:p + 4 + sl].decode("utf-8"))
            except UnicodeDecodeError:
                names.append(None)
            p = p + 4 + sl
        if len(names) < 3 or p + 10 > n:
            continue
        typ, nation = mm[p], mm[p + 3]
        rep = int.from_bytes(mm[p + 8:p + 10], "little")
        if typ not in _COMP_VALID_TYPES:
            continue
        # trailer signature: nation-bound leagues/cups are [type][02][00][nation]; friendlies
        # (type 9) are [9][ff][ff][ff]. Anything else is a colliding non-comp record.
        if not ((mm[p + 1] == 2 and mm[p + 2] == 0) or typ == 9):
            continue
        if not ((1 <= nation <= 250) or nation == 255):   # 0 = collision signature
            continue
        if rep < _MIN_COMP_REP:                            # rep-0 round-label collision
            continue
        return {"cid": cid, "uid": uid, "name": names[0], "short": names[1],
                "code": names[2], "type": COMP_TYPES.get(typ, f"type_{typ}"),
                "type_id": typ, "nation_id": None if nation == 255 else nation,
                "reputation": rep}


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
def info_offset(mm, tid):
    """Info field: TID bytes, FFFFFFFF nickname at +16, plausible DOB year at +22."""
    le = struct.pack("<I", tid)
    pos = 0
    while True:
        i = mm.find(le, pos)
        if i == -1:
            return None
        pos = i + 1
        if mm[i + 16:i + 20] == b"\xff\xff\xff\xff":
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
