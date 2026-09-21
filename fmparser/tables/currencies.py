#!/usr/bin/env python3
"""`currencies` — the 173-record Currencies catalog.

Declared by a `[>= 8 x 0xFF][count u16 = 173]` frame at ~13.98 MB.
Layout: [Uid u16][len u32][Name (UTF-8)][ExchangeRate f32 per GBP].
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..save import cache_key as _cache_key
from ..schema import F32, Field, Record, U16, U32
from .engine import StringCatalogDef

__all__ = [
    "CURRENCIES_CATALOG",
    "CURRENCIES_TABLE",
    "CURRENCY_COUNT",
    "CURRENCY_HEAD",
    "CURRENCY_TAIL",
    "currencies_table_spans",
    "locate_currencies",
    "scrape_currencies",
]

CURRENCY_COUNT = 173

CURRENCY_HEAD = Record("currency_head", 6, (
    Field(0, 2, "uid", U16, note="currency unique identifier"),
    Field(2, 4, "len", U32, note="length of UTF-8 name in bytes"),
), is_head=True)

CURRENCY_TAIL = Record("currency_tail", 4, (
    Field(0, 4, "exchange_rate", F32, note="exchange rate units per GBP"),
), is_head=True)

_CURRENCIES_CACHE: Dict[str, Optional[Tuple[int, int]]] = {}


def locate_currencies(mm: Any) -> Optional[Tuple[int, int]]:
    """(base, declared_count) for the 173-record currencies catalog, or None."""
    key = _cache_key(mm)
    if key in _CURRENCIES_CACHE:
        return _CURRENCIES_CACHE[key]

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
                _CURRENCIES_CACHE[key] = res
                return res
        pos = idx + 1

    _CURRENCIES_CACHE[key] = None
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


def scrape_currencies(mm: Any) -> Dict[int, Dict[str, Any]]:
    """{currency_uid: record} with the exchange rate per GBP."""
    return CURRENCIES_CATALOG.id_map(mm, key_field="uid")


def currencies_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """Return [(start, end)] byte spans covering the currencies table and its header."""
    return CURRENCIES_CATALOG.spans(mm, include_count_header=True)
