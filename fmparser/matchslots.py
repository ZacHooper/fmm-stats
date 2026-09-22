#!/usr/bin/env python3
"""Compatibility shim: `fmparser.matchslots` has moved to `fmparser.tables.match_slots`.

Re-exports all symbols from `fmparser.tables.match_slots` so existing callers and test suites
continue to function without interruption.
"""
from .tables.match_slots import *  # noqa: F401, F403
from .tables.match_slots import (  # noqa: F401
    MATCH_SLOTS_TABLE,
    NO_CLUB,
    SLOT,
    STRIDE,
    TRAILER,
    TRAILER_OFF,
    locate,
    locate_match_slots,
    match_slots_table_spans,
    read_slot,
    scrape,
)
