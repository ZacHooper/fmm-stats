#!/usr/bin/env python3
"""Injury and loan spells for the managed squad, from the weekly Player Progress table.

The table (`tables/player_progress.py`) holds one status bitfield per player per week.
Injured weeks (bits 0-1) include TRAINING injuries, which `match_events` never sees, so this
is the source for "how many injuries / how long" per squad player across a season. Bit 5
marks the weeks a player is out on loan: exact loan windows for players we loan OUT. It
tracks the loan, not the squad the player is registered to -- verified on
`denmark-23-mid-start-of-winter.fms`: Wedege / Davidsen / Moller-Jensen carry it across both
seasons, Dirksen (registered to the reserves, not on loan) never does, and Balck (registered
to the first team, out on loan) does for 48 weeks. Players loaned IN to us are never flagged.

A spell is a run of weeks with the bit set, allowing a gap of `max_gap_days` between weeks.
"""
from .tables.player_progress import INJURED, OFF_SEASON, ON_LOAN, progress_series

__all__ = ["INJURED", "OFF_SEASON", "ON_LOAN", "extract_availability", "injury_spells",
           "loan_spells"]


def _spells(series, bit, max_gap_days):
    """[(start_date, end_date, weeks)] -- consecutive weeks with `bit` set."""
    hit = [d for d, flag in series if flag & bit]
    spells = []
    for d in hit:
        if spells and (d - spells[-1][-1]).days <= max_gap_days:
            spells[-1].append(d)
        else:
            spells.append([d])
    return [(sp[0], sp[-1], len(sp)) for sp in spells]


def injury_spells(series, max_gap_days=8):
    """[(start_date, end_date, weeks)] -- runs of injured weeks."""
    return _spells(series, INJURED, max_gap_days)


def loan_spells(series, max_gap_days=22):
    """[(start_date, end_date, weeks)] -- runs of on-loan weeks.

    The gap is wider than for injuries because the series pauses over the off-season week at
    the season boundary (flag 16), which would otherwise split one continuous loan in two.
    """
    return _spells(series, ON_LOAN, max_gap_days)


def _iso(spells):
    return [(a.isoformat(), b.isoformat(), w) for a, b, w in spells]


def extract_availability(mm, squad_tids, season):
    """({tid: injury spells}, {tid: loan spells}) for the managed squad.

    Each spell is `(start_iso, end_iso, weeks)`. `season` = campaign end-year; the weeks read
    are those dated in {season-1, season}, so a save only ever sees two calendar years of a
    player's history and callers must union across saves to get the whole picture.
    """
    years = {season - 1, season}
    weeks = progress_series(mm)
    inj, loan = {}, {}
    for tid in squad_tids:
        series = sorted((d, s) for d, s in weeks.get(int(tid), {}).items() if d.year in years)
        if (sp := injury_spells(series)):
            inj[int(tid)] = _iso(sp)
        if (sp := loan_spells(series)):
            loan[int(tid)] = _iso(sp)
    return inj, loan
