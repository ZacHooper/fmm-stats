#!/usr/bin/env python3
"""
Per-match decoding for FMM22 saves: stat blocks, events, team stats, formation.

Structure (validated on Karacabey 3-3 Bucaspor, ground_truth_match1.json):
  - Each match begins with a DELIMITER cluster (regions.DELIM_UNIT, repeated).
  - Then a HEADER: [homeTID:u16][awayTID:u16][day:u16][year:u16][att:u16], preceded
    by an EVENT list (goals/cards: minute + playerTID).
  - Then HOME XI then AWAY XI: 54-byte stat blocks, 8-byte 0xFF delimiter, stride 62;
    posOrder resets to 1 per team.
  - A trailer holds the managed team's formation string + a formation-shape template.
"""
from datetime import date, timedelta
from collections import defaultdict

from .regions import DELIM_UNIT, MATCH_LO
from .reference import comp_id_at, comp_name

# ---------------- stat block ----------------
BLOCK = 54
DELIM = 8
STRIDE = BLOCK + DELIM

FIELDS = {
    0: "assists", 3: "condition", 4: "crossA", 5: "crossC", 8: "dribbles",
    10: "goals", 11: "headA", 12: "headW", 16: "intercept", 19: "subOn",
    21: "subOff", 22: "mistakes", 23: "mistGoal", 25: "passA", 26: "passC",
    27: "keyPass", 32: "rating", 35: "shotA", 36: "shotO", 41: "posOrder",
    48: "tackA", 49: "tackW", 53: "yellow",
}


def decode_block(b: bytes) -> dict:
    d = {name: b[off] for off, name in FIELDS.items()}
    d["sid"] = b[28:30].hex()
    d["tid"] = b[42:46].hex()
    d["tid_int"] = int.from_bytes(b[42:46], "little")
    return d


def is_block_start(mm, i):
    if i + BLOCK > len(mm):
        return False
    return (1 <= mm[i + 3] <= 100
            and mm[i + 17] == 0xff and mm[i + 18] == 0xff and mm[i + 20] == 0xff
            and 1 <= mm[i + 41] <= 30
            and 0 < int.from_bytes(mm[i + 42:i + 46], "little") < 200000)


# ---------------- match discovery ----------------
def match_anchors(mm, lo=MATCH_LO, hi=None):
    """Delimiter clusters -> one anchor offset per match."""
    hi = hi or len(mm)
    hits, pos = [], lo
    while True:
        i = mm.find(DELIM_UNIT, pos)
        if i == -1 or i > hi:
            break
        hits.append(i)
        pos = i + 8
    if not hits:
        return []
    clusters, cur = [], [hits[0]]
    for h in hits[1:]:
        if h - cur[-1] <= 16:
            cur.append(h)
        else:
            clusters.append(cur)
            cur = [h]
    clusters.append(cur)
    return [c[0] for c in clusters]


def _valid_match_header(mm, anchor):
    """Strict test: does this delimiter cluster open a real match? Used to locate
    the match region by CONTENT (see find_match_region) instead of a hard-coded
    offset — the DELIM_UNIT also appears in the fixed tactic-template region, which
    has no plausible date/opponent header, so those clusters fail this test."""
    h = parse_header(mm, anchor)
    if not h:
        return False
    return (2018 <= h["year"] <= 2030 and 0 <= h["day"] <= 366
            and 0 < h["home_tid"] < 65000 and 0 < h["away_tid"] < 65000
            and h["home_tid"] != h["away_tid"])


def find_match_region(mm, margin=50_000):
    """DERIVE the per-match region [lo, hi] from the save's own content, so the
    match parser is career-agnostic (Bucaspor's matches sit ~56M, Frem's ~53.8M;
    a hard-coded MATCH_LO=55M silently drops Frem's — see savefile-boundary-map).

    Every delimiter cluster in the file is tested with `_valid_match_header`; only
    the true match cluster (headers with plausible date + two distinct clubs)
    survives, so its span is self-locating. Returns None if nothing validates
    (caller falls back to the hard-coded window)."""
    anchors = match_anchors(mm, lo=0, hi=len(mm))
    good = [a for a in anchors if _valid_match_header(mm, a)]
    if len(good) < 3:                       # too few to trust; let caller fall back
        return None
    return (max(0, good[0] - margin), min(len(mm), good[-1] + margin))


def parse_header(mm, anchor, window=1500):
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
            if 0 < home < 65000 and 0 < away < 65000 and att < 60000:
                return {"home_tid": home, "away_tid": away, "day": day,
                        "year": year, "att": att, "date_off": i - 6}
    return None


# ---------------- events ----------------
EVENT_TYPE = {
    0x01: "goal", 0x02: "own_goal", 0x03: "penalty", 0x04: "missed_penalty",
    0x05: "red_card", 0x06: "injury", 0x29: "disallowed_goal",
}


