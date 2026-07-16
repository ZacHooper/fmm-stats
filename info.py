#!/usr/bin/env python3
"""
Parse the player INFO FIELD (rough-guide Step 2), in the global player DB (~2.8 MB).

Confirmed layout (validated vs Demir/Duruk/Behram/Bıyık DOB + SID cross-check):
  +0  TID          u32
  +4  UID          u32
  +8  firstNameID  u32   (index into the global name DB — still-open to resolve)
  +12 lastNameID   u32
  +16 FFFFFFFF     nickname (FF = none)
  +20 DOB day-1    u16    (day-of-year minus 1)
  +22 DOB year     u16
  +24 nationality  u16    (173 = Turkey)
  +26 2nd nationality u16 (FFFF = none)
  +28 role flag    u8     (01 = player, 10 = manager)
  +42 club TID     u16
  +60 SID          u16    (== the match-stat block's SID -> links to per-match stats)

Still TODO (encoding not yet cracked): contract expiry date, transfer value.
Find the field: search the TID bytes, accept where mm[i+16:i+20] == FFFFFFFF.
"""
from datetime import date, timedelta
import struct
from fmtool import Save

NATIONS = {173: "Turkey"}  # extend as needed


def info_offset(mm, tid):
    """Find the info field: TID bytes, FFFFFFFF nickname at +16, AND a plausible
    DOB year at +22 (rejects false matches like a stray FFFFFFFF elsewhere)."""
    le = struct.pack("<I", tid)
    pos = 0
    while True:
        i = mm.find(le, pos)
        if i == -1:
            return None
        pos = i + 1
        if mm[i + 16:i + 20] == b"\xff\xff\xff\xff":
            year = int.from_bytes(mm[i + 22:i + 24], "little")
            if 1955 <= year <= 2012:          # plausible player birth year
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
        # +28 is NOT the role flag and NOT preferred foot (both disproven):
        #  - foot lives in the ATTRIBUTE record (rough guide Step 6: two 0-20
        #    bytes 'left,right' just before CA/PA), never in this info field.
        #  - Demir is "Left Only" in-game yet flag28=1, same as the right-footed
        #    Behram/Bıyık/Duruk -> flag28 does not encode foot.
        # Rough guide Step 2 shows an extra 'declared national team' u16 between
        # 2nd-nationality and the role flag, so +28 most likely = declared
        # national team (low byte). Left as raw `flag28` pending confirmation.
        "flag28": mm[i + 28],
        "club_tid": u16(42),
        "sid": mm[i + 60:i + 62].hex(),
    }


if __name__ == "__main__":
    import json
    s = Save()
    squad = json.load(open("bucaspor_players.json"))   # {tid: name}
    profiles = {}
    for tid_s, name in squad.items():
        info = parse_info(s.mm, int(tid_s))
        if info:
            info["name"] = name
            profiles[tid_s] = info
    json.dump(profiles, open("player_info.json", "w"), ensure_ascii=False, indent=1)
    print(f"{len(profiles)} player info records -> player_info.json\n")
    for tid_s, p in list(profiles.items())[:8]:
        print(f"  {p['name']:20} DOB {p['dob']}  {p['nationality']}  "
              f"club {p['club_tid']}  SID {p['sid']}")
