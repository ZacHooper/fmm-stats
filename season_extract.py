#!/usr/bin/env python3
"""
Season-wide match extractor for FMM22 saves.

Structure (reverse-engineered, validated on Karacabey 3-3 Bucaspor):
  - The match-stats region (~56 MB) holds ~75 matches.
  - Each match begins with a DELIMITER cluster: repeated `?2 22 55 15 0a 00 00 00`.
  - Then a HEADER containing (among tactics/team-stats):
        [homeTID:u16][awayTID:u16][day:u16][year:u16 == 0x07xx][attendance:u16]
    preceded by an EVENT list of goals/cards: `.. [minute:u16] .. [playerTID:u32] ff..`
  - Then the HOME XI stat blocks, then the AWAY XI stat blocks
    (54-byte blocks, 8-byte 0xFF delimiter, stride 62; posOrder resets to 1 per team).

Usage:
  python3 season_extract.py            # season summary table (all matches)
  python3 season_extract.py <anchor>   # full per-player detail for one match
"""
import struct
from fmtool import Save
from parse_match import is_block_start, decode_block, BLOCK, STRIDE

DELIM_UNIT = bytes.fromhex("21225515" + "0a000000")


def match_anchors(mm, lo=55_000_000, hi=None):
    """Delimiter clusters -> one anchor offset per match."""
    hi = hi or len(mm)
    hits = []
    pos = lo
    while True:
        i = mm.find(DELIM_UNIT, pos)
        if i == -1 or i > hi:
            break
        hits.append(i)
        pos = i + 8
    clusters, cur = [], [hits[0]]
    for h in hits[1:]:
        if h - cur[-1] <= 16:
            cur.append(h)
        else:
            clusters.append(cur)
            cur = [h]
    clusters.append(cur)
    return [c[0] for c in clusters]


def parse_header(mm, anchor, window=1500):
    """Find [homeTID][awayTID][day][year][att] by scanning for a plausible year word."""
    end = anchor + window
    for i in range(anchor, end):
        year = int.from_bytes(mm[i:i + 2], "little")
        if 2018 <= year <= 2030:
            day = int.from_bytes(mm[i - 2:i], "little")
            if not (0 <= day <= 366):
                continue
            home = int.from_bytes(mm[i - 6:i - 4], "little")
            away = int.from_bytes(mm[i - 4:i - 2], "little")
            att = int.from_bytes(mm[i + 2:i + 4], "little")
            # sanity: TIDs plausible, attendance plausible
            if 0 < home < 65000 and 0 < away < 65000 and att < 60000:
                return {"home_tid": home, "away_tid": away, "day": day,
                        "year": year, "att": att, "date_off": i - 6}
    return None


# Event unit = [b0][b1=TYPE][min:u16][b4][playerTID:u32][ff ff].
# b1 = event type (confirmed vs in-game); b0 = modifier (for goals, how-scored/assist).
# Plain yellow cards are NOT logged in this stream (only major events).
EVENT_TYPE = {
    0x01: "goal",
    0x02: "own_goal",
    0x03: "penalty",          # scored
    0x04: "missed_penalty",   # confirmed (incl. defenders forced to take when no taker set)
    0x05: "red_card",         # confirmed (Mar-5)
    0x06: "injury",
    0x29: "disallowed_goal",  # offside; confirmed (Apr-2)
}
GOAL_TYPES = {0x01, 0x02, 0x03}  # b1 values that count towards the score


