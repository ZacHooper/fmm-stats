#!/usr/bin/env python3
"""`save_header` — the save slot's title, the first 250 bytes of the file.

  [250 B, NUL-padded]  "<d/m/yy> - <manager> (<club nickname>)"   e.g. "9/8/27 - Mr Manager (Frem)"

The date is the in-game date the game wrote the save on, so it dates every save, including
one with no matches. Which campaign it belongs to depends on the career's rollover day, the
day the game starts the new season: it follows the home calendar (Denmark 30 June, Turkey
20 June -- `careers.Career.rollover`), and a save dated on or after it is the next campaign.

A new career's first save is dated before the rollover with no match played: the database
starts already rolled over (its last league positions are the season just gone), so it
belongs to the campaign about to start. A match-less save before the rollover only happens
there, so `campaign()` places it in the next campaign.
"""
import datetime
import re
from typing import Any, Dict, Optional, Tuple

from ..core import Field, RAW, Record

__all__ = ["SAVE_HEADER", "campaign", "read_save_header"]

SAVE_HEADER = Record("save_header", 250, (
    Field(0, 250, "title", RAW, note="NUL-padded text: '<d/m/yy> - <manager> (<nickname>)'"),
), is_head=True)

_TITLE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2}) - (.*) \(([^()]*)\)$")


def read_save_header(mm: Any) -> Dict[str, Optional[str]]:
    """{title, date (ISO), manager, nickname}; the parts are None if the title does not
    read as `d/m/yy - manager (nickname)`."""
    raw = SAVE_HEADER.read(mm, 0)["title"].split(b"\x00")[0]
    title = raw.decode("utf-8", "replace")
    out: Dict[str, Optional[str]] = {"title": title, "date": None, "manager": None,
                                     "nickname": None}
    m = _TITLE.match(title)
    if m:
        day, month, yy = int(m[1]), int(m[2]), int(m[3])
        try:
            out["date"] = datetime.date(2000 + yy, month, day).isoformat()
        except ValueError:
            return out
        out["manager"], out["nickname"] = m[4], m[5]
    return out


def campaign(date: str, has_matches: bool, rollover: Tuple[int, int]) -> int:
    """The campaign's end-year for a save dated `date`: on or after the `rollover`
    (month, day) is the next one, and so is a match-less save before it -- a new career's
    first save, which the database already places in the campaign about to start."""
    d = datetime.date.fromisoformat(date)
    if (d.month, d.day) >= tuple(rollover) or not has_matches:
        return d.year + 1
    return d.year
