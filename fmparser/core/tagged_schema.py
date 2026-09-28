#!/usr/bin/env python3
"""Declared schemas for TAGGED records -- the key-value counterpart of `schema.Record`.

A tagged record is a set of `[tag][type][value]` fields in the data-dictionary wire format
(`fmparser/datadict.py`), not bytes at fixed offsets: fields may come in any order, a tag may
be absent, and one tag's wire type can vary with its value (`ntms` is a u8 for 12 teams and
a u16 for 255). So the schema is declared per TAG rather than per offset:

    STAGE = TaggedRecord("comp_rules_stage", [
        Tag("indx", "stage_index", INT, required=True, note="= fix_man +76"),
        Tag("rnds", "rounds", ListOf(ROUND)),
    ], unread=("strq", "advs", ...))

The same three properties `Record` gives a byte layout hold here:

  * the schema is READ from: `read(fields)` returns {name: value} for the declared tags,
    checking each value's wire type against its kind;
  * a required tag that is absent is an error, never a None that looks like data;
  * COVERAGE: every tag seen is either declared (read) or listed in `unread` (seen and
    deliberately not read). A tag that is neither is a tag being stepped over by accident,
    and `coverage()` reports it -- the counterpart of an undeclared byte.

`tag_map()` prints the schema as documentation, generated from the declaration.
"""
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

TAGGED_REGISTRY: Dict[str, "TaggedRecord"] = {}

CONTAINER, LIST_TYPE, STRING_TYPE, REF_TYPE, PAIR_TYPE = 0x0a, 0x0b, 0x1a, 0x02, 0x0f
_INT_TYPES = frozenset({0x01, 0x03, 0x11, 0x12, 0x13, 0x14, 0x18, PAIR_TYPE})


class TaggedSchemaError(Exception):
    """A tagged record does not match its declared schema."""


class Kind:
    """How a tag's value is read. `accepts(wire_type)`; `read(value, wire_type)`."""
    label = "?"

    def accepts(self, typ: int) -> bool:
        raise NotImplementedError

    def read(self, value: Any, typ: int) -> Any:
        raise NotImplementedError

    def __repr__(self) -> str:
        return self.label


class _Int(Kind):
    """An integer of any width. A PAIR stores one value twice, (n, n), and reads as n."""
    label = "int"

    def accepts(self, typ):
        return typ in _INT_TYPES

    def read(self, value, typ):
        if typ == PAIR_TYPE:
            a, b = value
            if a != b:
                raise TaggedSchemaError(f"pair ({a}, {b}) does not repeat one value")
            return a
        return value


class _FourCC(Kind):
    """A four-character code: a u32 of reversed characters, or a type-0x02 reference."""
    label = "fourcc"

    def accepts(self, typ):
        return typ in (0x01, REF_TYPE)

    def read(self, value, typ):
        if typ == REF_TYPE:
            return value
        s = value.to_bytes(4, "little")[::-1]
        if not all(32 <= c < 127 for c in s):
            raise TaggedSchemaError(f"{value:#x} is not a four-character code")
        return s.decode("latin-1").strip()


class _String(Kind):
    label = "string"

    def accepts(self, typ):
        return typ == STRING_TYPE

    def read(self, value, typ):
        return value


class Nested(Kind):
    """A container read with another TaggedRecord; `pick` returns one of its fields."""

    def __init__(self, record: "TaggedRecord", pick: Optional[str] = None):
        self.record, self.pick = record, pick
        self.label = f"{record.name}" + (f".{pick}" if pick else "")

    def accepts(self, typ):
        return typ == CONTAINER

    def read(self, value, typ):
        row = self.record.read(value)
        return row[self.pick] if self.pick else row


class ListOf(Kind):
    """A list (0x0b) whose elements are tagless containers, each read with `record`."""

    def __init__(self, record: "TaggedRecord"):
        self.record = record
        self.label = f"list of {record.name}"

    def accepts(self, typ):
        return typ == LIST_TYPE

    def read(self, value, typ):
        out = []
        for tag, etyp, ev in value:
            if tag is not None or etyp != CONTAINER:
                raise TaggedSchemaError(f"list element is not a tagless container")
            out.append(self.record.read(ev))
        return out


class AnyOf(Kind):
    """The first alternative whose wire type matches."""

    def __init__(self, *kinds: Kind):
        self.kinds = kinds
        self.label = " | ".join(k.label for k in kinds)

    def accepts(self, typ):
        return any(k.accepts(typ) for k in self.kinds)

    def read(self, value, typ):
        return next(k for k in self.kinds if k.accepts(typ)).read(value, typ)


