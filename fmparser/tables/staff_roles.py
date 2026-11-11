#!/usr/bin/env python3
"""`coaches`, `scouts`, `physios` — the three 7-byte staff role tables.

They follow the staff table directly, in that order, each `[>= 8 x 0xFF][count u32]` and
then `[id u32][specialism u8][u8][aptitude u8]` rows with `id == slot index` (fmm-editor's
FMM26 `Coach`). A person points at his row: the person record's `coach_row`, `scout_row` and
`physio_row` (person_info). Every row is pointed at by at most one person; a manager has no
coach row unless he is the user. The same layout on FMM22 and FMM27.

    Frem    1,971 / 560 / 816 rows        Truro   2,841 / 772 / 1,157 rows

The Staff Profile shows `specialism` (a code per role: coach 1 General, physio 2 Prevention)
and `aptitude` (1 Poor, 3 Natural).
"""
from typing import Any, Dict, List, Optional, Tuple

from ..core import Field, Record, TableDef, U8, U32, UNKNOWN
from ..save import cache_key as _cache_key
from .clubs import after_frame
from .staff import STAFF_STRIDE, locate_staff

__all__ = [
    "COACHES_TABLE",
    "PHYSIOS_TABLE",
    "ROLE_TABLES",
    "SCOUTS_TABLE",
    "STAFF_ROLE",
    "locate_staff_roles",
    "scrape_staff_roles",
]

STAFF_ROLE = Record("staff_role", 7, (
    Field(0, 4, "id", U32, note="== the slot index"),
    Field(4, 1, "specialism", U8, note="per role: coach 1 General; physio 2 Prevention"),
    Field(5, 1, UNKNOWN, U8, note="1-3; 1 on both Bronze Badge profiles: the badge?"),
    Field(6, 1, "aptitude", U8, note="1 Poor, 3 Natural; 255 on the user"),
))

ROLES = ("coaches", "scouts", "physios")
_CACHE: Dict[Any, Optional[List[Tuple[int, int]]]] = {}


def locate_staff_roles(mm: Any) -> Optional[List[Tuple[int, int]]]:
    """[(record 0, count)] for coaches, scouts and physios, chained from the staff table's
    end; None if any frame is missing."""
    key = _cache_key(mm)
    if key in _CACHE:
        return _CACHE[key]
    res: Optional[List[Tuple[int, int]]] = None
    st = locate_staff(mm)
    if st is not None:
        end, runs = st[0] + st[1] * STAFF_STRIDE, []
        for _ in ROLES:
            loc = after_frame(mm, end, 4)
            if loc is None:
                break
            runs.append(loc)
            end = loc[0] + loc[1] * STAFF_ROLE.span
        if len(runs) == len(ROLES):
            res = runs
    _CACHE[key] = res
    return res


def _role_table(k: int, name: str) -> TableDef:
    def locator(mm: Any) -> Optional[Tuple[int, int]]:
        runs = locate_staff_roles(mm)
        return runs[k] if runs else None
    return TableDef(name=name, segments=(STAFF_ROLE,), locator=locator,
                    invariant=lambda rec, slot: rec["id"] == slot)


COACHES_TABLE, SCOUTS_TABLE, PHYSIOS_TABLE = (_role_table(k, n) for k, n in enumerate(ROLES))
ROLE_TABLES = dict(zip(ROLES, (COACHES_TABLE, SCOUTS_TABLE, PHYSIOS_TABLE)))


def scrape_staff_roles(mm: Any) -> Dict[str, List[Dict[str, Any]]]:
    """{role: rows} for coaches, scouts and physios, every row as stored plus `tid`: the
    person whose record points at it (None for a row nobody points at). Raises `ValueError`
    if a table is not located or does not walk to its declared count."""
    from .person_info import person_role_rows
    runs = locate_staff_roles(mm)
    if runs is None:
        raise ValueError("staff roles: the tables are not located after the staff table")
    owners = person_role_rows(mm)
    out = {}
    for role, (_, count) in zip(ROLES, runs):
        rows = ROLE_TABLES[role].scrape(mm)
        if len(rows) != count:
            raise ValueError(f"{role}: walk read {len(rows)} of {count} declared rows")
        who = owners[role]
        out[role] = [{"id": r["id"], "tid": who.get(r["id"]), "specialism": r["specialism"],
                      "aptitude": r["aptitude"]} for r in rows]
    return out
