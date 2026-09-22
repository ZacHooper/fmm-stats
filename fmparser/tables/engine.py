#!/usr/bin/env python3
"""Generic composite-stream table abstraction and walking engine for FM savefile tables.

A table is a sequence of records declared by a locator shape. Each record in turn
is a composite sequence of typed segments:
1. Fixed-struct records (`Record` from `schema.py`) read by struct unpack.
2. Length-prefixed string primitives (`PString`) with optional null-termination.
3. Custom dynamic segments (e.g. counted arrays, tails) with a `read(mm, pos, limit)` method.

This unifies uniform preallocated grids, single-string catalogs, and multi-string catalogs
into a single data-driven engine with automatic byte-span generation and ID mapping.
"""
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from .. import records as RD
from ..schema import PString, Record

@dataclass(frozen=True)
class TableDef:
    """Definition for a savefile table composed of sequential segments."""
    name: str
    segments: Tuple[Any, ...]  # Sequence of Record | PString | CustomSegment
    locator: Callable[[Any], Optional[Tuple[int, int]]]  # mm -> (base_offset, record_count)
    include_offset: bool = False
    post_process: Optional[Callable[..., Optional[Dict[str, Any]]]] = None

    @property
    def is_fixed_stride(self) -> bool:
        """True if the table consists solely of a single fixed Record."""
        return len(self.segments) == 1 and isinstance(self.segments[0], Record) and not self.segments[0].is_head

    @property
    def stride(self) -> int:
        if self.is_fixed_stride:
            rec = self.segments[0]
            return rec.stride or rec.span
        raise AttributeError(f"{self.name} is a variable-length table with no single stride")

    def scrape(self, mm: Any) -> List[Dict[str, Any]]:
        return walk_table(mm, self)

    def spans(self, mm: Any, include_count_header: bool = True) -> List[Tuple[int, int]]:
        return table_spans(mm, self, include_count_header=include_count_header)

    def id_map(self, mm: Any, key_field: str = "id") -> Dict[Any, Dict[str, Any]]:
        return {r[key_field]: r for r in self.scrape(mm) if key_field in r}


def walk_table(mm: Any, table_def: TableDef) -> List[Dict[str, Any]]:
    """Read all records from a table using its TableDef."""
    info = table_def.locator(mm)
    if not info:
        return []
    base, count = info
    pos = base
    n = len(mm)
    out: List[Dict[str, Any]] = []

    # Fast path for single fixed-stride Record grids
    if table_def.is_fixed_stride:
        rec_schema = table_def.segments[0]
        stride = rec_schema.stride or rec_schema.span
        for k in range(count):
            rec_start = base + k * stride
            if rec_start + stride > n:
                break
            rec = RD.read(mm, rec_schema, rec_start)
            if table_def.include_offset and "offset" not in rec:
                rec["offset"] = rec_start
            if table_def.post_process is not None:
                try:
                    rec = table_def.post_process(rec, rec_start)
                except TypeError:
                    rec = table_def.post_process(rec)  # type: ignore[call-arg]
            if rec is not None:
                out.append(rec)
        return out

    # General composite segment walker
    for _ in range(count):
        if pos >= n:
            break
        rec_start = pos
        row: Dict[str, Any] = {}
        aborted = False

        for seg in table_def.segments:
            if isinstance(seg, Record):
                seg_span = seg.stride or seg.span
                if pos + seg_span > n:
                    aborted = True
                    break
                part = RD.read(mm, seg, pos)
                row.update(part)
                pos += seg_span
            elif isinstance(seg, PString):
                res = seg.read(mm, pos, n)
                if res is None:
                    aborted = True
                    break
                part_s, pos = res
                row.update(part_s)
            elif hasattr(seg, "read"):
                res = seg.read(mm, pos, n)
                if res is None:
                    aborted = True
                    break
                part_c, pos = res
                row.update(part_c)
            else:
                # callable segment: fn(mm, pos, n) -> (part_dict, next_pos)
                res = seg(mm, pos, n)
                if res is None:
                    aborted = True
                    break
                part_fn, pos = res
                row.update(part_fn)

        if aborted:
            break

        if table_def.include_offset and "offset" not in row:
            row["offset"] = rec_start
        if table_def.post_process is not None:
            try:
                row = table_def.post_process(row, rec_start)
            except TypeError:
                row = table_def.post_process(row)  # type: ignore[call-arg]
        if row is not None:
            out.append(row)

    return out


def table_spans(mm: Any, table_def: TableDef, include_count_header: bool = True) -> List[Tuple[int, int]]:
    """Return [(start, end)] byte spans covering the table records and count header."""
    info = table_def.locator(mm)
    if not info:
        return []
    base, count = info
    n = len(mm)
    spans: List[Tuple[int, int]] = []

    if include_count_header and base >= 4:
        spans.append((base - 4, base))

    if table_def.is_fixed_stride:
        stride = table_def.stride
        for k in range(count):
            rec_start = base + k * stride
            spans.append((rec_start, rec_start + stride))
        return spans

    pos = base
    for _ in range(count):
        if pos >= n:
            break
        rec_start = pos
        aborted = False
        for seg in table_def.segments:
            if isinstance(seg, Record):
                pos += seg.stride or seg.span
            elif isinstance(seg, PString):
                res = seg.read(mm, pos, n)
                if res is None:
                    aborted = True
                    break
                _, pos = res
            elif hasattr(seg, "read"):
                res = seg.read(mm, pos, n)
                if res is None:
                    aborted = True
                    break
                _, pos = res
            else:
                res = seg(mm, pos, n)
                if res is None:
                    aborted = True
                    break
                _, pos = res
        if aborted:
            break
        spans.append((rec_start, pos))

    return spans
