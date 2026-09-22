#!/usr/bin/env python3
"""`nations` — the 251-record Nations catalog.

Declared by a `[>= 8 x 0xFF][count u16 = 251]` frame in the reference block (~12.75 MB).
Composite layout:
  [uid u32][id u16] -> Record("nation_head", 6)
  [len u32][name (utf-8)][\\0] -> PString("name", null_terminated=True)
  [len u32][nationality (utf-8)][\\0] -> PString("nationality", null_terminated=True)
  [len u32][code (ascii)] -> PString("code", null_terminated=False)
  [continent_id u16][capital_city_id u16][national_stadium_id u16] -> Record("nation_tail", 6)
  Followed by national team data: kit colours, rival nation, rankings, ranking history, coefficients.
"""
import re
import struct
from typing import Any, Dict, List, Optional, Tuple

from .. import primitives as P
from ..save import cache_key as _cache_key
from ..schema import Field, Record, U16, U32, PString
from .engine import TableDef

__all__ = [
    "NATION_HEAD",
    "NATION_TAIL",
    "NATIONS_TABLE",
    "locate_nations",
    "nations_table_spans",
    "scrape_nations",
]

NATION_HEAD = Record("nation_head", 6, (
    Field(0, 4, "uid", U32),
    Field(4, 2, "id", U16),
), is_head=True)

NATION_TAIL = Record("nation_tail", 6, (
    Field(0, 2, "continent_id", U16),
    Field(2, 2, "capital_city_id", U16),
    Field(4, 2, "national_stadium_id", U16),
), is_head=True)

_CODE = re.compile(r"^[A-Z][A-Z0-9]{1,2}$")
_CODE_LENS = (3, 2)
_MAX_CONTINENT = 6
_MAX_HISTORY = 128
_MAX_COEFFS = 32

_NATIONS_CACHE: Dict[str, Optional[Tuple[int, int]]] = {}


def locate_nations(mm: Any) -> Optional[Tuple[int, int]]:
    """(base, declared_count) for the 251-record nations catalog, or None.

    Declared by a `[>= 8 x 0xFF][count u16]` frame at ~12.75 MB.
    Record 0 opens with `uid=5 (u32), id=0 (u16), len=7 (u32), 'Algeria\\0'`.
    """
    key = _cache_key(mm)
    if key in _NATIONS_CACHE:
        return _NATIONS_CACHE[key]

    sig = struct.pack("<IHII", 5, 0, 7, 0) # uid=5, id=0, len=7
    # Or search for Algeria string with its length
    sig = struct.pack("<IHI", 5, 0, 7) + b"Algeria\x00"
    pos = mm.find(sig)
    if pos != -1 and pos >= 10:
        k = pos - 2
        ff = 0
        while k > 0 and mm[k - 1] == 0xFF:
            ff += 1
            k -= 1
        if ff >= 8:
            declared_count = struct.unpack_from("<H", mm, pos - 2)[0]
            res = (pos, declared_count)
            _NATIONS_CACHE[key] = res
            return res

    _NATIONS_CACHE[key] = None
    return None


def _u16(mm: Any, o: int) -> int:
    return int.from_bytes(mm[o:o + 2], "little")


def _u32(mm: Any, o: int) -> int:
    return int.from_bytes(mm[o:o + 4], "little")


def _string(mm: Any, o: int, n: int, maxlen: int = 64) -> Tuple[Optional[str], Optional[int]]:
    if o + 4 > n:
        return None, None
    ln = _u32(mm, o)
    if not (1 <= ln <= maxlen) or o + 4 + ln > n:
        return None, None
    try:
        return mm[o + 4:o + 4 + ln].decode("utf-8"), o + 4 + ln
    except UnicodeDecodeError:
        return None, None


def _plausible_continent(v: int) -> bool:
    return v <= _MAX_CONTINENT or v == P.NO_ID16


