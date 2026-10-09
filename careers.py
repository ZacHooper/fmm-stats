#!/usr/bin/env python3
"""Managed-career registry: the loader's side, never the parser's.

One store holds one managed career. The career-specific facts are the club you manage (its
TID) and its reserve side, the day its season rolls over, the tactic it plays and the
store's file name. `extract.py` needs none of them: a save's tables read the same whatever
career it belongs to. The loader writes them into the store (`raw.app_config`), places each
snapshot in its campaign (`campaign`), and checks the match table against the fixture list
for our two clubs.

Starting a new career: find its club TID with `scripts/discover_career.py <save>`
(it reads the "(Nickname)" the save header opens with and resolves it to a club),
add a row below, and load with `load_duckdb.py <extract> --career <key>`.
"""
from __future__ import annotations

import datetime
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
    # NOTE: The game engine runs a 365-day internal season clock without leap year compensation,
    # so every leap year (2024, 2028) slips the in-game calendar rollover back by 1 day.
    rollover: tuple = (6, 30)
    # per-year (year, (month, day)) overrides when a career's rollover date drifts
    rollovers: tuple = ()

    def rollover_for(self, year: int) -> tuple[int, int]:
        for y, ro in self.rollovers:
            if y == year:
                return ro
        return self.rollover

    def campaign(self, date: str, has_matches: bool) -> int:
        """The campaign a save dated `date` belongs to (`campaign`)."""
        d = datetime.date.fromisoformat(date)
        return campaign(date, has_matches, self.rollover_for(d.year))


def campaign(date: str, has_matches: bool, rollover: tuple) -> int:
    """The campaign's end-year for a save dated `date` (ISO): on or after the `rollover`
    (month, day) is the next one, and so is a match-less save before it.

    A new career's first save is dated before the rollover with no match played: the
    database starts already rolled over (its last league positions are the season just
    gone), so it belongs to the campaign about to start. A match-less save before the
    rollover only happens there."""
    d = datetime.date.fromisoformat(date)
    if (d.month, d.day) >= tuple(rollover) or not has_matches:
        return d.year + 1
    return d.year


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
                   rating_method="frem_minmax_4231", rollover=(6, 30),
                   rollovers=((2028, (6, 29)),)),
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
