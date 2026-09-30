#!/usr/bin/env python3
"""Table abstraction and walking engine for savefile tables.

A table is a name, a LOCATOR that finds its rows, and the SCHEMA that reads each row. The
engine does the walk. Two kinds, matching the two kinds of record (`schema.py`):

`TableDef` -- PACKED rows. The locator returns `(base, count)`, or several such runs; each
row is a composite sequence of typed segments, walked by offset:
1. Fixed Record layouts (from `schema.py`).
2. Variable-length segments whose length the bytes declare (`types.py`): `PString`, a
   length-prefixed string, and `CountedList`, `[count][count x Record]`; `FixedList`,
   `[n x Record]` with n fixed by the layout; and `Block`, a named run of segments read into
   one nested dict, for a structure a row holds more than once.
3. Custom dynamic segments implementing `read(mm, pos, limit)`.

`LinkedTableDef` -- a fixed pool of PACKED rows, each holding the index of the next row in
its chain (shape B). The locator returns `(base, count)`; the rows are read column-wise and
the table's invariant is that the pointers form a forest of chains (`forest`). Following a
chain, and what its rows mean together, is left to the caller.

`TaggedTableDef` -- TAGGED rows. The locator returns `[(offset, n)]`, one per row: a block
of n tagged fields starting at offset. The engine reads exactly n fields strictly
(`types.read_tree`) and the row's `TaggedRecord` reads them. `scan_tagged_blocks` is the
locator shape for a region of count-framed blocks, `[u32 n][n fields]`.
"""
import re
from dataclasses import dataclass
from typing import (Any, Callable, Dict, Iterator, List, NamedTuple, Optional, Sequence,
                    Tuple, Union)

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
    """Where the table's `[>= 8 x 0xFF][count]` frame starts, for a table whose record 0 is
    at `base` (count u16 or u32); `base` itself when there is no frame."""
    for width in (2, 4):
        k = base - width
        if k >= 8 and mm[k - 8:k] == b"\xff" * 8:
            while k > 0 and mm[k - 1] == 0xFF:
                k -= 1
            return k
    return base


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


def _segment_instances(mm: Any, seg: Any, pos: int) -> List[Tuple[Record, int]]:
    """The packed records one already-read list or block segment at `pos` holds."""
    from .types import KIND_WIDTH, Block, CountedList, FixedList
    if isinstance(seg, CountedList):
        cw = KIND_WIDTH[seg.count]
        n = int.from_bytes(mm[pos:pos + cw], "little")
        return [(seg.item, pos + cw + i * seg.item.span) for i in range(n)]
    if isinstance(seg, FixedList):
        return [(seg.item, pos + i * seg.item.span) for i in range(seg.n)]
    if isinstance(seg, Block):
        out: List[Tuple[Record, int]] = []
        for sub in seg.segments:
            if isinstance(sub, Record):
                out.append((sub, pos))
                pos += sub.span
            else:
                out.extend(_segment_instances(mm, sub, pos))
                pos = sub.read(mm, pos, len(mm))[1]
        return out
    return []


def record_instances(mm: Any, table: Any) -> Iterator[Tuple[Record, int]]:
    """Every packed record a table's walk reads, as (Record, offset): each row's fixed
    segments, each element of its counted lists, and a linked table's header and rows. The
    walk stops where `walk_table` stops, at the first row that breaks the invariant."""
    if isinstance(table, LinkedTableDef):
        base, count = table.run(mm)
        if table.header is not None:
            yield table.header, base - table.header.span
        for i in range(count):
            yield table.row, base + i * table.stride
        return
    limit = len(mm)
    index = 0
    for base, count in table.runs(mm):
        pos = base
        for i in range(count):
            if table.is_fixed_stride:
                pos = base + i * table.stride
            found, rec, ok = [], {}, True
            for seg in table.segments:
                if isinstance(seg, Record):
                    if pos + seg.span > limit:
                        ok = False
                        break
                    found.append((seg, pos))
                    rec.update(seg.read(mm, pos))
                    pos += seg.span
                elif hasattr(seg, "read"):
                    res = seg.read(mm, pos, limit)
                    if res is None:
                        ok = False
                        break
                    part, end = res
                    found.extend(_segment_instances(mm, seg, pos))
                    rec.update(part)
                    pos = end
            if not ok or (table.invariant is not None and not table.invariant(rec, index)):
                return
            index += 1
            yield from found


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


