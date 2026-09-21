#!/usr/bin/env python3
"""Generic table abstraction and walking engine for FM savefile tables.

Encapsulates the common table archetypes found in the binary save:
1. Fixed-stride preallocated grids (e.g. match officials, stadiums, cities, staff).
2. Length-prefixed string catalogs with optional trailers (e.g. round & leg names, currencies).
3. Frame locating, record decoding, span generation for coverage audits, and ID mapping.
"""
from dataclasses import dataclass
import struct
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from . import primitives as P
from . import records as RD
from .save import cache_key as _cache_key
from .schema import Record
from .schemas.currencies import CURRENCY_COUNT, CURRENCY_HEAD, CURRENCY_TAIL
from .schemas.officials import OFFICIAL, OFFICIAL_STRIDE
from .schemas.places import CITY, CITY_RECORD
from .schemas.rounds import ROUND_COUNT, ROUND_HEAD, ROUND_TRAILER
from .schemas.staff import (
    FORMATION_SLOTS,
    STAFF,
    STAFF_ATTRS,
    STAFF_STRIDE,
    reputation_tier,
    style,
)


@dataclass(frozen=True)
class FixedTableDef:
    """Definition for a table of uniform, fixed-stride records."""
    name: str
    record_schema: Record
    locator: Callable[[Any], Optional[Tuple[int, int]]]  # mm -> (base_offset, record_count)
    include_offset: bool = False
    post_process: Optional[Callable[[Dict[str, Any], int], Dict[str, Any]]] = None

    @property
    def stride(self) -> int:
        return self.record_schema.stride

    def scrape(self, mm: Any) -> List[Dict[str, Any]]:
        return walk_fixed_table(mm, self)

    def spans(self, mm: Any, include_count_header: bool = True) -> List[Tuple[int, int]]:
        return fixed_table_spans(mm, self, include_count_header=include_count_header)

    def id_map(self, mm: Any, key_field: str = "id") -> Dict[Any, Dict[str, Any]]:
        return {r[key_field]: r for r in self.scrape(mm) if key_field in r}


@dataclass(frozen=True)
class StringCatalogDef:
    """Definition for a variable-length catalog of length-prefixed strings with optional trailer."""
    name: str
    head_schema: Record  # Schema containing string length (typically Field 'len')
    trailer_schema: Optional[Record] = None
    locator: Callable[[Any], Optional[Tuple[int, int]]] = None  # mm -> (base_offset, record_count)
    string_field: str = "name"
    len_field: str = "len"
    encoding: str = "utf-8"
    fallback_encoding: str = "latin-1"
    null_terminated: bool = True
    include_offset: bool = False
    post_process: Optional[Callable[[Dict[str, Any], int], Dict[str, Any]]] = None

    def scrape(self, mm: Any) -> List[Dict[str, Any]]:
        return walk_string_catalog(mm, self)

    def spans(self, mm: Any, include_count_header: bool = True) -> List[Tuple[int, int]]:
        return string_catalog_spans(mm, self, include_count_header=include_count_header)

    def id_map(self, mm: Any, key_field: str = "id") -> Dict[Any, Dict[str, Any]]:
        return {r[key_field]: r for r in self.scrape(mm) if key_field in r}


def walk_fixed_table(mm: Any, table_def: FixedTableDef) -> List[Dict[str, Any]]:
    """Read all records from a fixed-stride table using its TableDef."""
    info = table_def.locator(mm)
    if not info:
        return []
    base, count = info
    stride = table_def.stride
    out = []
    for k in range(count):
        rec_start = base + k * stride
        rec = RD.read(mm, table_def.record_schema, rec_start)
        if table_def.include_offset and "offset" not in rec:
            rec["offset"] = rec_start
        if table_def.post_process is not None:
            try:
                rec = table_def.post_process(rec, rec_start)
            except TypeError:
                rec = table_def.post_process(rec)  # type: ignore[call-arg]
        if rec is not None:
            out.append(rec)
    return out


