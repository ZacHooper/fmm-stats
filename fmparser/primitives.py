#!/usr/bin/env python3
"""The byte readers, written once.

Before this module there were 12 `_u16`s, 9 `_u32`s, 5 `_f32`s, 5 date decoders, 9
length-prefixed-string readers and 13 hand-rolled reversed-tag reads across `fmparser/`, in
two different idioms (`int.from_bytes` and `struct.unpack_from`) that are not interchangeable
at the edges: `struct.unpack_from` raises past the end of the buffer, `int.from_bytes` on a
short slice silently returns a SMALLER NUMBER. A parser that walks to the end of a region gets
a different failure depending on which copy it happened to import.

Everything here is pure: `(buffer, offset) -> value`. No locating, no plausibility windows, no
caching. Those are the parts that are genuinely different per record, and pretending otherwise
is how a shared helper starts lying.

TWO THINGS DELIBERATELY NOT HERE
--------------------------------
**Money.** The save uses four different money conventions -- contract wage units (x520 for
GBP/yr), transfer fees in thousands, an f32 of whole GBP, and a u32 of whole GBP -- and which
one applies is a property of the RECORD, not of the byte width. A shared `money()` helper
would let a call site be wrong by a factor of 520 while still returning a plausible number,
which is exactly the class of bug that is invisible in review. Each record converts its own.

**Plausibility windows.** `1 <= ln <= 120` for a stadium name, `0 < cid < 20000`, the DOB year
gate -- these look like validation but they are LOCATING: each is separately measured evidence
about one table, and centralising them would make a table's extent a function of a shared
constant instead of its own invariant. See `docs/parser-architecture.md`.

The one exception is `pstring`, which takes its `maxlen` as an argument precisely so the
caller keeps owning that number.
"""
import struct
from datetime import date, timedelta

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
    (`sid`, which is `ffffffff` for staff). Kept textual so a sentinel stays legible."""
    return bytes(mm[off:off + 4]).hex()


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
def pstring(mm, off, hi, maxlen, encoding="utf-8"):
    """`(text, next_offset)` for a `[len u32][bytes]` string, or `(None, None)`.

    The length prefix is **u32**, not one byte. `docs/table-framing.md` writes these as
    `[7]'Algeria'` and the real bytes are `07 00 00 00 'Algeria'`; a search written from that
    description returns zero hits, which cost a hunt.

    `hi` bounds the read and `maxlen` is the caller's own measured ceiling for this table --
    both stay arguments so the string reader never owns a table's extent.
    """
    if off < 0 or off + 4 > hi:
        return None, None
    ln = struct.unpack_from("<I", mm, off)[0]
    if not (1 <= ln <= maxlen) or off + 4 + ln > hi:
        return None, None
    try:
        return bytes(mm[off + 4:off + 4 + ln]).decode(encoding), off + 4 + ln
    except UnicodeDecodeError:
        return None, None


def tag4(mm, off):
    """A 4-byte tag, stored REVERSED. `datadict.py` and `tagged.py` read these 13 times
    between them; the reversal is the thing that is easy to drop."""
    return bytes(mm[off:off + 4])[::-1].decode("latin-1").strip()


def tag4_to_disk(tag):
    """The inverse: a tag as it appears in the file, for searching."""
    return tag.ljust(4)[:4][::-1].encode("latin-1")