def parse_events(mm, hdr_off, player_tids, back=380):
    events, lo, i = [], max(0, hdr_off - back), max(0, hdr_off - 380)
    while i < hdr_off - 6:
        tid = int.from_bytes(mm[i + 5:i + 9], "little")
        if tid in player_tids and mm[i + 9] == 0xff and mm[i + 10] == 0xff:
            b0, b1 = mm[i], mm[i + 1]
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


# ---------------- XI walking ----------------
def looks_like_block(mm, i):
    """Does a stat block start at i?

    `condition` (+3) is a match-fitness percentage for anyone who played, but an UNUSED
    SUBSTITUTE carries 0xff. Requiring a plausible 1..100 here used to abort the walk at
    the first unused sub, silently truncating the XI at 11 and dropping every block after
    it — including players who were subbed ON later in the list (26 real appearances lost
    in frem-2024-11-10.fms alone). posOrder + tid are the actual structural signature, so
    condition is only rejected when it is neither a percentage nor the unused sentinel.
    """
    if i + BLOCK > len(mm):
        return False
    tid = int.from_bytes(mm[i + 42:i + 46], "little")
    cond_ok = (1 <= mm[i + 3] <= 100) or mm[i + 3] == 0xff
    return cond_ok and 1 <= mm[i + 41] <= 30 and 0 < tid < 200000


MIN_XI = 7


def _walk_run(mm, i, hi):
    blocks, prev = [], 0
    while i < hi and looks_like_block(mm, i):
        d = decode_block(mm[i:i + BLOCK])
        if blocks and d["posOrder"] <= prev:
            break
        blocks.append(d)
        prev = d["posOrder"]
        i += STRIDE
    return blocks, i


def find_xis(mm, lo, hi):
    runs, i = [], lo
    while i < hi:
        if is_block_start(mm, i):
            run, j = _walk_run(mm, i, hi)
            if len(run) >= MIN_XI:
                runs.append(run)
                i = j
                continue
        i += 1
    return runs


# ---------------- formation ----------------
FORMATION_MARKER = bytes([118, 185, 244, 7])


def parse_formation(mm, anchor, next_anchor):
    hi = next_anchor or anchor + 8000
    i = mm.find(FORMATION_MARKER, anchor, hi)
    if i == -1:
        return None
    j = i + 4
    out = bytearray()
    while j < hi and (48 <= mm[j] <= 57 or mm[j] == 45):
        out.append(mm[j])
        j += 1
    return out.decode("ascii") if out else None


# ---------------- slot positions ----------------
# Immediately after the formation string sit 11 pairs of 2 bytes — one per starting
# slot, in posOrder order — giving each starter's actual on-pitch position. This is the
# ONLY place position is stored; the per-player stat block holds none (exhaustively
# ruled out). Full write-up + validation: docs/agent-context/match-position-encoding.md.
POSITION_BANDS = {0x01: "GK", 0x04: "D", 0x08: "DM", 0x10: "M", 0x20: "AM", 0x40: "ST"}
LEFT_FLAG = 0x80        # band byte: player is the wide-LEFT one of his band
WIDE_RIGHT = 0x08       # column byte: player is the wide-RIGHT one of his band


def slot_position(band_byte, col_byte):
    """One (band, column) pair -> an FM position code ('DR', 'DMC', 'AML', ...)."""
    band = POSITION_BANDS.get(band_byte & ~LEFT_FLAG)
    if band is None:
        return None
    if band == "GK":
        return "GK"
    if band == "ST":
        return "FC"
    if col_byte == WIDE_RIGHT:
        return band + "R"
    return band + ("L" if band_byte & LEFT_FLAG else "C")


def parse_slot_positions(mm, anchor, next_anchor):
    """The 11 starting positions for the MANAGED club's XI, or None.

    Only our own club's shape is stored (same as the formation string), so the caller
    must attach these to whichever side is ours — see extract_match. A None means the
    array didn't decode; callers keep going with position unknown rather than failing.
    """
    hi = next_anchor or anchor + 8000
    i = mm.find(FORMATION_MARKER, anchor, hi)
    if i == -1:
        return None
    j = i + 4
    while j < hi and (48 <= mm[j] <= 57 or mm[j] == 45):
        j += 1
    k = j
    while k < hi and mm[k] == 0:            # skip the zero padding
        k += 1
    if k + 22 > hi:
        return None
    slots = [slot_position(mm[k + 2 * n], mm[k + 2 * n + 1]) for n in range(11)]
    return None if any(s is None for s in slots) else slots


def formation_from_slots(slots):
    """Collapse decoded slots back into a formation string.

    This is the self-check that makes the decode verifiable WITHOUT screenshots: it must
    equal the save's own formation string (108/108 across two careers). Prefer it over a
    post-match screenshot, which is a different moment in time if the manager changed
    shape mid-match.
    """
    order = ["D", "DM", "M", "AM", "ST"]
    counts = {o: 0 for o in order}
    for s in slots or ():
        if s == "GK":
            continue
        counts["ST" if s == "FC" else s[:-1]] += 1
    return "-".join(str(counts[o]) for o in order if counts[o])


