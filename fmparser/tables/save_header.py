#!/usr/bin/env python3
"""`save_header` — the save slot's header, at the start of the file. Two formats:

FMM22: the first 250 bytes, NUL-padded text.

  [250 B, NUL-padded]  "<d/m/yy> - <manager> (<club nickname>)"   e.g. "9/8/27 - Mr Manager (Frem)"

FMM27: length-prefixed strings around fixed binary blocks (u32-length `pstring`s throughout).

  pstring   club name                   "Truro City"
  pstring   name_2                      "Truro"     } which is the short name and which the
  pstring   name_3                      "Truro"     } nickname is not yet shown
  64 B      stamp (FMM27_STAMP): the in-game date, the real-world write time
  pstring   build                       "27.0.0-d+2495469"
  pstring   channel                     "fmm27-rel-staging"
  1 B
  pstring   build_2                     "27.0.0+2495469"
  pstring   channel_2
  14 B      (FMM27_VERSIONS)
  pstring   channel_3
  pstring   build_3
  ...       not yet declared: where the header ends is not proved

The FMM27 header carries no manager name.

The date is the in-game date the game wrote the save on, so it dates every save, including
one with no matches. It is the snapshot's identity; which campaign it belongs to is the
career's rollover rule, applied by the loader (`careers.campaign`).

Which format a save is in is the version the save declares: FMM27 names itself in its channel
string (`fmm27-rel-staging`), the first `fmm<NN>-` pstring in the header. FMM22 declares no
version, so a save that declares none is read as FMM22. A declared version with no reader here
(`fmm26`) is returned as declared and reads no date.
"""
import datetime
import re
import struct
from typing import Any, Dict, Optional

from ..core import DATE, Field, PString, RAW, Record, TableDef, U16, U32, U8, UNKNOWN
from ..core.table import table_spans

__all__ = ["SAVE_HEADER", "FMM27_HEADER", "FMM22", "FMM27", "save_format",
           "save_header_end", "read_save_header"]

FMM22, FMM27 = "fmm22", "fmm27"

SAVE_HEADER = Record("save_header", 250, (
    Field(0, 250, "title", RAW, note="NUL-padded text: '<d/m/yy> - <manager> (<nickname>)'"),
), is_head=True)

_TITLE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2}) - (.*) \(([^()]*)\)$")

# The block after the three names. `date` and `written_at` are the two fields that differ
# between two saves of one career three in-game days apart (with `written_hour`/`_minute`);
# `written_at` is a Unix timestamp, the hour and minute the same moment in local time.
FMM27_STAMP = Record("save_header_fmm27_stamp", 64, (
    Field(0,  4, UNKNOWN, U32, note="3,125 on both Truro saves"),
    Field(4,  24, UNKNOWN, RAW),
    Field(28, 4, "date", DATE),
    Field(32, 3, UNKNOWN, RAW),
    Field(35, 4, "written_at", U32, note="Unix time, seconds"),
    Field(39, 8, UNKNOWN, RAW),
    Field(47, 1, "written_hour", U8),
    Field(48, 1, "written_minute", U8),
    Field(49, 1, UNKNOWN, RAW),
    Field(50, 4, UNKNOWN, U32, note="27,000,034: the client version?"),
    Field(54, 4, UNKNOWN, U32, note="27,000,034 again"),
    Field(58, 6, UNKNOWN, RAW),
), is_head=True)

FMM27_GAP = Record("save_header_fmm27_gap", 1, (
    Field(0, 1, UNKNOWN, RAW),
), is_head=True)

FMM27_VERSIONS = Record("save_header_fmm27_versions", 14, (
    Field(0,  4, UNKNOWN, U32, note="27,000,034"),
    Field(4,  4, UNKNOWN, U32, note="27,000,034"),
    Field(8,  2, UNKNOWN, U16, note="2,706"),
    Field(10, 2, UNKNOWN, U16, note="2,700"),
    Field(12, 2, UNKNOWN, U16, note="2,026"),
), is_head=True)

_MAX_NAME = 256


_CHANNEL = re.compile(rb"fmm(\d{2})-")
_VERSION_SCAN = 0x200     # the FMM27 header's strings all sit in its first 0xe6 bytes


def save_format(mm: Any) -> str:
    """The declared game version, `fmm<NN>`, from the first `fmm<NN>-` pstring in the header;
    FMM22 when the save declares none."""
    head = bytes(mm[:_VERSION_SCAN + 4 + _MAX_NAME])
    for o in range(min(_VERSION_SCAN, len(head) - 4)):
        n = struct.unpack_from("<I", head, o)[0]
        if 6 <= n <= _MAX_NAME and o + 4 + n <= len(head):
            m = _CHANNEL.match(head, o + 4, o + 4 + n)
            if m:
                return "fmm" + m[1].decode()
    return FMM22


FMM27_HEADER = TableDef(
    name="save_header_fmm27",
    segments=(
        PString("club", max_len=_MAX_NAME),
        PString("name_2", max_len=_MAX_NAME),
        PString("name_3", max_len=_MAX_NAME),
        FMM27_STAMP,
        PString("build", max_len=_MAX_NAME),
        PString("channel", max_len=_MAX_NAME),
        FMM27_GAP,
        PString("build_2", max_len=_MAX_NAME),
        PString("channel_2", max_len=_MAX_NAME),
        FMM27_VERSIONS,
        PString("channel_3", max_len=_MAX_NAME),
        PString("build_3", max_len=_MAX_NAME),
    ),
    locator=lambda mm: (0, 1) if save_format(mm) == FMM27 else None,
)


def save_header_end(mm: Any) -> int:
    """Where the declared header ends: the first byte any table can start at."""
    if save_format(mm) == FMM27:
        spans = table_spans(mm, FMM27_HEADER, include_count_header=False)
        if spans:
            return spans[0][1]
    return SAVE_HEADER.span


def read_save_header(mm: Any) -> Dict[str, Optional[str]]:
    """{title, date (ISO), manager, nickname, format}; the parts are None where the header
    does not read, and `format` is always the declared version (`save_format`). FMM22's title is `d/m/yy - manager (nickname)`; FMM27 has no title text, so its
    title is the club name and it names no manager or nickname. A declared version with no
    reader reads as all None."""
    fmt = save_format(mm)
    if fmt != FMM22:
        rows = FMM27_HEADER.scrape(mm) if fmt == FMM27 else []
        if not rows:
            return {"title": None, "date": None, "manager": None, "nickname": None,
                    "format": fmt}
        return {"title": rows[0]["club"], "date": rows[0]["date"], "manager": None,
                "nickname": None, "format": fmt}
    raw = SAVE_HEADER.read(mm, 0)["title"].split(b"\x00")[0]
    title = raw.decode("utf-8", "replace")
    out: Dict[str, Optional[str]] = {"title": title, "date": None, "manager": None,
                                     "nickname": None, "format": FMM22}
    m = _TITLE.match(title)
    if m:
        day, month, yy = int(m[1]), int(m[2]), int(m[3])
        try:
            out["date"] = datetime.date(2000 + yy, month, day).isoformat()
        except ValueError:
            return out
        out["manager"], out["nickname"] = m[4], m[5]
    return out
