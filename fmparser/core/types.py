#!/usr/bin/env python3
"""Field types and binary primitives for declarative schemas."""
from typing import Any, Dict, Optional, Tuple


class _Unknown:
    """A byte we have decided we cannot name yet. Declaring it UNKNOWN makes it covered AND visible."""
    __slots__ = ()

    def __repr__(self) -> str:
        return "UNKNOWN"

    def __bool__(self) -> bool:
        return False


UNKNOWN = _Unknown()

# Field kind identifiers
U8, U16, U32 = "u8", "u16", "u32"
I16, I32 = "i16", "i32"
F32 = "f32"
DATE = "date"
HEX4, HEX2 = "hex4", "hex2"
RAW = "raw"      # Verbatim byte range (any width)
PAD = "pad"      # Structural filler / declared-unknown span (never emitted)

# Expected byte width for each fixed kind
KIND_WIDTH = {
    U8: 1,
    U16: 2,
    U32: 4,
    I16: 2,
    I32: 4,
    F32: 4,
    DATE: 4,
    HEX4: 4,
    HEX2: 2,
}
VARIABLE_KINDS = frozenset({RAW, PAD})


class PString:
    """Length-prefixed string primitive: `[len u32][bytes (encoding)][\\0?]`.

    Manages reading length-prefixed strings with optional null-terminators and
    character decoding fallbacks.
    """
    __slots__ = ("name", "null_terminated", "allow_empty", "encoding", "fallback_encoding", "max_len")

    def __init__(
        self,
        name: str,
        null_terminated: bool = False,
        allow_empty: bool = False,
        encoding: str = "utf-8",
        fallback_encoding: str = "latin-1",
        max_len: int = 4096,
    ):
        self.name = name
        self.null_terminated = null_terminated
        self.allow_empty = allow_empty
        self.encoding = encoding
        self.fallback_encoding = fallback_encoding
        self.max_len = max_len

    def __repr__(self) -> str:
        flags = []
        if self.null_terminated:
            flags.append("null_terminated=True")
        if self.allow_empty:
            flags.append("allow_empty=True")
        if self.encoding != "utf-8":
            flags.append(f"encoding={self.encoding!r}")
        extra = f", {', '.join(flags)}" if flags else ""
        return f"PString({self.name!r}{extra})"

    def read(self, mm: Any, offset: int, limit: int) -> Optional[Tuple[Dict[str, str], int]]:
        """Read string from `offset` bounded by `limit`.

        Returns `({name: decoded_str}, next_offset)` or `None` if invalid/out-of-bounds.
        """
        if offset + 4 > limit:
            return None
        slen = int.from_bytes(mm[offset:offset + 4], "little")
        lo = 0 if self.allow_empty else 1
        if not (lo <= slen <= self.max_len):
            return None
        term_len = 1 if self.null_terminated else 0
        total_len = 4 + slen + term_len
        if offset + total_len > limit:
            return None
        if self.null_terminated and mm[offset + 4 + slen] != 0:
            return None

        raw = bytes(mm[offset + 4:offset + 4 + slen])
        try:
            val = raw.decode(self.encoding)
        except UnicodeDecodeError:
            val = raw.decode(self.fallback_encoding, errors="replace")
        return {self.name: val}, offset + total_len
