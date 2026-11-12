#!/usr/bin/env python3
"""`id_list` — an unread list of ids between the currencies and the languages.

    [>= 8 x ff][count u16]                 888 on every FMM22 save, 924 on Truro
    per row: [id u32][3 bytes]             7 bytes; ids ascending with gaps, 1 to 3,221

The walk ends on the languages table's own frame on every save. The three bytes are
`00 00 00` on every FMM22 row and `ff ff 00` on every FMM27 one. The last FMM27 id is
2,000,254,886, not a small id. What the ids name is open: they match no id field of the
person, club, competition, nation, stadium, city, staff, official or rule-file tables.
"""
from typing import Any, Dict, List, Optional, Tuple

from ..core import Field, Record, TableDef, RAW, U32, UNKNOWN
from ..save import cache_key as _cache_key
from .clubs import after_frame
from .currencies import CURRENCIES_TABLE
from .languages import locate_languages

__all__ = ["ID_LIST_ROW", "ID_LIST_TABLE", "locate_id_list", "scrape_id_list"]

ID_LIST_ROW = Record("id_list_row", 7, (
    Field(0, 4, "id", U32, note="ascending, with gaps"),
    Field(4, 3, UNKNOWN, RAW, note="00 00 00 on FMM22, ff ff 00 on FMM27, every row"),
))

_CACHE: Dict[Any, Optional[Tuple[int, int]]] = {}


def locate_id_list(mm: Any) -> Optional[Tuple[int, int]]:
    """(record 0, count): the frame after the currencies, whose rows end on the 0xFF run in
    front of the languages table's count. None otherwise."""
    key = _cache_key(mm)
    if key in _CACHE:
        return _CACHE[key]
    res = None
    spans = CURRENCIES_TABLE.spans(mm)
    lang = locate_languages(mm)
    if spans and lang:
        loc = after_frame(mm, spans[-1][1], 2)
        if loc is not None:
            end = loc[0] + loc[1] * ID_LIST_ROW.span
            frame = lang[0] - 2
            if end < frame and all(b == 0xFF for b in mm[end:frame]) and frame - end >= 8:
                res = loc
    _CACHE[key] = res
    return res


ID_LIST_TABLE = TableDef(name="id_list", segments=(ID_LIST_ROW,), locator=locate_id_list)


def scrape_id_list(mm: Any) -> List[Dict[str, Any]]:
    """Every row. Raises `ValueError` when not located."""
    if locate_id_list(mm) is None:
        raise ValueError("id_list: no frame after the currencies that ends on the languages")
    return ID_LIST_TABLE.scrape(mm)
