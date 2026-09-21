#!/usr/bin/env python3
"""Compatibility shim: official schemas live in `fmparser.tables.officials`."""
from ..tables.officials import OFFICIAL, OFFICIAL_STRIDE

__all__ = [
    "OFFICIAL",
    "OFFICIAL_STRIDE",
]
