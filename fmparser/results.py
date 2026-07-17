#!/usr/bin/env python3
"""
Match RESULTS sweep -> competition membership.

Played matches are stored (near each managed region, but present for all loaded
leagues) as `[FF x8 delimiter][teamA:u16][teamB:u16][comp CID:u16] ...`. Sweeping the
whole file and grouping the two teams by CID gives, per competition, the set of clubs
that played in it. For LEAGUE competitions that set is the league's membership.

Decoded with ground truth: our 34 league fixtures land here and comp 228 resolves to
exactly its 18 clubs. CID is the same u16 used by reference.comp_detail, so it joins
straight to the competition table.
"""
from collections import defaultdict

DELIM = b"\xff" * 8


def memberships(mm, valid_clubs, lo=0, hi=None):
    """{comp_cid: set(club_tid)} from the results records. `valid_clubs` gates false
    positives (the FFx8 delimiter is common); both teams must be known clubs."""
    hi = hi or len(mm)
    mem = defaultdict(set)
    p = lo
    while True:
        i = mm.find(DELIM, p, hi)
        if i == -1:
            break
        p = i + 1
        a = int.from_bytes(mm[i + 8:i + 10], "little")
        b = int.from_bytes(mm[i + 10:i + 12], "little")
        cid = int.from_bytes(mm[i + 12:i + 14], "little")
        if a != b and 0 < cid < 20000 and a in valid_clubs and b in valid_clubs:
            mem[cid].add(a)
            mem[cid].add(b)
    return mem
