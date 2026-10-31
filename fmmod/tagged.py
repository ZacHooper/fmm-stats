"""A lossless reader and writer for the save's tagged format.

The format is the one `fmparser/core/types.py` documents:

    field = [tag: 4 bytes, REVERSED][0x01][type][value]      tagged
          = [0x01][type][value]                              tagless (a list element)

    0x0a CONTAINER [u32 n][n fields]    0x0b LIST [u32 n][n fields]    0x1a STRING [u32 len][bytes]
    every other type a fixed-width value (fmparser.core.types.TYPE_SIZE)

`fmparser.core.types.read_tree` decodes values for reading (it strips tags and four-character
codes, turns strings into str), so its output cannot be written back byte for byte. `Node`
keeps the raw tag bytes, the type code and, for a scalar, the raw value bytes; `encode(parse(b))`
is `b` exactly. Edits go through the helpers, which keep the type code (so a u8 stays a u8).

Every count in the format is a FIELD count (containers, lists, a rule file's top level), never
a byte length, except a string's own length. Changing a block's length therefore needs only
the counts inside it, which `encode` writes from the children.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Union

from fmparser.core.types import (TYPE_CONTAINER, TYPE_LIST, TYPE_SIZE, TYPE_STRING, TreeError,
                                 _head)

__all__ = ["TYPE_CONTAINER", "TYPE_LIST", "Node", "parse", "parse_block", "encode", "encode_block", "tag", "c", "u8", "u16",
           "u32", "lst"]

_COMPOUND = (TYPE_CONTAINER, TYPE_LIST)


@dataclass
class Node:
    """One field. `tag_raw` is the 4 tag bytes as stored (reversed), None on a tagless field;
    `value` is a list of Nodes for a container or list, else the raw value bytes (a string's
    bytes without its length)."""
    tag_raw: Optional[bytes]
    typ: int
    value: Union[bytes, List["Node"]] = field(default_factory=list)

    @property
    def tag(self) -> Optional[str]:
        """The tag as `read_tree` names it ('id', 'stgs', '#16967d20'); None if tagless."""
        if self.tag_raw is None:
            return None
        t = self.tag_raw[::-1]
        if all(0x20 <= x < 127 for x in t):
            return t.decode("latin-1").strip()
        return "#" + t.hex()

    @property
    def kids(self) -> List["Node"]:
        if self.typ not in _COMPOUND:
            raise TypeError(f"{self.tag!r} (type 0x{self.typ:02x}) has no children")
        return self.value

    @property
    def int(self) -> int:
        if self.typ in _COMPOUND or self.typ == TYPE_STRING:
            raise TypeError(f"{self.tag!r} (type 0x{self.typ:02x}) is not a number")
        return int.from_bytes(self.value[:4], "little")

    @int.setter
    def int(self, v: int) -> None:
        width = TYPE_SIZE[self.typ]
        if width == 8:                         # a pair: both halves carry the value
            self.value = v.to_bytes(4, "little") * 2
        else:
            self.value = v.to_bytes(width, "little")   # OverflowError if it does not fit

    # -- navigation ---------------------------------------------------------------------
    def get(self, t: str) -> Optional["Node"]:
        """The first child tagged `t`, or None."""
        return next((k for k in self.kids if k.tag == t), None)

    def __getitem__(self, t: str) -> "Node":
        k = self.get(t)
        if k is None:
            raise KeyError(f"no {t!r} under {self.tag!r}")
        return k

    def remove(self, t: str) -> None:
        """Drop every child tagged `t`."""
        self.value = [k for k in self.kids if k.tag != t]

    def set(self, node: "Node") -> None:
        """Replace the first child with node's tag, or append node if there is none."""
        for i, k in enumerate(self.kids):
            if k.tag == node.tag:
                self.value[i] = node
                return
        self.value.append(node)


def parse(buf, p: int, hi: int):
    """One field at p -> (Node, next_p). Strict, like `read_tree`."""
    tag, typ, vpos = _head(buf, p, hi)
    tag_raw = None if tag is None else bytes(buf[p:p + 4])
    if typ in _COMPOUND or typ == TYPE_STRING:
        n = int.from_bytes(buf[vpos:vpos + 4], "little")
        if typ == TYPE_STRING:
            if vpos + 4 + n > hi:
                raise TreeError(f"string at {vpos} runs past {hi}")
            return Node(tag_raw, typ, bytes(buf[vpos + 4:vpos + 4 + n])), vpos + 4 + n
        q, kids = vpos + 4, []
        for _ in range(n):
            kid, q = parse(buf, q, hi)
            kids.append(kid)
        return Node(tag_raw, typ, kids), q
    size = TYPE_SIZE[typ]
    if vpos + size > hi:
        raise TreeError(f"value of type 0x{typ:02x} at {vpos} runs past {hi}")
    return Node(tag_raw, typ, bytes(buf[vpos:vpos + size])), vpos + size


def parse_block(buf, start: int, n: int, hi: Optional[int] = None):
    """n top-level fields from start -> ([Node], end)."""
    hi = len(buf) if hi is None else hi
    out, q = [], start
    for _ in range(n):
        node, q = parse(buf, q, hi)
        out.append(node)
    return out, q


def encode(node: Node) -> bytes:
    head = (node.tag_raw + b"\x01" if node.tag_raw is not None else b"\x01") + bytes([node.typ])
    if node.typ in _COMPOUND:
        return head + len(node.value).to_bytes(4, "little") + b"".join(map(encode, node.value))
    if node.typ == TYPE_STRING:
        return head + len(node.value).to_bytes(4, "little") + node.value
    if len(node.value) != TYPE_SIZE[node.typ]:
        raise ValueError(f"{node.tag!r}: {len(node.value)} value bytes for type 0x{node.typ:02x}")
    return head + node.value


def encode_block(fields: List[Node]) -> bytes:
    """The fields without their leading u32 count."""
    return b"".join(map(encode, fields))


# ---- building new fields -------------------------------------------------------------------
def tag(name: str) -> bytes:
    """A four-character tag as stored: right-padded with spaces, then reversed."""
    if len(name) > 4:
        raise ValueError(name)
    return name.ljust(4).encode("latin-1")[::-1]


def _scalar(name: Optional[str], typ: int, v: int) -> Node:
    n = Node(None if name is None else tag(name), typ, b"")
    n.int = v
    return n


def u8(name: Optional[str], v: int) -> Node:
    return _scalar(name, 0x11, v)


def u16(name: Optional[str], v: int) -> Node:
    return _scalar(name, 0x12, v)


def u32(name: Optional[str], v: int) -> Node:
    return _scalar(name, 0x01, v)


def c(name: Optional[str], *kids: Node) -> Node:
    """A container."""
    return Node(None if name is None else tag(name), TYPE_CONTAINER, list(kids))


def lst(name: Optional[str], *items: Node) -> Node:
    """A list (its elements tagless)."""
    return Node(None if name is None else tag(name), TYPE_LIST, list(items))