def fixed_table_spans(mm: Any, table_def: FixedTableDef, include_count_header: bool = True) -> List[Tuple[int, int]]:
    """Return [(start, end)] byte spans covering the fixed table and its count header."""
    info = table_def.locator(mm)
    if not info:
        return []
    base, count = info
    stride = table_def.stride
    spans = []
    if include_count_header and base >= 4:
        spans.append((base - 4, base))
    for k in range(count):
        rec_start = base + k * stride
        spans.append((rec_start, rec_start + stride))
    return spans


def walk_string_catalog(mm: Any, catalog_def: StringCatalogDef) -> List[Dict[str, Any]]:
    """Read all records from a variable-length string catalog."""
    info = catalog_def.locator(mm)
    if not info:
        return []
    base, count = info
    pos = base
    n = len(mm)
    head_len = catalog_def.head_schema.span
    trailer_len = (catalog_def.trailer_schema.stride or catalog_def.trailer_schema.span) if catalog_def.trailer_schema else 0
    term_len = 1 if catalog_def.null_terminated else 0

    out = []
    for _ in range(count):
        if pos + head_len > n:
            break
        head = RD.read(mm, catalog_def.head_schema, pos)
        slen = head.get(catalog_def.len_field, 0)
        rec_len = head_len + slen + term_len + trailer_len
        if pos + rec_len > n:
            break

        raw_str = bytes(mm[pos + head_len:pos + head_len + slen])
        try:
            val_str = raw_str.decode(catalog_def.encoding)
        except UnicodeDecodeError:
            val_str = raw_str.decode(catalog_def.fallback_encoding, errors="replace")

        row = dict(head)
        if catalog_def.len_field in row:
            del row[catalog_def.len_field]
        row[catalog_def.string_field] = val_str

        if catalog_def.trailer_schema:
            trailer_pos = pos + head_len + slen + term_len
            trailer = RD.read(mm, catalog_def.trailer_schema, trailer_pos)
            row.update(trailer)

        if catalog_def.include_offset and "offset" not in row:
            row["offset"] = pos

        if catalog_def.post_process is not None:
            try:
                row = catalog_def.post_process(row, pos)
            except TypeError:
                row = catalog_def.post_process(row)  # type: ignore[call-arg]

        out.append(row)
        pos += rec_len
    return out


def string_catalog_spans(mm: Any, catalog_def: StringCatalogDef, include_count_header: bool = True) -> List[Tuple[int, int]]:
    """Return [(start, end)] byte spans covering the string catalog records and count header."""
    info = catalog_def.locator(mm)
    if not info:
        return []
    base, count = info
    pos = base
    n = len(mm)
    head_len = catalog_def.head_schema.span
    trailer_len = (catalog_def.trailer_schema.stride or catalog_def.trailer_schema.span) if catalog_def.trailer_schema else 0
    term_len = 1 if catalog_def.null_terminated else 0

    spans = []
    if include_count_header and base >= 4:
        spans.append((base - 4, base))
    for _ in range(count):
        if pos + head_len > n:
            break
        head = RD.read(mm, catalog_def.head_schema, pos)
        slen = head.get(catalog_def.len_field, 0)
        rec_len = head_len + slen + term_len + trailer_len
        if pos + rec_len > n:
            break
        spans.append((pos, pos + rec_len))
        pos += rec_len
    return spans


# =====================================================================
# Registered Table Definitions & Locators
# =====================================================================

_LOCATOR_CACHE: Dict[str, Dict[str, Optional[Tuple[int, int]]]] = {
    "rounds": {},
    "officials": {},
    "cities": {},
    "staff": {},
    "currencies": {},
}


# 1. Round Names Catalog (273 records)
def locate_rounds(mm: Any) -> Optional[Tuple[int, int]]:
    """(base, declared_count) for the 273 round/leg name catalog, or None."""
    key = _cache_key(mm)
    cache = _LOCATOR_CACHE["rounds"]
    if key in cache:
        return cache[key]
    pat = b"\xff" * 8 + struct.pack("<I", ROUND_COUNT) + struct.pack("<I", 1) + struct.pack("<I", 6) + b"Replay\x00"
    pos = mm.find(pat)
    if pos == -1:
        cache[key] = None
        return None
    res = (pos + 12, ROUND_COUNT)
    cache[key] = res
    return res


