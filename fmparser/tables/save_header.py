#!/usr/bin/env python3
"""`save_header` — the save slot's title, the first 250 bytes of the file.

  [250 B, NUL-padded]  "<d/m/yy> - <manager> (<club nickname>)"   e.g. "9/8/27 - Mr Manager (Frem)"

The date is the in-game date the game wrote the save on, so it dates every save, including
one with no matches. It is the snapshot's identity; which campaign it belongs to is the
career's rollover rule, applied by the loader (`careers.campaign`).
"""
import datetime
import re
from typing import Any, Dict, Optional

from ..core import Field, RAW, Record

__all__ = ["SAVE_HEADER", "read_save_header"]

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

