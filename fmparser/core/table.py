#!/usr/bin/env python3
"""Table abstraction and walking engine for savefile tables.

A table is a sequence of records declared by a locator shape. Each record in turn
is a composite sequence of typed segments:
1. Fixed Record layouts (from `schema.py`).
2. Length-prefixed string primitives (`PString` from `types.py`).
3. Custom dynamic segments implementing `read(mm, pos, limit)`.
"""
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from .schema import Record


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
        return len(self.segments) == 1 and (isinstance(self.segments[0], Record) or self.segments[0].__class__.__name__ == "Record") and not self.segments[0].is_head

    @property
    def stride(self) -> int:
        if len(self.segments) >= 1 and (isinstance(self.segments[0], Record) or self.segments[0].__class__.__name__ == "Record"):
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
                try:
                    rec = table.post_process(rec, rec_start)
                except TypeError:
                    rec = table.post_process(rec)
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
            if isinstance(seg, Record) or seg.__class__.__name__ == "Record":
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
            try:
                processed = table.post_process(rec, rec_start)
            except TypeError:
                processed = table.post_process(rec)
            if processed is None:
                continue
            rec = processed

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
            if isinstance(seg, Record) or seg.__class__.__name__ == "Record":
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