def parse_events(mm, hdr_off, player_tids, back=380):
    """Scan the region before the header for match events.
    Event unit: [b0][b1=type][min:u16][b4][playerTID:u32][ff ff ...].
    A TID is accepted only if it belongs to the match (robust vs numeric range)."""
    events = []
    lo = max(0, hdr_off - back)
    i = lo
    while i < hdr_off - 6:
        # tid sits 5 bytes into the unit, followed by ff ff
        tid = int.from_bytes(mm[i + 5:i + 9], "little")
        if tid in player_tids and mm[i + 9] == 0xff and mm[i + 10] == 0xff:
            b0, b1 = mm[i], mm[i + 1]
            # minute is a u16, but stoppage time is packed: low byte = base minute
            # (0-based -> +1), high byte = added minutes. e.g. 59 03 -> 90+3 (not 858).
            base = mm[i + 2] + 1
            added = mm[i + 3]
            disp = f"{base}+{added}" if added else str(base)
            events.append({"min": base, "added": added, "min_display": disp,
                           "tid": tid, "type_byte": b1,
                           "type": EVENT_TYPE.get(b1, f"?{b1:02x}"), "b0": b0})
            i += 9
        else:
            i += 1
    out = []
    for e in events:
        if not out or out[-1] != e:
            out.append(e)
    return out


def looks_like_block(mm, i):
    """Tolerant block check for walking a locked-on stride (subs/scorers can
    fail the strict start heuristic): condition in range + plausible TID."""
    if i + BLOCK > len(mm):
        return False
    tid = int.from_bytes(mm[i + 42:i + 46], "little")
    return 1 <= mm[i + 3] <= 100 and 1 <= mm[i + 41] <= 30 and 0 < tid < 200000


MIN_XI = 7  # a real XI run has 11 starters (+ subs); lone false-positives are 1-2


def _walk_run(mm, i, hi):
    """Walk a stride-62 run from i; stop when posOrder resets or a block is invalid."""
    blocks, prev = [], 0
    while i < hi and looks_like_block(mm, i):
        d = decode_block(mm[i:i + BLOCK])
        if blocks and d["posOrder"] <= prev:   # posOrder reset -> next team
            break
        blocks.append(d)
        prev = d["posOrder"]
        i += STRIDE
    return blocks, i


def find_xis(mm, lo, hi):
    """Return the XI runs (lists of decoded blocks) in [lo, hi).
    Only runs of >= MIN_XI consecutive blocks count, so team-totals / header
    records that look block-like (but stand alone) are skipped."""
    runs = []
    i = lo
    while i < hi:
        if is_block_start(mm, i):
            run, j = _walk_run(mm, i, hi)
            if len(run) >= MIN_XI:
                runs.append(run)
                i = j
                continue
        i += 1
    return runs


# The managed team's formation is stored as an ASCII string (e.g. "4-2-3-1") in the
# match trailer, always preceded by this 4-byte marker. Only ONE formation per match
# is stored — the opponent's is not kept as a string.
FORMATION_MARKER = bytes([118, 185, 244, 7])


def parse_formation(mm, anchor, next_anchor):
    hi = next_anchor or anchor + 8000
    i = mm.find(FORMATION_MARKER, anchor, hi)
    if i == -1:
        return None
    j = i + 4
    out = bytearray()
    while j < hi and (48 <= mm[j] <= 57 or mm[j] == 45):  # digits and '-'
        out.append(mm[j]); j += 1
    txt = out.decode("ascii") if out else None
    return txt or None


def extract_match(mm, anchor, next_anchor):
    hdr = parse_header(mm, anchor)
    if hdr:
        from comps import comp_id_at, name_for
        hdr["comp_id"] = comp_id_at(mm, hdr["date_off"])
        hdr["competition"] = name_for(mm, hdr["comp_id"])
    hi = next_anchor or anchor + 6000
    runs = find_xis(mm, anchor, hi)      # file order = home XI, then away XI
    home = runs[0] if len(runs) >= 1 else None
    away = runs[1] if len(runs) >= 2 else None
    home_tids = {b["tid_int"] for b in (home or [])}
    away_tids = {b["tid_int"] for b in (away or [])}
    ev = parse_events(mm, hdr["date_off"], home_tids | away_tids) if hdr else []
    # score = credited player goals + own goals (which no player's `goals` counts).
    # An own goal by a home player counts for away, and vice-versa.
    hg = sum(b["goals"] for b in home) if home else 0
    ag = sum(b["goals"] for b in away) if away else 0
    for e in ev:
        if e["type"] == "own_goal":
            if e["tid"] in home_tids:
                ag += 1
            elif e["tid"] in away_tids:
                hg += 1
    return {"anchor": anchor, "hdr": hdr, "home": home, "away": away,
            "events": ev, "score": (hg, ag),
            "star_home": _star(home), "star_away": _star(away)}


