#!/usr/bin/env python3
"""
Where the data lives in the save, and the managed-career config.

Scope: this parser targets ONE career (Bucaspor) pulled at different points in a
season. Two kinds of constant live here:

  * CAREER CONFIG — stable across the whole career (managed club TID, its
    competition IDs). These do NOT change as the save grows; only a *different*
    career would change them.

  * REGION WINDOWS — byte ranges where the three big structures sit. These DO
    drift as the save file grows over a season, so they are deliberately generous
    and every record is validated on read (grid phase, value ranges, name shape).
    If a future save moves data outside these windows, widen them here — the
    ground-truth test (tests/) will flag it.
"""
from .careers import resolve_career

# ---- default managed career ----
# Which club you manage now lives in careers.py, so multiple careers share this
# parser; pick one per run with `extract.py --career <key>`. The names below are the
# DEFAULT career (Bucaspor) for callers that don't pass one explicitly — every hot
# path threads the actual club marker through instead (see attributes.py).
_DEFAULT = resolve_career()
MANAGED_CLUB_TID = _DEFAULT.managed_tid       # Bucaspor 1928 (first team)
MANAGED_RESERVE_TID = _DEFAULT.reserve_tid    # Bucaspor reserves (AI-run)
LEAGUE_COMP_IDS = _DEFAULT.league_comps
CLUB_MARKER = _DEFAULT.club_marker            # managed club TID (u16 LE) + ff ff

# per-match delimiter cluster (same in every FMM22 save)
DELIM_UNIT = bytes.fromhex("21225515" + "0a000000")

# ---- region windows (generous; validated per-record on read) ----
# global attribute records (keyed by SID, fixed 78-byte grid)
ATTR_LO, ATTR_HI = 3_800_000, 6_600_000
# managed squad snapshot (full names + attributes + feet, before the club marker)
SNAPSHOT_LO, SNAPSHOT_HI = 62_300_000, 63_200_000
# per-match stat region (home XI then away XI, delimiter-clustered)
MATCH_LO = 55_000_000
# light results (simulated non-managed games): [home][away][sH][sA]..[flags 0x40xx].[cid]
LIGHT_LO, LIGHT_HI = 47_000_000, 50_500_000
# player contract records ([TID][UID]..0x0087 marker..status byte); keyed by TID+UID
CONTRACT_LO, CONTRACT_HI = 54_000_000, 58_000_000
