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
    # role-weight set that matches the shape this career actually plays; rates our squad in a
    # scout. Distinct from app_config.default_method, which is the web app's display default.
    rating_method: str | None = None
    # (month, day) the game starts this career's new season. It follows the home calendar,
    # so it is per career: measured as the day the managed club's record changes its last
    # league position (Frem 29 June old / 30 June new; Bucaspor 19 June old / 20 June new).
    rollover: tuple = (6, 30)


# `active=False` means: keep the saves in the archive, but don't rebuild the store. The
# dashboard's career selector keys off whether the store FILE exists (db.available_careers),
# so not building one is all it takes to drop a career from the UI. Bucaspor stays registered
# and its saves stay in R2 because they're the only cross-career regression test the parser
# has — a decode that works on Denmark and Turkey is a decode that generalises.
CAREERS = {
    # Turkish career (the original) — Bucaspor 1928. Archived: no longer played.
    "bucaspor": Career("bucaspor", "Bucaspor 1928", 6567, 11320, (228, 227, 117),
                       "fm-buca.duckdb", active=False, rating_method="buca_433",
                       rollover=(6, 20)),
    # Danish career — Boldklubben Frem (started 2026-08). tids verified from the save.
    "frem": Career("frem", "Boldklubben Frem", 346, 7296, (), "fm-frem.duckdb",
                   rating_method="frem_minmax_4231", rollover=(6, 30)),
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
