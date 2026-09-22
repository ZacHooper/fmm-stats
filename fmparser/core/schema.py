#!/usr/bin/env python3
"""Declarative record schemas, field definitions, and record reader."""
from typing import Any, Dict, List, Optional, Set, Tuple

from . import primitives as P
from .types import (
    DATE,
    F32,
    HEX2,
    HEX4,
    I16,
    I32,
    KIND_WIDTH,
    PAD,
    RAW,
    U8,
    U16,
    U32,
    UNKNOWN,
)

# Registry of all instantiated Record layouts
REGISTRY: Dict[str, "Record"] = {}

_READERS = {
    U8: P.u8,
    U16: P.u16,
    U32: P.u32,
    I16: P.i16,
    I32: P.i32,
    F32: P.f32,
    DATE: P.ymd,
    HEX4: P.hex4,
    HEX2: P.hex2,
}


class Field:
    """One declared field in a record layout."""
    __slots__ = ("offset", "width", "name", "kind", "group", "alias", "note")

    def __init__(
        self,
        offset: int,
        width: int,
        name: Any,
        kind: Optional[str] = None,
        group: Optional[str] = None,
        alias: bool = False,
        note: str = "",
    ):
        self.offset = offset
        self.width = width
        self.name = name
        self.kind = kind
        self.group = group
        self.alias = alias
        self.note = note

    @property
    def emits(self) -> bool:
        """True if reading this field produces a key in the output dict."""
        return self.name is not UNKNOWN and self.kind is not PAD

    def __repr__(self) -> str:
        k = f", kind={self.kind!r}" if self.kind else ""
        return f"Field({self.offset}, {self.width}, {self.name!r}{k})"


