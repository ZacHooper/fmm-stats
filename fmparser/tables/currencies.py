#!/usr/bin/env python3
"""`currencies` — the 173-record Currencies catalog.

Declared by a `[>= 8 x 0xFF][count u16 = 173]` frame at ~13.98 MB.
Layout: [Uid u16][len u32][Name (UTF-8)][ExchangeRate f32 per GBP].
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..save import cache_key as _cache_key
from ..core import F32, Field, Record, U16, U32, PString
from ..core import TableDef

__all__ = [
    "CURRENCIES_TABLE",
    "CURRENCY_HEAD",
    "CURRENCY_TAIL",
    "currencies_table_spans",
    "locate_currencies",
    "scrape_currencies",
]

CURRENCY_HEAD = Record("currency_head", 2, (
    Field(0, 2, "uid", U16, note="currency unique identifier"),
), is_head=True)

CURRENCY_TAIL = Record("currency_tail", 4, (
    Field(0, 4, "exchange_rate", F32, note="exchange rate units per GBP"),
), is_head=True)

_CURRENCIES_CACHE: Dict[str, Optional[Tuple[int, int]]] = {}


def locate_currencies(mm: Any) -> Optional[Tuple[int, int]]:
    """(base, declared_count) for the currencies catalog, or None.

    Declared by a `[>= 8 x 0xFF][count u16]` frame at ~13.98 MB.
    Record 0 opens with `uid=2 (u16), len=12 (u32), 'Albanian Lek'`.
    """
    key = _cache_key(mm)
    if key in _CURRENCIES_CACHE:
        return _CURRENCIES_CACHE[key]

    sig = struct.pack("<HI", 2, 12) + b"Albanian Lek"
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
            _CURRENCIES_CACHE[key] = res
            return res

    _CURRENCIES_CACHE[key] = None
    return None


CURRENCIES_TABLE = TableDef(
    name="currencies",
    segments=(
        CURRENCY_HEAD,
        PString("name", null_terminated=False),
        CURRENCY_TAIL,
    ),
    locator=locate_currencies,
    include_offset=True,
    post_process=lambda r, pos: {
        "uid": r["uid"],
        "name": r["name"],
        "exchange_rate": round(r["exchange_rate"], 6),
        "offset": pos,
    },
)


def scrape_currencies(mm: Any) -> Dict[int, Dict[str, Any]]:
    """{currency_uid: record} with the exchange rate per GBP."""
    return CURRENCIES_TABLE.id_map(mm, key_field="uid")


def currencies_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """Return [(start, end)] byte spans covering the currencies table and its header."""
    return CURRENCIES_TABLE.spans(mm, include_count_header=True)
