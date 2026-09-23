"""League tables, read from mart.league_tables (rebuilt from the world fixture list).

The rules — how a league's stages are identified, how a split league ranks, when a season
counts as complete, and which countries' tables are verified — live with the view in
fmparser/mart.py.
"""
from dataclasses import dataclass

import pandas as pd


@dataclass
class LeagueTable:
    season: int                # campaign end-year, the store's `season` convention
    label: str                 # "2025/26"
    league: str | None
    nation: str | None
    table: pd.DataFrame        # pos, club_tid, club, p, w, d, l, gf, ga, gd, pts, group
    complete: bool
    split: bool


def league_table(st, seed_tid, season=None):
    """The table of the league `seed_tid` played in during `season` (default: the store's
    latest). Raises LookupError when the store holds no league table for that club."""
    season = season or st.season
    row = st.con.execute("""SELECT league_key FROM mart.league_tables
                            WHERE season = ? AND club_tid = ?""", [season, seed_tid]).fetchone()
    if row is None:
        raise LookupError(f"no league table for club {seed_tid} in "
                          f"{season - 1}/{str(season)[2:]}")
    t = st.con.execute("""
        SELECT pos, club_tid, club, p, w, d, l, gf, ga, gd, pts, "group",
               league_name, nation, complete, split
        FROM mart.league_tables WHERE season = ? AND league_key = ? ORDER BY pos""",
                       [season, row[0]]).df()
    meta = t.iloc[0]
    return LeagueTable(season, f"{season - 1}/{str(season)[2:]}", meta["league_name"],
                       meta["nation"],
                       t.drop(columns=["league_name", "nation", "complete", "split"]),
                       bool(meta["complete"]), bool(meta["split"]))
