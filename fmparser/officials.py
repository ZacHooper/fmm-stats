#!/usr/bin/env python3
"""Compatibility shim: `match_officials` table has moved to `fmparser.tables.officials`."""
from .tables.officials import *  # noqa: F401, F403
