#!/usr/bin/env python3
"""Compatibility shim: `round_names` catalog has moved to `fmparser.tables.rounds`."""
from .tables.rounds import *  # noqa: F401, F403
