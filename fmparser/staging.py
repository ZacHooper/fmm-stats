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

from .attributes import _valid_positions, ATTR_OFFSETS, POSITIONS
from .regions import ATTR_LO, ATTR_HI, CONTRACT_LO, CONTRACT_HI

# free agents / unattached carry this sentinel club id
NO_CLUB = 65535

# squad-availability status byte in the contract record. 65 = out on loan / unavailable
# (validated against the managed club's squad vs an in-game screenshot); 112 = normal
# squad member. Other values are further squad statuses (undecoded).
LOAN_STATUS = 65


def scrape_players(mm):
    """The identity spine: {tid: info dict}. One sweep of the whole file for info
    records (TID, then FFFFFFFF nickname at +16, then a plausible DOB year)."""
    players = {}
    i = 0
    while True:
        j = mm.find(b"\xff\xff\xff\xff", i)
        if j == -1:
            break
        i = j + 1
        base = j - 16                       # the FFFFFFFF is the nickname field at +16
        if base < 0:
            continue
        year = int.from_bytes(mm[base + 22:base + 24], "little")
        if not (1955 <= year <= 2012):
            continue
        tid = int.from_bytes(mm[base:base + 4], "little")
        if not (100 < tid < 70000) or tid in players:
            continue
        day1 = int.from_bytes(mm[base + 20:base + 22], "little")
        try:
            dob = (date(year, 1, 1) + timedelta(days=day1)).isoformat()
        except ValueError:
            dob = None
        players[tid] = {
            "tid": tid,
            "uid": int.from_bytes(mm[base + 4:base + 8], "little"),
            "first_name_id": int.from_bytes(mm[base + 8:base + 12], "little"),
            "last_name_id": int.from_bytes(mm[base + 12:base + 16], "little"),
            "dob": dob,
            "nationality_id": int.from_bytes(mm[base + 24:base + 26], "little"),
            "flag28": mm[base + 28],
            "club_tid": int.from_bytes(mm[base + 42:base + 44], "little"),
            "sid": mm[base + 60:base + 64].hex(),
        }
    return players


def scrape_contract_status(mm, info, lo=CONTRACT_LO, hi=CONTRACT_HI):
    """{tid: squad_status_code} from the contract records (~55-57 MB). Each record is
    keyed by [TID:u32][UID:u32]; a 0x0087 marker sits at TID+37 and the status byte at
    TID+39. Every hit is validated against the info spine (TID+UID must match), so there
    are no false positives. See LOAN_STATUS (65 = out on loan / unavailable)."""
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
                }
                out.setdefault(sid, rec)
                P += 78
                continue
        P += 1
    return out
