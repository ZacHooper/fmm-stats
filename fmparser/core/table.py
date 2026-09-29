#!/usr/bin/env python3
"""Table abstraction and walking engine for savefile tables.

A table is a name, a LOCATOR that finds its rows, and the SCHEMA that reads each row. The
engine does the walk. Two kinds, matching the two kinds of record (`schema.py`):

`TableDef` -- PACKED rows. The locator returns `(base, count)`; each row is a composite
sequence of typed segments, walked by offset:
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


@dataclass(frozen=True)
class TableDef:
    """Definition for a savefile table composed of sequential segments."""
    name: str
    segments: Tuple[Any, ...]  # Sequence of Record | PString | CustomSegment
    locator: Callable[[Any], Optional[Tuple[int, int]]]  # mm -> (base_offset, record_count)
    include_offset: bool = False
    # The archive member the table is read from (shape D), or None for the save itself
    member: Optional[str] = None
    # (row, row offset) -> the row to emit, or None to drop it
    post_process: Optional[Callable[[Dict[str, Any], int], Optional[Dict[str, Any]]]] = None

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

    def scrape(self, mm: Any) -> List[Dict[str, Any]]:
        return walk_table(mm, self)

    def spans(self, mm: Any, include_count_header: bool = True) -> List[Tuple[int, int]]:
        return table_spans(mm, self, include_count_header=include_count_header)

    def id_map(self, mm: Any, key_field: str = "id") -> Dict[int, Dict[str, Any]]:
        rows = self.scrape(mm)
        return {r[key_field]: r for r in rows if key_field in r}


# Alias Table -> TableDef for crisp naming
Table = TableDef


def walk_table(mm: Any, table: TableDef) -> List[Dict[str, Any]]:
    """Walk all records of a table and return a list of decoded dictionaries."""
    loc = table.locator(mm)
    if not loc:
        return []

    base, count = loc
    pos = base
    limit = len(mm)
    results = []

    # Fast path for fixed-stride tables
    if table.is_fixed_stride:
        rec_schema = table.segments[0]
        stride = rec_schema.stride or rec_schema.span
        for i in range(count):
            rec_start = base + i * stride
            if rec_start + rec_schema.span > limit:
                break
            rec = rec_schema.read(mm, rec_start)
            if table.include_offset:
                rec["offset"] = rec_start
            if table.post_process:
                rec = table.post_process(rec, rec_start)
                if rec is None:
                    continue
            results.append(rec)
        return results

    # Composite / variable-length table walk
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
                part = seg.read(mm, pos)
                rec.update(part)
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

        if table.include_offset:
            rec["offset"] = rec_start
        if table.post_process:
            rec = table.post_process(rec, rec_start)
            if rec is None:
                continue

        results.append(rec)

    return results


def table_spans(mm: Any, table: TableDef, include_count_header: bool = True) -> List[Tuple[int, int]]:
    """Calculate the byte spans [(start, end)] covering the table in the save."""
    loc = table.locator(mm)
    if not loc:
        return []

    base, count = loc
    limit = len(mm)
    start = base

    if include_count_header:
        # Step back over count header and preceding 0xFF sentinel bytes
        p = base
        if p >= 4:
            k = p
            while k > 0 and mm[k - 1] == 0xFF:
                k -= 1
            if p - k < 4 and k >= 4:
                # Step over 2 or 4 byte count
                k2 = k
                while k2 > 0 and mm[k2 - 1] == 0xFF:
                    k2 -= 1
                if p - k2 >= 6:
                    start = k2
            elif p - k >= 8:
                start = k

    if table.is_fixed_stride:
        stride = table.segments[0].stride or table.segments[0].span
        end = base + count * stride
        return [(start, end)]

    # Variable-length walk to find exact end
    pos = base
    for _ in range(count):
        if pos >= limit:
            break
        for seg in table.segments:
            if isinstance(seg, Record):
                pos += seg.span
            elif hasattr(seg, "read"):
                res = seg.read(mm, pos, limit)
                if res is None:
                    return [(start, pos)]
                _, pos = res

    return [(start, pos)]


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
