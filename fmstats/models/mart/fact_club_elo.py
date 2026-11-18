"""Every home-nation club's Elo rating, match by match.

One row per team per rating event: a `seed` row when the team first appears in the home
nation's men's leagues (int_home_team_tiers), then one `match` row per match it plays in
that nation's competitions (league and cup) against another rated team. A team's seed is
var('region_elo').base + per_level_point x (its tier's level_ca - the lowest scored tier's)
on the snapshot it first appears in (fact_tier_level_snapshot), so the gap between two
tiers is the gap in their regulars' level. A match moves both sides by
k x margin x (result - expected): result 1 / 0.5 / 0 (a shootout is a draw), expected
from the rating gap with the home side home_advantage up (none at a neutral venue is not
known to the save, so every match has a home side), margin 1 for one goal, 1.5 for two,
(11 + n) / 8 beyond. Matches are rated in date order, then match_id.
"""
import pandas as pd


def model(dbt, session):
    dbt.config(materialized="table")
    # var('region_elo'), handed over by the model's config in _mart.yml
    elo_vars = {"base": float(dbt.config.get("elo_base")),
                "per_level_point": float(dbt.config.get("elo_per_level_point")),
                "k": float(dbt.config.get("elo_k")),
                "home_advantage": float(dbt.config.get("elo_home_advantage"))}

    tiers = dbt.ref("int_home_team_tiers").df()
    levels = dbt.ref("fact_tier_level_snapshot").df()
    matches = dbt.ref("int_matches").df()
    competitions = dbt.ref("int_competitions").df()

    # seeds: each team on the first snapshot it appears in
    first = tiers.sort_values("snapshot_date").drop_duplicates("team_tid")
    lowest = (levels[levels["is_scored"]].groupby("snapshot_date")["level_ca"].min()
              .rename("lowest_scored_ca").reset_index())
    seeds = (first.merge(levels[["snapshot_date", "tier", "level_ca"]],
                         on=["snapshot_date", "tier"], how="inner")
             .merge(lowest, on="snapshot_date", how="inner"))
    seeds["elo"] = (elo_vars["base"] + elo_vars["per_level_point"]
                    * (seeds["level_ca"] - seeds["lowest_scored_ca"]))

    nations = set(tiers["nation_id"].unique())
    home_cids = set(competitions[competitions["nation_id"].isin(nations)
                                 & ~competitions["is_women"].astype(bool)]["cid"])
    played = matches[matches["cid"].isin(home_cids)
                     & matches["home_goals"].notna() & matches["away_goals"].notna()]
    played = played.sort_values(["match_date", "match_id"])

    rating = {}
    seeded_on = {}
    rows = []
    for s in seeds.itertuples():
        rating[s.team_tid] = float(s.elo)
        seeded_on[s.team_tid] = s.snapshot_date
        rows.append((s.team_tid, "seed", None, s.snapshot_date, None, None, float(s.elo)))

    k, hfa = elo_vars["k"], elo_vars["home_advantage"]
    for m in played.itertuples():
        home, away = m.home_team_tid, m.away_team_tid
        if home not in rating or away not in rating:
            continue          # a side outside the home nation's leagues has no rating
        gh, ga = int(m.home_goals), int(m.away_goals)
        expected = 1 / (1 + 10 ** ((rating[away] - rating[home] - hfa) / 400))
        result = 1.0 if gh > ga else 0.5 if gh == ga else 0.0
        diff = abs(gh - ga)
        margin = 1.0 if diff <= 1 else 1.5 if diff == 2 else (11 + diff) / 8
        change = k * margin * (result - expected)
        for team, opponent, delta in ((home, away, change), (away, home, -change)):
            before = rating[team]
            rating[team] = before + delta
            rows.append((team, "match", m.match_id, m.match_date, opponent, before,
                         rating[team]))

    out = pd.DataFrame(rows, columns=["team_tid", "rating_event", "match_id", "rating_date",
                                      "opponent_tid", "elo_before", "elo"])
    out["event_order"] = out.groupby("team_tid").cumcount()
    out["rating_date"] = pd.to_datetime(out["rating_date"])
    # fixed types, so an empty store builds the same table
    return session.from_df(out).project("""
        cast(team_tid as integer) as team_tid,
        cast(rating_event as varchar) as rating_event,
        cast(match_id as bigint) as match_id,
        cast(rating_date as date) as rating_date,
        cast(opponent_tid as integer) as opponent_tid,
        cast(elo_before as double) as elo_before,
        cast(elo as double) as elo,
        cast(event_order as integer) as event_order""")
