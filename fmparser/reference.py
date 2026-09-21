#!/usr/bin/env python3
"""Compatibility shim: `fmparser.reference` has moved to `fmparser.clubs_comps`.

Re-exports all symbols from `fmparser.clubs_comps` so existing callers continue to
function without interruption.
"""
from .clubs_comps import *  # noqa: F401, F403

# Re-export internal helpers used across tests and audit scripts
from .clubs_comps import (  # noqa: F401
    ClubTableError,
    CompTableError,
    _build_refdata_index,
    _club_table_anchor,
    _comp_table_anchor,
    _name_table_bounds,
    _nation_table_bounds,
    _read_club_slot,
    _read_comp_slot,
    _walk_browse,
    _walk_browse_bounds,
    _walk_club_table,
    _walk_comp_table,
)
