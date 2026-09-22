#!/usr/bin/env python3
"""Squad attributes and managed club squad parsing.

In FM Mobile, the managed club's squad (and reserve/loan players) is written
with exact 1-20 attributes, positions, preferred feet, and transfer valuations
in dedicated squad-list blocks (~61-63 MB).
"""
import re
import struct
from typing import Any, Dict, List, Optional, Tuple

from .careers import resolve_career

# Default club marker (managed club TID u16 LE + 0xFFFF)
CLUB_MARKER = resolve_career().club_marker
from .tables.player_attributes import POSITIONS


CONFIRMED = {
    0: "Aerial", 1: "Agility", 2: "Communication", 3: "Handling",
    4: "Kicking", 5: "Throwing", 6: "Reflexes", 7: "Crossing",
    8: "Dribbling", 10: "Passing", 11: "Shooting", 12: "Tackling",
    13: "Technique", 14: "Aggression", 15: "Creativity", 16: "Decisions",
    17: "Leadership", 18: "Movement", 19: "Positioning", 20: "Teamwork",
    21: "Pace", 22: "Stamina", 23: "Strength",
}

_NAME_LEN = re.compile(rb"([\x03-\x40])\x00\x00\x00")
_FULLNAME = re.compile(r"[A-ZÀ-ſ][\w'. À-ſ-]{2,}$")


def decode_confirmed_attributes(attrs: List[int]) -> Dict[str, int]:
    """{attribute: value} for the 23 confirmed own-squad attributes."""
    return {name: attrs[i] for i, name in CONFIRMED.items()}


def preferred_foot(feet: Tuple[int, int]) -> str:
    l, r = feet
    if l >= 16 and r >= 16 and abs(l - r) <= 3:
        return "Either"
    if l > r:
        return "Left only" if r <= 7 else "Left"
    if r > l:
        return "Right only" if l <= 7 else "Right"
    return "Either" if l >= 16 else "Right"


def loan_marker(managed_tid: int, parent_tid: int) -> bytes:
    """The 4-byte marker that anchors a LOANED-IN player's exact attribute record:
    `[parent_club_tid][managed_tid]`, both u16 LE."""
    return struct.pack("<HH", parent_tid, managed_tid)


def _name_before(mm: Any, marker_i: int) -> Optional[str]:
    """The player's full name from the record body preceding a club marker, or None."""
    win = mm[marker_i - 280:marker_i]
    for m in _NAME_LEN.finditer(win):
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
            return txt
    return None


class SnapshotNotFound(Exception):
    """The managed squad snapshot could not be located."""


def snapshot_bounds(mm: Any, margin: int = 5000, marker: bytes = CLUB_MARKER) -> Tuple[int, int]:
    """Locate the squad-snapshot region adaptively for `marker`."""
    hits, pos = [], 0
    while True:
        i = mm.find(marker, pos)
        if i == -1:
            break
        hits.append(i)
        pos = i + 1
    if not hits:
        raise SnapshotNotFound(
            f"the managed club marker {marker.hex()} does not appear in this save -- "
            f"wrong career? (careers.py), or the save is not an FMM22 .fms")
    clusters, cur = [], [hits[0]]
    for h in hits[1:]:
        if h - cur[-1] < 50_000:
            cur.append(h)
        else:
            clusters.append(cur)
            cur = [h]
    clusters.append(cur)

    best, best_score = None, 0
    for c in clusters:
        score = sum(1 for i in c[:12] if _name_before(mm, i))
        if score > best_score:
            best, best_score = c, score
    if not best:
        raise SnapshotNotFound(
            f"found {len(hits)} club markers but no cluster is preceded by player names, "
            f"so none of them is the squad snapshot")
    return max(0, best[0] - margin), best[-1] + margin


def squad_snapshot_bounds(mm: Any, markers: Tuple[bytes, ...]) -> Tuple[int, int]:
    """Union of the per-marker snapshot windows."""
    los, his = [], []
    for m in markers:
        try:
            lo, hi = snapshot_bounds(mm, marker=m)
        except SnapshotNotFound:
            continue
        los.append(lo)
        his.append(hi)
    if not los:
        raise SnapshotNotFound(
            f"none of the {len(list(markers))} club markers resolves to a squad snapshot")
    return min(los), max(his)


