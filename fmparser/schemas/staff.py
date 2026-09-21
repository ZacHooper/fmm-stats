#!/usr/bin/env python3
"""Compatibility shim: staff schemas live in `fmparser.tables.staff`."""
from ..tables.staff import (
    FORMATION_SLOTS,
    HIDDEN_OFFSETS,
    STAFF,
    STAFF_ATTRS,
    STAFF_FORMATION_SLOTS,
    STAFF_GRID_STRIDE,
    STAFF_HIDDEN_OFFSETS,
    STAFF_STRIDE,
    _STYLE_BANDS,
    _TIER_BANDS,
    reputation_tier,
    style,
)

__all__ = [
    "FORMATION_SLOTS",
    "HIDDEN_OFFSETS",
    "STAFF",
    "STAFF_ATTRS",
    "STAFF_FORMATION_SLOTS",
    "STAFF_GRID_STRIDE",
    "STAFF_HIDDEN_OFFSETS",
    "STAFF_STRIDE",
    "_STYLE_BANDS",
    "_TIER_BANDS",
    "reputation_tier",
    "style",
]
