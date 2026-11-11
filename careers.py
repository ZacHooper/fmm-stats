#!/usr/bin/env python3
"""Managed-career registry: the loader's side, never the parser's.

One store holds one managed career. The career-specific facts are the club you manage (its
TID) and its reserve side, the day its season rolls over, the tactic it plays and the
store's file name. `extract.py` needs none of them: a save's tables read the same whatever
career it belongs to. The loader writes them into the store (`raw.app_config`), places each
snapshot in its campaign (`campaign`), and checks the match table against the fixture list
for our two clubs.

The careers themselves are the user's and live in `fmm.toml` (see `fmm.example.toml`); this
module turns each `[careers.<key>]` table into a `Career`. Starting a new career: find its
club TID with `scripts/discover_career.py <save>` (it reads the "(Nickname)" the save header
opens with and resolves it to a club), add a `[careers.<key>]` table, and load with
`load_duckdb.py <extract> --career <key>`.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass

import fmconfig


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
    # the career's first in-game day (ISO). A new career can open after the game has already
    # played some of the club's fixtures (Truro's two pre-season friendlies); the match table
    # holds only games from this day on.
    start: str | None = None
    # the career's signing rule, if it plays one: (club tid, region) for every club whose
    # youth products count as local. Empty = no rule.
    eligible_origin_clubs: tuple = ()

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


def _from_config(key: str, t: dict) -> Career:
    """One `[careers.<key>]` table of fmm.toml -> a Career."""
    def pair(v):
        return (int(v[0]), int(v[1]))
    return Career(
        key=key,
        name=t.get("name", key),
        managed_tid=int(t["managed_tid"]),
        reserve_tid=int(t["reserve_tid"]) if t.get("reserve_tid") is not None else None,
        league_comps=tuple(t.get("league_comps", ())),
        db=t.get("db", f"fm-{key}.duckdb"),
        active=bool(t.get("active", True)),
        rating_method=t.get("rating_method"),
        rollover=pair(t.get("rollover", (6, 30))),
        rollovers=tuple(sorted((int(y), pair(v)) for y, v in t.get("rollovers", {}).items())),
        start=str(t["start"]) if t.get("start") is not None else None,
        eligible_origin_clubs=tuple(
            (int(tid), str(region))
            for region, tids in t.get("eligible_origin_clubs", {}).items() for tid in tids),
    )


# Careers are the user's, so they come from fmm.toml (`fmconfig`), never from this file.
# `active = false` keeps a career's saves in the archive but stops its store being rebuilt:
# a career with no store file has nothing to query or publish, so not building one drops it.
CAREERS = {k: _from_config(k, t) for k, t in fmconfig.career_tables().items()}

DEFAULT_CAREER = fmconfig.default_career() or next(
    (k for k, c in CAREERS.items() if c.active), None)


def resolve_career(key: str | None = None) -> Career:
    """Look up a career by key; defaults to `[careers] default` in fmm.toml."""
    key = key or DEFAULT_CAREER
    if not CAREERS:
        raise SystemExit(
            f"no careers configured ({fmconfig.config_path()} has none). Copy "
            "fmm.example.toml to fmm.toml and add yours; "
            "`scripts/discover_career.py <save.fms>` finds your club's tids.")
    try:
        return CAREERS[key]
    except KeyError:
        known = ", ".join(sorted(CAREERS))
        raise SystemExit(f"unknown career '{key}'. known careers (fmm.toml): {known}")
