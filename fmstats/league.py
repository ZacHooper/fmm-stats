"""League tables rebuilt from the world fixture list (mart.world_club_fixtures).

The save's own standings records do not parse for this career, but the zstd archive's fixture
list carries every played match with its score (docs/save-archive.md). A league is identified by
its STAGES: the multi-round stage a seed club played in (`stage_index` 0, the regular season),
plus every other multi-round stage that season whose clubs all came from it — a split league's
championship and relegation groups. Cup and European ties between the same clubs are
single-round stages and fall out. A split league ranks the first group above the second, with
points carried over.

The fixture list only holds games played by the snapshot date, so the store's current season
is a table AS OF the snapshot. It counts as complete only when every club has played as many
league games as clubs did the season before.
"""
from dataclasses import dataclass

import pandas as pd


@dataclass
class LeagueTable:
    season: int                # campaign end-year, the store's `season` convention
    label: str                 # "2025/26"
    table: pd.DataFrame        # pos, club_tid, club, p, w, d, l, gf, ga, gd, pts, group
    complete: bool
    split: bool


def _league_fixtures(season_fx, base_key):
    """One season's fixtures in a league: its regular stage `base_key` plus every other
    multi-round stage whose clubs all played in it."""
    members = set(season_fx.loc[season_fx["stage_key"] == base_key, "club_tid"])
    if not members:
        return season_fx.iloc[0:0]
    keys = [k for k, g in season_fx.groupby("stage_key")
            if set(g["club_tid"]) <= members and set(g["opp_tid"]) <= members]
    return season_fx[season_fx["stage_key"].isin(keys)]


def league_table(st, seed_tid, season=None):
    """The table of the league `seed_tid` played in during `season` (default: the store's
    latest). Raises LookupError when the store holds no league fixtures for that club."""
    season = season or st.season
    sy = season - 1            # the fixture list's season_year is the campaign's START year
    fx = st.con.execute("""
        SELECT f.*, fs.num_rounds FROM mart.world_club_fixtures f
        JOIN (SELECT stage_key, subr, max(num_rounds) AS num_rounds
              FROM mart.fixture_stages GROUP BY 1, 2) fs USING (stage_key, subr)
        WHERE f.season_year IN (?, ?) AND fs.num_rounds > 1""", [sy, sy - 1]).df()
    cur = fx[fx["season_year"] == sy]
    base = cur[(cur["club_tid"] == seed_tid) & (cur["stage_index"] == 0)]
    if base.empty:
        raise LookupError(f"no league fixtures for club {seed_tid} in {sy}/{str(sy + 1)[2:]}")
    base_key = base["stage_key"].mode().iat[0]
    lg = _league_fixtures(cur, base_key)
    prev = _league_fixtures(fx[fx["season_year"] == sy - 1], base_key)

    group_of = lg[lg["stage_index"] > 0].groupby("club_tid")["stage_index"].min()
    t = lg.groupby("club_tid").agg(club=("club", "first"), p=("result", "size"),
                                   w=("result", lambda s: (s == "W").sum()),
                                   d=("result", lambda s: (s == "D").sum()),
                                   l=("result", lambda s: (s == "L").sum()),
                                   gf=("gf", "sum"), ga=("ga", "sum"), pts=("pts", "sum"))
    t.insert(t.columns.get_loc("pts"), "gd", t["gf"] - t["ga"])
    t["group"] = t.index.map(lambda c: group_of.get(c, 0))
    t = t.sort_values(["group", "pts", "gd", "gf"], ascending=[True, False, False, False])
    t.insert(0, "pos", range(1, len(t) + 1))
    for c in ("p", "w", "d", "l", "gf", "ga", "gd", "pts", "group"):
        t[c] = t[c].astype(int)
    t = t.reset_index()

    if season < st.season:
        complete = True
    else:
        full = prev.groupby("club_tid").size().max() if not prev.empty else None
        complete = bool(full) and t["p"].min() == t["p"].max() == full
    return LeagueTable(season, f"{sy}/{str(sy + 1)[2:]}", t, complete,
                       bool(t["group"].max() > 0))
