#!/usr/bin/env python3
"""`save_header` — the save slot's title, the first 250 bytes of the file.

  [250 B, NUL-padded]  "<d/m/yy> - <manager> (<club nickname>)"   e.g. "9/8/27 - Mr Manager (Frem)"

The date is the in-game date the game wrote the save on, so it dates every save, including
one with no matches. The game's new season starts on 30 June (the club record's last league
position changes between the 29 June and 30 June saves of 2023, 2024, 2025 and 2026), so a
save dated 30 June or later belongs to the next campaign.

The one save a date cannot place is a new career's first, dated before 30 June with no
match played: the database starts already rolled over (its last league positions are the
season just gone), so it belongs to the campaign about to start. `campaign()` returns None
for it and the caller supplies the season.
"""
import datetime
import re
from typing import Any, Dict, Optional

from ..core import Field, RAW, Record

__all__ = ["ROLLOVER", "SAVE_HEADER", "campaign", "read_save_header"]

SAVE_HEADER = Record("save_header", 250, (
    Field(0, 250, "title", RAW, note="NUL-padded text: '<d/m/yy> - <manager> (<nickname>)'"),
), is_head=True)

ROLLOVER = (6, 30)            # (month, day) the game's new season starts

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


def campaign(date: str, has_matches: bool) -> Optional[int]:
    """The campaign's end-year for a save dated `date`: 30 June or later is the next one.
    None for a match-less save before 30 June -- a new career's first save, which the
    database already places in the campaign about to start."""
    d = datetime.date.fromisoformat(date)
    if (d.month, d.day) >= ROLLOVER:
        return d.year + 1
    return d.year if has_matches else None
