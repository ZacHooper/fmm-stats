#!/usr/bin/env python3
"""Managed-career registry.

This parser targets ONE managed career per database. The only genuinely
career-specific fact is the club you manage (its TID) — that TID is how the
snapshot reader finds your squad's exact names + attributes. Everything else in
the extraction is career-agnostic.

Starting a new career: find its club TID with `scripts/discover_career.py <save>`
(it reads the "(Nickname)" the save header opens with and resolves it to a club),
add a row below, and run `extract.py <save> --career <key>`.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass


@dataclass(frozen=True)
class Career:
    key: str                       # short id used on the CLI (--career <key>)
    name: str                      # display name
    managed_tid: int               # club we get exact names+attributes for
    reserve_tid: int | None = None # its reserve side (AI-run); used downstream to split matches
    league_comps: tuple = ()       # first-team competition ids (informational for now)
    db: str = "fm.duckdb"          # DuckDB store for this career (one file per career)
    active: bool = True            # False = saves archived, store NOT rebuilt (see below)

    @property
    def club_marker(self) -> bytes:
        """Squad-membership marker in the save = managed club TID (u16 LE) + ff ff."""
        return struct.pack("<H", self.managed_tid) + b"\xff\xff"

    @property
    def reserve_marker(self) -> bytes | None:
        """Same marker for the reserve side, or None if the career has no reserve tid."""
        if self.reserve_tid is None:
            return None
        return struct.pack("<H", self.reserve_tid) + b"\xff\xff"

    @property
    def squad_markers(self) -> tuple[bytes, ...]:
        """Every club marker whose snapshot records describe players we manage.

        The reserve list is a SEPARATE squad snapshot with its own marker. A player who
        moves between the two keeps a record under both, and the one under the club he is
        currently in is the live copy — the other freezes at the moment he left that list.
        Scanning only the first-team marker therefore reads stale attributes for anyone in
        the reserves (see docs/ATTRIBUTE_DECODING.md 7.3)."""
        if self.reserve_marker is None:
            return (self.club_marker,)
        return (self.club_marker, self.reserve_marker)


# `active=False` means: keep the saves in the archive, but don't rebuild the store. The
# dashboard's career selector keys off whether the store FILE exists (db.available_careers),
# so not building one is all it takes to drop a career from the UI. Bucaspor stays registered
# and its saves stay in R2 because they're the only cross-career regression test the parser
# has — a decode that works on Denmark and Turkey is a decode that generalises.
CAREERS = {
    # Turkish career (the original) — Bucaspor 1928. Archived: no longer played.
    "bucaspor": Career("bucaspor", "Bucaspor 1928", 6567, 11320, (228, 227, 117),
                       "fm-buca.duckdb", active=False),
    # Danish career — Boldklubben Frem (started 2026-08). tids verified from the save.
    "frem": Career("frem", "Boldklubben Frem", 346, 7296, (), "fm-frem.duckdb"),
}

DEFAULT_CAREER = "frem"


def resolve_career(key: str | None = None) -> Career:
    """Look up a career by key; defaults to the original Bucaspor career."""
    key = key or DEFAULT_CAREER
    try:
        return CAREERS[key]
    except KeyError:
        known = ", ".join(sorted(CAREERS))
        raise SystemExit(f"unknown career '{key}'. known careers: {known}")
