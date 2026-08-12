#!/usr/bin/env python3
"""Player-Progress weekly availability -> injury spells for the managed squad.

FMM's in-game **Player Progress** page (the weekly skill-line graph with Injured / Off-Season /
On-loan shaded bands) is stored as a per-player weekly table. Each weekly entry, keyed by the
player's TID (u32 LE), carries five skill-category ratings, a status flag, and the week's date:

    +0   u32  player TID (search key)
    +4..+14  u16  five skill-category lines (Physical/Mental/Attacking/Defending/Overall), ~1-20
    +16  u16  status flag  -> injured that week iff (flag & 3) != 0
                             (bit0/bit1 = injured; bit4=16 / bit6=64 = off-season / on-loan, ignored)
    +18  u16  == 0 (validation)
    +20  u16  week day-of-year (0-based)      +22  u16  year

Only IN-MATCH injuries reach `match_events`; this table also captures **training injuries**, so it
is the source of truth for "how many injuries / how long" per squad player across a season.

We locate a player's series by scanning the save for their TID with a valid (date, flag) signature,
keep the densest cluster (the real progress zone; avoids stray file-wide TID collisions), dedupe the
two interleaved copies by keeping the max flag per date, then group injured weeks into spells.

Region/offsets are structural (found per save via the TID search) — no hard-coded zone, so this
survives per-save/per-career drift. See memory: injury-progress-decode.
"""
import struct
import datetime

_CLUSTER_WIN = 262144        # 256KB: the progress zone for one player's ~30-45 weekly entries
_MIN_WEEKS = 12              # a real season-long series; below this it's a stray TID collision


def _u16(d, o):
    if 0 <= o <= len(d) - 2:
        return struct.unpack_from("<H", d, o)[0]
    return None


def _valid_entry(d, i, years):
    """(date, flag) if the bytes at TID-offset i look like a weekly-progress record, else None."""
    y = _u16(d, i + 22)
    if y not in years:
        return None
    if _u16(d, i + 18) != 0:
        return None
    doy = _u16(d, i + 20)
    if doy is None or doy > 366:
        return None
    flag = _u16(d, i + 16)
    if flag is None or flag > 255:
        return None
    try:
        date = datetime.date(y, 1, 1) + datetime.timedelta(days=int(doy))
    except ValueError:
        return None
    return date, flag


def weekly_series(mm, tid, years):
    """Sorted [(date, injured_bool)] for a player's weekly-progress series.

    `years` is the set of calendar years the season spans (e.g. {2021, 2022}). Returns [] if no
    plausible series is found.
    """
    key = struct.pack("<I", int(tid))
    cands, s = [], 0
    while True:
        i = mm.find(key, s)
        if i < 0:
            break
        s = i + 1
        e = _valid_entry(mm, i, years)
        if e:
            cands.append((i, e[0], e[1]))
    if not cands:
        return []
    cands.sort()
    # densest 256KB window = the real progress zone (drop stray file-wide TID matches)
    best_lo, best_n, j = cands[0][0], 0, 0
    for k in range(len(cands)):
        while cands[k][0] - cands[j][0] > _CLUSTER_WIN:
            j += 1
        if k - j + 1 > best_n:
            best_n, best_lo = k - j + 1, cands[j][0]
    # dedupe interleaved copies by date, keeping "injured if any copy says so"
    bydate = {}
    for off, date, flag in cands:
        if best_lo <= off <= best_lo + _CLUSTER_WIN:
            bydate[date] = bydate.get(date, False) or ((flag & 3) != 0)
    return sorted(bydate.items())


def injury_spells(series, max_gap_days=8):
    """[(start_date, end_date, weeks)] — consecutive injured weeks (gap <= max_gap) = one spell."""
    hurt = [d for d, inj in series if inj]
    spells = []
    for d in hurt:
        if spells and (d - spells[-1][-1]).days <= max_gap_days:
            spells[-1].append(d)
        else:
            spells.append([d])
    return [(sp[0], sp[-1], len(sp)) for sp in spells]


def extract_injuries(mm, squad_tids, season):
    """{tid: [(start_iso, end_iso, weeks), ...]} for managed-squad players with >=1 injury spell.

    `season` = campaign end-year; the weekly series spans {season-1, season}.
    """
    years = {season - 1, season}
    out = {}
    for tid in squad_tids:
        series = weekly_series(mm, tid, years)
        if len(series) < _MIN_WEEKS:
            continue
        spells = injury_spells(series)
        if spells:
            out[int(tid)] = [(a.isoformat(), b.isoformat(), w) for a, b, w in spells]
    return out
