#!/usr/bin/env python3
"""Discover the managed club in an FMM save — to add a new career to fmm.toml.

    uv run python scripts/discover_career.py path/to/new-save.fms [--write]

FMM saves open (byte 0) with "<date> - <Manager> (<Nickname>)", and the managed
club's squad is written season by season into the player-list table's club lists
(`fmparser/tables/player_lists.py`, lists 31-61), each scrapbook entry naming the club that holds
the player. So we print the header nickname, then rank the clubs those lists name by how many
distinct players each holds: the managed first team and its reserves are the only clubs
there. It prints a ready-made [careers.<key>] table for fmm.toml; `--write` adds it (and
creates fmm.toml if there is none). Then extract, and load with
`load_duckdb.py --career <key>`.
"""
import os
import re
import sys
import tomllib
import unicodedata
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fmparser.save import Save          # noqa: E402
from fmparser.tables.player_lists import CLUB_LISTS, NO_CLUB, scrape_player_lists  # noqa: E402
from fmparser.tables.clubs import scrape_clubs  # noqa: E402
from fmparser.tables.save_header import read_save_header  # noqa: E402


def header_nickname(mm):
    head = read_save_header(mm)
    return head["title"], head["nickname"]


def career_key(nick):
    """'Boldklubben Frem' -> 'boldklubben-frem'; an ASCII slug safe as a TOML key and file name."""
    s = unicodedata.normalize("NFKD", nick or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "mycareer"


def career_block(key, name, managed, reserve):
    lines = [f"[careers.{key}]", f'name = "{name}"', f"managed_tid = {managed}"]
    if reserve is not None:
        lines.append(f"reserve_tid = {reserve}")
    lines += ["# The day this country's new season starts, as [month, day]. 30 June suits most",
              "# European leagues; change it if your league's season turns over on another day.",
              "rollover = [6, 30]",
              'rating_method = "frem_minmax_4231"   # the role-weight set (seeds/role_weights.csv)']
    return "\n".join(lines) + "\n"


def write_config(path, key, block):
    """Add the career to fmm.toml, creating it if needed. Refuses to touch a career already there."""
    if os.path.exists(path):
        with open(path, "rb") as f:
            cfg = tomllib.load(f)
        if key in cfg.get("careers", {}):
            sys.exit(f"{path} already has a [careers.{key}] table; edit it by hand.")
        text = open(path, encoding="utf-8").read()
        if not text.endswith("\n"):
            text += "\n"
        text += "\n" + block
        if "default" not in cfg.get("careers", {}):
            print(f"  note: {path} names no default career; pass --career {key} to the loader.")
    else:
        text = ("# Your settings (gitignored). Every option is explained in fmm.example.toml.\n\n"
                f'[careers]\ndefault = "{key}"\n\n' + block)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"wrote [careers.{key}] to {path}")


def discover(path, write=False):
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
    clubs = scrape_clubs(mm)
    print(f"{'players':>7} {'tid':>6}  club")
    for clubtid, players in ranked[:12]:
        name = (clubs.get(clubtid) or {}).get("name") or "?"
        flag = "  <-- matches nickname" if nick and nick.lower() in name.lower() else ""
        print(f"{len(players):>7} {clubtid:>6}  {name}{flag}")
    s.close()

    named = [(t, (clubs.get(t) or {}).get("name") or "?") for t, _ in ranked[:12]]
    named = [(t, n) for t, n in named if nick and nick.lower() in n.lower()]
    if not named:
        print("\nNo club matches the save's nickname: pick your first team (and its reserves) "
              "from the list and add a [careers.<key>] table to fmm.toml by hand.")
        return 1
    (managed, name), rest = named[0], named[1:]
    reserve = next((t for t, n in rest if "reserve" in n.lower()), rest[0][0] if rest else None)
    key = career_key(nick)
    block = career_block(key, name, managed, reserve)
    print("\nSuggested fmm.toml career (check the first team and reserves above):\n")
    print(block)
    if write:
        import fmconfig
        write_config(fmconfig.config_path(), key, block)
    else:
        print("Add it with:  uv run python scripts/discover_career.py <save.fms> --write")
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--write"]
    if len(args) != 1:
        sys.exit("usage: uv run python scripts/discover_career.py <save.fms> [--write]")
    sys.exit(discover(args[0], write="--write" in sys.argv[1:]))
