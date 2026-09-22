#!/usr/bin/env python3
"""`languages` — the 124-record Languages catalog.

Declared by a `[>= 8 x 0xFF][count u16 = 124]` frame in the reference block (~13.97 MB).
Composite layout:
  [id u16][uid u32] -> Record("language_head", 6)
  [len u32][name (utf-8)] -> PString("name")
  [len u32][other_name (utf-8, allow_empty=True)] -> PString("other_name", allow_empty=True)
  [nation_id u16][difficulty u8] -> Record("language_tail", 3)
"""
import struct
from typing import Any, Dict, List, Optional, Tuple

from ..save import cache_key as _cache_key
from ..schema import Field, Record, U16, U32, U8, PString
from .engine import TableDef

__all__ = [
    "LANGUAGES_TABLE",
    "LANGUAGE_HEAD",
    "LANGUAGE_TAIL",
    "languages_table_spans",
    "locate_languages",
    "scrape_languages",
]

LANGUAGE_HEAD = Record("language_head", 6, (
    Field(0, 2, "id", U16, note="what person record language list references"),
    Field(2, 4, "uid", U32),
), is_head=True)

LANGUAGE_TAIL = Record("language_tail", 3, (
    Field(0, 2, "nation_id", U16),
    Field(2, 1, "difficulty", U8),
), is_head=True)

_LANGUAGES_CACHE: Dict[str, Optional[Tuple[int, int]]] = {}


def locate_languages(mm: Any) -> Optional[Tuple[int, int]]:
    """(base, declared_count) for the 124-record languages catalog, or None.

    Declared by a `[>= 8 x 0xFF][count u16]` frame at ~13.97 MB.
    Record 0 opens with `id=0, uid=1, len=8, 'Albanian'`.
    """
    key = _cache_key(mm)
    if key in _LANGUAGES_CACHE:
        return _LANGUAGES_CACHE[key]

    sig = struct.pack("<HII", 0, 1, 8) + b"Albanian"
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
            _LANGUAGES_CACHE[key] = res
            return res

    _LANGUAGES_CACHE[key] = None
    return None


LANGUAGES_TABLE = TableDef(
    name="languages",
    segments=(
        LANGUAGE_HEAD,
        PString("name", null_terminated=False),
        PString("other_name", null_terminated=False, allow_empty=True),
        LANGUAGE_TAIL,
    ),
    locator=locate_languages,
    include_offset=True,
)


def scrape_languages(mm: Any) -> Dict[int, Dict[str, Any]]:
    """{language_id: record} for every language in the save."""
    return LANGUAGES_TABLE.id_map(mm, key_field="id")


def languages_table_spans(mm: Any) -> List[Tuple[int, int]]:
    """Return [(start, end)] byte spans covering the languages table and count header."""
    return LANGUAGES_TABLE.spans(mm, include_count_header=True)
