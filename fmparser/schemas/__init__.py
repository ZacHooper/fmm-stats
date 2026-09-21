#!/usr/bin/env python3
"""Schemas for Football Manager binary savefile tables."""
from .officials import OFFICIAL, OFFICIAL_STRIDE
from .rounds import ROUND_COUNT, ROUND_HEAD, ROUND_TRAILER, ROUND_TRAILER_WIDTH

__all__ = [
    "OFFICIAL",
    "OFFICIAL_STRIDE",
    "ROUND_COUNT",
    "ROUND_HEAD",
    "ROUND_TRAILER",
    "ROUND_TRAILER_WIDTH",
]