ROUNDS_CATALOG = StringCatalogDef(
    name="round_names",
    head_schema=ROUND_HEAD,
    trailer_schema=ROUND_TRAILER,
    locator=locate_rounds,
    string_field="name",
    len_field="len",
    null_terminated=True,
    post_process=lambda r, _: {
        "id": r["id"],
        "name": r["name"],
        "is_replay": bool(r.get("is_replay", 0)),
        "is_extra_time": bool(r.get("is_extra_time", 0)),
        "is_penalties": bool(r.get("is_penalties", 0)),
        "leg_flag": r.get("leg_flag", 0),
    },
)


# 2. Match Officials Table (622 / 1,109 records x 99B)
def locate_officials(mm: Any) -> Optional[Tuple[int, int]]:
    """(base, declared_count) for the 99-byte match officials table, or None."""
    key = _cache_key(mm)
    cache = _LOCATOR_CACHE["officials"]
    if key in cache:
        return cache[key]
    pat = b"\xff" * 8 + struct.pack("<I", ROUND_COUNT) + struct.pack("<I", 1) + struct.pack("<I", 6) + b"Replay\x00"
    pos = mm.find(pat)
    if pos == -1:
        cache[key] = None
        return None
    for cnt in (622, 1109, 621, 623, 1108, 1110):
        span = cnt * OFFICIAL_STRIDE
        hdr_candidate = pos - span - 4
        if hdr_candidate >= 8 and all(mm[hdr_candidate - 1 - j] == 0xFF for j in range(8)):
            c = struct.unpack_from("<I", mm, hdr_candidate)[0]
            if c == cnt:
                res = (hdr_candidate + 4, cnt)
                cache[key] = res
                return res
    cache[key] = None
    return None


OFFICIALS_TABLE = FixedTableDef(
    name="match_officials",
    record_schema=OFFICIAL,
    locator=locate_officials,
)


# 3. Cities Table (10,956 records x 20B)
def locate_cities(mm: Any) -> Optional[Tuple[int, int]]:
    """(base, declared_count) for the 20-byte cities table, or None."""
    key = _cache_key(mm)
    cache = _LOCATOR_CACHE["cities"]
    if key in cache:
        return cache[key]
    pat = b"\xff" * 8 + struct.pack("<H", 10956)
    pos = 0
    while True:
        idx = mm.find(pat, pos)
        if idx == -1:
            break
        base = idx + len(pat)
        if base + 2 <= len(mm) and struct.unpack("<H", mm[base:base + 2])[0] == 0:
            res = (base, 10956)
            cache[key] = res
            return res
        pos = idx + 1
    cache[key] = None
    return None


def _process_city(rec: Dict[str, Any], offset: int) -> Dict[str, Any]:
    placed = (-60.0 <= rec["latitude"] <= 80.0 and -180.0 <= rec["longitude"] <= 180.0)
    rec["latitude"] = round(rec["latitude"], 6) if placed else None
    rec["longitude"] = round(rec["longitude"], 6) if placed else None
    rec["offset"] = offset
    return rec


CITIES_TABLE = FixedTableDef(
    name="cities",
    record_schema=CITY,
    locator=locate_cities,
    include_offset=True,
    post_process=_process_city,
)


# 4. Staff Attributes Table (4,642 / 5,697 records x 39B)
def _candidates_staff(mm: Any) -> np.ndarray:
    a = np.frombuffer(mm, dtype=np.uint8)
    n = a.size - STAFF_STRIDE
    m = np.ones(n, dtype=bool)
    for d in STAFF_ATTRS:
        v = a[d:n + d]
        m &= (v >= 1) & (v <= 20)
    for d in FORMATION_SLOTS:
        m &= a[d:n + d] < 21
    return np.flatnonzero(m)