def own_squad_full(
    mm: Any,
    lo: Optional[int] = None,
    hi: Optional[int] = None,
    marker: bytes = CLUB_MARKER,
) -> Dict[int, Dict[str, Any]]:
    """{tid: {'name', 'loaned_in', 'parent_club_tid'}} for the managed club's squad."""
    if lo is None or hi is None:
        lo, hi = snapshot_bounds(mm, marker=marker)
    club_le = marker[:2]                       # managed club tid, u16 LE
    out: Dict[int, Dict[str, Any]] = {}
    pos = lo
    while True:
        j = mm.find(club_le, pos, hi)
        if j == -1:
            break
        pos = j + 1
        if mm[j + 2:j + 4] == b"\xff\xff":     # OWNED: tid 8 bytes before marker
            tid = int.from_bytes(mm[j - 8:j - 4], "little")
            loaned_in, parent = False, None
        else:                                  # LOAN: tid 10 bytes before; owner is u16 before
            tid = int.from_bytes(mm[j - 10:j - 6], "little")
            loaned_in = True
            parent = int.from_bytes(mm[j - 2:j], "little")
            if not (1 <= parent < 70000):
                continue
        if not (1000 < tid < 70000):
            continue
        name = _name_before(mm, j)
        if name:
            out[tid] = {"name": name, "loaned_in": loaned_in, "parent_club_tid": parent}
    return out


def own_squad(
    mm: Any,
    lo: Optional[int] = None,
    hi: Optional[int] = None,
    marker: bytes = CLUB_MARKER,
) -> Dict[int, str]:
    """{player_tid: full_name} for the managed club's squad."""
    return {t: v["name"] for t, v in own_squad_full(mm, lo, hi, marker).items()}


def attr_record(
    mm: Any,
    tid: int,
    bounds: Optional[Tuple[int, int]] = None,
    marker: bytes = CLUB_MARKER,
) -> Optional[Dict[str, Any]]:
    """Own-squad exact record: {'attrs':[36], 'positions':{}, 'feet':(l,r), 'M', 'value'}."""
    lo, hi = bounds or snapshot_bounds(mm, marker=marker)
    le = struct.pack("<I", tid)
    pos = lo
    found = None
    while True:
        i = mm.find(le, pos)
        if i == -1 or i > hi:
            return found
        pos = i + 1
        if mm[i + 8:i + 12] == marker:
            M = i + 8
            attrs = list(mm[M - 59:M - 23])
            posb = list(mm[M - 23:M - 8])
            positions = {POSITIONS[k]: v for k, v in enumerate(posb) if v > 1}
            feet = (mm[M + 33], mm[M + 34])
            value = int.from_bytes(mm[M + 4:M + 8], "little")
            found = {"attrs": attrs, "positions": positions, "feet": feet,
                     "M": M, "value": value}


def attr_records(
    mm: Any,
    tid: int,
    bounds: Optional[Tuple[int, int]] = None,
    markers: Tuple[bytes, ...] = (CLUB_MARKER,),
) -> Dict[bytes, Dict[str, Any]]:
    """{marker: freshest record} — one entry per club marker this tid appears under."""
    lo, hi = bounds or squad_snapshot_bounds(mm, markers)
    le = struct.pack("<I", tid)
    out: Dict[bytes, Dict[str, Any]] = {}
    pos = lo
    while True:
        i = mm.find(le, pos)
        if i == -1 or i > hi:
            return out
        pos = i + 1
        m = bytes(mm[i + 8:i + 12])
        if m in markers:
            M = i + 8
            posb = list(mm[M - 23:M - 8])
            out[m] = {"attrs": list(mm[M - 59:M - 23]),
                      "positions": {POSITIONS[k]: v for k, v in enumerate(posb) if v > 1},
                      "feet": (mm[M + 33], mm[M + 34]),
                      "M": M,
                      "value": int.from_bytes(mm[M + 4:M + 8], "little")}
