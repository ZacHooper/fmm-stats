#!/usr/bin/env python3
"""
Staging scrapers: sweep each region of the save ONCE into a flat, keyed table.

Design (see docs/BUGS.md and the README): the player INFO section is the identity
spine — one record per player carrying every foreign key (SID -> attributes,
club_tid -> club, name IDs -> names). We scrape each region independently, capturing
its join keys, and defer all joins to the caller.

Sweeping record-by-record (rather than searching for a value) is both faster at scale
(~31k players) and collision-free: we read each record's embedded key instead of
hunting for bytes that might appear as stray data.
"""
from datetime import date, timedelta

from . import reference as R
from .attributes import (_valid_positions, ATTR_OFFSETS, POSITIONS, hidden_attributes,
                         record_tail)
from .regions import (ATTR_LO, ATTR_HI, CONTRACTREC_LO, CONTRACTREC_HI,
                      WAGE_GBP_PER_UNIT)

# free agents / unattached carry this sentinel club id
NO_CLUB = 65535

# The info record's NICKNAME field at +16. FFFFFFFF is the "no nickname" sentinel; a
# player who HAS one carries a real nickname id there instead. See `scrape_players`.
NO_NICKNAME = b"\xff\xff\xff\xff"

# DOB year plausibility window for an info record.
#
# The ceiling was 2012, which sounds generous until you notice the youngest cohort in a 2026
# save is already 2009/2010 — roughly three seasons before newgens start being born past the
# ceiling and vanishing from the spine entirely, silently, exactly like every other bug in
# this family. Raised to 2030.
#
# Measured cost of raising it, across 6 saves: bucaspor picks up TWO placeholder records
# (dob 2021-01-01, i.e. a one-year-old in a 2022 save — 'Sabri Davids', 'Edgar Carrera').
# They carry no SID so they gain no attributes, and 2 in 33,943 is the same order as the
# junk sweep 1 has always carried. Judged worth it against a scheduled, silent data loss.
# The day-of-year check added to sweep 1 below removes strictly more junk than this admits
# (one bogus record per save, on all 6).
#
# The FLOOR is fine and stays: the oldest people taper off smoothly (1956: 2, 1957: 4,
# 1958: 9), which is a real cohort edge, not a clipped one.
DOB_YEAR_LO, DOB_YEAR_HI = 1955, 2030

# first/last/nickname ids index the whole-DB name tables (~46k entries — see
# reference.build_name_resolver). The largest REAL id seen across the 30,798 records of
# a full save is 32,147; exactly two junk records carry 82M and 0xFFFF0000. 65536 sits
# comfortably above the real range and below the junk.
NAME_ID_MAX = 65536

# squad-availability status byte in the contract record. 65 = out on loan / unavailable
# (validated against the managed club's squad vs an in-game screenshot); 112 = normal
# squad member. Other values are further squad statuses (undecoded).
LOAN_STATUS = 65


# The 8 personality bytes at info+52..59, in order. Verified byte-exact against all 7
# ground-truth managers' Manager Profile screenshots (BUGS #14) and matching the order
# fmm-editor's `People.cs` declares. They live on the INFO record -- every person has them,
# player or staff -- NOT on the attribute record, which is what ATTRIBUTE_DECODING.md's old
# `P-50..P-43` row wrongly claimed.
#
# Two notes on the names. Slot 3 reads DETERMINATION on the FMM22 screens we verified against
# and `Controversy` in People.cs -- ours is the ground-truth reading for our game. And
# `sportsmanship` is the one of the eight with no UI to check against; it is the only slot
# taken on the order's authority alone, which is why the old Bucaspor lead could only ever
# match 6 of 8 against on-screen values.
PERSONALITY = ("adaptability", "ambition", "determination", "loyalty", "pressure",
               "professionalism", "sportsmanship", "temperament")
