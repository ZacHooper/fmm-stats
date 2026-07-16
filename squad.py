#!/usr/bin/env python3
"""
Own-club player TID -> full name, from the squad-snapshot region (~62-63 MB).

This resolves *our* players without needing the (still-open) global name index:
each Bucaspor squad-snapshot record stores the player's full name inline, and the
player TID appears later in the record, 8 bytes before the club marker `a7 19 ff ff`.
Record shape (per player):
  [len]full name [len]first [len]last 0000 [len]display [len]"Bucaspor 1928" ...
  ... attributes ... positions ... <playerTID:u32><4 bytes> a7 19 ff ff ...
"""
import re
from fmtool import Save

SNAPSHOT_LO, SNAPSHOT_HI = 62_300_000, 63_200_000
CLUB_MARKER = b"\xa7\x19\xff\xff"          # Bucaspor club TID + ff ff, ends each record's id block
_NAME_LEN = re.compile(rb"([\x03-\x20])\x00\x00\x00")
# leading class allows Turkish uppercase initials (Ç Ğ İ Ö Ş Ü, in À-ſ) — otherwise
# players like "Şener Özcan" are skipped and fall through to the club name.
_FULLNAME = re.compile(r"[A-ZÀ-ſ][\w'. À-ſ-]{2,}$")


def own_squad(mm, lo=SNAPSHOT_LO, hi=SNAPSHOT_HI):
    """Return {player_tid: full_name} for the managed club's squad."""
    out = {}
    pos = lo
    while True:
        i = mm.find(CLUB_MARKER, pos)
        if i == -1 or i > hi:
            break
        pos = i + 1
        tid = int.from_bytes(mm[i - 8:i - 4], "little")
        if not (1000 < tid < 70000):
            continue
        win = mm[i - 280:i]                # the record body precedes the marker
        for m in _NAME_LEN.finditer(win):  # first length-prefixed "First Last" = full name
            L = m.group(1)[0]
            s = m.end()
            cand = win[s:s + L]
            if len(cand) != L:
                continue
            try:
                txt = cand.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if " " in txt and _FULLNAME.match(txt) and not any(c.isdigit() for c in txt):
                out.setdefault(tid, txt)
                break
    return out


if __name__ == "__main__":
    import json
    s = Save()
    squad = own_squad(s.mm)
    for tid in sorted(squad):
        print(f"  {tid:>6}  {squad[tid]}")
    json.dump({str(k): v for k, v in squad.items()},
              open("bucaspor_players.json", "w"), ensure_ascii=False, indent=1)
    print(f"\n{len(squad)} players -> bucaspor_players.json")