def _star(team):
    """The team's stand-out player TID (in-game 'star man' for that side).
    = highest rating [byte 32]; ties broken by goals, then assists, then
    completed passes. Verified: Menize (rtg 9) for Bucaspor in the 3-3, and
    Duruk (rtg 9) in the 2022-05-25 play-off. Only integer ratings are stored,
    so among equal ratings this is a best-effort heuristic."""
    if not team:
        return None
    b = max(team, key=lambda x: (x["rating"], x["goals"],
                                 x["assists"], x["passC"]))
    return b["tid_int"]


from datetime import date, timedelta

_XI_FIELDS = ["posOrder", "tid_int", "rating", "goals", "assists", "passA",
              "passC", "keyPass", "tackA", "tackW", "intercept", "headA",
              "headW", "crossA", "crossC", "dribbles", "mistakes", "shotA",
              "shotO", "condition", "subOn", "subOff", "yellow"]


def _xi(team):
    return [{k: b[k] for k in _XI_FIELDS} for b in (team or [])]


def _appeared(b):
    """A player featured in the match if he started (posOrder 1-11) or was
    subbed on (subOn is a minute, not 0xFF). Unused bench = posOrder>11 with
    subOn==0xFF."""
    return b["posOrder"] <= 11 or b["subOn"] != 0xFF


def team_stats(team):
    """Team match-summary stats DERIVED from the per-player blocks (they are not
    stored separately). Verified vs ground_truth_match1 (Karacabey 3-3 Bucaspor):
      - shots            = Σ shotA           (home 11 / away 8   — exact)
      - shots_on_target  = Σ shotO           (home 5  / away 4   — exact)
      - rating           = mean rating of players who appeared, 1 dp
                           (home 6.6 / away 6.7 — exact)
    NOT recoverable: possession and clear-cut-chances are match-engine aggregates
    that are NOT stored anywhere in the save (never appear as bytes in the match
    region), so they cannot be reconstructed — same as the man-of-the-match, which
    is also derived rather than stored.
    """
    if not team:
        return None
    app = [b for b in team if _appeared(b)]
    r = [b["rating"] for b in app]
    return {
        "shots": sum(b["shotA"] for b in team),
        "shots_on_target": sum(b["shotO"] for b in team),
        "rating": round(sum(r) / len(r), 1) if r else None,
        "players_used": len(app),
        # bonus aggregates (all exact sums; no ground truth to name the screen labels)
        "passes": sum(b["passA"] for b in team),
        "passes_completed": sum(b["passC"] for b in team),
        "tackles": sum(b["tackA"] for b in team),
        "tackles_won": sum(b["tackW"] for b in team),
        "crosses": sum(b["crossA"] for b in team),
        "interceptions": sum(b["intercept"] for b in team),
    }


