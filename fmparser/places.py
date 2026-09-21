#!/usr/bin/env python3
"""Compatibility shim: cities and stadiums have moved to `fmparser.tables.cities` and `fmparser.tables.stadiums`."""
from .tables.cities import *    # noqa: F401, F403
from .tables.stadiums import *  # noqa: F401, F403
from .tables.stadiums import _chain_len, _stadium_at  # noqa: F401

