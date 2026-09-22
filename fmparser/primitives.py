#!/usr/bin/env python3
"""The byte readers, written once.

DEPRECATED: This module is maintained for backward compatibility with unmigrated parsers.
It will be removed once all domain parsers are migrated to `fmparser.core`.
New code should import directly from `fmparser.core`.
"""
import struct
from datetime import date, timedelta
from typing import Any, Optional

from .core.primitives import (
    DATE_EPOCH,
    NO_ID16,
    NO_ID32,
    SEASON_EPOCH,
    date_to_days,
    days_to_date,
    f32,
    hex2,
    hex4,
    i16,
    i32,
    tag4,
    tag4_to_disk,
    u8,
    u16,
    u16_or_none,
    u32,
    ymd,
)

# ---------------------------------------------------------------------------------------
# Sentinels. Declared once, under one name each.
#
# The no-club sentinel was previously declared four times under three names (`NO_CLUB`,
# `NOCLUB`, and a bare `0xffff` literal), and the person record reads it 4 bytes wide while
# every comparison downstream is 2 bytes wide -- see `staging.INFO_LAYOUT`'s `club_tid` note.
# Both widths are named here so that normalisation is a visible step rather than a coincidence.
# ---------------------------------------------------------------------------------------
NO_ID16 = 0xFFFF          # "no club" / "no reference", in a u16 field
NO_ID32 = 0xFFFFFFFF      # the same idea in a u32 field; also the end-of-chain marker
SEASON_EPOCH = 1971       # season code n means the campaign ending 1971 + n


# ---------------------------------------------------------------------------------------
# Integers. `struct` throughout, so a read past the end of the buffer RAISES rather than
# quietly returning a truncated value.
# ---------------------------------------------------------------------------------------
def u8(mm, off):
    return mm[off]


def u16(mm, off):
    return struct.unpack_from("<H", mm, off)[0]


def u32(mm, off):
    return struct.unpack_from("<I", mm, off)[0]


def i16(mm, off):
    return struct.unpack_from("<h", mm, off)[0]


def i32(mm, off):
    return struct.unpack_from("<i", mm, off)[0]


def f32(mm, off):
    """A 32-bit float, via `struct` and NEVER via numpy.

    `np.float32` is not JSON-serialisable and its `repr` differs from the builtin's, so a
    numpy-backed reader changes `extract.py`'s output bytes even when the value is the same
    number. The columnar path in `history.py` uses numpy on purpose and converts at the edge.
    """
    return struct.unpack_from("<f", mm, off)[0]


def u16_or_none(mm, off):
    """`u16` for callers walking to the edge of a bounded buffer, where running off the end is
    an expected outcome and not an error (`injuries.py` reads a weekly series this way)."""
    if 0 <= off <= len(mm) - 2:
        return struct.unpack_from("<H", mm, off)[0]
    return None


def hex4(mm, off):
    """4 bytes as a lowercase hex string -- for id fields we carry but never do arithmetic on
    (the person record's `sid`, which is `ffffffff` for staff). Kept textual so a sentinel
    stays legible."""
    return bytes(mm[off:off + 4]).hex()


def hex2(mm, off):
    """2 bytes as a lowercase hex string.

    A separate reader rather than a width argument because the two are NOT the same field
    written differently: the person record's `sid` is 4 bytes and the match player block's
    `sid` is 2, and conflating those widths is exactly the bug that was just deleted with
    `reference.parse_info`. Declaring the width per record keeps `schema.validate` able to
    check it.
    """
    return bytes(mm[off:off + 2]).hex()


# ---------------------------------------------------------------------------------------
# Dates. The save stores `[day-of-year u16][year u16]`, day 0-based.
# ---------------------------------------------------------------------------------------
def ymd(mm, off):
    """ISO date from a `[day u16][year u16]` pair, or None if it is not a real date.

    Returning None rather than raising is the established behaviour: an empty person slot
    carries garbage here (joined dates in 1290 and 2570) and the caller blanks the whole block
    on `uid == 0` instead of on the date. Do not turn this into a plausibility window -- that
    argument is settled in `staging._decode_info` and the reasoning is recorded there.
    """
    day = struct.unpack_from("<H", mm, off)[0]
    year = struct.unpack_from("<H", mm, off + 2)[0]
    try:
        return (date(year, 1, 1) + timedelta(days=day)).isoformat()
    except (ValueError, OverflowError):
        return None


def ymd_from(year, day):
    """The same conversion for callers that already hold the two numbers (match headers read
    them from separate fields)."""
    try:
        return (date(year, 1, 1) + timedelta(days=day)).isoformat()
    except (ValueError, OverflowError):
        return None


def season_end_year(code):
    """Season code -> the end-year of that campaign. 50 is the 2020/21 season."""
    return SEASON_EPOCH + code


# ---------------------------------------------------------------------------------------
# Strings.
# ---------------------------------------------------------------------------------------
# DEPRECATED: pstring is removed in favor of `from fmparser.core import PString`



def tag4(mm, off):
    """A 4-byte tag, stored REVERSED. `datadict.py` and `tagged.py` read these 13 times
    between them; the reversal is the thing that is easy to drop."""
    return bytes(mm[off:off + 4])[::-1].decode("latin-1").strip()


def tag4_to_disk(tag):
    """The inverse: a tag as it appears in the file, for searching."""
    return tag.ljust(4)[:4][::-1].encode("latin-1")
