#!/usr/bin/env python3
"""Discover the managed club in an FMM save — to add a new career to fmparser/careers.py.

    python3 scripts/discover_career.py path/to/new-save.fms

FMM saves open (byte 0) with "<date> - <Manager> (<Nickname>)", and the managed
club's squad is written season by season into the player-list table's club lists
(`fmparser/tables/player_lists.py`, lists 31-61), each scrapbook entry naming the club that holds
the player. So we print the header nickname, then rank the clubs those lists name by how many
distinct players each holds: the managed first team and its reserves are the only clubs
there. Match against the nickname, then add the tids to careers.py and extract with
`--career <key>`.
"""
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fmparser.save import Save          # noqa: E402
from fmparser.tables.player_lists import CLUB_LISTS, NO_CLUB, scrape_player_lists  # noqa: E402
from fmparser import clubs_comps as R       # noqa: E402
from fmparser.tables.save_header import read_save_header  # noqa: E402


def header_nickname(mm):
    head = read_save_header(mm)
    return head["title"], head["nickname"]


def discover(path):
    s = Save(path)
    mm = s.mm
    head, nick = header_nickname(path and mm)
    print(f"save header : {head!r}")
    print(f"nickname    : {nick!r}\n")

    club_players = defaultdict(set)      # clubtid -> {player_tid}
    for lst in scrape_player_lists(mm):
        if lst["index"] not in CLUB_LISTS:
            continue
        for e in lst["entries"]:
            club = e["loan_club_tid"] if e["loan_club_tid"] != NO_CLUB else e["club_tid"]
            club_players[club].add(e["player_tid"])

    ranked = sorted(club_players.items(), key=lambda kv: len(kv[1]), reverse=True)
    print(f"{'players':>7} {'tid':>6}  club")
    for clubtid, players in ranked[:12]:
        name = R.resolve_club(mm, clubtid, "long") or "?"
        flag = "  <-- matches nickname" if nick and nick.lower() in name.lower() else ""
        print(f"{len(players):>7} {clubtid:>6}  {name}{flag}")
    print("\nAdd the managed first team (and its Reserves tid) to fmparser/careers.py.")
    s.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python3 scripts/discover_career.py <save.fms>")
    discover(sys.argv[1])