def _valid_staff(mm: Any, o: int, n: int) -> bool:
    if o + STAFF_STRIDE > n:
        return False
    ca = int.from_bytes(mm[o + 4:o + 6], "little")
    pa = int.from_bytes(mm[o + 6:o + 8], "little")
    if not (0 <= ca <= pa <= 200):
        return False
    for d in STAFF_ATTRS:
        if not (1 <= mm[o + d] <= 20):
            return False
    for d in FORMATION_SLOTS:
        if mm[o + d] >= 21:
            return False
    return True


def locate_staff(mm: Any) -> Optional[Tuple[int, int]]:
    """(base, declared_count) for the 39-byte staff attributes table, or None."""
    key = _cache_key(mm)
    cache = _LOCATOR_CACHE["staff"]
    if key in cache:
        return cache[key]
    n = len(mm)
    for o in _candidates_staff(mm).tolist()[:4000]:
        if not _valid_staff(mm, o, n):
            continue
        k = int.from_bytes(mm[o:o + 4], "little")
        if not (0 <= k < 1_000_000):
            continue
        base = o - k * STAFF_STRIDE
        if base < 12:
            continue
        if not all(mm[base - 4 - 1 - j] == 0xFF for j in range(8)):
            continue
        count = int.from_bytes(mm[base - 4:base], "little")
        if not (0 < count < 1_000_000) or k >= count:
            continue
        if base + count * STAFF_STRIDE > n:
            continue
        if all(int.from_bytes(mm[base + j * STAFF_STRIDE:base + j * STAFF_STRIDE + 4], "little") == j
               for j in range(min(count, 50))):
            res = (base, count)
            cache[key] = res
            return res
    cache[key] = None
    return None


def _process_staff(rec: Dict[str, Any], offset: int) -> Optional[Dict[str, Any]]:
    ca, pa = rec.get("ca", 0), rec.get("pa", 0)
    if not (0 <= ca <= pa <= 200):
        return None
    for attr in STAFF_ATTRS.values():
        val = rec.get(attr, 0)
        if not (1 <= val <= 20):
            return None
    for fslot in FORMATION_SLOTS.values():
        if rec.get(fslot, 0) >= 21:
            return None

    row = {"id2": rec["id2"], "offset": offset}
    for f, v in rec.items():
        if f != "id2":
            row[f] = v
    row["reputation_tier"] = reputation_tier(rec["world_reputation"])
    row["style"] = style(rec["attacking_intent"])
    return row


STAFF_TABLE = FixedTableDef(
    name="staff_attributes",
    record_schema=STAFF,
    locator=locate_staff,
    include_offset=True,
    post_process=_process_staff,
)


# 5. Currencies Catalog (173 records)
def locate_currencies(mm: Any) -> Optional[Tuple[int, int]]:
    """(base, declared_count) for the 173-record currencies catalog, or None."""
    key = _cache_key(mm)
    cache = _LOCATOR_CACHE["currencies"]
    if key in cache:
        return cache[key]
    pat = b"\xff" * 8 + struct.pack("<H", CURRENCY_COUNT)
    pos = 0
    while True:
        idx = mm.find(pat, pos)
        if idx == -1:
            break
        base = idx + len(pat)
        if base + 6 <= len(mm):
            uid, slen = struct.unpack("<HI", mm[base:base + 6])
            if uid == 2 and 5 <= slen <= 25:
                res = (base, CURRENCY_COUNT)
                cache[key] = res
                return res
        pos = idx + 1
    cache[key] = None
    return None


CURRENCIES_CATALOG = StringCatalogDef(
    name="currencies",
    head_schema=CURRENCY_HEAD,
    trailer_schema=CURRENCY_TAIL,
    locator=locate_currencies,
    string_field="name",
    len_field="len",
    null_terminated=False,
    include_offset=True,
    post_process=lambda r, pos: {
        "uid": r["uid"],
        "name": r["name"],
        "exchange_rate": round(r["exchange_rate"], 6),
        "offset": pos,
    },
)

CURRENCIES_TABLE = CURRENCIES_CATALOG
