#!/usr/bin/env python3
"""Compatibility shim: currency schemas live in `fmparser.tables.currencies`."""
from ..tables.currencies import CURRENCY_COUNT, CURRENCY_HEAD, CURRENCY_TAIL

__all__ = [
    "CURRENCY_COUNT",
    "CURRENCY_HEAD",
    "CURRENCY_TAIL",
]