# ==== LINKED tables ===========================================================================

class LinkedTableError(Exception):
    """A linked table was not located, or its pointers do not form a forest of chains."""


class Forest(NamedTuple):
    """The pointer structure of a linked table, measured over every row."""
    rows: int
    heads: int           # rows no pointer reaches: the chain starts
    ends: int            # rows holding the end marker
    max_indegree: int    # most pointers reaching one row
    outside: int         # pointers that are neither the end marker nor a row index
    on_chains: int       # rows reached by walking every chain from its head

    @property
    def ok(self) -> bool:
        """Every row on exactly one chain: no row reached twice, no pointer out of the pool,
        and no cycle (a cycle has no head, so its rows are the ones no chain reaches)."""
        return (self.max_indegree <= 1 and self.outside == 0 and self.heads == self.ends
                and self.on_chains == self.rows)


def follow(next_col: Sequence[int], head: int, end: int = 0xFFFFFFFF) -> Iterator[int]:
    """The row indices of one chain, head first. Stops at the end marker, a pointer outside
    the pool, or a row already visited."""
    seen = set()
    k = head
    while 0 <= k < len(next_col) and k not in seen:
        seen.add(k)
        yield k
        k = next_col[k]
        if k == end:
            return


def forest(next_col: Sequence[int], end: int = 0xFFFFFFFF) -> Forest:
    """Measure whether `next_col` (row -> next row index, `end` = none) is a forest of chains."""
    n = len(next_col)
    indeg = [0] * n
    ends = outside = 0
    for p in next_col:
        if p == end:
            ends += 1
        elif 0 <= p < n:
            indeg[p] += 1
        else:
            outside += 1
    heads = [k for k in range(n) if indeg[k] == 0]
    on_chains = 0
    if max(indeg, default=0) <= 1 and outside == 0:
        on_chains = sum(1 for h in heads for _ in follow(next_col, h, end))
    return Forest(n, len(heads), ends, max(indeg, default=0), outside, on_chains)


@dataclass(frozen=True)
class LinkedTableDef:
    """Definition for a LINKED table: a pool of `count` fixed-width rows from `base`, each row
    carrying in `next_field` the index of the next row in its chain.

    `locator(mm)` returns `(base, count)` or None. `header` is the record in front of row 0,
    if the table has one. The pool is read whole, every row, whether or not anything points
    at its chain: which chains matter is a question for whoever reads them."""
    name: str
    row: Record
    next_field: str
    locator: Callable[[Any], Optional[Run]]
    header: Optional[Record] = None
    end: int = 0xFFFFFFFF

    @property
    def stride(self) -> int:
        return self.row.stride or self.row.span

    def run(self, mm: Any) -> Run:
        loc = self.locator(mm)
        if not loc:
            raise LinkedTableError(f"{self.name}: not located")
        return loc

    def columns(self, mm: Any) -> Dict[str, List[Any]]:
        """Every row, column-wise: {field: [value per row]}."""
        base, count = self.run(mm)
        return self.row.columns(mm, base, count, stride=self.stride)

    def check(self, mm: Any) -> Forest:
        base, count = self.run(mm)
        nxt = self.row.columns(mm, base, count, names=[self.next_field], stride=self.stride)
        return forest(nxt[self.next_field], self.end)

    def scrape(self, mm: Any) -> Dict[str, Any]:
        """{base, count, header, rows}: the header record and every row, column-wise. Raises
        LinkedTableError if the pointers are not a forest of chains."""
        base, count = self.run(mm)
        rows = self.columns(mm)
        f = forest(rows[self.next_field], self.end)
        if not f.ok:
            raise LinkedTableError(f"{self.name}: pointers are not a forest of chains: {f}")
        head = self.header.read(mm, base - self.header.span) if self.header else None
        return {"base": base, "count": count, "header": head, "rows": rows}

    def spans(self, mm: Any) -> List[Tuple[int, int]]:
        """[(start, end)]: the header and every row."""
        base, count = self.run(mm)
        start = base - (self.header.span if self.header else 0)
        return [(start, base + count * self.stride)]


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
