#!/usr/bin/env python3
"""`info_offset`: a player's info record by tid.

Clubs and competitions are read from their own tables, `tables/clubs.py` and
`tables/competitions.py`; names from `tables/names.py`.
"""
import struct


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


# `parse_info` lived here and was DEAD -- nothing in the repo called it (the two `archive/`
# scripts that import `parse_info` import it from a top-level `info` module that no longer
# exists, so they are already broken and not evidence of use). It is deleted rather than
# migrated, which retires two real bugs at zero risk: it read `sid` as 2 bytes where
# `staging.INFO_LAYOUT` says 4 and every other reader agrees, and it carried a `1955..2012`
# DOB gate that `DOB_YEAR_HI = 2030` superseded in the live path.
#
# Its live sibling `info_offset` above still carries that same 1955..2012 gate. That one is a
# REAL open bug, but a locating one: widening it changes which records are found, so it needs
# a measured before/after count and does not belong in a migration commit.