# ---------------- team stats ----------------
def _appeared(b):
    return b["posOrder"] <= 11 or b["subOn"] != 0xFF


def team_stats(team):
    """Team match-summary stats DERIVED from the player blocks (not stored):
    shots = Sum shotA, shots_on_target = Sum shotO, rating = mean of appeared
    players' ratings (1 dp). Verified vs ground truth (11/8, 5/4, 6.6/6.7)."""
    if not team:
        return None
    app = [b for b in team if _appeared(b)]
    r = [b["rating"] for b in app]
    return {
        "shots": sum(b["shotA"] for b in team),
        "shots_on_target": sum(b["shotO"] for b in team),
        "rating": round(sum(r) / len(r), 1) if r else None,
        "players_used": len(app),
        "passes": sum(b["passA"] for b in team),
        "passes_completed": sum(b["passC"] for b in team),
        "tackles": sum(b["tackA"] for b in team),
        "tackles_won": sum(b["tackW"] for b in team),
        "crosses": sum(b["crossA"] for b in team),
        "interceptions": sum(b["intercept"] for b in team),
    }


def _star(team):
    if not team:
        return None
    b = max(team, key=lambda x: (x["rating"], x["goals"], x["assists"], x["passC"]))
    return b["tid_int"]


# ---------------- per-match assembly ----------------
def extract_match(mm, anchor, next_anchor):
    hdr = parse_header(mm, anchor)
    if hdr:
        hdr["comp_id"] = comp_id_at(mm, hdr["date_off"])
        hdr["competition"] = comp_name(mm, hdr["comp_id"])
    hi = next_anchor or anchor + 6000
    runs = find_xis(mm, anchor, hi)
    home = runs[0] if len(runs) >= 1 else None
    away = runs[1] if len(runs) >= 2 else None
    home_tids = {b["tid_int"] for b in (home or [])}
    away_tids = {b["tid_int"] for b in (away or [])}
    ev = parse_events(mm, hdr["date_off"], home_tids | away_tids) if hdr else []
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


_XI_FIELDS = ["posOrder", "tid_int", "rating", "goals", "assists", "passA",
              "passC", "keyPass", "tackA", "tackW", "intercept", "headA",
              "headW", "crossA", "crossC", "dribbles", "mistakes", "shotA",
              "shotO", "condition", "subOn", "subOff", "yellow"]


def _xi(team, slots=None):
    """Serialise a side's blocks, attaching the decoded starting position when known.

    `slots` is the 11-entry array from parse_slot_positions and is only ever OUR club's
    (the save stores no shape for the opposition), so the caller passes it for our side
    only. Substitutes get position None: the array covers the starting XI, and where a
    sub actually played is not recorded.
    """
    out = []
    for b in (team or []):
        row = {k: b[k] for k in _XI_FIELDS}
        n = b["posOrder"]
        row["position"] = slots[n - 1] if (slots and 1 <= n <= 11) else None
        out.append(row)
    return out


def _label_playoffs(matches):
    legs = defaultdict(list)
    for m in matches:
        if m["comp_id"] == 227:
            m["competition"] = f"{m['competition']} Play-Off"
            legs[frozenset((m["home_tid"], m["away_tid"]))].append(m)
    for tie in legs.values():
        if len(tie) == 2:
            for i, m in enumerate(sorted(tie, key=lambda x: x["date"] or "")):
                m["competition"] += f" ({'First Leg' if i == 0 else 'Second Leg'})"
                m["leg"] = i + 1


def extract_season(mm, our_tids=()):
    """Full season as a list of match dicts (the content of season_data.json).

    `our_tids` = the career's club tids (first team + reserves). Only our own shape is
    stored in the save, so starting positions are attached to whichever side is ours;
    pass nothing and every position is simply None (positions are additive — no caller
    breaks without them).
    """
    region = find_match_region(mm)                       # self-locating, career-agnostic
    if region:
        anchors = match_anchors(mm, lo=region[0], hi=region[1])
    else:
        anchors = match_anchors(mm)                       # fall back to hard-coded MATCH_LO
    ours = {t for t in our_tids if t}
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
        slots = parse_slot_positions(mm, a, nxt)
        out.append({
            "anchor": a, "date": d,
            "competition": h.get("competition"), "comp_id": h.get("comp_id"),
            "home_flag": mm[h["date_off"] - 1],
            "home_tid": h["home_tid"], "away_tid": h["away_tid"],
            "attendance": h["att"],
            "score": {"home": m["score"][0], "away": m["score"][1]},
            "star_home": m["star_home"], "star_away": m["star_away"],
            "team_stats": {"home": team_stats(m["home"]),
                           "away": team_stats(m["away"])},
            "formation": parse_formation(mm, a, nxt),
            "events": m["events"],
            "home_xi": _xi(m["home"], slots if h["home_tid"] in ours else None),
            "away_xi": _xi(m["away"], slots if h["away_tid"] in ours else None),
        })
    _label_playoffs(out)
    return out