# Everything the INFO record contributes that is true of a PERSON rather than of a player or
# a staff member -- named once so extract.py, the loader and the mart cannot drift apart.
PERSON_FIELDS = PERSONALITY + ("international_caps", "international_goals")
# 0 means "not populated", not a real rating: all 622 staff who read 0 are exactly the staff
# with no attribute record at all -- placeholder people the save never filled in. Every staff
# member who HAS a record reads 1-20 on all eight.


def _decode_info(mm, base):
    """Decode one info record at `base` into the spine's identity dict."""
    year = int.from_bytes(mm[base + 22:base + 24], "little")
    day1 = int.from_bytes(mm[base + 20:base + 22], "little")
    try:
        dob = (date(year, 1, 1) + timedelta(days=day1)).isoformat()
    except ValueError:
        dob = None
    return {
        "tid": int.from_bytes(mm[base:base + 4], "little"),
        "uid": int.from_bytes(mm[base + 4:base + 8], "little"),
        "first_name_id": int.from_bytes(mm[base + 8:base + 12], "little"),
        "last_name_id": int.from_bytes(mm[base + 12:base + 16], "little"),
        "dob": dob,
        "nationality_id": int.from_bytes(mm[base + 24:base + 26], "little"),
        "flag28": mm[base + 28],
        "club_tid": int.from_bytes(mm[base + 42:base + 44], "little"),
        "sid": mm[base + 60:base + 64].hex(),
        # The info record carries TWO link fields, not one. `sid` (+60) points at the PLAYER
        # attribute record and is ffffffff for staff; `id2` (+64) points at the STAFF
        # attribute record, which holds coaching ability and the formation triple. It was
        # carried in the docs as an "unexplained u32" until 2026-09. See fmparser/staff.py.
        "id2": int.from_bytes(mm[base + 64:base + 68], "little"),
        # International record. Both are u8 in FMM22, NOT the u16 pair People.cs declares for
        # FMM26: Latal reads 47 caps / 1 goal as bytes, matching his screenshot, where a u16
        # at +38 would make it 303 caps. Verified exact on all 7 managers.
        #
        # 255 is a SENTINEL, not a value: 77 records carry 255 in BOTH fields and they are the
        # same 77, with nothing at all between 200 and 254. The real ceiling is ~200 caps, so a
        # 255 is "unknown", and storing it would invent a striker with 255 international goals.
        "international_caps": None if mm[base + 38] == 255 else mm[base + 38],
        "international_goals": None if mm[base + 39] == 255 else mm[base + 39],
        **{name: mm[base + 52 + i] for i, name in enumerate(PERSONALITY)},
    }


def _scrape_nicknamed(mm, found):
    """The info records `scrape_players`' FFFFFFFF sweep structurally cannot see.

    Anchoring on FFFFFFFF finds the nickname field only when it is EMPTY, so every player
    who HAS a nickname was invisible to the whole player decode — no name, no attributes,
    no squad membership, no ratings. On a real save that is ~2,100 records, heavily
    concentrated in the nickname-using nations: Brøndby's Carlos Polo ("Peque Polo") and
    Waldo Rubio ("Waldo") both started against us and neither existed in our data.

    There is no anchor byte to search for here and the records are variable length
    (91-107 bytes, no alignment), so we sweep the 58 possible DOB-year u16 values instead
    — each an `mm.find` at C speed — and validate hard. `found` is the FFFFFFFF sweep's
    result, which supplies the strongest validator we have: the set of club ids already
    known to be real. A false positive would need a plausible tid, a plausible day-of-year,
    a real club id AND a pair of name ids that resolve to actual names.
    """
    clubs = {p["club_tid"] for p in found.values()} - {NO_CLUB}
    # Every one of the 30,798 records the FFFFFFFF sweep finds resolves to a name, so
    # "resolves" is a sound invariant to filter on. Degrade gracefully if the name tables
    # aren't discoverable rather than dropping every candidate.
    try:
        resolves = R.build_name_resolver(mm)
    except Exception:
        resolves = False

    out = {}
    end = len(mm)
    for year in range(DOB_YEAR_LO, DOB_YEAR_HI + 1):
        pat = year.to_bytes(2, "little")
        p = 0
        while True:
            k = mm.find(pat, p)
            if k == -1:
                break
            p = k + 1
            base = k - 22                   # the year u16 sits at +22
            if base < 0 or base + 64 > end:
                continue
            if mm[base + 16:base + 20] == NO_NICKNAME:
                continue                    # the FFFFFFFF sweep already had its chance
            tid = int.from_bytes(mm[base:base + 4], "little")
            if not (100 < tid < 70000) or tid in found or tid in out:
                continue
            if int.from_bytes(mm[base + 20:base + 22], "little") > 366:
                continue                    # day-of-year
            club = int.from_bytes(mm[base + 42:base + 44], "little")
            if club != NO_CLUB and club not in clubs:
                continue
            rec = _decode_info(mm, base)
            nick = int.from_bytes(mm[base + 16:base + 20], "little")
            if max(rec["first_name_id"], rec["last_name_id"], nick) >= NAME_ID_MAX:
                continue
            if resolves and R.resolve_name(
                    mm, rec["first_name_id"], rec["last_name_id"]) is None:
                continue
            out[tid] = rec
    return out


