#!/usr/bin/env python3
"""Table abstraction and walking engine for savefile tables.

A table is a name, a LOCATOR that finds its rows, and the SCHEMA that reads each row. The
engine does the walk. Two kinds, matching the two kinds of record (`schema.py`):

`TableDef` -- PACKED rows. The locator returns `(base, count)`, or several such runs; each
row is a composite sequence of typed segments, walked by offset:
1. Fixed Record layouts (from `schema.py`).
2. Length-prefixed string primitives (`PString` from `types.py`).
3. Custom dynamic segments implementing `read(mm, pos, limit)`.

`TaggedTableDef` -- TAGGED rows. The locator returns `[(offset, n)]`, one per row: a block
of n tagged fields starting at offset. The engine reads exactly n fields strictly
(`types.read_tree`) and the row's `TaggedRecord` reads them. `scan_tagged_blocks` is the
locator shape for a region of count-framed blocks, `[u32 n][n fields]`.
"""
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple, Union

from .schema import Record, TaggedRecord, TaggedSchemaError
from .types import TreeError, read_tree


Run = Tuple[int, int]            # (base offset, row count)


@dataclass(frozen=True)
class TableDef:
    """Definition for a savefile table composed of sequential segments.

    `locator(mm)` returns `(base, count)`, or a list of such runs where one table is stored
    as several arrays (the world fixture list), or None. The engine walks every run in order.
    """
    name: str
    segments: Tuple[Any, ...]  # Sequence of Record | PString | CustomSegment
    locator: Callable[[Any], Union[None, Run, List[Run]]]
    include_offset: bool = False
    # The archive member the table is read from (shape D), or None for the save itself
    member: Optional[str] = None
    # (row, row offset) -> the row to emit, or None to drop it
    post_process: Optional[Callable[[Dict[str, Any], int], Optional[Dict[str, Any]]]] = None
    # The table's own invariant, (raw row, row index) -> bool: the walk STOPS at the first
    # row that breaks it, so the row count is the table's structure, never a tuned constant
    invariant: Optional[Callable[[Dict[str, Any], int], bool]] = None
    # Fixed-stride tables only: read just these fields, in this order (key order is part of
    # the extract output bytes)
    fields: Optional[Tuple[str, ...]] = None

    @property
    def is_fixed_stride(self) -> bool:
        """True if the table consists solely of a single fixed Record."""
        return (len(self.segments) == 1 and isinstance(self.segments[0], Record)
                and not self.segments[0].is_head)

    @property
    def stride(self) -> int:
        if self.segments and isinstance(self.segments[0], Record):
            rec = self.segments[0]
            return rec.stride or rec.span
        raise AttributeError(f"{self.name} is a variable-length table with no single stride")

    def runs(self, mm: Any) -> List[Run]:
        """The located runs, [(base, count)], in order."""
        loc = self.locator(mm)
        if not loc:
            return []
        return list(loc) if isinstance(loc, list) else [loc]

    def scrape(self, mm: Any) -> List[Dict[str, Any]]:
        return walk_table(mm, self)

    def spans(self, mm: Any, include_count_header: bool = True) -> List[Tuple[int, int]]:
        return table_spans(mm, self, include_count_header=include_count_header)

    def id_map(self, mm: Any, key_field: str = "id") -> Dict[int, Dict[str, Any]]:
        rows = self.scrape(mm)
        return {r[key_field]: r for r in rows if key_field in r}


# Alias Table -> TableDef for crisp naming
Table = TableDef

_STOP = object()     # a row that breaks the table's invariant


def _read_fixed(table: TableDef, mm: Any, off: int) -> Dict[str, Any]:
    rec = table.segments[0]
    return rec.read_fields(mm, off, table.fields) if table.fields else rec.read(mm, off)


def _emit(table: TableDef, rec: Dict[str, Any], off: int, index: int) -> Any:
    """The row to emit: None to skip it, _STOP where it breaks the invariant."""
    if table.invariant is not None and not table.invariant(rec, index):
        return _STOP
    if table.include_offset:
        rec["offset"] = off
    if table.post_process:
        rec = table.post_process(rec, off)
    return rec


