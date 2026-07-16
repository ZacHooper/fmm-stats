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
import struct

# ---- career config (stable across the career) ----
MANAGED_CLUB_TID = 6567       # Bucaspor 1928 (first team)
MANAGED_RESERVE_TID = 11320   # Bucaspor reserves (AI-run)
# competitions the FIRST team contests (league + play-off + cup); excludes the
# reserve league (1370) and friendlies (65). Used to pick the league player set.
LEAGUE_COMP_IDS = (228, 227, 117)

# club marker = managed club TID (u16, little-endian) + ff ff, e.g. a7 19 ff ff.
CLUB_MARKER = struct.pack("<H", MANAGED_CLUB_TID) + b"\xff\xff"

# per-match delimiter cluster (same in every FMM22 save)
DELIM_UNIT = bytes.fromhex("21225515" + "0a000000")

# ---- region windows (generous; validated per-record on read) ----
# global attribute records (keyed by SID, fixed 78-byte grid)
ATTR_LO, ATTR_HI = 3_800_000, 6_600_000
# managed squad snapshot (full names + attributes + feet, before the club marker)
SNAPSHOT_LO, SNAPSHOT_HI = 62_300_000, 63_200_000
# per-match stat region (home XI then away XI, delimiter-clustered)
MATCH_LO = 55_000_000