def scrape_players(mm):
    """The identity spine: {tid: info dict}, in two sweeps.

    1. Records with NO nickname, found by searching for the FFFFFFFF sentinel that sits in
       the nickname field at +16 (then a plausible DOB year and tid). Fast, and it covers
       ~94% of the database.
    2. Records WITH a nickname, which sweep 1 cannot see by construction — see
       `_scrape_nicknamed`. Sweep 1's results are passed in and always win a tid clash, so
       this only ever ADDS to the spine.
    """
    players = {}
    i = 0
    while True:
        j = mm.find(NO_NICKNAME, i)
        if j == -1:
            break
        i = j + 1
        base = j - 16                       # the FFFFFFFF is the nickname field at +16
        if base < 0:
            continue
        year = int.from_bytes(mm[base + 22:base + 24], "little")
        if not (DOB_YEAR_LO <= year <= DOB_YEAR_HI):
            continue
        tid = int.from_bytes(mm[base:base + 4], "little")
        if not (100 < tid < 70000) or tid in players:
            continue
        # Day-of-year sanity, which _scrape_nicknamed has always applied and this sweep
        # never did. It only started to matter when the DOB ceiling was raised: a junk
        # record carrying a plausible year and a day-of-year of ~61,000 rolls forward into
        # a DOB of 2199 and was admitted to the spine ('Rajagobal Rajagobal', 2-5 per save).
        # The two sweeps validate the same field the same way now.
        if int.from_bytes(mm[base + 20:base + 22], "little") > 366:
            continue
        players[tid] = _decode_info(mm, base)

    players.update(_scrape_nicknamed(mm, players))
    return players


def scrape_contract_status(mm, info, lo=None, hi=None):
    """{tid: squad_status_code} from the contract records. Each record is keyed by
    [TID:u32][UID:u32]; a 0x0087 marker sits at TID+37 and the status byte at TID+39.

    SCANS THE WHOLE FILE by default. It used to scan a 54-58 MB window (regions.py),
    which was measured on Bucaspor and is simply the wrong place on Frem — the section runs
    ~50-60 MB there, so the window opened ~4 MB after it started and threw away everything
    before that. Measured cost of the constant: frem-2021-07-01 and frem-2023-07-01 found
    ZERO of ~25,500 records (squad_status entirely NULL for those snapshots), the later Frem
    saves 39-57%, and Bucaspor — the career it was tuned on — a flawless 100%.

    No window is needed because the validation is already far stronger than a byte range:
    every hit must match BOTH the tid and the uid from the info spine, 8 exact bytes. Across
    the whole file that yields 25,687 records on frem-2026 with no tid disagreeing on status.
    `lo`/`hi` are kept for callers that want to restrict the scan.
    """
    lo = 0 if lo is None else lo
    hi = len(mm) if hi is None else hi
    uid_of = {tid: p["uid"] for tid, p in info.items()}
    out = {}
    p = lo
    while True:
        m = mm.find(b"\x87\x00", p, hi)
        if m == -1:
            break
        p = m + 1
        if m - 37 < 0:
            continue
        tid = int.from_bytes(mm[m - 37:m - 33], "little")
        if uid_of.get(tid) == int.from_bytes(mm[m - 33:m - 29], "little"):
            out[tid] = mm[m + 2]                # status is a u8 at TID+39
    return out


