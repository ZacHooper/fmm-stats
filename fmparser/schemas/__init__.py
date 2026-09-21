#!/usr/bin/env python3
"""Schemas for Football Manager binary savefile tables."""
from .officials import OFFICIAL, OFFICIAL_STRIDE
from .places import CITY, CITY_RECORD, STADIUM_HEAD, STADIUM_HEADER
from .rounds import ROUND_COUNT, ROUND_HEAD, ROUND_TRAILER, ROUND_TRAILER_WIDTH
from .staff import STAFF, STAFF_STRIDE, STAFF_GRID_STRIDE

__all__ = [
    "CITY",
    "CITY_RECORD",
    "OFFICIAL",
    "OFFICIAL_STRIDE",
    "ROUND_COUNT",
    "ROUND_HEAD",
    "ROUND_TRAILER",
    "ROUND_TRAILER_WIDTH",
    "STADIUM_HEAD",
    "STADIUM_HEADER",
    "STAFF",
    "STAFF_GRID_STRIDE",
    "STAFF_STRIDE",
]
