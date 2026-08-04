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


def league_name(mm, code, want="long"):
    """Name for a club-record league code (e.g. 1147 -> '3. Division').

    These competition records carry a large UID (~2 billion) that resolve_comp rejects,
    and league names can start with a digit ('3. Division', '2. Bundesliga'), so this uses
    a dedicated relaxed resolver rather than comp_name."""
    le = struct.pack("<H", code)
    pos = 0
    while True:
        i = mm.find(le, pos)
        if i == -1:
            return None
        pos = i + 1
        uid = int.from_bytes(mm[i + 2:i + 6], "little")
        if not (1_000_000_000 <= uid <= 4_000_000_000):
            continue
        ln = int.from_bytes(mm[i + 6:i + 10], "little")
        if not (3 <= ln <= 45):
            continue
        try:
            nm = mm[i + 10:i + 10 + ln].decode("utf-8")
        except UnicodeDecodeError:
            continue
        if nm and (nm[0].isupper() or nm[0].isdigit()) and sum(c.isalpha() for c in nm) >= 3:
            return nm


# ---------------- competitions ----------------
def comp_id_at(mm, date_off):
    return int.from_bytes(mm[date_off - 3:date_off - 1], "little")


_COMP_CACHE = {}


def resolve_comp(mm, cid, want="long"):
    le = struct.pack("<H", cid)
    pos = 0
    while True:
        i = mm.find(le, pos)
        if i == -1:
            return None
        pos = i + 1
        uid = int.from_bytes(mm[i + 2:i + 6], "little")
        if not (1000 <= uid <= 300_000_000):
            continue
        ln = int.from_bytes(mm[i + 6:i + 10], "little")
        if not (3 <= ln <= 45):
            continue
        try:
            long_name = mm[i + 10:i + 10 + ln].decode("utf-8")
        except UnicodeDecodeError:
            continue
        if not (long_name and long_name[0].isupper()
                and sum(c.isalpha() for c in long_name) >= 3):
            continue
        j = i + 10 + ln
        for pad in (0, 1):
            ln2 = int.from_bytes(mm[j + pad:j + pad + 4], "little")
            if 3 <= ln2 <= 45:
                try:
                    short = mm[j + pad + 4:j + pad + 4 + ln2].decode("utf-8")
                except UnicodeDecodeError:
                    short = None
                if short and short[0].isalnum() and sum(c.isalpha() for c in short) >= 2:
                    return short if want == "short" else long_name
    return None


def comp_name(mm, cid, want="long"):
    key = (id(mm), cid, want)
    if key not in _COMP_CACHE:
        _COMP_CACHE[key] = resolve_comp(mm, cid, want)
    return _COMP_CACHE[key]


# competition type byte (immediately after the 3 name strings). Calibrated on Turkey:
# league(228)/play-off(227)=1, cup(117)=2, reserve league(1370)=8, friendly(65)=9.
COMP_TYPES = {1: "league", 2: "cup", 8: "reserve_league", 9: "friendly"}


def comp_detail(mm, cid):
    """Full competition record: cid, uid, name, short, code, type, nation.
    After the 3 name strings come: type byte (+0), nation byte (+3). See COMP_TYPES."""
    le = struct.pack("<H", cid)
    pos = 0
    while True:
        i = mm.find(le, pos)
        if i == -1:
            return None
        pos = i + 1
        uid = int.from_bytes(mm[i + 2:i + 6], "little")
        if not (1000 <= uid <= 300_000_000):
            continue
        ln = int.from_bytes(mm[i + 6:i + 10], "little")
        if not (3 <= ln <= 45):
            continue
        try:
            long = mm[i + 10:i + 10 + ln].decode("utf-8")
        except UnicodeDecodeError:
            continue
        if not (long and long[0].isupper() and sum(c.isalpha() for c in long) >= 3):
            continue
        # skip 3 length-prefixed strings from i+6 (long/short/code), tolerating a
        # 1-byte pad, to land on the type/nation bytes.
        p = i + 6
        names = []
        for _ in range(3):
            sl = int.from_bytes(mm[p:p + 4], "little")
            if not (1 <= sl <= 45):
                p += 1
                sl = int.from_bytes(mm[p:p + 4], "little")
            if not (1 <= sl <= 45) or p + 4 + sl > len(mm):
                break                       # not a real comp record here
            try:
                names.append(mm[p + 4:p + 4 + sl].decode("utf-8"))
            except UnicodeDecodeError:
                names.append(None)
            p = p + 4 + sl
        if len(names) < 3 or p + 3 >= len(mm):
            continue
        typ, nation = mm[p], mm[p + 3]
        return {"cid": cid, "uid": uid, "name": names[0], "short": names[1],
                "code": names[2],
                "type": COMP_TYPES.get(typ, f"type_{typ}"), "type_id": typ,
                "nation_id": None if nation == 255 else nation}


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
