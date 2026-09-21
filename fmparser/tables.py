#!/usr/bin/env python3
"""Generic table abstraction and walking engine for FM savefile tables.

Encapsulates the common table archetypes found in the binary save:
1. Fixed-stride preallocated grids (e.g. match officials, stadiums, cities, staff).
2. Length-prefixed string catalogs with optional trailers (e.g. round & leg names).
3. Frame locating, record decoding, and span generation for coverage audits.
"""
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple
import struct

from . import records as RD
from .save import cache_key as _cache_key
from .schema import Record


@dataclass(frozen=True)
class FixedTableDef:
    """Definition for a table of uniform, fixed-stride records."""
    name: str
    record_schema: Record
    locator: Callable[[Any], Optional[Tuple[int, int]]]  # mm -> (base_offset, record_count)
    post_process: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None

    @property
    def stride(self) -> int:
        return self.record_schema.stride


@dataclass(frozen=True)
class StringCatalogDef:
    """Definition for a variable-length catalog of length-prefixed strings with optional trailer."""
    name: str
    head_schema: Record  # Schema containing string length (typically Field 'len')
    trailer_schema: Optional[Record] = None
    locator: Callable[[Any], Optional[Tuple[int, int]]] = None  # mm -> (base_offset, record_count)
    string_field: str = "name"
    len_field: str = "len"
    encoding: str = "utf-8"
    fallback_encoding: str = "latin-1"
    null_terminated: bool = True
    post_process: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None


def walk_fixed_table(mm: Any, table_def: FixedTableDef) -> List[Dict[str, Any]]:
    """Read all records from a fixed-stride table using its TableDef."""
    info = table_def.locator(mm)
    if not info:
        return []
    base, count = info
    stride = table_def.stride
    out = []
    for k in range(count):
        rec = RD.read(mm, table_def.record_schema, base + k * stride)
        if table_def.post_process is not None:
            rec = table_def.post_process(rec)
        out.append(rec)
    return out


def fixed_table_spans(mm: Any, table_def: FixedTableDef, include_count_header: bool = True) -> List[Tuple[int, int]]:
    """Return [(start, end)] byte spans covering the fixed table and its count header."""
    info = table_def.locator(mm)
    if not info:
        return []
    base, count = info
    stride = table_def.stride
    spans = []
    if include_count_header and base >= 4:
        spans.append((base - 4, base))
    for k in range(count):
        rec_start = base + k * stride
        spans.append((rec_start, rec_start + stride))
    return spans


def walk_string_catalog(mm: Any, catalog_def: StringCatalogDef) -> List[Dict[str, Any]]:
    """Read all records from a variable-length string catalog."""
    info = catalog_def.locator(mm)
    if not info:
        return []
    base, count = info
    pos = base
    n = len(mm)
    head_len = catalog_def.head_schema.span
    trailer_len = (catalog_def.trailer_schema.stride or catalog_def.trailer_schema.span) if catalog_def.trailer_schema else 0
    term_len = 1 if catalog_def.null_terminated else 0

    out = []
    for _ in range(count):
        if pos + head_len > n:
            break
        head = RD.read(mm, catalog_def.head_schema, pos)
        slen = head.get(catalog_def.len_field, 0)
        rec_len = head_len + slen + term_len + trailer_len
        if pos + rec_len > n:
            break

        raw_str = bytes(mm[pos + head_len:pos + head_len + slen])
        try:
            val_str = raw_str.decode(catalog_def.encoding)
        except UnicodeDecodeError:
            val_str = raw_str.decode(catalog_def.fallback_encoding, errors="replace")

        row = dict(head)
        if catalog_def.len_field in row:
            del row[catalog_def.len_field]
        row[catalog_def.string_field] = val_str

        if catalog_def.trailer_schema:
            trailer_pos = pos + head_len + slen + term_len
            trailer = RD.read(mm, catalog_def.trailer_schema, trailer_pos)
            row.update(trailer)

        if catalog_def.post_process is not None:
            row = catalog_def.post_process(row)

        out.append(row)
        pos += rec_len
    return out


def string_catalog_spans(mm: Any, catalog_def: StringCatalogDef, include_count_header: bool = True) -> List[Tuple[int, int]]:
    """Return [(start, end)] byte spans covering the string catalog records and count header."""
    info = catalog_def.locator(mm)
    if not info:
        return []
    base, count = info
    pos = base
    n = len(mm)
    head_len = catalog_def.head_schema.span
    trailer_len = (catalog_def.trailer_schema.stride or catalog_def.trailer_schema.span) if catalog_def.trailer_schema else 0
    term_len = 1 if catalog_def.null_terminated else 0

    spans = []
    if include_count_header and base >= 4:
        spans.append((base - 4, base))
    for _ in range(count):
        if pos + head_len > n:
            break
        head = RD.read(mm, catalog_def.head_schema, pos)
        slen = head.get(catalog_def.len_field, 0)
        rec_len = head_len + slen + term_len + trailer_len
        if pos + rec_len > n:
            break
        spans.append((pos, pos + rec_len))
        pos += rec_len
    return spans
