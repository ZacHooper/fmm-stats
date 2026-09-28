#!/usr/bin/env python3
"""The TAGGED wire format, read strictly.

The save's data dictionary (`tables/rule_files.py`) and the archive's `comp_<uid>.dat`
members (`tables/comp_rules.py`) store key-value fields in one format:

    field = [tag: 4 bytes, REVERSED][0x01][type][value]      tagged
          = [0x01][type][value]                              tagless (a list element)

    type            size            value
    0x00             0              none
    0x01 0x13        4              u32
    0x15             4              u32 id (`Ttea` = a team, repeated by the next `DBID`)
    0x02             4              a reference: a reversed four-character code
    0x03 0x11        1              u8
    0x12             2              u16
    0x19             4              f32 (kept as its raw u32)
    0x20             4              u32 (the timestamp in the file trailer `EdDt`)
    0x0f             8              a PAIR of u32; a name id stored this way repeats (28, 28)
    0x14 0x18        8              u64
    0x05             8              f64 (prize money: `cash` = 150000.0)
    0x0a             4 + children   CONTAINER: u32 child count, then the children
    0x0b             4 + elements   LIST: u32 element count, then that many tagless fields
    0x1a             4 + len        STRING: u32 byte length, then the bytes (latin-1)

A tag is usually four printable characters, but not always: the discipline rules (`dsrl`)
carry fields whose tag is an arbitrary u32 (`20 7d 96 16`). Such a tag is read only where
neither a printable tag nor a tagless field fits, and is named `#` + its eight hex digits
in the same reversed order (`#16967d20`).

`read_tree` is STRICT: it is only ever called on a block whose extent is declared (a
field count), so anything that does not parse is an error, never a shorter result. The
schemas that name what the fields mean are declared per tag (`core/tagged_schema.py`).
"""
import struct

CONTAINER = 0x0a
LIST = 0x0b
STRING = 0x1a
PAIR = 0x0f
REF = 0x02
F64 = 0x05
FIXED = {0x00: 0, 0x01: 4, 0x13: 4, 0x15: 4, REF: 4, 0x03: 1, 0x11: 1, 0x12: 2, 0x19: 4,
         0x20: 4, PAIR: 8, 0x14: 8, 0x18: 8, F64: 8}
KNOWN_TYPES = frozenset(FIXED) | {CONTAINER, LIST, STRING}

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
    a PAIR to a (u32, u32) tuple, a REF to its four-character code, a STRING to str, an
    f64 to float, every other type to an int."""
    tag, typ, vpos = _head(mm, p, hi)
    if typ not in KNOWN_TYPES:
        raise TreeError(f"unknown field type 0x{typ:02x} at {p}")
    if typ in (CONTAINER, LIST, STRING):
        if vpos + 4 > hi:
            raise TreeError(f"count at {vpos} runs past {hi}")
        n = int.from_bytes(mm[vpos:vpos + 4], "little")
        if typ == STRING:
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
    size = FIXED[typ]
    if vpos + size > hi:
        raise TreeError(f"value of type 0x{typ:02x} at {vpos} runs past {hi}")
    raw = mm[vpos:vpos + size]
    if typ == PAIR:
        value = (int.from_bytes(raw[:4], "little"), int.from_bytes(raw[4:], "little"))
    elif typ == F64:
        value = struct.unpack("<d", raw)[0]
    elif typ == REF:
        value = raw[::-1].decode("latin-1", "replace").strip()
    else:
        value = int.from_bytes(raw, "little")
    return (tag, typ, value), vpos + size
