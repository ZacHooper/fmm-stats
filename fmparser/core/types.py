#!/usr/bin/env python3
"""Field types and binary primitives for declarative schemas.

Two encodings of a value: PACKED fields at fixed offsets (the kinds `U8` .. `PAD`, and the
length-prefixed `PString`), and the TAGGED format, where each field carries its own
tag and type code (`read_tree`, below).
"""
import struct
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


# ---- the TAGGED format -----------------------------------------------------------------------
# The save's data dictionary (`tables/rule_files.py`) and the archive's `comp_<uid>.dat`
# members (`tables/comp_rules.py`) store key-value fields in one format:
#
#     field = [tag: 4 bytes, REVERSED][0x01][type][value]      tagged
#           = [0x01][type][value]                              tagless (a list element)
#
#     type            size            value
#     0x00             0              none
#     0x01 0x13        4              u32
#     0x15             4              u32 id (`Ttea` = a team, repeated by the next `DBID`)
#     0x02             4              a reference: a reversed four-character code
#     0x03 0x11        1              u8
#     0x12             2              u16
#     0x19             4              f32 (kept as its raw u32)
#     0x20             4              u32 (the timestamp in the file trailer `EdDt`)
#     0x0f             8              a PAIR of u32; a name id stored this way repeats (28, 28)
#     0x14 0x18        8              u64
#     0x05             8              f64 (prize money: `cash` = 150000.0)
#     0x0a             4 + children   CONTAINER: u32 child count, then the children
#     0x0b             4 + elements   LIST: u32 element count, then that many tagless fields
#     0x1a             4 + len        STRING: u32 byte length, then the bytes (latin-1)
#
# A tag is usually four printable characters, but not always: the discipline rules (`dsrl`)
# carry fields whose tag is an arbitrary u32 (`20 7d 96 16`). Such a tag is read only where
# neither a printable tag nor a tagless field fits, and is named `#` + its eight hex digits
# in the same reversed order (`#16967d20`).
#
# The TYPE CODE is the byte after the 0x01 marker: it says how many bytes the value takes,
# and the `TYPE_*` constants below name it. It is not what the value MEANS -- that is the
# schema's kind (`schema.INT`, `schema.STRING`, ...), and one kind may accept several codes
# (`INT` takes a u8, a u16, a u32 ...).
#
# `read_tree` is STRICT: it is only ever called on a block whose extent is declared (a
# field count), so anything that does not parse is an error, never a shorter result. The
# schemas that name what the fields mean are declared per tag (`schema.TaggedRecord`).

TYPE_CONTAINER = 0x0a
TYPE_LIST = 0x0b
TYPE_STRING = 0x1a
TYPE_PAIR = 0x0f
TYPE_REF = 0x02
TYPE_F64 = 0x05
TYPE_SIZE = {0x00: 0, 0x01: 4, 0x13: 4, 0x15: 4, TYPE_REF: 4, 0x03: 1, 0x11: 1, 0x12: 2,
             0x19: 4, 0x20: 4, TYPE_PAIR: 8, 0x14: 8, 0x18: 8, TYPE_F64: 8}
KNOWN_TYPES = frozenset(TYPE_SIZE) | {TYPE_CONTAINER, TYPE_LIST, TYPE_STRING}

_MAX_STRLEN = 1_000_000       # a mis-read length cannot run off the block


class TreeError(Exception):
    """A tagged block did not read to its declared extent."""


def _printable4(b) -> bool:
    return len(b) == 4 and all(0x20 <= x < 127 for x in b)


def _head(mm, p, hi):
    """(tag, type, value_pos) of the field at p."""
    if p + 6 <= hi and _printable4(mm[p:p + 4]) and mm[p + 4] == 0x01:
        return mm[p:p + 4][::-1].decode("latin-1").strip(), mm[p + 5], p + 6
    if p + 2 <= hi and mm[p] == 0x01 and mm[p + 1] in KNOWN_TYPES:
        return None, mm[p + 1], p + 2
    if p + 6 <= hi and mm[p + 4] == 0x01 and mm[p + 5] in KNOWN_TYPES:
        return "#" + mm[p:p + 4][::-1].hex(), mm[p + 5], p + 6
    raise TreeError(f"no tagged field at {p}")


def read_tree(mm, p, hi, max_items=5000):
    """One field at p -> ((tag, type, value), next_p).

    Tagless fields have tag None. Containers and lists decode to a list of child fields,
    a pair to a (u32, u32) tuple, a reference to its four-character code, a string to str,
    an f64 to float, every other type to an int."""
    tag, typ, vpos = _head(mm, p, hi)
    if typ not in KNOWN_TYPES:
        raise TreeError(f"unknown field type 0x{typ:02x} at {p}")
    if typ in (TYPE_CONTAINER, TYPE_LIST, TYPE_STRING):
        if vpos + 4 > hi:
            raise TreeError(f"count at {vpos} runs past {hi}")
        n = int.from_bytes(mm[vpos:vpos + 4], "little")
        if typ == TYPE_STRING:
            if n > _MAX_STRLEN or vpos + 4 + n > hi:
                raise TreeError(f"string at {vpos} runs past {hi}")
            return (tag, typ, mm[vpos + 4:vpos + 4 + n].decode("latin-1", "replace")), \
                vpos + 4 + n
        if n > max_items:
            raise TreeError(f"implausible item count {n} at {p}")
        q, kids = vpos + 4, []
        for _ in range(n):
            kid, q = read_tree(mm, q, hi, max_items)
            kids.append(kid)
        return (tag, typ, kids), q
    size = TYPE_SIZE[typ]
    if vpos + size > hi:
        raise TreeError(f"value of type 0x{typ:02x} at {vpos} runs past {hi}")
    raw = mm[vpos:vpos + size]
    if typ == TYPE_PAIR:
        value = (int.from_bytes(raw[:4], "little"), int.from_bytes(raw[4:], "little"))
    elif typ == TYPE_F64:
        value = struct.unpack("<d", raw)[0]
    elif typ == TYPE_REF:
        value = raw[::-1].decode("latin-1", "replace").strip()
    else:
        value = int.from_bytes(raw, "little")
    return (tag, typ, value), vpos + size