def export_season(mm, path="season_data.json"):
    """Write the full season to JSON (reproducible replacement for the previous
    ad-hoc export). Includes star_home/star_away, yellow cards and min_display."""
    import json
    from comps import comp_id_at, name_for
    anchors = match_anchors(mm)
    out = []
    for n, a in enumerate(anchors):
        nxt = anchors[n + 1] if n + 1 < len(anchors) else None
        m = extract_match(mm, a, nxt)
        h = m["hdr"]
        if not h:
            continue
        try:
            d = (date(h["year"], 1, 1) + timedelta(days=h["day"])).isoformat()
        except ValueError:
            d = None
        out.append({
            "anchor": a, "date": d,
            "competition": h.get("competition"), "comp_id": h.get("comp_id"),
            "home_flag": mm[h["date_off"] - 1],  # 1 = managed team is home (bonus find)
            "home_tid": h["home_tid"], "away_tid": h["away_tid"],
            "attendance": h["att"],
            "score": {"home": m["score"][0], "away": m["score"][1]},
            "star_home": m["star_home"], "star_away": m["star_away"],
            "team_stats": {"home": team_stats(m["home"]),
                           "away": team_stats(m["away"])},
            "formation": parse_formation(mm, a, nxt),  # managed team's shape only
            "events": m["events"],
            "home_xi": _xi(m["home"]), "away_xi": _xi(m["away"]),
        })
    _label_playoffs(out)
    json.dump(out, open(path, "w"), ensure_ascii=False, indent=1)
    return out


def _label_playoffs(matches):
    """comp_id 227 is the promotion PLAY-OFF phase (filed under the parent
    "Turkish 2. League"), which read identically to regular-season games.
    Re-label as "... Play-Off" and, for a two-legged tie (same two clubs),
    tag First/Second Leg by date order. (No explicit round field is stored in
    the header we can trust from a single tie, so leg is inferred by date.)"""
    from collections import defaultdict
    legs = defaultdict(list)
    for m in matches:
        if m["comp_id"] == 227:
            m["competition"] = f"{m['competition']} Play-Off"
            legs[frozenset((m["home_tid"], m["away_tid"]))].append(m)
    for tie in legs.values():
        if len(tie) == 2:
            for i, m in enumerate(sorted(tie, key=lambda x: x["date"] or "")):
                leg = "First Leg" if i == 0 else "Second Leg"
                m["competition"] += f" ({leg})"
                m["leg"] = i + 1


if __name__ == "__main__":
    import sys
    s = Save()
    anchors = match_anchors(s.mm)
    if len(sys.argv) > 1 and sys.argv[1] == "dump":
        data = export_season(s.mm)
        print(f"{len(data)} matches -> season_data.json (with star/yellow/min_display)")
        sys.exit(0)
    if len(sys.argv) > 1:  # detail for one match near an offset
        anchor = min(anchors, key=lambda a: abs(a - int(sys.argv[1], 0)))
        idx = anchors.index(anchor)
        nxt = anchors[idx + 1] if idx + 1 < len(anchors) else None
        m = extract_match(s.mm, anchor, nxt)
        h = m["hdr"]
        print(f"anchor {anchor} (0x{anchor:x})")
        if h:
            print(f"home_tid={h['home_tid']} away_tid={h['away_tid']} "
                  f"date=day{h['day']}/{h['year']} att={h['att']} score={m['score']}")
        print("events:", [(e['min'], e['tid']) for e in m["events"]])
        for label, team in [("HOME", m["home"]), ("AWAY", m["away"])]:
            print(f"\n{label} ({len(team or [])} blocks)")
            for b in team or []:
                print(f"  pos{b['posOrder']:>2} tid={b['tid_int']:>6} rtg={b['rating']} "
                      f"G={b['goals']} A={b['assists']} PaA={b['passA']} ShA={b['shotA']} Con={b['condition']}")
    else:  # season summary
        print(f"{len(anchors)} matches\n")
        print(f"{'#':>3} {'anchor':>9} {'day':>4} {'year':>5} {'home':>6} {'away':>6} {'att':>6} {'score':>6}")
        for n, a in enumerate(anchors):
            nxt = anchors[n + 1] if n + 1 < len(anchors) else None
            m = extract_match(s.mm, a, nxt)
            h = m["hdr"] or {}
            sc = f"{m['score'][0]}-{m['score'][1]}"
            print(f"{n:>3} {a:>9} {h.get('day',''):>4} {h.get('year',''):>5} "
                  f"{h.get('home_tid',''):>6} {h.get('away_tid',''):>6} {h.get('att',''):>6} {sc:>6}")
