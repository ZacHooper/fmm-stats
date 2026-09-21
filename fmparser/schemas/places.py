#!/usr/bin/env python3
"""Compatibility shim: city and stadium schemas live in `fmparser.tables.cities` and `stadiums`."""
from ..tables.cities import CITY, CITY_COUNT, CITY_RECORD
from ..tables.stadiums import STADIUM_HEAD, STADIUM_HEADER

__all__ = [
    "CITY",
    "CITY_COUNT",
    "CITY_RECORD",
    "STADIUM_HEAD",
    "STADIUM_HEADER",
]