def walk_table(mm: Any, table: TableDef) -> List[Dict[str, Any]]:
    """Walk every run of a table and return its rows, stopping at the first row that breaks
    the table's invariant."""
    limit = len(mm)
    results: List[Dict[str, Any]] = []
    index = 0
    for base, count in table.runs(mm):
        if table.is_fixed_stride:
            stride = table.stride
            span = table.segments[0].span
            for i in range(count):
                off = base + i * stride
                if off + span > limit:
                    break
                rec = _emit(table, _read_fixed(table, mm, off), off, index)
                index += 1
                if rec is _STOP:
                    return results
                if rec is not None:
                    results.append(rec)
            continue

        # Composite / variable-length rows
        pos = base
        for _ in range(count):
            if pos >= limit:
                break
            rec_start = pos
            rec: Dict[str, Any] = {}
            valid = True
            for seg in table.segments:
                if isinstance(seg, Record):
                    if pos + seg.span > limit:
                        valid = False
                        break
                    rec.update(seg.read(mm, pos))
                    pos += seg.span
                elif hasattr(seg, "read"):
                    res = seg.read(mm, pos, limit)
                    if res is None:
                        valid = False
                        break
                    part, pos = res
                    rec.update(part)
                else:
                    raise TypeError(f"Unknown segment type in table {table.name}: {type(seg)}")
            if not valid:
                break
            out = _emit(table, rec, rec_start, index)
            index += 1
            if out is _STOP:
                return results
            if out is not None:
                results.append(out)
    return results


def _count_header_start(mm: Any, base: int) -> int:
    """Step back from `base` over a count and its preceding 0xFF sentinel, if there is one."""
    start = base
    p = base
    if p >= 4:
        k = p
        while k > 0 and mm[k - 1] == 0xFF:
            k -= 1
        if p - k < 4 and k >= 4:
            k2 = k
            while k2 > 0 and mm[k2 - 1] == 0xFF:
                k2 -= 1
            if p - k2 >= 6:
                start = k2
        elif p - k >= 8:
            start = k
    return start


def table_spans(mm: Any, table: TableDef, include_count_header: bool = True) -> List[Tuple[int, int]]:
    """The byte spans [(start, end)] covering the table, one per run."""
    limit = len(mm)
    out: List[Tuple[int, int]] = []
    for base, count in table.runs(mm):
        start = _count_header_start(mm, base) if include_count_header else base
        if table.is_fixed_stride:
            out.append((start, base + count * table.stride))
            continue
        pos = base
        for _ in range(count):
            if pos >= limit:
                break
            stopped = False
            for seg in table.segments:
                if isinstance(seg, Record):
                    pos += seg.span
                elif hasattr(seg, "read"):
                    res = seg.read(mm, pos, limit)
                    if res is None:
                        stopped = True
                        break
                    _, pos = res
            if stopped:
                break
        out.append((start, pos))
    return out


def find_framed_count(
    mm: Any,
    start: int,
    hi: int,
    width: int = 4,
    min_ff: int = 8,
) -> Optional[Tuple[int, int]]:
    """Scan forward from `start` to `hi` for `[min_ff * 0xFF][count:width]`.

    Returns `(content_offset, count)` or None.
    """
    import struct
    pos = start
    target = b"\xff" * min_ff

    while pos < hi:
        idx = mm.find(target, pos, hi)
        if idx == -1:
            return None
        j = idx + min_ff
        while j < hi and mm[j] == 0xFF:
            j += 1
        if j + width <= hi:
            if width == 4:
                count = struct.unpack_from("<I", mm, j)[0]
            elif width == 2:
                count = struct.unpack_from("<H", mm, j)[0]
            else:
                raise ValueError(f"unsupported width {width}")
            return (j + width, count)
        pos = j

    return None


# ==== TAGGED tables ===========================================================================

class TaggedTableError(Exception):
    """A located block did not read to its declared field count, or through its schema."""


