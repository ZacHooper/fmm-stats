#!/usr/bin/env python3
"""Compatibility shim: `staff_attributes` table has moved to `fmparser.tables.staff`."""
from .tables.staff import *  # noqa: F401, F403