INT, FOURCC, STRING = _Int(), _FourCC(), _String()


class Tag:
    """One declared tag: the wire tag, the name it is read into, how, and whether it must
    be present."""
    __slots__ = ("tag", "name", "kind", "required", "note")

    def __init__(self, tag: str, name: str, kind: Kind, required: bool = False,
                 note: str = ""):
        self.tag, self.name, self.kind = tag, name, kind
        self.required, self.note = required, note


class TaggedRecord:
    """A declared tagged record: the tags it reads and the tags it knowingly leaves."""

    def __init__(self, name: str, tags: Sequence[Tag], unread: Iterable[str] = (),
                 note: str = "", register: bool = True):
        self.name, self.tags, self.note = name, tuple(tags), note
        self.unread = tuple(unread)
        self.by_tag = {t.tag: t for t in self.tags}
        if register:
            TAGGED_REGISTRY[name] = self

    @property
    def declared(self) -> frozenset:
        return frozenset(self.by_tag) | frozenset(self.unread)

    def read(self, fields: List[Tuple[Optional[str], int, Any]]) -> Dict[str, Any]:
        """{name: value} for every declared tag, None where an optional tag is absent."""
        seen = {tag: (typ, val) for tag, typ, val in fields}
        out: Dict[str, Any] = {}
        for t in self.tags:
            if t.tag not in seen:
                if t.required:
                    raise TaggedSchemaError(f"{self.name}: required tag {t.tag!r} absent")
                out[t.name] = None
                continue
            typ, val = seen[t.tag]
            if not t.kind.accepts(typ):
                raise TaggedSchemaError(
                    f"{self.name}.{t.tag}: wire type 0x{typ:02x} is not {t.kind.label}")
            out[t.name] = t.kind.read(val, typ)
        return out

    def coverage(self, fields, report: Optional[Dict] = None) -> Dict:
        """Tally every tag of `fields` (and of nested declared records) against the
        declaration: {record: {"n": elements, "seen": {tag: count}, "undeclared": {tag:
        count}, "missing": {tag: count}}}."""
        report = {} if report is None else report
        r = report.setdefault(self.name, {"n": 0, "seen": {}, "undeclared": {}, "missing": {}})
        r["n"] += 1
        present = set()
        for tag, typ, val in fields:
            present.add(tag)
            r["seen"][tag] = r["seen"].get(tag, 0) + 1
            if tag not in self.declared:
                r["undeclared"][tag] = r["undeclared"].get(tag, 0) + 1
                continue
            t = self.by_tag.get(tag)
            kinds = []
            if t is not None:
                kinds = t.kind.kinds if isinstance(t.kind, AnyOf) else (t.kind,)
            for k in kinds:
                if isinstance(k, Nested) and typ == CONTAINER:
                    k.record.coverage(val, report)
                elif isinstance(k, ListOf) and typ == LIST_TYPE:
                    for _, _, ev in val:
                        k.record.coverage(ev, report)
        for t in self.tags:
            if t.required and t.tag not in present:
                r["missing"][t.tag] = r["missing"].get(t.tag, 0) + 1
        return report


def validate_tagged(rec: TaggedRecord) -> List[str]:
    """Internal soundness: no tag declared twice, no name used twice, required only on
    read tags."""
    problems = []
    tags = [t.tag for t in rec.tags] + list(rec.unread)
    dup = {t for t in tags if tags.count(t) > 1}
    if dup:
        problems.append(f"{rec.name}: tags declared twice: {sorted(dup)}")
    names = [t.name for t in rec.tags]
    dupn = {n for n in names if names.count(n) > 1}
    if dupn:
        problems.append(f"{rec.name}: names used twice: {sorted(dupn)}")
    return problems


def tag_map(rec: TaggedRecord, seen: Optional[Dict[str, int]] = None,
            n: Optional[int] = None) -> List[str]:
    """The per-tag schema as text lines: the record documentation, generated."""
    lines = [f"{rec.name}  ({len(rec.tags)} read, {len(rec.unread)} known unread)"]
    for t in rec.tags:
        freq = f"  {100 * seen.get(t.tag, 0) / n:3.0f}%" if seen is not None and n else ""
        req = "required" if t.required else "optional"
        lines.append(f"  {t.tag:5}  {t.name:16} {t.kind.label:28} {req}{freq}"
                     + (f"  -- {t.note}" if t.note else ""))
    unread = ", ".join(rec.unread)
    lines.append(f"  unread: {unread}")
    return lines
