#!/usr/bin/env python3
"""`attribute_changes` — the change arrows on a player's profile: a signed change per attribute.

Between [player progress](player_progress.py) and the [training](training.py) table's count,
both games, with no count or frame of its own:

    [person count x 23 B]      row k = person tid k (the count is training's)

Each byte is an i8: the change the profile marks with an arrow beside that attribute, one up
or down arrow for 1, a double arrow for 2 or more (Zac Bell's +3 Stamina shows as a double).
Zero is no arrow. Only the managed club's players have rows set, youth candidates included
(the 16-year-old youth candidate Barnaby Dolaghan has two). Every row is zero
on a day-one save; 3 are set on truro-2026-08-08, 23 on 16 Nov, 29 to 55 on the FMM22 saves.
Values run -3 to +3.

**The columns**, pinned on seven Player Profile screens of truro-2026-11-16
(`tests/test_attribute_changes_evidence.py`): every arrow on the screen is a non-zero byte in
its column with the arrow's sign, and every other column is zero.

     0-5    Crossing, Dribbling, Aerial, Passing, Shooting, Tackling
     6-7    not named; by position Technique and Aggression
     8-13   Creativity, Decisions, Leadership, Movement, Positioning, Teamwork
    14-16   Pace, Stamina, Strength
    17-19   not named; by position the goalkeeper's Agility, Communication and
            Handling
    20-22   Kicking, Reflexes, Throwing (goalkeepers)

No Truro save sets the five unnamed columns; 11 rows across the FMM22 saves do (column 6
three times, 18 and 19 on goalkeepers), with no screen to name them yet.

**What the change is measured from.** Not the season start, and not one fixed day: a row can
hold a change from August next to one from November (En-Neyah's −1 is on both the 8 Aug and
16 Nov saves). The stated attributes the store reads (a player's scrapbook entry, written on
the 1st of a month) already include some of a row's changes and not others, so a row is not a
correction to add to them.

**How it is found.** From the end of player progress to four bytes before the training rows
(training's u32 person count); accepted only if that span is exactly the count x 23.
"""
from typing import Any, Dict, List, Optional, Tuple

from ..core import Field, I8, Record, TableDef, UNKNOWN
from ..save import cache_key as _cache_key

__all__ = ["ATTRIBUTE_CHANGE", "ATTRIBUTE_CHANGES_TABLE", "COLUMNS",
           "attribute_changes_table_spans", "locate_attribute_changes",
           "scrape_attribute_changes"]

# Column -> attribute, None where no screen has named the column yet (a row still emits it,
# as unknown_<column>).
COLUMNS = ("Crossing", "Dribbling", "Aerial", "Passing", "Shooting", "Tackling", None, None,
           "Creativity", "Decisions", "Leadership", "Movement", "Positioning", "Teamwork",
           "Pace", "Stamina", "Strength", None, None, None, "Kicking", "Reflexes", "Throwing")
_GUESS = {6: "Technique", 7: "Aggression", 17: "Agility", 18: "Communication",
          19: "Handling"}
STRIDE = len(COLUMNS)

ATTRIBUTE_CHANGE = Record("attribute_change", STRIDE, tuple(
    Field(k, 1, name, I8) if name else
    Field(k, 1, UNKNOWN, I8, note=f"not named; by position {_GUESS[k]}")
    for k, name in enumerate(COLUMNS)))

_CACHE: Dict[Any, Optional[Tuple[int, int]]] = {}


def locate_attribute_changes(mm: Any) -> Optional[Tuple[int, int]]:
    """(row 0, person count), or None: the bytes between player progress and the training
    table's count, accepted only if they are exactly one row per person."""
    key = _cache_key(mm)
    if key in _CACHE:
        return _CACHE[key]
    from .player_progress import PROGRESS_ROW, locate_player_progress
    from .training import locate_training
    res = None
    pp, tr = locate_player_progress(mm), locate_training(mm)
    if pp and tr:
        base, end, n = pp[0] + pp[1] * PROGRESS_ROW.span, tr[0] - 4, tr[1]
        if end - base == n * STRIDE:
            res = (base, n)
    _CACHE[key] = res
    return res


def attribute_changes_table_spans(mm: Any) -> List[Tuple[int, int]]:
    loc = locate_attribute_changes(mm)
    return [(loc[0], loc[0] + loc[1] * STRIDE)] if loc else []


ATTRIBUTE_CHANGES_TABLE = TableDef(name="attribute_changes", segments=(ATTRIBUTE_CHANGE,),
                                   locator=locate_attribute_changes)


def scrape_attribute_changes(mm: Any) -> List[Dict[str, Any]]:
    """Every row with a change, in tid order: `tid` and the 23 columns, by attribute name
    (`unknown_<column>` for the five not yet named). Raises `ValueError` when not
    located."""
    loc = locate_attribute_changes(mm)
    if loc is None:
        raise ValueError("attribute_changes: player progress to training is not one row "
                         "per person")
    base, n = loc
    names = [name or f"unknown_{k}" for k, name in enumerate(COLUMNS)]
    out = []
    for tid in range(n):
        row = mm[base + tid * STRIDE:base + (tid + 1) * STRIDE]
        if any(row):
            out.append({"tid": tid, **{name: (b - 256 if b > 127 else b)
                                       for name, b in zip(names, row)}})
    return out