class TaggedBlock(NamedTuple):
    """One row of a tagged table: the fields of a block, read strictly."""
    start: int                  # offset of the first field
    end: int                    # one past the last field
    fields: List[Tuple[Optional[str], int, Any]]

    @property
    def top_tags(self) -> frozenset:
        return frozenset(f[0] for f in self.fields)

    def get(self, tag: str, default: Any = None) -> Any:
        """The raw value of a top-level tag."""
        return next((v for t, _, v in self.fields if t == tag), default)


def read_block(mm: Any, start: int, n: int, hi: Optional[int] = None) -> TaggedBlock:
    """Exactly n tagged fields from start; raises TreeError on anything short of that."""
    hi = len(mm) if hi is None else hi
    q, fields = start, []
    for _ in range(n):
        f, q = read_tree(mm, q, hi)
        fields.append(f)
    return TaggedBlock(start, q, fields)


# `[tag x4][0x01][type]`: the head of a tagged field, the only thing a block opens with.
_FIELD_HEAD = re.compile(rb"[\x20-\x7e]{4}\x01[\x00-\x20]")
_MAX_FIELDS = 5000


def scan_tagged_blocks(mm: Any, lo: int, hi: int) -> List[TaggedBlock]:
    """Every count-framed block `[u32 n][n tagged fields]` in [lo, hi), in order.

    The locator shape for a region of tagged blocks. One forward pass: at every candidate
    `[u32 n][tag 01 type]` it reads n fields strictly, and a block that reads is taken
    whole and the pass resumes after it, so a block's inner containers are never re-read as
    blocks of their own. Nothing is taken on a tag match alone -- a candidate is a block
    only if all n declared fields read."""
    out: List[TaggedBlock] = []
    end = lo
    for m in _FIELD_HEAD.finditer(mm, lo + 4, hi):
        p = m.start()
        if p - 4 < end:
            continue
        n = int.from_bytes(mm[p - 4:p], "little")
        if not 0 < n <= _MAX_FIELDS:
            continue
        try:
            block = read_block(mm, p, n, hi)
        except TreeError:
            continue
        out.append(block)
        end = block.end
    return out


@dataclass(frozen=True)
class TaggedTableDef:
    """Definition for a table of TAGGED rows.

    `locator(mm) -> [(offset, n)]` finds the rows; `schema` is the `TaggedRecord` every row
    reads with, or a function `block -> TaggedRecord` where the rows are of several kinds.
    A row declaring 0 fields is a stub: `blocks` returns it, `scrape` and `coverage` skip
    it."""
    name: str
    locator: Callable[[Any], List[Tuple[int, int]]]
    schema: Union[TaggedRecord, Callable[[TaggedBlock], TaggedRecord]]
    # The archive member the table is read from (shape D), or None for the save itself
    member: Optional[str] = None

    def schema_for(self, block: TaggedBlock) -> TaggedRecord:
        return self.schema if isinstance(self.schema, TaggedRecord) else self.schema(block)

    def blocks(self, mm: Any) -> List[TaggedBlock]:
        """Every located row, read strictly to its declared field count."""
        out = []
        for start, n in self.locator(mm) or []:
            try:
                out.append(read_block(mm, start, n))
            except TreeError as e:
                raise TaggedTableError(f"{self.name}: block at {start}: {e}") from e
        return out

    def read(self, block: TaggedBlock) -> Dict[str, Any]:
        """A row read through its schema."""
        try:
            return self.schema_for(block).read(block.fields)
        except TaggedSchemaError as e:
            raise TaggedTableError(f"{self.name}: block at {block.start}: {e}") from e

    def scrape(self, mm: Any) -> List[Dict[str, Any]]:
        return [self.read(b) for b in self.blocks(mm) if b.fields]

    def coverage(self, mm: Any, report: Optional[Dict] = None) -> Dict:
        """Every tag of every row against its schema: see `TaggedRecord.coverage`."""
        report = {} if report is None else report
        for b in self.blocks(mm):
            if b.fields:
                self.schema_for(b).coverage(b.fields, report)
        return report