class Record:
    """A declared fixed-width binary struct layout.

    Capable of reading itself from a buffer via `read()`, `read_into()`, or `read_group()`.
    """
    __slots__ = ("name", "span", "fields", "stride", "anchor", "is_head", "note")

    def __init__(
        self,
        name: str,
        span: int,
        fields: Any,
        stride: Optional[int] = None,
        anchor: int = 0,
        is_head: bool = False,
        note: str = "",
        register: bool = True,
    ):
        self.name = name
        self.span = span
        self.fields = tuple(fields)
        self.stride = stride if stride is not None else span
        self.anchor = anchor
        self.is_head = is_head
        self.note = note

        if register:
            REGISTRY[name] = self

    def field(self, name: str) -> Field:
        """Look up a declared field by name."""
        for f in self.fields:
            if f.name == name:
                return f
        raise KeyError(f"{self.name} has no field {name!r}")

    def groups(self) -> Set[str]:
        """All group names declared in this record."""
        return {f.group for f in self.fields if f.group}

    def read_field(self, mm: Any, field: Field, base: int) -> Any:
        """Read a single field value from `mm` at `base + field.offset`."""
        if field.kind == RAW:
            return bytes(mm[base + field.offset:base + field.offset + field.width])
        if field.kind == PAD or field.kind is None:
            return None
        return _READERS[field.kind](mm, base + field.offset)

    def read(self, mm: Any, base: int) -> Dict[str, Any]:
        """Read the whole declared record at `base` in declaration order."""
        return {f.name: self.read_field(mm, f, base) for f in self.fields if f.emits}

    def read_into(
        self,
        dst: Dict[str, Any],
        mm: Any,
        base: int,
        names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Read fields into an existing dict (preserving existing keys)."""
        wanted = set(names) if names is not None else None
        for f in self.fields:
            if not f.emits:
                continue
            if wanted is not None and f.name not in wanted:
                continue
            dst[f.name] = self.read_field(mm, f, base)
        return dst

    def read_group(self, mm: Any, base: int, group: str) -> Dict[str, Any]:
        """Read only the fields declared with `group=group`."""
        return {
            f.name: self.read_field(mm, f, base)
            for f in self.fields
            if f.emits and f.group == group
        }

    def read_at_anchor(self, mm: Any, anchor_off: int) -> Dict[str, Any]:
        """Read the record whose locator landmark sits at `anchor_off`."""
        return self.read(mm, anchor_off - self.anchor)

    def __repr__(self) -> str:
        return f"Record({self.name!r}, span={self.span}, {len(self.fields)} fields)"


def validate(rec: Record) -> List[str]:
    """Return a list of problems with a declared layout. Empty means it is sound.

    Five checks. The first two are what `audit_records._coverage` already did; the last three
    are new, and each one corresponds to a mistake that is currently possible.
    """
    problems = []
    solid = [f for f in rec.fields if not f.alias]

    # 1. width agrees with kind.
    for f in rec.fields:
        if f.kind in KIND_WIDTH and f.width != KIND_WIDTH[f.kind]:
            problems.append(
                f"{f.name}: declared width {f.width} but kind {f.kind} reads "
                f"{KIND_WIDTH[f.kind]}")
        if f.kind is None and f.emits:
            problems.append(f"{f.name}: emits a value but declares no kind")
        if f.width <= 0:
            problems.append(f"{f.name}: width {f.width}")

    # 2. coverage + overlap: every byte in [0, span) owned exactly once.
    owner = [None] * rec.span
    for f in solid:
        if f.offset < 0 or f.offset + f.width > rec.span:
            problems.append(
                f"{f.name}: [{f.offset},{f.offset + f.width}) outside [0,{rec.span})")
            continue
        for b in range(f.offset, f.offset + f.width):
            if owner[b] is not None:
                problems.append(f"byte {b}: {owner[b]} overlaps {f.name}")
            owner[b] = f.name
    gaps = [b for b in range(rec.span) if owner[b] is None]
    if gaps:
        problems.append(
            f"{len(gaps)} unaccounted byte(s) {_runs(gaps)} -- name them, or declare them "
            f"PAD. A byte that is neither is a byte we are stepping over by accident.")

    # 3. an alias must actually alias something.
    for f in rec.fields:
        if not f.alias:
            continue
        covered = all(0 <= b < rec.span and owner[b] is not None
                      for b in range(f.offset, f.offset + f.width))
        if not covered:
            problems.append(
                f"{f.name}: alias=True but [{f.offset},{f.offset + f.width}) is not covered "
                f"by a declared field -- an alias re-reads bytes, it does not add them")

    # 4. no two fields emit the same key.
    emitted = [f.name for f in rec.fields if f.emits]
    dupes = sorted({n for n in emitted if emitted.count(n) > 1})
    if dupes:
        problems.append(f"duplicate emitted name(s): {', '.join(map(str, dupes))}")

    # 5. a walked record's stride must be at least its span.
    if rec.stride is not None and rec.stride < rec.span:
        problems.append(f"stride {rec.stride} < span {rec.span}: records would overlap")
    if rec.anchor < 0 or rec.anchor >= max(rec.span, 1):
        problems.append(f"anchor {rec.anchor} outside [0,{rec.span})")

    return problems


def _runs(nums: Any) -> str:
    out, start, prev = [], None, None
    for n in list(nums) + [None]:
        if start is None:
            start = prev = n
            continue
        if n == prev + 1:
            prev = n
            continue
        out.append(str(start) if start == prev else f"{start}-{prev}")
        start = prev = n
    return ",".join(out)


def per_byte_map(rec: Record) -> str:
    """Generate human-readable byte-by-byte coverage map of a Record."""
    lines = [f"{rec.name}: span {rec.span}"
             + (f", stride {rec.stride}" if rec.stride != rec.span else "")
             + (f", anchor +{rec.anchor}" if rec.anchor else "")
             + ("  [HEAD of a variable-length record]" if rec.is_head else "")]
    for f in sorted(rec.fields, key=lambda f: (f.offset, f.alias)):
        hi = f.offset + f.width
        span = f"{f.offset:>4}" if f.width == 1 else f"{f.offset:>4}..{hi - 1}"
        flag = " (alias)" if f.alias else ""
        lines.append(f"  {span:<11} {str(f.kind or '-'):<5} {str(f.name):<28}{flag}"
                     + (f"  # {f.note}" if f.note else ""))
    return "\n".join(lines)
