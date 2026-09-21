#!/usr/bin/env python3
"""Compatibility shim: round schemas live in `fmparser.tables.rounds`."""
from ..tables.rounds import (
    ROUND_COUNT,
    ROUND_HEAD,
    ROUND_TRAILER,
    ROUND_TRAILER_WIDTH,
)

__all__ = [
    "ROUND_COUNT",
    "ROUND_HEAD",
    "ROUND_TRAILER",
    "ROUND_TRAILER_WIDTH",
]