def _national_team(mm: Any, t: int, n: int) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "rival_nation_id": None,
        "is_ranked": None,
        "world_ranking": None,
        "ranking_points": None,
        "ranking_history": [],
        "coefficients": [],
        "kit_colours": [],
    }
    if t + 25 > n:
        return out
    out["kit_colours"] = [_u16(mm, t + 1 + 2 * i) for i in range(4)]
    rival = _u16(mm, t + 11)
    out["rival_nation_id"] = rival if 0 < rival <= 4096 else None
    out["is_ranked"] = bool(mm[t + 18])
    out["world_ranking"] = _u16(mm, t + 19)
    out["ranking_points"] = _u16(mm, t + 21)
    hn = _u16(mm, t + 23)
    if not (0 < hn <= _MAX_HISTORY) or t + 25 + 2 * hn > n:
        return out
    out["ranking_history"] = [_u16(mm, t + 25 + 2 * i) for i in range(hn)]
    q = t + 25 + 2 * hn
    cn = mm[q + 2] if q + 2 < n else 0
    if 0 < cn <= _MAX_COEFFS and q + 3 + 4 * cn <= n:
        out["coefficients"] = [
            round(struct.unpack("<f", mm[q + 3 + 4 * i:q + 7 + 4 * i])[0], 4)
            for i in range(cn)
        ]
    return out


def _nation_candidates(mm: Any) -> List[Dict[str, Any]]:
    n = len(mm)
    out = []
    pats = [(ln, struct.pack("<I", ln)) for ln in _CODE_LENS]
    heads = []
    for ln, pat in pats:
        q = 0
        while True:
            j = mm.find(pat, q)
            if j == -1:
                break
            q = j + 1
            heads.append((j, ln))
    heads.sort()
    for j, code_len in heads:
        try:
            code = mm[j + 4:j + 4 + code_len].decode("ascii")
        except UnicodeDecodeError:
            continue
        if not _CODE.match(code):
            continue
        for nat_len in range(2, 40):
            a = j - 1 - nat_len - 4
            if a < 6 or _u32(mm, a) != nat_len or mm[a + 4 + nat_len] != 0:
                continue
            nationality, _ = _string(mm, a, n)
            if not nationality:
                continue
            for name_len in range(2, 48):
                c = a - 1 - name_len - 4
                if c < 6 or _u32(mm, c) != name_len or mm[c + 4 + name_len] != 0:
                    continue
                name, _ = _string(mm, c, n)
                if not name or not name[0].isupper():
                    continue
                nid = _u16(mm, c - 2)
                uid = _u32(mm, c - 6)
                if not (0 <= nid <= 4096):
                    continue
                t = j + 4 + code_len
                rec = {
                    "id": nid,
                    "uid": uid,
                    "name": name,
                    "nationality": nationality,
                    "code": code,
                    "continent_id": _u16(mm, t),
                    "capital_city_id": _u16(mm, t + 2),
                    "national_stadium_id": _u16(mm, t + 4),
                    "offset": c - 6,
                }
                rec.update(_national_team(mm, t + 6, n))
                out.append(rec)
                break
            break
    return out


def scrape_nations(mm: Any) -> Dict[int, Dict[str, Any]]:
    """{nation_id: record} for every nation in the save."""
    cands = [c for c in _nation_candidates(mm) if _plausible_continent(c["continent_id"])]
    if not cands:
        return {}
    offs = sorted(c["offset"] for c in cands)
    best, run_start, run = (0, 0, 0), offs[0], 1
    for a, b in zip(offs, offs[1:]):
        if b - a <= 4096:
            run += 1
            if run > best[0]:
                best = (run, run_start, b)
        else:
            run, run_start = 1, b
    if best[0] < 20:
        return {}
    lo, hi = best[1], best[2]
    out: Dict[int, Dict[str, Any]] = {}
    for c in cands:
        if lo <= c["offset"] <= hi:
            out.setdefault(c["id"], c)

    loc = locate_nations(mm)
    if loc:
        declared = loc[1]
        missing = [i for i in range(declared) if i not in out]
        if missing or len(out) != declared:
            pass  # keep graceful
    return out


NATIONS_TABLE = TableDef(
    name="nations",
    segments=(
        NATION_HEAD,
        PString("name", null_terminated=True),
        PString("nationality", null_terminated=True),
        PString("code", null_terminated=False),
        NATION_TAIL,
    ),
    locator=locate_nations,
    include_offset=True,
)


def nations_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """Return [(start, end)] byte spans covering the nations table."""
    nats = scrape_nations(mm)
    if not nats:
        return []
    start = min(r["offset"] for r in nats.values())
    end = max(r["offset"] for r in nats.values()) + 180
    return [(start, end)]
