#!/usr/bin/env python3
"""
Reader for the save's self-describing TAGGED region (~13-20MB): competitions,
finances, staff, history, fixtures metadata.

Format: each field is `[tag: 4 bytes, stored REVERSED][0x01 marker][typecode][value]`.
Typecodes seen so far: 0x01/0x0a/0x0b = u32, 0x11 = u8, 0x12 = u16. Tags read
(reversed) include comp, level, Group, cash/przm (prize money), valu, curr, year,
type, id, team, ntms (num teams). See docs/BUGS.md #13.

Only a slice is decoded here (what we need now). The bulk player/attribute/match data
is NOT in this region — it stays in the packed structures parsed elsewhere.
"""
TAGGED_LO, TAGGED_HI = 13_000_000, 20_000_000

# on-disk tag bytes (the field name reversed)
_TAG_COMP = b"pmoc"   # "comp"
_TAG_NTMS = b"smtn"   # "ntms" (number of teams)


def league_team_counts(mm, lo=TAGGED_LO, hi=TAGGED_HI):
    """{comp_uid: num_teams} from the per-league records `[comp:u32][ntms:u8]`.
    These records exist only for LOADED leagues (~90), so this doubles as the list
    of leagues that have real club membership."""
    out = {}
    p = lo
    while True:
        i = mm.find(_TAG_COMP, p, hi)
        if i == -1:
            break
        p = i + 1
        if mm[i + 4] == 0x01 and mm[i + 5] == 0x01:      # comp field, u32
            uid = int.from_bytes(mm[i + 6:i + 10], "little")
            j = i + 10
            if mm[j:j + 4] == _TAG_NTMS and mm[j + 4] == 0x01 and mm[j + 5] == 0x11:
                out[uid] = mm[j + 6]
    return out