def scrape_contracts(mm, info, lo=CONTRACTREC_LO, hi=CONTRACTREC_HI):
    """{tid: {wage_units, wage_gbp, expiry, expiry_year}} from the contract DETAIL records.

    Record layout (anchored on the player TID): `[tid u32][0x01 marker][wage u16][6×00]
    [expiry day-of-year u16][expiry year u16]`. Wage £/yr = units × WAGE_GBP_PER_UNIT
    (validated £15.5K–£17.75M, ±2%). Expiry is a full date in the same day-of-year+year
    encoding as DOB. We scan the section and keep every hit whose TID is in the info spine
    (collision-safe), first record per tid wins."""
    out = {}
    # -17, not 0: the record body reads as far as p+16 (expiry year at +15..+17), so a bare
    # `p < len(mm)` walks off the end and raises IndexError. Harmless while hi defaulted to
    # 40M, but scrape_contract_status now scans to EOF and this is the same family of scan.
    end = min(hi, len(mm) - 17)
    p = lo
    while p < end:
        if mm[p + 4] == 0x01:
            yr = int.from_bytes(mm[p + 15:p + 17], "little")
            if 2018 <= yr <= 2035:
                tid = int.from_bytes(mm[p:p + 4], "little")
                if tid in info and tid not in out:
                    units = int.from_bytes(mm[p + 5:p + 7], "little")
                    day = int.from_bytes(mm[p + 13:p + 15], "little")
                    try:
                        expiry = (date(yr, 1, 1) + timedelta(days=day)).isoformat()
                    except ValueError:
                        expiry = None
                    out[tid] = {
                        "wage_units": units,
                        "wage_gbp": units * WAGE_GBP_PER_UNIT,
                        "expiry": expiry,
                        "expiry_year": yr,
                    }
        p += 1
    return out


def scrape_attributes(mm, lo=ATTR_LO, hi=ATTR_HI):
    """Every global attribute record in [lo, hi), keyed by its embedded SID.

    Records sit on a 78-byte grid; we scan for a structurally valid record (15 valid
    positions + feet + 0<CA<=PA<=200), read the SID at P-42, and skip ahead. First
    SID wins (records are 1:1 with SID)."""
    out = {}
    P = lo
    while P < hi:
        seg = mm[P:P + 15]
        if _valid_positions(seg):
            left, right = mm[P + 15], mm[P + 16]
            ca = int.from_bytes(mm[P + 17:P + 19], "little")
            pa = int.from_bytes(mm[P + 19:P + 21], "little")
            if 0 <= left <= 20 and 0 <= right <= 20 and 0 < ca <= pa <= 200:
                sid = mm[P - 42:P - 38].hex()
                rec = {
                    "sid": sid, "P": P,
                    "positions": {POSITIONS[k]: v for k, v in enumerate(seg) if v > 1},
                    "feet": {"left": left, "right": right},
                    "ca": ca, "pa": pa,
                    "reputation": int.from_bytes(mm[P + 21:P + 23], "little"),
                    "attributes": {n: mm[P + rel] for rel, n in ATTR_OFFSETS.items()},
                    **record_tail(mm, P),
                    **hidden_attributes(mm, P),
                }
                out.setdefault(sid, rec)
                P += 78
                continue
        P += 1
    return out
