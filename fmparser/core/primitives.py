#!/usr/bin/env python3
"""Low-level byte readers and sentinels for binary savefile parsing.

Everything here is pure: `(buffer, offset) -> value`.
Integers use `struct.unpack_from` so that reads past the buffer end raise IndexError
rather than quietly returning a truncated value.
"""
import struct
from datetime import date, timedelta
from typing import Any, Optional

# Sentinels
NO_ID16 = 0xFFFF          # "no club" / "no reference", in a u16 field
NO_ID32 = 0xFFFFFFFF      # the same idea in a u32 field; also the end-of-chain marker
SEASON_EPOCH = 1971       # season code n means the campaign ending 1971 + n
DATE_EPOCH = date(1900, 1, 1)


def u8(mm: Any, off: int) -> int:
    """Read an unsigned 8-bit integer."""
    return mm[off]


def u16(mm: Any, off: int) -> int:
    """Read a little-endian unsigned 16-bit integer."""
    return struct.unpack_from("<H", mm, off)[0]


def u32(mm: Any, off: int) -> int:
    """Read a little-endian unsigned 32-bit integer."""
    return struct.unpack_from("<I", mm, off)[0]


def i16(mm: Any, off: int) -> int:
    """Read a little-endian signed 16-bit integer."""
    return struct.unpack_from("<h", mm, off)[0]


def i32(mm: Any, off: int) -> int:
    """Read a little-endian signed 32-bit integer."""
    return struct.unpack_from("<i", mm, off)[0]


def f32(mm: Any, off: int) -> float:
    """Read a little-endian 32-bit float via struct (never numpy)."""
    return struct.unpack_from("<f", mm, off)[0]


def u16_or_none(mm: Any, off: int) -> Optional[int]:
    """Read u16 if within buffer bounds, else return None."""
    if 0 <= off <= len(mm) - 2:
        return struct.unpack_from("<H", mm, off)[0]
    return None


def hex4(mm: Any, off: int) -> str:
    """Read 4 bytes as a lowercase hex string."""
    return bytes(mm[off:off + 4]).hex()


def hex2(mm: Any, off: int) -> str:
    """Read 2 bytes as a lowercase hex string."""
    return bytes(mm[off:off + 2]).hex()


def days_to_date(days: int) -> Optional[date]:
    """Convert days since 1900-01-01 to a Python date, or None if invalid."""
    if not (0 <= days <= 73000):
        return None
    return DATE_EPOCH + timedelta(days=days)


def date_to_days(d: date) -> int:
    """Convert a Python date to days since 1900-01-01."""
    return (d - DATE_EPOCH).days


def ymd(mm: Any, off: int) -> Optional[str]:
    """ISO date from a `[day u16][year u16]` pair, or None if it is not a real date."""
    day = struct.unpack_from("<H", mm, off)[0]
    year = struct.unpack_from("<H", mm, off + 2)[0]
    try:
        return (date(year, 1, 1) + timedelta(days=day)).isoformat()
    except (ValueError, OverflowError):
        return None


def ymd_from(year: int, day: int) -> Optional[str]:
    """The same conversion for callers that already hold the two numbers."""
    try:
        return (date(year, 1, 1) + timedelta(days=day)).isoformat()
    except (ValueError, OverflowError):
        return None


# A pitch position as a (band, column) byte pair -- the match slot array and the training
# Focus Pos both store it this way.
POSITION_BANDS = {0x01: "GK", 0x04: "D", 0x08: "DM", 0x10: "M", 0x20: "AM", 0x40: "ST"}
LEFT_FLAG = 0x80          # band byte: the wide-LEFT player of his band
WIDE_RIGHT = 0x08         # column byte: the wide-RIGHT player of his band


def pitch_position(band_byte: int, col_byte: int) -> Optional[str]:
    """One (band, column) pair -> an FM position code ('GK', 'DR', 'DMC', 'AML', 'FC', ...)."""
    band = POSITION_BANDS.get(band_byte & ~LEFT_FLAG)
    if band is None:
        return None
    if band == "GK":
        return "GK"
    if band == "ST":
        return "FC"
    if col_byte == WIDE_RIGHT:
        return band + "R"
    return band + ("L" if band_byte & LEFT_FLAG else "C")


def tag4(mm: Any, off: int) -> str:
    """A 4-byte tag, stored reversed."""
    return bytes(mm[off:off + 4])[::-1].decode("latin-1").strip()


def tag4_to_disk(tag: str) -> bytes:
    """The inverse of tag4: a tag as it appears in the file."""
    return tag.ljust(4)[:4][::-1].encode("latin-1")
