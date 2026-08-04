#!/usr/bin/env python3
"""Discover the managed club in an FMM save — to add a new career to fmparser/careers.py.

    python3 scripts/discover_career.py path/to/new-save.fms

FMM saves open (byte 0) with "<date> - <Manager> (<Nickname>)", and the managed
squad is written as records ending in a club marker (clubtid u16 + ff ff) preceded
by real player names. So we print the header nickname, then rank clubs by how many
DISTINCT named players sit behind their marker. The managed first team ranks at/near
the top; its reserves usually show up too. Match against the nickname, then add the
tids to careers.py and extract with `--career <key>`.

Note: some famous clubs (e.g. Real Madrid) also carry named star players, so don't
trust the raw top row blindly — use the nickname match + a plausible squad size.
"""
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fmparser.save import Save          # noqa: E402
from fmparser import attributes as A     # noqa: E402
from fmparser import reference as R       # noqa: E402


def header_nickname(mm):
    head = mm[:128].split(b"\x00")[0].decode("latin-1", "replace")
    m = re.search(r"\(([^)]+)\)", head)
    return head, (m.group(1) if m else None)


def discover(path):
    s = Save(path)
    mm = s.mm
    head, nick = header_nickname(path and mm)
    print(f"save header : {head!r}")
    print(f"nickname    : {nick!r}\n")

    club_players = defaultdict(set)      # clubtid -> {player_tid}
    club_pos = defaultdict(list)         # clubtid -> [offsets], for the cluster span
    ff = b"\xff\xff"
    pos = 0
    while True:
        p = mm.find(ff, pos)
        if p == -1:
            break
        pos = p + 1
        j = p - 2                        # marker start: [clubtid u16][ff ff]
        if j < 8:
            continue
        clubtid = int.from_bytes(mm[j:j + 2], "little")
        if not (100 < clubtid < 65000):  # allow small (lower-league) tids
            continue
        ptid = int.from_bytes(mm[j - 8:j - 4], "little")
        if not (1000 < ptid < 70000):    # cheap prune before the name scan
            continue
        if A._name_before(mm, j):
            club_players[clubtid].add(ptid)
            club_pos[clubtid].append(j)

    ranked = sorted(club_players.items(), key=lambda kv: len(kv[1]), reverse=True)
    print(f"{'players':>7} {'span_kb':>7} {'tid':>6}  club")
    for clubtid, players in ranked[:12]:
        offs = club_pos[clubtid]
        span = (max(offs) - min(offs)) / 1000
        name = R.resolve_club(mm, clubtid, "long") or "?"
        flag = "  <-- matches nickname" if nick and nick.lower() in name.lower() else ""
        print(f"{len(players):>7} {span:>7.0f} {clubtid:>6}  {name}{flag}")
    print("\nAdd the managed first team (and its Reserves tid) to fmparser/careers.py.")
    s.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python3 scripts/discover_career.py <save.fms>")
    discover(sys.argv[1])
