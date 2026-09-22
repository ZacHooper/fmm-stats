#!/usr/bin/env python3
"""DEPRECATED: Forwarding shim for fmparser.core.table.

This module is maintained for backward compatibility.
TableDef, walk_table, and table_spans have moved to `fmparser.core`.
"""
from ..core.table import (
    Table,
    TableDef,
    find_framed_count,
    table_spans,
    walk_table,
)

__all__ = [
    "Table",
    "TableDef",
    "find_framed_count",
    "table_spans",
    "walk_table",
]
