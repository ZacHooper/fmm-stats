#!/usr/bin/env python3
"""The person name resolver and `info_offset`.

Clubs and competitions are read from their own tables, `tables/clubs.py` and
`tables/competitions.py`.
"""
import struct

from .core import primitives as P
from .save import cache_key as _cache_key

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


from .tables.names import (
    FIRST_NAMES_TABLE,
    NICKNAMES_TABLE,
    SURNAMES_TABLE,
    chain_id_tables as _chain_id_tables,
    discover_id_tables as _discover_id_tables,
    locate_name_tables as _locate_name_tables,
    walk_browse as _walk_browse,
    walk_browse_bounds as _walk_browse_bounds,
)


_NAME_TABLES = {}   # _cache_key -> {"first": [...], "last": [...], "common": [...] or None}


def build_name_resolver(mm, validate=None):
    """Read the name tables for `mm` once and cache, per table, each name id's string (the
    list index is the id). False if there are fewer than two (surnames and first names are
    both needed for a name)."""
    tabs = _locate_name_tables(mm)
    browse = _walk_browse(mm)

    def strings(table):
        out = []
        for row in table.scrape(mm):
            k = row["ordinal"]
            out.append(browse[k] if 0 <= k < len(browse) else None)
        return out

    _NAME_TABLES[_cache_key(mm)] = {
        "first": strings(FIRST_NAMES_TABLE) if "first_names" in tabs else None,
        "last": strings(SURNAMES_TABLE) if "surnames" in tabs else None,
        "common": strings(NICKNAMES_TABLE) if "nicknames" in tabs else None,
    }
    return len(tabs) >= 2


def _browse_name(names, name_id):
    """The string for a name id, or None."""
    if names is None or name_id is None or not 0 <= name_id < len(names):
        return None
    return names[name_id]


def resolve_common_name(mm, common_name_id):
    """The name the game DISPLAYS, when a person has one, else None.

    `common_name_id` is `staging.INFO_LAYOUT` +16 (People.cs `CommonNameId`), 0xFFFFFFFF when
    unset. It indexes the third id-table (nicknames), not either name table. Set on 2,424 of
    32,760 people (7.4%) on frem-2023-07-02, and all 2,424 resolve.

    This is a DISPLAY name and often not a shortening of the legal one at all -- 'Tite' for
    Adenor Leonardo Bachi, 'Renato Gaucho' for Renato Portaluppi, 'Michel' for Jose Miguel
    Gonzalez Martin del Campo -- so it cannot be derived from the first/last ids and has to
    come from the table.
    """
    t = _NAME_TABLES.get(_cache_key(mm))
    if not t or common_name_id == P.NO_ID32:
        return None
    return _browse_name(t["common"], common_name_id)


def resolve_name(mm, first_name_id, last_name_id):
    """Full 'First Last' for any player from their info-field name ids, or None. Call
    build_name_resolver(mm) once first (cached per mmap)."""
    t = _NAME_TABLES.get(_cache_key(mm))
    if not t:
        return None
    first = _browse_name(t["first"], first_name_id)
    last = _browse_name(t["last"], last_name_id)
    if first is None or last is None:
        return None
    return f"{first} {last}"
